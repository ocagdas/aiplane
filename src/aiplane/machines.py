from __future__ import annotations

import json
import platform
import shlex
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .azure_cli import account_status as _az_account_status
from .azure_cli import command_status as _az_command_status
from .azure_cli import run_az as _run_az
from .azure_inventory import AzureRetailPricing
from .boundaries import CommandRunner, HttpTransport, SubprocessCommandRunner, UrllibHttpTransport
from .persistence import atomic_write_text
from .config import dump_yaml, parse_yaml
from .hardware import HardwareManager
from .model_catalog import ModelCatalog
from .models import Profile
from .network_validation import validate_port, validate_ssh_host, validate_ssh_user
from .runtime_catalog import RuntimeCatalog

AZURE_CLI_TIMEOUT_SECONDS = 10

WORKLOAD_CLASSES: dict[str, dict[str, Any]] = {
    "inference_tiny": {
        "min_ram_gb": 8,
        "min_vram_gb": 0,
        "notes": "CPU/laptop smoke tests and tiny local models",
    },
    "inference_small": {
        "min_ram_gb": 16,
        "min_vram_gb": 8,
        "notes": "1B-7B local coding/chat models",
    },
    "inference_medium": {
        "min_ram_gb": 64,
        "min_vram_gb": 24,
        "notes": "7B-32B models on a GPU workstation or VM",
    },
    "inference_large": {
        "min_ram_gb": 128,
        "min_vram_gb": 48,
        "notes": "32B-70B+ models, high VRAM or multi-GPU",
    },
    "training_finetune": {
        "min_ram_gb": 128,
        "min_vram_gb": 40,
        "notes": "fine-tuning/training experiments; storage and isolation also matter",
    },
    "batch_embedding_indexing": {
        "min_ram_gb": 64,
        "min_vram_gb": 0,
        "notes": "RAM/CPU/storage-heavy preprocessing and indexing",
    },
    "compile_build": {
        "min_ram_gb": 32,
        "min_vram_gb": 0,
        "notes": "CPU/RAM-heavy builds and package compilation",
    },
    "media_generation": {
        "min_ram_gb": 64,
        "min_vram_gb": 16,
        "notes": "image/video/audio generation pipelines",
    },
}

AZURE_SKU_HINTS: dict[str, dict[str, Any]] = {
    "Standard_NC4as_T4_v3": {
        "cpu_cores": 4,
        "memory_gb": 28,
        "gpu_vendor": "nvidia",
        "gpu_model": "T4",
        "gpu_count": 1,
        "vram_gb": 16,
    },
    "Standard_NVadsA10_v5": {
        "cpu_cores": 18,
        "memory_gb": 220,
        "gpu_vendor": "nvidia",
        "gpu_model": "A10",
        "gpu_count": 1,
        "vram_gb": 24,
    },
    "Standard_NC24ads_A100_v4": {
        "cpu_cores": 24,
        "memory_gb": 220,
        "gpu_vendor": "nvidia",
        "gpu_model": "A100",
        "gpu_count": 1,
        "vram_gb": 80,
    },
    "Standard_NC40ads_H100_v5": {
        "cpu_cores": 40,
        "memory_gb": 320,
        "gpu_vendor": "nvidia",
        "gpu_model": "H100 NVL",
        "gpu_count": 1,
        "vram_gb": 94,
    },
    "Standard_ND96asr_v4": {
        "cpu_cores": 96,
        "memory_gb": 900,
        "gpu_vendor": "nvidia",
        "gpu_model": "A100",
        "gpu_count": 8,
        "vram_gb": 80,
        "total_vram_gb": 640,
    },
    "Standard_D16s_v5": {
        "cpu_cores": 16,
        "memory_gb": 64,
        "gpu_vendor": "none",
        "gpu_model": "none",
        "gpu_count": 0,
        "vram_gb": 0,
    },
    "Standard_E32s_v5": {
        "cpu_cores": 32,
        "memory_gb": 256,
        "gpu_vendor": "none",
        "gpu_model": "none",
        "gpu_count": 0,
        "vram_gb": 0,
    },
}


