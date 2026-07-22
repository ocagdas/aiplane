"""Cross-platform hardware discovery with normalized per-device evidence."""

from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

from .boundaries import CommandRunner
from .platform_support import HostPlatform


def discover_hardware(runner: CommandRunner, host: HostPlatform) -> dict[str, Any]:
    memory = _memory(host, runner)
    found: dict[str, Any] = {
        "schema_version": "2.0",
        "platform": platform.platform(),
        "platform_support": host.summary(),
        "machine": host.machine,
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "memory_gb": memory.get("total_gb"),
        "available_memory_gb": memory.get("available_gb"),
        "memory": memory,
        "gpus": [],
        "gpu_groups": [],
        "topology": {"state": "not_available", "links": []},
        "notes": [],
    }
    if host.normalized_system == "linux":
        nvidia, topology = _nvidia(runner)
        found["gpus"] += nvidia + _amd(runner)
        found["gpus"] += _pci_devices(runner, "intel", "openvino")
        found["topology"] = topology
    elif host.normalized_system == "darwin":
        found["gpus"] += _apple(runner, memory)
    elif host.normalized_system == "windows":
        win_memory, gpus = _windows(runner)
        if win_memory:
            found["memory"] = win_memory
            found["memory_gb"] = win_memory.get("total_gb")
            found["available_memory_gb"] = win_memory.get("available_gb")
        found["gpus"] += gpus
    else:
        found["notes"].append(f"Hardware probes are not implemented for {host.system}")
    for index, gpu in enumerate(found["gpus"]):
        gpu.setdefault("index", index)
        gpu.setdefault("device_id", str(gpu.get("uuid") or gpu.get("pci_bus_id") or index))
        gpu.setdefault("free_vram_gb", None)
        gpu.setdefault("unified_memory", False)
    found["gpu_groups"] = group_gpus(found["gpus"])
    if not found["gpus"]:
        found["notes"].append("No supported accelerator was discovered through available platform tools")
    return found


def _memory(host: HostPlatform, runner: CommandRunner) -> dict[str, Any]:
    if host.linux:
        values: dict[str, int] = {}
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(value.split()[0])
        except (OSError, ValueError, IndexError):
            pass
        return {
            "architecture": "system",
            "total_gb": _kib_to_gib(values.get("MemTotal")),
            "available_gb": _kib_to_gib(values.get("MemAvailable")),
            "source": "/proc/meminfo" if values else None,
        }
    if host.normalized_system == "darwin":
        text = _run(runner, ["sysctl", "-n", "hw.memsize"])
        try:
            total = round(int(text) / 1024**3, 2) if text else None
        except ValueError:
            total = None
        return {"architecture": "unified", "total_gb": total, "available_gb": None, "source": "sysctl"}
    return {"architecture": "unknown", "total_gb": None, "available_gb": None, "source": None}


