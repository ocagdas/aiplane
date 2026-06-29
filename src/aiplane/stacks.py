from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from typing import Any

from .config import dump_yaml, project_root
from .env import EnvironmentManager
from .integrations import IntegrationManager
from .machines import MachineManager
from .model_catalog import ModelCatalog
from .models import Profile
from .orchestrators import OrchestratorCatalog
from .runtime_catalog import RuntimeCatalog


class StackManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.config = profile.hardware or {}

    def list(self) -> list[dict[str, Any]]:
        rows = []
        for name, stack in self._stacks().items():
            if isinstance(stack, dict):
                rows.append({"name": name, "orchestrator": stack.get("orchestrator"), "runtime": stack.get("runtime"), "model": stack.get("model"), "machine": stack.get("machine"), "access": stack.get("access"), "endpoint_policy": stack.get("endpoint_policy"), "limits": stack.get("limits", {}), "tools": stack.get("tools", {})})
        return sorted(rows, key=lambda row: str(row["name"]))

    def show(self, name: str) -> dict[str, Any]:
        return {"name": name, "stack": self._stack(name)}

    def create(self, name: str, model: str, runtime: str, machine: str, access: str = "ssh_tunnel", endpoint_policy: str = "private", endpoint: str | None = None, orchestrator: str | None = None) -> dict[str, Any]:
        return self.setup(name, orchestrator=orchestrator, runtime=runtime, model=model, machine=machine, access=access, endpoint_policy=endpoint_policy, endpoint=endpoint, dry_run=False, yes=True)

    def setup(self, name: str, orchestrator: str | None, runtime: str, model: str, machine: str, access: str = "ssh_tunnel", endpoint_policy: str = "private", endpoint: str | None = None, limits: dict[str, object] | None = None, tools: dict[str, object] | None = None, dry_run: bool = False, yes: bool | None = None) -> dict[str, Any]:
        if not name or "/" in name or "\\" in name:
            raise ValueError("stack name must be a simple name")
        if orchestrator:
            OrchestratorCatalog(self.profile).show(orchestrator)
        ModelCatalog(self.profile).get(model)
        machines = {row["name"] for row in MachineManager(self.profile).list()}
        if machine not in machines:
            raise ValueError(f"unknown machine: {machine}")
        if runtime not in {row["name"] for row in RuntimeCatalog(self.profile).list(include_gui=True)}:
            raise ValueError(f"unknown runtime: {runtime}")
        stack = {"orchestrator": orchestrator, "runtime": runtime, "model": model, "machine": machine, "access": access, "endpoint_policy": endpoint_policy, "limits": limits or {}, "tools": tools or {}}
        if endpoint:
            stack["endpoint"] = endpoint
        payload = {"name": name, "dry_run": dry_run, "path": str(self.profile.root / "hardware.yaml"), "stack": stack, "notes": ["A stack currently represents one primary orchestrator/runtime/model/machine tuple. Add separate stacks for separate serving targets."]}
        if dry_run:
            return payload
        self.config.setdefault("stacks", {})[name] = stack
        self._write_config()
        return payload

    def plan(self, name: str) -> dict[str, Any]:
        stack = self._stack(name)
        orchestrator = str(stack.get("orchestrator") or "")
        model_name = str(stack.get("model") or "")
        runtime = str(stack.get("runtime") or "")
        machine_name = str(stack.get("machine") or "")
        model = ModelCatalog(self.profile).show(model_name)
        machine = MachineManager(self.profile).show(machine_name)["machine"]
        runtime_catalog = RuntimeCatalog(self.profile)
        runtime_status = runtime_catalog.runtime_available(runtime)
        endpoint = stack.get("endpoint") or _default_endpoint(runtime)
        preflight = self._preflight(stack, runtime, model_name, endpoint, runtime_catalog)
        steps = [
            {"name": "check machine fit", "action": "aiplane machines recommend", "mutates": False},
            {"name": "install or update runtime", "command": [str(project_root() / "scripts" / "provider_helper.sh"), "--provider", runtime, "--action", "install", "--profile", self.profile.name, "--model", model_name], "mutates": True},
            {"name": "pull model", "command": [str(project_root() / "scripts" / "provider_helper.sh"), "--provider", runtime, "--action", "pull", "--profile", self.profile.name, "--model", model_name], "mutates": True},
            {"name": "start runtime", "command": [str(project_root() / "scripts" / "provider_helper.sh"), "--provider", runtime, "--action", "start", "--profile", self.profile.name, "--model", model_name], "mutates": True},
            {"name": "export IDE config", "command": ["aiplane", "stacks", "export", "continue", name], "mutates": False},
        ]
        if orchestrator:
            steps.insert(1, {"name": "prepare orchestrator environment", "command": ["aiplane", "stacks", "prepare", name], "mutates": True})
        if stack.get("access") == "ssh_tunnel":
            steps.insert(4 if orchestrator else 3, {"name": "prepare SSH tunnel", "command": ["aiplane", "remote", "tunnel", "plan", "--target", str(stack.get("target") or machine_name)], "mutates": False})
        return {
            "name": name,
            "orchestrator": orchestrator or None,
            "runtime": runtime,
            "model": model_name,
            "machine": machine_name,
            "access": stack.get("access"),
            "endpoint_policy": stack.get("endpoint_policy"),
            "endpoint": endpoint,
            "fit": MachineManager(self.profile).recommend(model=model_name, runtime=runtime, limit=None),
            "model_config": model,
            "machine_config": machine,
            "runtime_status": runtime_status,
            "orchestrator_status": OrchestratorCatalog(self.profile).doctor(orchestrator) if orchestrator else None,
            "preflight": preflight,
            "limits": stack.get("limits", {}),
            "tools": stack.get("tools", {}),
            "steps": steps,
            "notes": ["Stack lifecycle execution is same-host/local first; SSH/Azure/AKS stacks currently return plans until remote execution and audit controls are hardened."],
        }

    def doctor(self, name: str) -> dict[str, Any]:
        plan = self.plan(name)
        machine_rows = [row for row in plan["fit"]["machines"] if row["name"] == plan["machine"]]
        checks = [
            {"name": "machine_exists", "ok": bool(machine_rows), "detail": plan["machine"]},
            {"name": "machine_fit", "ok": bool(machine_rows and machine_rows[0]["level"] != "not_recommended"), "detail": machine_rows[0]["reason"] if machine_rows else "machine missing"},
            {"name": "runtime_known", "ok": bool(plan["runtime_status"].get("name")), "detail": plan["runtime_status"].get("reason")},
            {"name": "runtime_available_now", "ok": bool(plan["runtime_status"].get("available")), "detail": plan["runtime_status"].get("reason")},
        ]
        for check in plan.get("preflight", {}).get("checks", []):
            if isinstance(check, dict):
                checks.append(check)
        if plan.get("orchestrator"):
            orch = plan.get("orchestrator_status") or {}
            checks.append({"name": "orchestrator_known", "ok": bool(orch.get("name")), "detail": plan.get("orchestrator")})
        return {"name": name, "checks": checks, "plan_summary": {"orchestrator": plan.get("orchestrator"), "runtime": plan["runtime"], "model": plan["model"], "machine": plan["machine"], "endpoint": plan["endpoint"]}}

    def export(self, artifact: str, name: str) -> dict[str, Any]:
        stack = self._stack(name)
        model = str(stack.get("model") or "")
        runtime = str(stack.get("runtime") or "")
        orchestrator = str(stack.get("orchestrator") or "")
        endpoint = str(stack.get("endpoint") or _default_endpoint(runtime))
        if artifact in {"continue", "openai-compatible"}:
            exported = IntegrationManager(self.profile).export(artifact, model, endpoint=endpoint)
            return {"name": name, "artifact": artifact, "tool": exported.tool, "model": exported.model, "provider": exported.provider, "endpoint": exported.endpoint, "content": exported.content, "notes": exported.notes}
        if artifact in {"dockerfile", "conda-yaml"}:
            mode = "docker" if artifact == "dockerfile" else "conda"
            runtime_plan = RuntimeCatalog(self.profile).bundle_plan(runtime, model_name=model, mode=mode)
            orchestrator_plan = OrchestratorCatalog(self.profile).bundle_plan(orchestrator, mode=mode) if orchestrator else None
            metadata = self._export_metadata(name, stack, endpoint)
            content = _merge_bundle_content(artifact, runtime_plan, orchestrator_plan, metadata)
            return {"name": name, "artifact": artifact, "orchestrator": orchestrator or None, "runtime": runtime, "model": model, "endpoint": endpoint, "metadata": metadata, "content": content, "notes": ["Exported artifact is a starter packaging file. Review before building or applying it.", "Stack limits and tool policies are pass-through metadata; enforcement belongs to the runtime/orchestrator."]}
        if artifact == "compose":
            metadata = self._export_metadata(name, stack, endpoint)
            return {"name": name, "artifact": artifact, "orchestrator": orchestrator or None, "runtime": runtime, "model": model, "endpoint": endpoint, "metadata": metadata, "content": _compose_yaml(name, runtime, model, endpoint, metadata), "notes": ["Compose export is a starter file for local/VM use and may need runtime-specific tuning.", "Stack limits and tool policies are pass-through metadata; enforcement belongs to the runtime/orchestrator."]}
        raise ValueError(f"unknown stack export artifact: {artifact}")

    def prepare(self, name: str, dry_run: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "prepare", dry_run=dry_run)

    def start(self, name: str, dry_run: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "start", dry_run=dry_run)

    def stop(self, name: str, dry_run: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "stop", dry_run=dry_run)

    def restart(self, name: str, dry_run: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "restart", dry_run=dry_run)

    def status(self, name: str) -> dict[str, Any]:
        stack = self._stack(name)
        runtime = str(stack.get("runtime") or "")
        orchestrator = str(stack.get("orchestrator") or "")
        return {
            "name": name,
            "orchestrator": orchestrator or None,
            "runtime": runtime,
            "model": stack.get("model"),
            "machine": stack.get("machine"),
            "limits": stack.get("limits", {}),
            "tools": stack.get("tools", {}),
            "runtime_status": RuntimeCatalog(self.profile).runtime_available(runtime),
            "orchestrator_status": OrchestratorCatalog(self.profile).doctor(orchestrator) if orchestrator else None,
        }

    def _preflight(self, stack: dict[str, Any], runtime: str, model: str, endpoint: object, runtime_catalog: RuntimeCatalog) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        prerequisites = runtime_catalog.prerequisites(runtime)
        missing_required = prerequisites.get("missing_required", [])
        checks.append({
            "name": "runtime_prerequisites",
            "ok": bool(prerequisites.get("ok")),
            "detail": "ok" if prerequisites.get("ok") else f"missing required tools: {', '.join(str(row.get('name')) for row in missing_required if isinstance(row, dict))}",
            "suggested_actions": [f"aiplane runtimes prerequisites {runtime}"],
        })
        for port in _host_ports_for_runtime(runtime):
            available = _port_available(port)
            checks.append({
                "name": f"port_available:{port}",
                "ok": available,
                "warning": not available,
                "detail": "available" if available else f"localhost:{port} is already accepting connections; confirm this is the intended runtime",
            })
        endpoint_policy = str(stack.get("endpoint_policy") or "private")
        endpoint_text = str(endpoint or "")
        if endpoint_policy in {"public", "shared"}:
            checks.append({
                "name": "endpoint_auth_policy",
                "ok": False,
                "warning": True,
                "detail": "public/shared endpoints should normally have TLS and authentication before team use",
            })
        else:
            checks.append({"name": "endpoint_auth_policy", "ok": True, "detail": endpoint_policy})
        if runtime in {"vllm", "tgi", "transformers"} and not (os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE")):
            checks.append({
                "name": "model_cache_path",
                "ok": False,
                "warning": True,
                "detail": "HF_HOME/HUGGINGFACE_HUB_CACHE is not set; large model downloads will use the runtime default cache",
            })
        else:
            checks.append({"name": "model_cache_path", "ok": True, "detail": "configured or not required"})
        return {
            "runtime": runtime,
            "model": model,
            "endpoint": endpoint_text,
            "ok": all(bool(check.get("ok")) for check in checks if not check.get("warning")),
            "checks": checks,
        }

    def _export_metadata(self, name: str, stack: dict[str, Any], endpoint: str) -> dict[str, Any]:
        machine_name = str(stack.get("machine") or "")
        machine = MachineManager(self.profile).show(machine_name)["machine"]
        env = EnvironmentManager(self.profile).show()
        docker_resources = {}
        resource_controls = self.config.get("resource_controls", {}) if isinstance(self.config, dict) else {}
        if isinstance(resource_controls, dict):
            docker_resources = resource_controls.get("docker", {}) if isinstance(resource_controls.get("docker", {}), dict) else {}
        return {
            "name": name,
            "profile": self.profile.name,
            "orchestrator": stack.get("orchestrator"),
            "runtime": stack.get("runtime"),
            "model": stack.get("model"),
            "machine": machine_name,
            "endpoint": endpoint,
            "access": stack.get("access"),
            "endpoint_policy": stack.get("endpoint_policy"),
            "limits": stack.get("limits", {}),
            "tools": stack.get("tools", {}),
            "environment": {"active": env.get("active"), "config": env.get("modes", {}).get(str(env.get("active")), {})},
            "machine_summary": {
                "placement": machine.get("placement"),
                "substrate": machine.get("substrate"),
                "cpu": machine.get("cpu"),
                "memory": machine.get("memory"),
                "gpu": machine.get("gpu"),
                "accelerator_apis": machine.get("accelerator_apis", []),
            },
            "docker_resources": docker_resources,
        }

    def _lifecycle(self, name: str, action: str, dry_run: bool = False) -> dict[str, Any]:
        stack = self._stack(name)
        runtime = str(stack.get("runtime") or "")
        model = str(stack.get("model") or "")
        orchestrator = str(stack.get("orchestrator") or "")
        commands = self._lifecycle_commands(name, action, runtime, model, orchestrator)
        executable, reason = self._lifecycle_executable(stack)
        if dry_run or not executable:
            return {
                "name": name,
                "action": action,
                "dry_run": dry_run,
                "status": "planned" if dry_run else "planned_not_executed",
                "reason": None if executable else reason,
                "commands": commands,
            }
        results = []
        failed_step = None
        for item in commands:
            completed = subprocess.run(item["command"], cwd=item.get("cwd") or self.profile.workspace, text=True, capture_output=True, check=False)
            row = {"name": item["name"], "command": item["command"], "returncode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}
            results.append(row)
            if completed.returncode != 0:
                failed_step = row
                break
        runtime_status_after = RuntimeCatalog(self.profile).runtime_available(runtime)
        outcome = "completed" if failed_step is None and len(results) == len(commands) else "failed"
        return {
            "name": name,
            "action": action,
            "dry_run": False,
            "status": "executed",
            "outcome": outcome,
            "steps_total": len(commands),
            "steps_executed": len(results),
            "failed_step": failed_step,
            "runtime_status_after": runtime_status_after,
            "results": results,
            "notes": ["Same-host lifecycle execution ran local helper commands directly; runtime_status_after is a best-effort post-action readiness snapshot."],
        }

    def _lifecycle_commands(self, stack_name: str, action: str, runtime: str, model: str, orchestrator: str) -> list[dict[str, Any]]:
        if action == "prepare":
            commands = [
                self._runtime_helper_command("install runtime", runtime, "install", model),
                self._runtime_helper_command("pull model", runtime, "pull", model),
            ]
            if orchestrator:
                packages = OrchestratorCatalog(self.profile).show(orchestrator).get("packages", [])
                if packages:
                    plan = EnvironmentManager(self.profile).plan(["python", "-m", "pip", "install", *[str(package) for package in packages]])
                    commands.append({"name": "install orchestrator packages", "command": plan.command, "cwd": str(plan.cwd), "environment_mode": plan.mode})
            return commands
        if action in {"start", "stop", "restart"}:
            return [self._runtime_helper_command(f"{action} runtime", runtime, action, model)]
        raise ValueError(f"unknown stack lifecycle action: {action}")

    def _runtime_helper_command(self, name: str, runtime: str, action: str, model: str) -> dict[str, Any]:
        helper = project_root() / "scripts" / "provider_helper.sh"
        return {
            "name": name,
            "command": [str(helper), "--provider", runtime, "--action", action, "--profile", self.profile.name, "--model", model],
            "cwd": str(project_root()),
        }

    def _lifecycle_executable(self, stack: dict[str, Any]) -> tuple[bool, str | None]:
        access = str(stack.get("access") or "")
        machine_name = str(stack.get("machine") or "")
        try:
            machine = MachineManager(self.profile).show(machine_name)["machine"]
        except Exception as exc:  # noqa: BLE001 - report as lifecycle planning reason.
            return False, f"machine lookup failed: {exc}"
        placement = str(machine.get("placement") or "") if isinstance(machine, dict) else ""
        if access in {"same_host", "local"} or placement == "same_host":
            return True, None
        return False, "automatic stack lifecycle execution is currently limited to same-host/local stacks; use --dry-run output for remote/SSH/Azure/AKS targets"

    def deploy(self, name: str, yes: bool = False) -> dict[str, Any]:
        if not yes:
            raise PermissionError("stack deploy is mutating; run stacks plan and stacks doctor first")
        plan = self.plan(name)
        access = str(plan.get("access") or "")
        machine = plan.get("machine_config", {})
        placement = str(machine.get("placement") or "") if isinstance(machine, dict) else ""
        if access not in {"same_host", "local"} and placement != "same_host":
            return {
                "name": name,
                "status": "planned_not_executed",
                "reason": "automatic stack execution is currently limited to same-host/local stacks; use the rendered plan for SSH/Azure targets",
                "next_manual_steps": plan["steps"],
            }
        results = []
        for step in plan["steps"]:
            command = step.get("command") if isinstance(step, dict) else None
            if not command or not step.get("mutates"):
                continue
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            results.append({
                "name": step.get("name"),
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            })
            if completed.returncode != 0:
                break
        return {"name": name, "status": "executed_same_host_steps", "results": results}

    def _stack(self, name: str) -> dict[str, Any]:
        stack = self._stacks().get(name)
        if not isinstance(stack, dict):
            raise ValueError(f"unknown stack: {name}")
        return stack

    def _stacks(self) -> dict[str, Any]:
        stacks = self.config.get("stacks", {})
        return stacks if isinstance(stacks, dict) else {}

    def _write_config(self) -> None:
        path = self.profile.root / "hardware.yaml"
        path.write_text(dump_yaml(self.config), encoding="utf-8")


def _merge_bundle_content(artifact: str, runtime_plan: dict[str, Any], orchestrator_plan: dict[str, Any] | None, metadata: dict[str, Any]) -> str:
    header = _artifact_header(metadata)
    if artifact == "dockerfile":
        runtime_file = str(runtime_plan["files"]["Dockerfile"])
        env_lines = _docker_env_lines(metadata)
        if orchestrator_plan:
            orch_packages = " ".join(str(package) for package in orchestrator_plan.get("packages", []))
            extra = f"\n# Orchestrator packages\nRUN python -m pip install {orch_packages}\n" if orch_packages else "\n# Orchestrator uses project-specific install instructions.\n"
        else:
            extra = ""
        return header + runtime_file.rstrip() + "\n" + env_lines + extra
    runtime_file = str(runtime_plan["files"]["environment.yaml"])
    packages = [str(package) for package in orchestrator_plan.get("packages", [])] if orchestrator_plan else []
    extra = ""
    if packages:
        extra = "\n# Orchestrator pip packages to add if not already present:\n" + "".join(f"#   - {package}\n" for package in packages)
    return header + runtime_file.rstrip() + extra


def _compose_yaml(name: str, runtime: str, model: str, endpoint: str, metadata: dict[str, Any]) -> str:
    docker = metadata.get("docker_resources", {}) if isinstance(metadata.get("docker_resources"), dict) else {}
    env = {
        "AIPLANE_STACK": name,
        "AIPLANE_PROFILE": str(metadata.get("profile") or ""),
        "AIPLANE_ORCHESTRATOR": str(metadata.get("orchestrator") or ""),
        "AIPLANE_RUNTIME": runtime,
        "AIPLANE_MODEL": model,
        "AIPLANE_ENDPOINT": endpoint,
        "AIPLANE_LIMITS_JSON": _compact_json(metadata.get("limits", {})),
        "AIPLANE_TOOLS_JSON": _compact_json(metadata.get("tools", {})),
    }
    lines = [
        "# Generated by aiplane stacks export compose.",
        "# Review before use; stack limits/tool policies are pass-through metadata.",
        "services:",
        f"  {name}:",
        "    image: aiplane-stack:latest",
        "    working_dir: /workspace",
        "    volumes:",
        "      - .:/workspace",
        "    environment:",
    ]
    lines.extend(f"      {key}: {value}" for key, value in env.items())
    ports = _ports_for_runtime(runtime)
    if ports:
        lines.append("    ports:")
        lines.extend(f'      - "{port}"' for port in ports)
    if docker.get("gpus") not in (None, "", "none", "null"):
        lines.append(f"    gpus: {docker.get('gpus')}")
    deploy_lines = _compose_deploy_lines(docker)
    if deploy_lines:
        lines.extend(deploy_lines)
    return "\n".join(lines) + "\n"


def _artifact_header(metadata: dict[str, Any]) -> str:
    lines = [
        "# Generated by aiplane stack export.",
        "# Review before building or applying.",
        "# Stack limits and tool policies are pass-through metadata; enforcement belongs to the runtime/orchestrator.",
        f"# stack: {metadata.get('name')}",
        f"# profile: {metadata.get('profile')}",
        f"# orchestrator: {metadata.get('orchestrator')}",
        f"# runtime: {metadata.get('runtime')}",
        f"# model: {metadata.get('model')}",
        f"# machine: {metadata.get('machine')}",
        f"# endpoint: {metadata.get('endpoint')}",
    ]
    if metadata.get("limits"):
        lines.append(f"# limits: {_compact_json(metadata.get('limits'))}")
    if metadata.get("tools"):
        lines.append(f"# tools: {_compact_json(metadata.get('tools'))}")
    return "\n".join(lines) + "\n"


def _docker_env_lines(metadata: dict[str, Any]) -> str:
    pairs = {
        "AIPLANE_STACK": metadata.get("name"),
        "AIPLANE_PROFILE": metadata.get("profile"),
        "AIPLANE_ORCHESTRATOR": metadata.get("orchestrator") or "",
        "AIPLANE_RUNTIME": metadata.get("runtime"),
        "AIPLANE_MODEL": metadata.get("model"),
        "AIPLANE_ENDPOINT": metadata.get("endpoint"),
        "AIPLANE_LIMITS_JSON": _compact_json(metadata.get("limits", {})),
        "AIPLANE_TOOLS_JSON": _compact_json(metadata.get("tools", {})),
    }
    return "\n".join(f"ENV {key}='{value}'" for key, value in pairs.items()) + "\n"


def _compose_deploy_lines(docker: dict[str, Any]) -> list[str]:
    limits: list[str] = []
    cpus = docker.get("cpus")
    memory = docker.get("memory")
    if cpus not in (None, "", "null"):
        limits.append(f"          cpus: '{cpus}'")
    if memory not in (None, "", "null"):
        limits.append(f"          memory: {memory}")
    if not limits:
        return []
    return ["    deploy:", "      resources:", "        limits:", *limits]


def _ports_for_runtime(runtime: str) -> list[str]:
    ports = {
        "ollama": ["11434:11434"],
        "vllm": ["8000:8000"],
        "llamacpp": ["8080:8080"],
        "tgi": ["8081:80"],
        "localai": ["8082:8080"],
    }
    return ports.get(runtime, [])


def _host_ports_for_runtime(runtime: str) -> list[int]:
    ports = []
    for mapping in _ports_for_runtime(runtime):
        raw = str(mapping).split(":", 1)[0]
        try:
            ports.append(int(raw))
        except ValueError:
            continue
    return ports


def _port_available(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return False
    except OSError:
        return True


def _compact_json(value: object) -> str:
    import json

    return json.dumps(value if isinstance(value, dict) else {}, separators=(",", ":"))


def _default_endpoint(runtime: str) -> str:
    if runtime == "ollama":
        return "http://localhost:11434/v1"
    if runtime == "vllm":
        return "http://localhost:8000/v1"
    if runtime == "llamacpp":
        return "http://localhost:8080/v1"
    if runtime == "tgi":
        return "http://localhost:8081/v1"
    if runtime == "localai":
        return "http://localhost:8082/v1"
    return "http://localhost:8000/v1"