class MachineManager:
    def __init__(
        self,
        profile: Profile,
        command_runner: CommandRunner | None = None,
        http_transport: HttpTransport | None = None,
    ):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.http_transport = http_transport or UrllibHttpTransport()
        self.config = profile.hardware or {}

    def export_machine(self, name: str, origin: str = "local", include_discovery: bool = False) -> dict[str, Any]:
        hardware = HardwareManager(self.profile)
        discovered = hardware.discover()
        machine = hardware.machine(discovered)
        machine["name"] = name
        machine["origin"] = origin
        machine["exported_from"] = {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "profile": self.profile.name,
        }
        machine["runtime_hints"] = self._runtime_hints()
        if include_discovery:
            machine["discovery"] = discovered
        return {"name": name, "machine": machine}

    def list(self) -> list[dict[str, Any]]:
        rows = []
        for name, machine in self._machines().items():
            if not isinstance(machine, dict):
                continue
            rows.append(
                {
                    "name": name,
                    "provider": (machine.get("stock") or {}).get("provider") or machine.get("provider"),
                    "origin": machine.get("origin"),
                    "placement": machine.get("placement"),
                    "substrate": machine.get("substrate"),
                    "cpu": machine.get("cpu"),
                    "memory": machine.get("memory"),
                    "gpu": machine.get("gpu"),
                    "accelerator_apis": machine.get("accelerator_apis"),
                }
            )
        return sorted(rows, key=lambda row: str(row["name"]))

    def show(self, name: str) -> dict[str, Any]:
        machine = self._machines().get(name)
        if not isinstance(machine, dict):
            raise ValueError(f"unknown machine: {name}")
        return {"name": name, "machine": machine}

    def import_file(
        self,
        path: Path,
        name: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        loaded = load_machine_profile(path, name=name, overrides=overrides)
        machine_name = loaded["name"]
        machine = loaded["machine"]
        validation = loaded["validation"]
        self.config.setdefault("self_managed_machines", {})[machine_name] = machine
        self._write_config()
        return {
            "name": machine_name,
            "path": str(self.profile.root / "hardware.yaml"),
            "validation": validation,
            "machine": machine,
        }

    def recommend(
        self,
        model: str | None = None,
        runtime: str | None = None,
        workload: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        criteria = self._criteria(model, runtime, workload)
        rows = []
        for name, machine in self._machines().items():
            if not isinstance(machine, dict):
                continue
            fit = _machine_fit(machine, criteria)
            rows.append({"name": name, **fit, "machine": _machine_summary(machine)})
        rows.sort(key=lambda row: (-int(row["score"]), str(row["name"])))
        if limit is not None:
            rows = rows[:limit]
        return {"criteria": criteria, "machines": rows}

    def discover_azure(
        self,
        region: str,
        workload: str | None = None,
        model: str | None = None,
        gpu_vendor: str | None = None,
        min_cpu_cores: float | None = None,
        min_ram_gb: float | None = None,
        min_vram_gb: float | None = None,
        limit: int = 20,
        verbosity: int = 0,
        az_event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        criteria = self._criteria(model, None, workload)
        criteria["gpu_vendor"] = (gpu_vendor or "").strip().lower() or None
        criteria["min_cpu_cores"] = _float(min_cpu_cores)
        criteria["min_ram_gb"] = max(
            float(criteria.get("min_ram_gb") or 0.0),
            _float(min_ram_gb) or 0.0,
        )
        criteria["min_vram_gb"] = max(
            float(criteria.get("min_vram_gb") or 0.0),
            _float(min_vram_gb) or 0.0,
        )
        command = [
            "az",
            "vm",
            "list-skus",
            "--location",
            region,
            "--resource-type",
            "virtualMachines",
            "--all",
            "--output",
            "json",
        ]
        source = "static_hints"
        method = "offline"
        azure_cli = self.azure_status(
            region=region,
            run_sku_probe=False,
            verbosity=verbosity,
            az_event_sink=az_event_sink,
        )
        status = "az CLI unavailable; using built-in SKU hints"
        skus = []
        quota = {"method": "not_checked", "items": []}
        if azure_cli["cli_available"]:
            completed = _run_az(command, verbosity=verbosity, event_sink=az_event_sink, runner=self.command_runner)
            azure_cli["sku_query"] = _az_command_status(completed)
            if completed.returncode == 0 and completed.stdout.strip():
                live_values = json.loads(completed.stdout)
                skus = _azure_skus_from_cli(live_values, region)
                if skus:
                    source = "az_vm_list_skus"
                    method = "live"
                    status = (
                        "live Azure CLI discovery succeeded; matching live SKU results override cached/offline results"
                    )
                    quota = self.azure_quota(region, verbosity=verbosity, az_event_sink=az_event_sink)
                else:
                    status = (
                        "az CLI SKU query succeeded but returned no supported SKU matches; using built-in SKU hints"
                    )
            else:
                status = f"az CLI SKU query failed or returned no output (exit {completed.returncode}); using built-in SKU hints"
        if not skus:
            skus = [self.azure_machine_from_sku(name, region)["machine"] for name in AZURE_SKU_HINTS]
        pricing = {"method": "skipped", "ok": False, "reason": "requires live Azure SKU discovery", "items": {}}
        if method == "live":
            sku_names = [
                str(((machine.get("stock") or {}).get("stock_sku") or "")).strip()
                for machine in skus
                if isinstance(machine, dict)
            ]
            pricing = AzureRetailPricing(self.http_transport).prices(region, sku_names)
        candidates = []
        for machine in skus:
            fit = _machine_fit(machine, criteria)
            if fit["level"] == "not_recommended":
                continue
            if not _azure_machine_matches_filters(machine, criteria):
                continue
            sku_name = str(((machine.get("stock") or {}).get("stock_sku") or "")).strip()
            candidates.append(
                {
                    "name": machine["name"],
                    **fit,
                    "restrictions": machine.get("restrictions", []),
                    "pricing": pricing["items"].get(sku_name),
                    "machine": _machine_summary(machine),
                }
            )
        candidates.sort(key=lambda row: (-int(row["score"]), str(row["name"])))
        result = {
            "provider": "azure",
            "region": region,
            "source": source,
            "criteria": criteria,
            "quota": quota,
            "candidates": candidates[:limit],
        }
        cache = self._record_discovery("azure", region, criteria, result, method, source, command, status)
        result["discovery"] = {
            "method": method,
            "source": source,
            "status": status,
            "command": command,
            "azure_cli": azure_cli,
            "pricing": {k: v for k, v in pricing.items() if k != "items"},
            "cache": cache,
        }
        return result

    def azure_status(
        self,
        region: str | None = None,
        run_sku_probe: bool = False,
        verbosity: int = 0,
        az_event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        az_path = shutil.which("az")
        status: dict[str, Any] = {
            "name": "azure_cli",
            "cli_available": az_path is not None,
            "path": az_path,
            "account": {"ok": False},
            "sku_query": None,
        }
        if not az_path:
            status["account"] = {"ok": False, "reason": "az CLI not found on PATH"}
            return status
        account = _run_az(
            ["az", "account", "show", "--output", "json"],
            verbosity=verbosity,
            event_sink=az_event_sink,
            runner=self.command_runner,
        )
        status["account"] = _az_account_status(account)
        if run_sku_probe and region:
            query = _run_az(
                [
                    "az",
                    "vm",
                    "list-skus",
                    "--location",
                    region,
                    "--resource-type",
                    "virtualMachines",
                    "--all",
                    "--output",
                    "json",
                ],
                verbosity=verbosity,
                event_sink=az_event_sink,
                runner=self.command_runner,
            )
            status["sku_query"] = _az_command_status(query)
        return status

    def azure_quota(
        self,
        region: str,
        verbosity: int = 0,
        az_event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not shutil.which("az"):
            return {
                "method": "unavailable",
                "ok": False,
                "reason": "az CLI not found on PATH",
                "items": [],
            }
        command = ["az", "vm", "list-usage", "--location", region, "--output", "json"]
        completed = _run_az(command, verbosity=verbosity, event_sink=az_event_sink, runner=self.command_runner)
        if completed.returncode != 0 or not completed.stdout.strip():
            return {
                "method": "live",
                "ok": False,
                "reason": f"az vm list-usage failed or returned no output (exit {completed.returncode})",
                "command": command,
                "items": [],
            }
        try:
            values = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {
                "method": "live",
                "ok": False,
                "reason": "az vm list-usage returned non-JSON output",
                "command": command,
                "items": [],
            }
        items = []
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                limit = _float(item.get("limit"))
                current = _float(item.get("currentValue"))
                remaining = None if limit is None or current is None else max(limit - current, 0)
                name = item.get("name") if isinstance(item.get("name"), dict) else {}
                items.append(
                    {
                        "name": name.get("localizedValue") or name.get("value") or item.get("name"),
                        "current": current,
                        "limit": limit,
                        "remaining": remaining,
                        "unit": item.get("unit"),
                    }
                )
        return {"method": "live", "ok": True, "command": command, "items": items}

    def cache_list(self) -> dict[str, Any]:
        cache = self._load_discovery_cache()
        rows = []
        for key, value in sorted(cache.items()):
            if not isinstance(value, dict):
                continue
            discovery = value.get("discovery") if isinstance(value.get("discovery"), dict) else {}
            rows.append(
                {
                    "name": key,
                    "provider": value.get("provider"),
                    "region": value.get("region"),
                    "method": discovery.get("method"),
                    "source": discovery.get("source"),
                    "candidate_count": (
                        len(value.get("candidates", [])) if isinstance(value.get("candidates"), list) else 0
                    ),
                    "criteria": value.get("criteria", {}),
                }
            )
        return {"path": str(self._discovery_cache_path()), "entries": rows}

    def cache_clear(self, key: str | None = None) -> dict[str, Any]:
        path = self._discovery_cache_path()
        cache = self._load_discovery_cache()
        if key:
            existed = key in cache
            cache.pop(key, None)
            if cache:
                self._write_discovery_cache(cache)
            elif path.exists():
                path.unlink()
            return {
                "path": str(path),
                "cleared": [key] if existed else [],
                "remaining": len(cache),
            }
        count = len(cache)
        if path.exists():
            path.unlink()
        return {"path": str(path), "cleared_count": count, "remaining": 0}

    def validate(self, name: str | None = None) -> dict[str, Any]:
        machines = self._machines()
        rows = []
        for machine_name, machine in machines.items():
            if name and machine_name != name:
                continue
            validation = validate_machine(machine if isinstance(machine, dict) else {})
            rows.append({"name": machine_name, **validation})
        if name and not rows:
            raise ValueError(f"unknown machine: {name}")
        return {"ok": all(row["ok"] for row in rows), "machines": rows}

    def azure_machine_from_sku(self, sku: str, region: str, name: str | None = None) -> dict[str, Any]:
        hint = AZURE_SKU_HINTS.get(sku, {})
        machine_name = name or _safe_name("azure_" + sku)
        vram = hint.get("vram_gb", 0)
        gpu_count = hint.get("gpu_count", 0)
        machine = {
            "name": machine_name,
            "origin": "azure_sku",
            "stock": {
                "provider": "azure",
                "machine_tag": machine_name,
                "stock_sku": sku,
                "region": region,
            },
            "placement": "vm",
            "substrate": "docker",
            "cpu": {
                "architecture": "x86_64",
                "cores": hint.get("cpu_cores"),
                "threads": hint.get("cpu_cores"),
            },
            "memory": {
                "ram_gb": hint.get("memory_gb"),
                "unified_memory_gb": None,
                "memory_architecture": "discrete",
                "memory_bandwidth_gbps": None,
            },
            "gpu": {
                "vendor": hint.get("gpu_vendor", "unknown"),
                "model": hint.get("gpu_model", "unknown"),
                "count": gpu_count,
                "vram_gb": vram,
                "total_vram_gb": hint.get("total_vram_gb", (vram or 0) * (gpu_count or 0)),
                "indices": None,
            },
            "accelerator_apis": (["cuda"] if hint.get("gpu_vendor") == "nvidia" else ["cpu"]),
            "os": "linux",
            "notes": "Imported from Azure SKU hints; verify region availability, quota, and exact GPU memory before provisioning.",
        }
        return {"name": machine_name, "machine": machine}

    def import_azure_sku(
        self,
        sku: str,
        region: str,
        name: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self.azure_machine_from_sku(sku, region, name=name)
        machine = payload["machine"]
        for key, value in (overrides or {}).items():
            _set_machine_value(machine, key, value)
        validation = validate_machine(machine)
        if not validation["ok"]:
            raise ValueError("invalid Azure SKU machine profile: " + "; ".join(validation["errors"]))
        self.config.setdefault("self_managed_machines", {})[payload["name"]] = machine
        self._write_config()
        return {
            "name": payload["name"],
            "path": str(self.profile.root / "hardware.yaml"),
            "validation": validation,
            "machine": machine,
        }

    def profile_remote_plan(self, name: str, host: str, user: str | None = None, port: int = 22) -> dict[str, Any]:
        host = validate_ssh_host(host, "host")
        user = validate_ssh_user(user, "user")
        port = validate_port(port, "port")
        destination = f"{user}@{host}" if user else host
        remote = shlex.join(["aiplane", "hardware", "export-machine", "--profile", self.profile.name, "--name", name])
        return {
            "name": name,
            "mode": "ssh_remote_profile",
            "steps": [
                {
                    "name": "install-or-update aiplane on the remote machine",
                    "command": [
                        "ssh",
                        "-p",
                        str(port),
                        destination,
                        "<install aiplane>",
                    ],
                },
                {
                    "name": "export machine profile from remote",
                    "command": ["ssh", "-p", str(port), destination, remote],
                },
                {
                    "name": "import on this control machine",
                    "command": [
                        "aiplane",
                        "machines",
                        "import",
                        f"{name}.machine.yaml",
                        "--profile",
                        self.profile.name,
                    ],
                },
            ],
            "notes": [
                "This is a plan only; it does not SSH or copy files yet.",
                "The same pattern works for self-managed cloud VMs after SSH access is available.",
            ],
        }

    def _criteria(self, model: str | None, runtime: str | None, workload: str | None) -> dict[str, Any]:
        criteria = {
            "model": model,
            "runtime": runtime,
            "workload": workload,
            "min_ram_gb": 0.0,
            "min_vram_gb": 0.0,
            "recommended_ram_gb": None,
            "recommended_vram_gb": None,
        }
        if workload:
            if workload not in WORKLOAD_CLASSES:
                raise ValueError(f"unknown workload: {workload}")
            criteria.update(WORKLOAD_CLASSES[workload])
        if model:
            model_config = ModelCatalog(self.profile).get(model)
            criteria["min_ram_gb"] = max(
                float(criteria.get("min_ram_gb") or 0),
                _float(model_config.get("min_ram_gb")) or 0,
            )
            criteria["min_vram_gb"] = max(
                float(criteria.get("min_vram_gb") or 0),
                _float(model_config.get("min_vram_gb")) or 0,
            )
            criteria["recommended_ram_gb"] = model_config.get("recommended_ram_gb")
            criteria["recommended_vram_gb"] = model_config.get("recommended_vram_gb")
        if runtime:
            # Runtime checks are intentionally lightweight here; detailed runtime availability belongs to RuntimeCatalog.
            known = {row["name"] for row in RuntimeCatalog(self.profile).list(include_gui=True)}
            if runtime not in known:
                raise ValueError(f"unknown runtime: {runtime}")
        return criteria

    def _machines(self) -> dict[str, Any]:
        machines = self.config.get("self_managed_machines", {})
        return machines if isinstance(machines, dict) else {}

    def _record_discovery(
        self,
        provider: str,
        region: str,
        criteria: dict[str, Any],
        result: dict[str, Any],
        method: str,
        source: str,
        command: list[str],
        status: str,
    ) -> dict[str, Any]:
        cache = self._load_discovery_cache()
        key = _discovery_cache_key(provider, region, criteria)
        previous = cache.get(key) if isinstance(cache.get(key), dict) else None
        previous_method = (previous.get("discovery") or {}).get("method") if previous else None
        should_write = method == "live" or previous_method != "live"
        action = "skipped_offline_because_live_cache_exists"
        if should_write:
            cache[key] = {
                "provider": provider,
                "region": region,
                "criteria": criteria,
                "source": source,
                "candidates": result.get("candidates", []),
                "discovery": {
                    "method": method,
                    "source": source,
                    "status": status,
                    "command": command,
                },
            }
            self._write_discovery_cache(cache)
            action = "overrode_previous" if previous else "created"
        return {
            "path": str(self._discovery_cache_path()),
            "key": key,
            "written": should_write,
            "action": action,
            "previous_method": previous_method,
        }

    def _load_discovery_cache(self) -> dict[str, Any]:
        path = self._discovery_cache_path()
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _write_discovery_cache(self, cache: dict[str, Any]) -> None:
        path = self._discovery_cache_path()
        atomic_write_text(path, json.dumps(cache, indent=2))

    def _discovery_cache_path(self) -> Path:
        return self.profile.root / "machine-discovery-cache.json"

    def _runtime_hints(self) -> dict[str, Any]:
        return {
            "docker": shutil.which("docker") is not None,
            "nvidia_smi": shutil.which("nvidia-smi") is not None,
            "rocm_smi": shutil.which("rocm-smi") is not None,
            "ollama": shutil.which("ollama") is not None,
            "python": True,
        }

    def _write_config(self) -> None:
        path = self.profile.root / "hardware.yaml"
        atomic_write_text(path, dump_yaml(self.config))


def validate_machine(machine: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for key in [
        "name",
        "stock",
        "placement",
        "substrate",
        "cpu",
        "memory",
        "gpu",
        "accelerator_apis",
        "os",
    ]:
        if key not in machine:
            errors.append(f"missing {key}")
    if not isinstance(machine.get("stock"), dict):
        errors.append("stock must be a mapping")
    if not isinstance(machine.get("cpu"), dict):
        errors.append("cpu must be a mapping")
    if not isinstance(machine.get("memory"), dict):
        errors.append("memory must be a mapping")
    if not isinstance(machine.get("gpu"), dict):
        errors.append("gpu must be a mapping")
    ram = _float((machine.get("memory") or {}).get("ram_gb")) if isinstance(machine.get("memory"), dict) else None
    unified = (
        _float((machine.get("memory") or {}).get("unified_memory_gb"))
        if isinstance(machine.get("memory"), dict)
        else None
    )
    vram = _float((machine.get("gpu") or {}).get("vram_gb")) if isinstance(machine.get("gpu"), dict) else None
    if ram is None and unified is None:
        errors.append("memory.ram_gb or memory.unified_memory_gb is required")
    if vram is None and unified is None:
        errors.append("gpu.vram_gb or memory.unified_memory_gb is required")
    if isinstance(machine.get("gpu"), dict) and machine["gpu"].get("vendor") in {
        None,
        "",
    }:
        warnings.append("gpu.vendor is empty")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def load_machine_profile(
    path: Path,
    name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _read_payload(path)
    machine = payload.get("machine") if isinstance(payload.get("machine"), dict) else payload
    if not isinstance(machine, dict):
        raise ValueError("machine import file must contain a mapping or a top-level machine mapping")
    machine_name = name or str(payload.get("name") or machine.get("name") or machine.get("machine_tag") or "")
    if not machine_name:
        raise ValueError("machine import needs --name or a name in the file")
    machine = _deepcopy_json(machine)
    machine["name"] = machine_name
    for key, value in (overrides or {}).items():
        _set_machine_value(machine, key, value)
    validation = validate_machine(machine)
    if not validation["ok"]:
        raise ValueError("invalid machine profile: " + "; ".join(validation["errors"]))
    return {"name": machine_name, "machine": machine, "validation": validation}


def _read_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        loaded = parse_yaml(text)
    if not isinstance(loaded, dict):
        raise ValueError("machine import file must contain an object/mapping")
    return loaded


def _azure_skus_from_cli(values: list[dict[str, Any]], region: str) -> list[dict[str, Any]]:
    machines = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name or name not in AZURE_SKU_HINTS:
            continue
        machine = MachineManager.__new__(MachineManager).azure_machine_from_sku(name, region)["machine"]
        machine["restrictions"] = _azure_sku_restrictions(item)
        machine["zones"] = item.get("locationInfo", [])
        machines.append(machine)
    return machines


def _azure_sku_restrictions(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    restrictions = item.get("restrictions", [])
    if not isinstance(restrictions, list):
        return rows
    for restriction in restrictions:
        if not isinstance(restriction, dict):
            continue
        rows.append(
            {
                "type": restriction.get("type"),
                "reason_code": restriction.get("reasonCode"),
                "restriction_info": restriction.get("restrictionInfo"),
                "values": restriction.get("values", []),
            }
        )
    return rows


def _discovery_cache_key(provider: str, region: str, criteria: dict[str, Any]) -> str:
    parts = [
        provider,
        region,
        str(criteria.get("workload") or "any_workload"),
        str(criteria.get("model") or "any_model"),
        str(criteria.get("runtime") or "any_runtime"),
        f"gpu_{criteria.get('gpu_vendor') or 'any'}",
        f"cpu_{criteria.get('min_cpu_cores') or 'any'}",
        f"ram_{criteria.get('min_ram_gb') or 'any'}",
        f"vram_{criteria.get('min_vram_gb') or 'any'}",
    ]
    return "__".join(_safe_name(part) for part in parts)


def _azure_machine_matches_filters(machine: dict[str, Any], criteria: dict[str, Any]) -> bool:
    required_vendor = str(criteria.get("gpu_vendor") or "").strip().lower()
    machine_vendor = str((machine.get("gpu") or {}).get("vendor") or "").strip().lower()
    if required_vendor and machine_vendor != required_vendor:
        return False

    min_cpu = _float(criteria.get("min_cpu_cores")) or 0.0
    cpu_cores = _float((machine.get("cpu") or {}).get("cores")) or 0.0
    if cpu_cores < min_cpu:
        return False

    min_ram = _float(criteria.get("min_ram_gb")) or 0.0
    ram = (
        _float((machine.get("memory") or {}).get("ram_gb"))
        or _float((machine.get("memory") or {}).get("unified_memory_gb"))
        or 0.0
    )
    if ram < min_ram:
        return False

    min_vram = _float(criteria.get("min_vram_gb")) or 0.0
    vram = (
        _float((machine.get("gpu") or {}).get("vram_gb"))
        or _float((machine.get("memory") or {}).get("unified_memory_gb"))
        or 0.0
    )
    return vram >= min_vram


def _machine_fit(machine: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    ram = (
        _float((machine.get("memory") or {}).get("ram_gb"))
        or _float((machine.get("memory") or {}).get("unified_memory_gb"))
        or 0.0
    )
    vram = (
        _float((machine.get("gpu") or {}).get("vram_gb"))
        or _float((machine.get("memory") or {}).get("unified_memory_gb"))
        or 0.0
    )
    min_ram = _float(criteria.get("min_ram_gb")) or 0.0
    min_vram = _float(criteria.get("min_vram_gb")) or 0.0
    rec_ram = _float(criteria.get("recommended_ram_gb"))
    rec_vram = _float(criteria.get("recommended_vram_gb"))
    blockers = []
    if ram < min_ram:
        blockers.append(f"RAM {ram:g}GB < required {min_ram:g}GB")
    if vram < min_vram:
        blockers.append(f"VRAM {vram:g}GB < required {min_vram:g}GB")
    if blockers:
        return {"level": "not_recommended", "score": 0, "reason": "; ".join(blockers)}
    score = 60
    gaps = []
    if rec_ram is not None and ram < rec_ram:
        gaps.append(f"RAM {ram:g}GB < recommended {rec_ram:g}GB")
    else:
        score += 15
    if rec_vram is not None and vram < rec_vram:
        gaps.append(f"VRAM {vram:g}GB < recommended {rec_vram:g}GB")
    else:
        score += 15
    if vram > 0:
        score += 10
    return {
        "level": "usable" if gaps else "recommended",
        "score": score,
        "reason": "; ".join(gaps) if gaps else "meets configured machine fit criteria",
    }


def _machine_summary(machine: dict[str, Any]) -> dict[str, Any]:
    return {
        "stock": machine.get("stock"),
        "placement": machine.get("placement"),
        "substrate": machine.get("substrate"),
        "cpu": machine.get("cpu"),
        "memory": machine.get("memory"),
        "gpu": machine.get("gpu"),
        "accelerator_apis": machine.get("accelerator_apis"),
    }


def _set_machine_value(machine: dict[str, Any], key: str, value: Any) -> None:
    mapping = {
        "memory_gb": ["memory", "ram_gb"],
        "unified_memory_gb": ["memory", "unified_memory_gb"],
        "vram_gb": ["gpu", "vram_gb"],
        "total_vram_gb": ["gpu", "total_vram_gb"],
        "gpu_vendor": ["gpu", "vendor"],
        "gpu_model": ["gpu", "model"],
        "gpu_count": ["gpu", "count"],
        "cpu_cores": ["cpu", "cores"],
        "cpu_threads": ["cpu", "threads"],
        "stock_sku": ["stock", "stock_sku"],
        "machine_tag": ["stock", "machine_tag"],
        "provider": ["stock", "provider"],
    }
    path = mapping.get(key, [key])
    cursor = machine
    for part in path[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[path[-1]] = value


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "auto", "provider_defined", "node_pool_defined"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _deepcopy_json(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))