def _nvidia(runner: CommandRunner) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return [], {"state": "not_available", "links": []}
    fields = ["index", "name", "memory.total", "memory.free", "uuid", "pci.bus_id", "compute_cap", "driver_version"]
    text = _run(runner, ["nvidia-smi", f"--query-gpu={','.join(fields)}", "--format=csv,noheader,nounits"])
    devices = []
    for line in (text or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(fields):
            continue
        row = dict(zip(fields, parts))
        total = _number(row["memory.total"])
        free = _number(row["memory.free"])
        devices.append(
            {
                "index": _integer(row["index"], len(devices)),
                "device_id": row["uuid"],
                "vendor": "nvidia",
                "name": row["name"],
                "backend": "cuda",
                "vram_mb": _integer(total, None),
                "vram_gb": _mib_to_gib(total),
                "free_vram_mb": _integer(free, None),
                "free_vram_gb": _mib_to_gib(free),
                "uuid": row["uuid"],
                "pci_bus_id": row["pci.bus_id"],
                "compute_capability": row["compute_cap"],
                "driver_version": row["driver_version"],
                "unified_memory": False,
                "source": "nvidia-smi",
            }
        )
    return devices, _nvidia_topology(runner, len(devices))


def _nvidia_topology(runner: CommandRunner, count: int) -> dict[str, Any]:
    if count < 2:
        return {"state": "single_device" if count else "not_available", "links": []}
    text = _run(runner, ["nvidia-smi", "topo", "-m"])
    if not text:
        return {"state": "unresolved", "links": [], "source": "nvidia-smi topo -m"}
    lines = text.splitlines()
    headers = [item for item in lines[0].split() if item.startswith("GPU")]
    links = []
    for row in (line.split() for line in lines[1:] if line.strip().startswith("GPU")):
        for target, connection in zip(headers, row[1:]):
            if row[0] != target and connection not in {"X", "N/A"}:
                links.append({"source": row[0], "target": target, "connection": connection})
    return {"state": "detected", "links": links, "source": "nvidia-smi topo -m"}


def _amd(runner: CommandRunner) -> list[dict[str, Any]]:
    if shutil.which("rocm-smi"):
        text = _run(
            runner,
            [
                "rocm-smi",
                "--showproductname",
                "--showmeminfo",
                "vram",
                "--showuniqueid",
                "--showdriverversion",
                "--json",
            ],
        )
        try:
            payload = json.loads(text or "")
        except json.JSONDecodeError:
            payload = {}
        devices = _amd_json(payload)
        if devices:
            return devices
    return _pci_devices(runner, "amd", "rocm")


def _amd_json(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    devices = []
    for fallback, (card, raw) in enumerate(payload.items()):
        if not isinstance(raw, dict):
            continue
        flat = {str(key).lower(): value for key, value in raw.items()}
        total_bytes = _number(_find(flat, "vram total", "total memory"))
        used_bytes = _number(_find(flat, "vram used", "used memory"))
        total = round(total_bytes / 1024**3, 2) if total_bytes and total_bytes > 1024**2 else None
        free = round((total_bytes - used_bytes) / 1024**3, 2) if total_bytes and used_bytes is not None else None
        devices.append(
            {
                "index": _integer("".join(ch for ch in str(card) if ch.isdigit()), fallback),
                "vendor": "amd",
                "name": str(_find(flat, "card series", "product name", "device name") or card),
                "backend": "rocm",
                "vram_mb": int(total * 1024) if total is not None else None,
                "vram_gb": total,
                "free_vram_gb": free,
                "uuid": _find(flat, "unique id", "uniqueid"),
                "driver_version": _find(flat, "driver version"),
                "unified_memory": False,
                "source": "rocm-smi",
            }
        )
    return devices


def _pci_devices(runner: CommandRunner, vendor: str, backend: str) -> list[dict[str, Any]]:
    if not shutil.which("lspci"):
        return []
    devices = []
    for line in (_run(runner, ["lspci", "-D"]) or "").splitlines():
        lower = line.lower()
        display = any(kind in lower for kind in ("vga compatible", "3d controller", "display controller"))
        matches = vendor in lower or (vendor == "amd" and "advanced micro devices" in lower)
        if display and matches:
            bus, _, name = line.partition(" ")
            devices.append(
                {
                    "index": len(devices),
                    "device_id": bus,
                    "vendor": vendor,
                    "name": name.strip(),
                    "backend": backend,
                    "pci_bus_id": bus,
                    "vram_mb": None,
                    "vram_gb": None,
                    "free_vram_gb": None,
                    "unified_memory": False,
                    "source": "lspci",
                }
            )
    return devices


def _apple(runner: CommandRunner, memory: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        payload = json.loads(_run(runner, ["system_profiler", "SPDisplaysDataType", "-json"]) or "")
    except json.JSONDecodeError:
        return []
    rows = payload.get("SPDisplaysDataType", []) if isinstance(payload, dict) else []
    return [
        {
            "index": index,
            "vendor": "apple",
            "name": row.get("sppci_model") or row.get("_name"),
            "backend": "metal",
            "vram_mb": None,
            "vram_gb": memory.get("total_gb"),
            "free_vram_gb": None,
            "unified_memory": True,
            "source": "system_profiler",
        }
        for index, row in enumerate(rows)
        if isinstance(row, dict)
    ]


def _windows(runner: CommandRunner) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    shell = "powershell"
    script = (
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$gpu=Get-CimInstance Win32_VideoController;"
        "@{memory=@{total_kib=[double]$os.TotalVisibleMemorySize;available_kib=[double]$os.FreePhysicalMemory};"
        "gpus=@($gpu|Select-Object Name,AdapterRAM,PNPDeviceID,DriverVersion)}"
        "|ConvertTo-Json -Depth 4 -Compress"
    )
    try:
        payload = json.loads(_run(runner, [shell, "-NoProfile", "-NonInteractive", "-Command", script]) or "")
    except json.JSONDecodeError:
        return None, []
    raw = payload.get("memory", {}) if isinstance(payload, dict) else {}
    memory = {
        "architecture": "system",
        "total_gb": _kib_to_gib(raw.get("total_kib")),
        "available_gb": _kib_to_gib(raw.get("available_kib")),
        "source": "Win32_OperatingSystem",
    }
    rows = payload.get("gpus", []) if isinstance(payload, dict) else []
    rows = rows if isinstance(rows, list) else [rows]
    devices = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or "Windows display adapter")
        vendor = _vendor(name)
        ram = _number(row.get("AdapterRAM"))
        devices.append(
            {
                "index": len(devices),
                "device_id": row.get("PNPDeviceID"),
                "vendor": vendor,
                "name": name,
                "backend": "cuda" if vendor == "nvidia" else "directml",
                "vram_mb": int(ram / 1024**2) if ram else None,
                "vram_gb": round(ram / 1024**3, 2) if ram else None,
                "free_vram_gb": None,
                "driver_version": row.get("DriverVersion"),
                "unified_memory": False,
                "source": "Win32_VideoController",
            }
        )
    return memory, devices


def group_gpus(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, bool], list[dict[str, Any]]] = {}
    for device in devices:
        key = (
            str(device.get("vendor") or "unknown"),
            str(device.get("name") or "unknown"),
            str(device.get("backend") or "unknown"),
            bool(device.get("unified_memory")),
        )
        grouped.setdefault(key, []).append(device)
    result = []
    for (vendor, name, backend, unified), members in grouped.items():
        capacities = [_number(item.get("vram_gb")) for item in members]
        known = [value for value in capacities if value is not None]
        result.append(
            {
                "vendor": vendor,
                "model": name,
                "backend": backend,
                "unified_memory": unified,
                "count": len(members),
                "indices": [item.get("index") for item in members],
                "max_single_vram_gb": max(known) if known else None,
                "total_vram_gb": round(sum(known), 2) if len(known) == len(members) else None,
                "homogeneous": True,
            }
        )
    return sorted(result, key=lambda item: (str(item["vendor"]), str(item["model"])))


def _run(runner: CommandRunner, command: list[str]) -> str | None:
    try:
        completed = runner.run(command, text=True, capture_output=True, check=False)
    except OSError:
        return None
    return str(completed.stdout).strip() if completed.returncode == 0 else None


def _find(values: dict[str, Any], *needles: str) -> Any:
    return next((value for key, value in values.items() if any(needle in key for needle in needles)), None)


def _vendor(name: str) -> str:
    lower = name.lower()
    if "nvidia" in lower:
        return "nvidia"
    if "amd" in lower or "radeon" in lower:
        return "amd"
    if "intel" in lower:
        return "intel"
    return "unknown"


def _number(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "", "N/A", "[N/A]") else None
    except (TypeError, ValueError):
        return None


def _integer(value: object, default: int | None) -> int | None:
    number = _number(value)
    return int(number) if number is not None else default


def _mib_to_gib(value: float | None) -> float | None:
    return round(value / 1024, 2) if value is not None else None


def _kib_to_gib(value: object) -> float | None:
    number = _number(value)
    return round(number / 1024**2, 2) if number is not None else None
