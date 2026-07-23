from __future__ import annotations

import os
import socket
from typing import Any

from .boundaries import CommandRunner, SubprocessCommandRunner
from .agent_frameworks import render_framework_starter
from .persistence import atomic_write_text
from .config import dump_yaml, provider_helper_path
from .docker_model_runner import DockerModelRunner
from .env import EnvironmentManager
from .integrations import IntegrationManager
from .machines import MachineManager
from .model_catalog import ModelCatalog
from .models import Profile
from .orchestrators import OrchestratorCatalog
from .runtime_catalog import RuntimeCatalog
from .stack_lifecycle import StackLifecycle
from .stack_roles import StackRolePlanner
from .runtime_definitions import PROVIDER_ENDPOINT_DEFAULTS
from .remote import RemoteManager


FRAMEWORK_EXPORT_ARTIFACTS = {
    "langgraph": "langgraph",
    "crewai": "crewai",
    "autogen": "autogen",
    "semantic-kernel": "semantic_kernel",
    "llamaindex-workflows": "llamaindex_workflows",
    "openhands": "openhands",
}


class StackManager:
    def __init__(self, profile: Profile, command_runner: CommandRunner | None = None):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.config = profile.hardware or {}

    def list(self) -> list[dict[str, Any]]:
        rows = []
        for name, stack in self._stacks().items():
            if isinstance(stack, dict):
                rows.append(
                    {
                        "name": name,
                        "orchestrator": stack.get("orchestrator"),
                        "runtime": stack.get("runtime"),
                        "runtime_substrate": stack.get("runtime_substrate"),
                        "model": stack.get("model"),
                        "machine": stack.get("machine"),
                        "target": stack.get("target"),
                        "access": stack.get("access"),
                        "endpoint_policy": stack.get("endpoint_policy"),
                        "endpoint_auth": stack.get("endpoint_auth", {}),
                        "limits": stack.get("limits", {}),
                        "tools": stack.get("tools", {}),
                        "roles": stack.get("roles", {}),
                        "approval_mode": stack.get("approval_mode"),
                        "audit_label": stack.get("audit_label"),
                    }
                )
        return sorted(rows, key=lambda row: str(row["name"]))

    def show(self, name: str) -> dict[str, Any]:
        return {"name": name, "stack": self._stack(name)}

    def create(
        self,
        name: str,
        model: str,
        runtime: str,
        machine: str,
        runtime_substrate: str | None = None,
        target: str | None = None,
        access: str = "ssh_tunnel",
        endpoint_policy: str = "private",
        endpoint: str | None = None,
        orchestrator: str | None = None,
        roles: dict[str, str] | None = None,
        endpoint_auth: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        return self.setup(
            name,
            orchestrator=orchestrator,
            runtime=runtime,
            runtime_substrate=runtime_substrate,
            model=model,
            machine=machine,
            target=target,
            access=access,
            endpoint_policy=endpoint_policy,
            endpoint=endpoint,
            roles=roles,
            endpoint_auth=endpoint_auth,
            dry_run=False,
            yes=True,
        )

    def setup(
        self,
        name: str,
        orchestrator: str | None,
        runtime: str,
        model: str,
        machine: str,
        runtime_substrate: str | None = None,
        target: str | None = None,
        access: str = "ssh_tunnel",
        endpoint_policy: str = "private",
        endpoint: str | None = None,
        limits: dict[str, object] | None = None,
        tools: dict[str, object] | None = None,
        roles: dict[str, str] | None = None,
        endpoint_auth: dict[str, object] | None = None,
        approval_mode: str | None = None,
        audit_label: str | None = None,
        dry_run: bool = False,
        yes: bool | None = None,
    ) -> dict[str, Any]:
        if not name or "/" in name or "\\" in name:
            raise ValueError("stack name must be a simple name")
        if orchestrator:
            OrchestratorCatalog(self.profile).show(orchestrator)
        catalog = ModelCatalog(self.profile)
        catalog.get(model)
        machines = {row["name"] for row in MachineManager(self.profile).list()}
        if machine not in machines:
            raise ValueError(f"unknown machine: {machine}")
        runtime_catalog = RuntimeCatalog(self.profile)
        if runtime not in {row["name"] for row in runtime_catalog.list(include_gui=True)}:
            raise ValueError(f"unknown runtime: {runtime}")
        resolved_substrate = runtime_catalog.helper_substrate(runtime, runtime_substrate)
        normalized_roles = self._normalize_roles(
            roles or {},
            primary_model=model,
            primary_runtime=runtime,
            endpoint=endpoint,
            limits=limits or {},
            tools=tools or {},
            approval_mode=approval_mode,
            audit_label=audit_label or name,
        )
        stack = {
            "orchestrator": orchestrator,
            "runtime": runtime,
            "runtime_substrate": resolved_substrate,
            "model": model,
            "machine": machine,
            "access": access,
            "endpoint_policy": endpoint_policy,
            "limits": limits or {},
            "tools": tools or {},
        }
        if target:
            stack["target"] = target
        normalized_endpoint_auth = _normalize_endpoint_auth(endpoint_auth or {})
        if normalized_roles:
            stack["roles"] = normalized_roles
        if normalized_endpoint_auth:
            stack["endpoint_auth"] = normalized_endpoint_auth
        if approval_mode:
            stack["approval_mode"] = approval_mode
        if audit_label:
            stack["audit_label"] = audit_label
        if endpoint:
            stack["endpoint"] = endpoint
        payload = {
            "name": name,
            "dry_run": dry_run,
            "path": str(self.profile.root / "hardware.yaml"),
            "stack": stack,
            "notes": [
                "A stack keeps one primary runtime/model/machine tuple and can include optional orchestrator role metadata for framework exports."
            ],
        }
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
        runtime_substrate = runtime_catalog.helper_substrate(runtime, str(stack.get("runtime_substrate") or "") or None)
        runtime_status = runtime_catalog.runtime_available(runtime)
        endpoint = stack.get("endpoint") or _default_endpoint(runtime)
        preflight = self._preflight(stack, runtime, model_name, endpoint, runtime_catalog)
        runtime_evidence: dict[str, Any]
        try:
            runtime_evidence = runtime_catalog.evidence_bundle(runtime, model_name)
        except ValueError as exc:
            runtime_evidence = {"contract_version": "1.0", "available": False, "reason": str(exc)}
        steps = [
            {
                "name": "check machine fit",
                "action": "aiplane machines recommend",
                "mutates": False,
            },
            {
                "name": "install or update runtime",
                "command": [
                    str(provider_helper_path()),
                    "--provider",
                    runtime,
                    "--action",
                    "install",
                    "--profile",
                    self.profile.name,
                    "--model",
                    model_name,
                    "--substrate",
                    runtime_substrate,
                ],
                "mutates": True,
            },
            {
                "name": "pull model",
                "command": [
                    str(provider_helper_path()),
                    "--provider",
                    runtime,
                    "--action",
                    "pull",
                    "--profile",
                    self.profile.name,
                    "--model",
                    model_name,
                    "--substrate",
                    runtime_substrate,
                ],
                "mutates": True,
            },
            {
                "name": "start runtime",
                "command": [
                    str(provider_helper_path()),
                    "--provider",
                    runtime,
                    "--action",
                    "start",
                    "--profile",
                    self.profile.name,
                    "--model",
                    model_name,
                    "--substrate",
                    runtime_substrate,
                ],
                "mutates": True,
            },
            {
                "name": "export IDE config",
                "command": ["aiplane", "stacks", "export", "continue", name],
                "mutates": False,
            },
        ]
        if runtime == "docker_model_runner":
            native_model = str(model.get("model") or "")
            for step in steps:
                if step.get("name") == "install or update runtime":
                    step["command"] = DockerModelRunner.command("install", model=native_model)
                elif step.get("name") == "pull model":
                    step["command"] = DockerModelRunner.command("pull", model=native_model)
                elif step.get("name") == "start runtime":
                    step["command"] = DockerModelRunner.command("start", model=native_model)
                if step.get("command") and step.get("mutates"):
                    step["adapter"] = "docker_model_runner"

        if orchestrator:
            steps.insert(
                1,
                {
                    "name": "prepare orchestrator environment",
                    "command": ["aiplane", "stacks", "prepare", name, "--yes"],
                    "mutates": True,
                },
            )
        if stack.get("access") == "ssh_tunnel":
            steps.insert(
                4 if orchestrator else 3,
                {
                    "name": "prepare SSH tunnel",
                    "command": [
                        "aiplane",
                        "remote",
                        "tunnel",
                        "plan",
                        "--target",
                        str(stack.get("target") or machine_name),
                    ],
                    "mutates": False,
                },
            )
        return {
            "name": name,
            "orchestrator": orchestrator or None,
            "runtime": runtime,
            "runtime_substrate": runtime_substrate,
            "model": model_name,
            "machine": machine_name,
            "access": stack.get("access"),
            "endpoint_policy": stack.get("endpoint_policy"),
            "endpoint": endpoint,
            "fit": MachineManager(self.profile).recommend(model=model_name, runtime=runtime, limit=None),
            "model_config": model,
            "machine_config": machine,
            "runtime_status": runtime_status,
            "runtime_evidence": runtime_evidence,
            "orchestrator_status": (OrchestratorCatalog(self.profile).doctor(orchestrator) if orchestrator else None),
            "preflight": preflight,
            "endpoint_security": self.endpoint_plan(name),
            "limits": stack.get("limits", {}),
            "tools": stack.get("tools", {}),
            "roles": self._role_plan(stack, endpoint),
            "approval_mode": stack.get("approval_mode"),
            "audit_label": stack.get("audit_label"),
            "steps": steps,
            "notes": [
                "Stack lifecycle execution is same-host/local first; SSH/Azure/AKS stacks currently return plans until remote execution and audit controls are hardened."
            ],
        }

    def doctor(self, name: str) -> dict[str, Any]:
        plan = self.plan(name)
        machine_rows = [row for row in plan["fit"]["machines"] if row["name"] == plan["machine"]]
        runtime_evidence = plan.get("runtime_evidence", {})
        checks = [
            {
                "name": "machine_exists",
                "ok": bool(machine_rows),
                "detail": plan["machine"],
            },
            {
                "name": "machine_fit",
                "ok": bool(machine_rows and machine_rows[0]["level"] != "not_recommended"),
                "detail": (machine_rows[0]["reason"] if machine_rows else "machine missing"),
            },
            {
                "name": "runtime_known",
                "ok": bool(plan["runtime_status"].get("name")),
                "detail": plan["runtime_status"].get("reason"),
            },
            {
                "name": "runtime_evidence_rendered",
                "ok": bool(runtime_evidence.get("artifact_lock") and runtime_evidence.get("launch_manifest")),
                "detail": runtime_evidence.get("reason") or "artifact lock and launch manifest rendered",
            },
            {
                "name": "runtime_available_now",
                "ok": bool(plan["runtime_status"].get("available")),
                "detail": plan["runtime_status"].get("reason"),
            },
        ]
        for check in plan.get("preflight", {}).get("checks", []):
            if isinstance(check, dict):
                checks.append(check)
        for check in plan.get("endpoint_security", {}).get("checks", []):
            if isinstance(check, dict):
                checks.append(check)
        checks.extend(self._role_checks(plan.get("roles", {})))
        if plan.get("orchestrator"):
            orch = plan.get("orchestrator_status") or {}
            checks.append(
                {
                    "name": "orchestrator_known",
                    "ok": bool(orch.get("name")),
                    "detail": plan.get("orchestrator"),
                }
            )
        return {
            "name": name,
            "checks": checks,
            "plan_summary": {
                "orchestrator": plan.get("orchestrator"),
                "runtime": plan["runtime"],
                "model": plan["model"],
                "machine": plan["machine"],
                "endpoint": plan["endpoint"],
            },
        }

    def export(self, artifact: str, name: str) -> dict[str, Any]:
        stack = self._stack(name)
        model = str(stack.get("model") or "")
        runtime = str(stack.get("runtime") or "")
        orchestrator = str(stack.get("orchestrator") or "")
        endpoint = str(stack.get("endpoint") or _default_endpoint(runtime))
        if artifact in {"continue", "openai-compatible"}:
            exported = IntegrationManager(self.profile).export(artifact, model, endpoint=endpoint)
            return {
                "name": name,
                "artifact": artifact,
                "tool": exported.tool,
                "model": exported.model,
                "provider": exported.provider,
                "endpoint": exported.endpoint,
                "content": exported.content,
                "notes": exported.notes,
            }
        if artifact in {"dockerfile", "conda-yaml"}:
            mode = "docker" if artifact == "dockerfile" else "conda"
            runtime_plan = RuntimeCatalog(self.profile).bundle_plan(runtime, model_name=model, mode=mode)
            orchestrator_plan = (
                OrchestratorCatalog(self.profile).bundle_plan(orchestrator, mode=mode) if orchestrator else None
            )
            metadata = self._export_metadata(name, stack, endpoint)
            content = _merge_bundle_content(artifact, runtime_plan, orchestrator_plan, metadata)
            return {
                "name": name,
                "artifact": artifact,
                "orchestrator": orchestrator or None,
                "runtime": runtime,
                "model": model,
                "endpoint": endpoint,
                "metadata": metadata,
                "content": content,
                "notes": [
                    "Exported artifact is a starter packaging file. Review before building or applying it.",
                    "Stack limits and tool policies are pass-through metadata; enforcement belongs to the runtime/orchestrator.",
                ],
            }
        if artifact == "compose":
            metadata = self._export_metadata(name, stack, endpoint)
            return {
                "name": name,
                "artifact": artifact,
                "orchestrator": orchestrator or None,
                "runtime": runtime,
                "model": model,
                "endpoint": endpoint,
                "metadata": metadata,
                "content": _compose_yaml(name, runtime, model, endpoint, metadata),
                "notes": [
                    "Compose export is a starter file for local/VM use and may need runtime-specific tuning.",
                    "Stack limits and tool policies are pass-through metadata; enforcement belongs to the runtime/orchestrator.",
                ],
            }
        if artifact in FRAMEWORK_EXPORT_ARTIFACTS:
            metadata = self._export_metadata(name, stack, endpoint)
            target = FRAMEWORK_EXPORT_ARTIFACTS[artifact]
            return {
                "name": name,
                "artifact": artifact,
                "framework": target,
                "orchestrator": orchestrator or None,
                "runtime": runtime,
                "model": model,
                "endpoint": endpoint,
                "metadata": metadata,
                "content": _framework_starter_config(target, metadata),
                "notes": [
                    "Framework export is starter metadata for review; it does not install packages or run agents.",
                    "Role bindings, limits, tools, approvals, and audit labels are pass-through config for the chosen framework adapter.",
                ],
            }
        raise ValueError(f"unknown stack export artifact: {artifact}")

    def prepare(self, name: str, dry_run: bool = False, yes: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "prepare", dry_run=dry_run, yes=yes)

    def start(self, name: str, dry_run: bool = False, yes: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "start", dry_run=dry_run, yes=yes)

    def stop(self, name: str, dry_run: bool = False, yes: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "stop", dry_run=dry_run, yes=yes)

    def restart(self, name: str, dry_run: bool = False, yes: bool = False) -> dict[str, Any]:
        return self._lifecycle(name, "restart", dry_run=dry_run, yes=yes)

    def status(self, name: str) -> dict[str, Any]:
        stack = self._stack(name)
        runtime = str(stack.get("runtime") or "")
        orchestrator = str(stack.get("orchestrator") or "")
        return {
            "name": name,
            "orchestrator": orchestrator or None,
            "runtime": runtime,
            "runtime_substrate": RuntimeCatalog(self.profile).helper_substrate(
                runtime, str(stack.get("runtime_substrate") or "") or None
            ),
            "model": stack.get("model"),
            "runtime_evidence": RuntimeCatalog(self.profile).evidence_bundle(runtime, str(stack.get("model") or "")),
            "machine": stack.get("machine"),
            "limits": stack.get("limits", {}),
            "tools": stack.get("tools", {}),
            "roles": self._role_plan(stack, stack.get("endpoint") or _default_endpoint(runtime)),
            "endpoint_security": self.endpoint_plan(name),
            "approval_mode": stack.get("approval_mode"),
            "audit_label": stack.get("audit_label"),
            "runtime_status": RuntimeCatalog(self.profile).runtime_available(runtime),
            "orchestrator_status": (OrchestratorCatalog(self.profile).doctor(orchestrator) if orchestrator else None),
        }

    def endpoint_plan(self, name: str) -> dict[str, Any]:
        stack = self._stack(name)
        runtime = str(stack.get("runtime") or "")
        endpoint = str(stack.get("endpoint") or _default_endpoint(runtime))
        return _endpoint_security_plan(name, stack, endpoint)

    def _preflight(
        self,
        stack: dict[str, Any],
        runtime: str,
        model: str,
        endpoint: object,
        runtime_catalog: RuntimeCatalog,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        prerequisites = runtime_catalog.prerequisites(runtime)
        missing_required = prerequisites.get("missing_required", [])
        checks.append(
            {
                "name": "runtime_prerequisites",
                "ok": bool(prerequisites.get("ok")),
                "detail": (
                    "ok"
                    if prerequisites.get("ok")
                    else f"missing required tools: {', '.join(str(row.get('name')) for row in missing_required if isinstance(row, dict))}"
                ),
                "suggested_actions": [f"aiplane runtimes prerequisites {runtime}"],
            }
        )
        for port in _host_ports_for_runtime(runtime):
            available = _port_available(port)
            checks.append(
                {
                    "name": f"port_available:{port}",
                    "ok": available,
                    "warning": not available,
                    "detail": (
                        "available"
                        if available
                        else f"localhost:{port} is already accepting connections; confirm this is the intended runtime"
                    ),
                }
            )
        endpoint_text = str(endpoint or "")
        endpoint_security = _endpoint_security_plan("preflight", stack, endpoint_text)
        gateway_ready = bool(endpoint_security.get("ready_for_policy"))
        checks.append(
            {
                "name": "endpoint_auth_policy",
                "ok": gateway_ready,
                "warning": not gateway_ready,
                "detail": endpoint_security.get("summary"),
                "suggested_actions": endpoint_security.get("next_steps", []),
            }
        )
        access = str(stack.get("access") or "")
        if access == "ssh_tunnel":
            explicit_target = False
            tunnel_target = str(stack.get("target") or "").strip()
            if tunnel_target:
                explicit_target = True
            else:
                tunnel_target = str(stack.get("machine") or "").strip()

            if not tunnel_target:
                checks.append(
                    {
                        "name": "remote_tunnel_target",
                        "ok": False,
                        "detail": (
                            "stack access is ssh_tunnel but neither a remote target nor a machine is configured"
                        ),
                    }
                )
            else:
                try:
                    tunnel_plan = RemoteManager(self.profile).tunnel_plan(tunnel_target)
                    detail = f"tunnel target {tunnel_target} is configured"
                    if not explicit_target:
                        detail = f"{detail}; stack has no explicit target and is using machine name as target fallback"
                    checks.append(
                        {
                            "name": "remote_tunnel_target",
                            "ok": True,
                            "detail": detail,
                            "warning": (not bool(tunnel_plan.get("tool_available")) or not explicit_target),
                        }
                    )
                except ValueError as exc:
                    detail = str(exc)
                    if not explicit_target:
                        detail = f"{detail} (machine fallback was used for stack target)"
                    checks.append(
                        {
                            "name": "remote_tunnel_target",
                            "ok": False,
                            "detail": detail,
                        }
                    )
        if runtime in {"vllm", "tgi", "transformers"} and not (
            os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE")
        ):
            checks.append(
                {
                    "name": "model_cache_path",
                    "ok": False,
                    "warning": True,
                    "detail": "HF_HOME/HUGGINGFACE_HUB_CACHE is not set; large model downloads will use the runtime default cache",
                }
            )
        else:
            checks.append(
                {
                    "name": "model_cache_path",
                    "ok": True,
                    "detail": "configured or not required",
                }
            )
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
            docker_resources = (
                resource_controls.get("docker", {}) if isinstance(resource_controls.get("docker", {}), dict) else {}
            )
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
            "endpoint_auth": stack.get("endpoint_auth", {}),
            "endpoint_security": _endpoint_security_plan(name, stack, endpoint),
            "limits": stack.get("limits", {}),
            "tools": stack.get("tools", {}),
            "roles": self._role_plan(stack, endpoint),
            "approval_mode": stack.get("approval_mode"),
            "audit_label": stack.get("audit_label"),
            "environment": {
                "active": env.get("active"),
                "config": env.get("modes", {}).get(str(env.get("active")), {}),
            },
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

    def _role_planner(self):
        return StackRolePlanner(self.profile)

    def _normalize_roles(
        self, roles, primary_model, primary_runtime, endpoint, limits, tools, approval_mode, audit_label
    ):
        return self._role_planner()._normalize_roles(
            roles, primary_model, primary_runtime, endpoint, limits, tools, approval_mode, audit_label
        )

    def _role_plan(self, stack: dict[str, Any], endpoint: object) -> dict[str, Any]:
        return self._role_planner()._role_plan(stack, endpoint)

    def _role_checks(self, roles: object) -> list[dict[str, Any]]:
        return self._role_planner()._role_checks(roles)

    def _lifecycle(self, name: str, action: str, dry_run: bool = False, yes: bool = False) -> dict[str, Any]:
        return StackLifecycle(self)._lifecycle(name, action, dry_run, yes)

    def deploy(self, name: str, yes: bool = False) -> dict[str, Any]:
        return StackLifecycle(self).deploy(name, yes)

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
        atomic_write_text(path, dump_yaml(self.config))


def _normalize_endpoint_auth(endpoint_auth: dict[str, object]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    method = str(endpoint_auth.get("method") or "").strip()
    if method:
        if method not in {
            "none",
            "bearer",
            "api_key",
            "basic",
            "oauth2",
            "oidc",
            "mtls",
            "gateway",
        }:
            raise ValueError(
                "endpoint auth method must be none, bearer, api_key, basic, oauth2, oidc, mtls, or gateway"
            )
        normalized["method"] = method
    tls = str(endpoint_auth.get("tls") or "").strip()
    if tls:
        if tls not in {"required", "terminated", "not_configured", "not_required"}:
            raise ValueError("endpoint TLS mode must be required, terminated, not_configured, or not_required")
        normalized["tls"] = tls
    api_key_env = str(endpoint_auth.get("api_key_env") or "").strip()
    if api_key_env:
        normalized["api_key_env"] = api_key_env
    gateway = str(endpoint_auth.get("gateway") or "").strip()
    if gateway:
        normalized["gateway"] = gateway
    return normalized


def _endpoint_security_plan(name: str, stack: dict[str, Any], endpoint: str) -> dict[str, Any]:
    policy = str(stack.get("endpoint_policy") or "private")
    access = str(stack.get("access") or "")
    auth = stack.get("endpoint_auth") if isinstance(stack.get("endpoint_auth"), dict) else {}
    auth_method = str(auth.get("method") or "none")
    tls_mode = str(auth.get("tls") or "not_configured")
    gateway = str(auth.get("gateway") or "")
    api_key_env = str(auth.get("api_key_env") or "")
    endpoint_text = str(endpoint or "")
    https_endpoint = endpoint_text.startswith("https://")
    local_endpoint = _is_local_endpoint(endpoint_text)
    shared_policy = policy in {"public", "shared", "gateway"} or access in {
        "lan_http",
        "gateway",
    }
    vpn_policy = policy == "vpn"
    tls_ok = True if not shared_policy else (https_endpoint or tls_mode in {"required", "terminated"})
    auth_ok = auth_method not in {"", "none"}
    if auth_method in {"bearer", "api_key"} and not api_key_env:
        auth_ok = False
    gateway_ok = bool(gateway) if shared_policy else True
    private_ok = bool(local_endpoint or policy in {"private", "vpn"}) if not shared_policy else True
    checks = [
        {
            "name": "endpoint_policy_known",
            "ok": policy in {"private", "vpn", "gateway", "public", "shared"},
            "detail": policy,
        },
        {
            "name": "endpoint_tls",
            "ok": tls_ok,
            "warning": not tls_ok,
            "detail": ("configured" if tls_ok else "shared/public endpoints should use HTTPS or TLS termination"),
        },
        {
            "name": "endpoint_auth",
            "ok": auth_ok or not shared_policy,
            "warning": shared_policy and not auth_ok,
            "detail": _endpoint_auth_detail(auth_method, api_key_env, shared_policy),
        },
        {
            "name": "endpoint_gateway",
            "ok": gateway_ok,
            "warning": shared_policy and not gateway_ok,
            "detail": gateway or ("gateway/reverse-proxy not configured" if shared_policy else "not required"),
        },
        {
            "name": "endpoint_private_binding",
            "ok": private_ok,
            "warning": not private_ok,
            "detail": (
                "local/private endpoint" if private_ok else "non-local endpoint should declare shared/gateway controls"
            ),
        },
    ]
    if vpn_policy:
        checks.append(
            {
                "name": "endpoint_network_boundary",
                "ok": True,
                "warning": True,
                "detail": "vpn policy declared; verify firewall/VPN rules outside aiplane",
            }
        )
    ready = all(
        bool(check.get("ok"))
        for check in checks
        if check["name"]
        in {
            "endpoint_policy_known",
            "endpoint_tls",
            "endpoint_auth",
            "endpoint_gateway",
            "endpoint_private_binding",
        }
    )
    return {
        "name": name,
        "endpoint": endpoint_text,
        "endpoint_policy": policy,
        "access": access,
        "shared_or_public": shared_policy,
        "ready_for_policy": ready,
        "auth": {"method": auth_method, "api_key_env": api_key_env or None},
        "tls": tls_mode,
        "gateway": gateway or None,
        "checks": checks,
        "next_steps": _endpoint_next_steps(shared_policy, auth_method, api_key_env, tls_ok, gateway_ok),
        "summary": (
            "endpoint controls look configured" if ready else "endpoint controls need review before shared/public use"
        ),
        "notes": [
            "This is a non-mutating endpoint plan; configure reverse proxy, gateway, TLS, auth, quotas, and audit in the chosen platform.",
            "Do not expose raw runtime ports to teams or the internet without these controls.",
        ],
    }


def _endpoint_auth_detail(auth_method: str, api_key_env: str, shared_policy: bool) -> str:
    if auth_method in {"", "none"}:
        return "not required for private endpoint" if not shared_policy else "shared/public endpoints need auth"
    if auth_method in {"bearer", "api_key"} and not api_key_env:
        return f"{auth_method} auth needs an api key env var name"
    return auth_method


def _endpoint_next_steps(
    shared_policy: bool,
    auth_method: str,
    api_key_env: str,
    tls_ok: bool,
    gateway_ok: bool,
) -> list[str]:
    steps = []
    if shared_policy and not gateway_ok:
        steps.append(
            "Put a reverse proxy or gateway such as Caddy, Nginx, Traefik, APIM, or Kubernetes Gateway in front of the runtime."
        )
    if not tls_ok:
        steps.append("Terminate TLS at the gateway or use an HTTPS endpoint.")
    if shared_policy and auth_method in {"", "none"}:
        steps.append("Choose bearer/api_key/oauth2/oidc/mtls auth before shared use.")
    if auth_method in {"bearer", "api_key"} and not api_key_env:
        steps.append("Set --endpoint-auth-env to the environment variable that will hold the gateway credential.")
    if shared_policy:
        steps.append("Add quota/rate-limit and audit/logging controls in the gateway platform.")
    return steps


def _is_local_endpoint(endpoint: str) -> bool:
    lowered = endpoint.lower()
    return any(host in lowered for host in ["localhost", "127.0.0.1", "0.0.0.0", "::1"])


def _framework_starter_config(framework: str, metadata: dict[str, Any]) -> str:
    return render_framework_starter(framework, metadata)


def _merge_bundle_content(
    artifact: str,
    runtime_plan: dict[str, Any],
    orchestrator_plan: dict[str, Any] | None,
    metadata: dict[str, Any],
) -> str:
    header = _artifact_header(metadata)
    if artifact == "dockerfile":
        runtime_file = str(runtime_plan["files"]["Dockerfile"])
        env_lines = _docker_env_lines(metadata)
        if orchestrator_plan:
            orch_packages = " ".join(str(package) for package in orchestrator_plan.get("packages", []))
            extra = (
                f"\n# Orchestrator packages\nRUN python -m pip install {orch_packages}\n"
                if orch_packages
                else "\n# Orchestrator uses project-specific install instructions.\n"
            )
        else:
            extra = ""
        return header + runtime_file.rstrip() + "\n" + env_lines + extra
    runtime_file = str(runtime_plan["files"]["environment.yaml"])
    packages = [str(package) for package in orchestrator_plan.get("packages", [])] if orchestrator_plan else []
    extra = ""
    if packages:
        extra = "\n# Orchestrator pip packages to add if not already present:\n" + "".join(
            f"#   - {package}\n" for package in packages
        )
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
    provider_default = PROVIDER_ENDPOINT_DEFAULTS.get(runtime, {})
    if provider_default.get("ownership") == "managed_service" and provider_default.get("endpoint"):
        return str(provider_default.get("endpoint"))
    if runtime == "ollama":
        return "http://localhost:11434/v1"
    if runtime == "docker_model_runner":
        return "http://localhost:12434/engines/v1"
    if runtime == "vllm":
        return "http://localhost:8000/v1"
    if runtime == "llamacpp":
        return "http://localhost:8080/v1"
    if runtime == "tgi":
        return "http://localhost:8081/v1"
    if runtime == "localai":
        return "http://localhost:8082/v1"
    return "http://localhost:8000/v1"
