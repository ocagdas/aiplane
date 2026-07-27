from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request

from .boundaries import HttpTransport, UrllibHttpTransport
from .config import agent_artifacts_root, dump_yaml
from .agent_frameworks import (
    FRAMEWORK_SPECS,
    framework_control_enforcement,
    framework_package_versions,
    framework_readiness,
    normalize_framework,
    render_framework_starter,
)
from .integrations import IntegrationManager
from .model_catalog import ModelCatalog
from .network_validation import validate_http_endpoint
from .stacks import StackManager
from .models import Profile
from .secrets import contains_secret


AGENT_FRAMEWORKS: dict[str, dict[str, Any]] = {
    "langgraph": {
        "description": "Small LangGraph-style stateful agent scaffold using an OpenAI-compatible chat endpoint.",
        "packages": ["langgraph", "langchain-openai"],
        "good_for": [
            "reviewable state machines",
            "bounded tool loops",
            "human checkpoints",
        ],
        "files": ["agent.py", "requirements.txt", ".env.example"],
    },
    "simple-openai": {
        "description": "Minimal Python agent loop using the OpenAI-compatible API directly.",
        "packages": ["openai"],
        "good_for": [
            "small CLI agents",
            "endpoint smoke tests",
            "framework-free prototypes",
        ],
        "files": ["agent.py", "requirements.txt", ".env.example"],
    },
}

for _framework_name, _framework_spec in FRAMEWORK_SPECS.items():
    AGENT_FRAMEWORKS.setdefault(
        _framework_name,
        {
            "description": f"Render-only {_framework_name} agent environment starter configuration.",
            "packages": list(_framework_spec["packages"]),
            "good_for": ["reviewed role binding", "endpoint configuration", "tool-policy handoff"],
            "files": [
                "endpoint-smoke.py",
                "endpoint-smoke-requirements.txt",
                "requirements.txt",
                ".env.example",
                "agent-environment.json",
                "agent-environment.yaml",
                "framework-config.yaml",
            ],
        },
    )


_AGENT_CONFIG_FILES = [
    "endpoint-smoke.py",
    "endpoint-smoke-requirements.txt",
    "requirements.txt",
    ".env.example",
    "README.md",
    "agent-environment.json",
    "agent-environment.yaml",
    "framework-config.yaml",
]
for _framework_spec in AGENT_FRAMEWORKS.values():
    _framework_spec["files"] = list(dict.fromkeys([*_framework_spec.get("files", []), *_AGENT_CONFIG_FILES]))


@dataclass(frozen=True)
class AgentSelection:
    name: str
    framework: str
    model_alias: str
    model: str
    provider: str
    runtime: str
    endpoint: str
    api_key_env: str | None


_MAX_JOB_FILE_BYTES = 1_048_576
_MAX_TASK_CHARS = 10_000
_CONTROL_ENFORCEMENT_REQUIRED_KEYS = (
    "framework",
    "enforcement_ready",
    "requires_runtime_enforcement",
    "controls",
    "summary",
)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_job_workspace(value: str) -> str:
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(part in {"", "..", ".git"} for part in candidate.parts):
        raise ValueError("job workspace must be a safe relative path inside the selected workspace")
    return str(candidate)


class AgentManager:
    def __init__(self, profile: Profile, http_transport: HttpTransport | None = None):
        self.profile = profile
        self.integrations = IntegrationManager(profile)
        self.http_transport = http_transport or UrllibHttpTransport()

    def templates(self) -> list[dict[str, Any]]:
        return [{"name": name, **spec} for name, spec in sorted(AGENT_FRAMEWORKS.items())]

    def doctor(
        self,
        name: str,
        *,
        stack: str | None = None,
        framework: str = "langgraph",
        model: str | None = None,
        runtime: str | None = None,
        provider: str | None = None,
        endpoint: str | None = None,
        api_key_env: str | None = None,
        probe_endpoint: bool = False,
        timeout_seconds: int = 5,
    ) -> dict[str, Any]:
        """Inspect framework packages and optionally probe endpoint model inventories.

        The optional probe is intentionally credential-free and only verifies the
        OpenAI-compatible ``GET /models`` surface; it never starts a workflow.
        """
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("agent endpoint probe timeout must be between 1 and 60 seconds")
        manifest = self.manifest(
            name,
            stack=stack,
            framework=framework,
            model=model,
            runtime=runtime,
            provider=provider,
            endpoint=endpoint,
            api_key_env=api_key_env,
        )
        selected_framework = str(manifest["orchestrator"])
        roles = manifest.get("roles") if isinstance(manifest.get("roles"), dict) else {}
        package_versions = framework_package_versions(selected_framework)
        package_ok = all(bool(row["installed"]) for row in package_versions)
        probes = {
            role_name: self._probe_endpoint_models(
                str(role.get("endpoint") or ""),
                str(role.get("model_id") or ""),
                timeout_seconds=timeout_seconds,
                enabled=probe_endpoint,
            )
            for role_name, role in sorted(roles.items())
            if isinstance(role, dict)
        }
        endpoint_ok = all(bool(probe.get("ok")) for probe in probes.values()) if probe_endpoint else True
        readiness = manifest["readiness"]
        checks = [
            {
                "name": "framework_configuration",
                "ok": bool(readiness.get("ready")),
                "detail": "rendered agent-environment readiness",
            },
            {
                "name": "framework_packages",
                "ok": package_ok,
                "detail": (
                    "all framework distributions are installed"
                    if package_ok
                    else "install missing framework distributions from requirements.txt"
                ),
            },
            {
                "name": "endpoint_models_probe",
                "ok": endpoint_ok,
                "skipped": not probe_endpoint,
                "detail": (
                    "credential-free GET /models probe passed for every role"
                    if probe_endpoint and endpoint_ok
                    else "credential-free endpoint probe was not requested; pass --probe-endpoint"
                    if not probe_endpoint
                    else "one or more endpoint probes did not verify the selected model"
                ),
            },
        ]
        return {
            "record_type": "agent_framework_doctor",
            "name": name,
            "profile": self.profile.name,
            "source_stack": stack,
            "framework": selected_framework,
            "mutates": False,
            "network_contacted": probe_endpoint,
            "credential_behavior": "never reads or transmits credentials",
            "ready": all(bool(check["ok"]) for check in checks if not check.get("skipped")),
            "checks": checks,
            "package_versions": package_versions,
            "endpoint_probes": probes,
            "execution_boundary": {
                "imports_frameworks": False,
                "starts_agents": False,
                "writes_credentials": False,
                "runs_model_prompts": False,
            },
            "notes": [
                "Package versions are observed from installed distribution metadata only; compatibility is not inferred from a version number.",
                "Endpoint probing is opt-in, unauthenticated, and limited to GET /models. Use provider-specific tests for authenticated endpoint validation.",
            ],
        }

    def _probe_endpoint_models(
        self,
        endpoint: str,
        model_id: str,
        *,
        timeout_seconds: int,
        enabled: bool,
    ) -> dict[str, Any]:
        if not enabled:
            return {
                "attempted": False,
                "network_contacted": False,
                "ok": None,
                "reason": "pass --probe-endpoint to send a credential-free GET /models request",
            }
        try:
            models_url = _models_probe_url(endpoint)
        except ValueError as exc:
            return {
                "attempted": False,
                "network_contacted": False,
                "ok": False,
                "reason": str(exc),
            }
        request = Request(models_url, headers={"Accept": "application/json", "User-Agent": "aiplane/0.1"})
        try:
            with self.http_transport.open(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return {
                "attempted": True,
                "network_contacted": True,
                "ok": False,
                "url": models_url,
                "http_status": exc.code,
                "reason": "endpoint rejected the anonymous models probe; use provider-specific authenticated validation",
            }
        except (URLError, TimeoutError, OSError, ConnectionError, json.JSONDecodeError):
            return {
                "attempted": True,
                "network_contacted": True,
                "ok": False,
                "url": models_url,
                "reason": "endpoint did not return an OpenAI-compatible models response",
            }
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return {
                "attempted": True,
                "network_contacted": True,
                "ok": False,
                "url": models_url,
                "reason": "endpoint response does not contain an OpenAI-compatible data array",
            }
        model_ids = sorted(
            {
                str(item.get("id"))
                for item in data
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
            }
        )
        model_available = bool(model_id) and model_id in model_ids
        return {
            "attempted": True,
            "network_contacted": True,
            "ok": model_available,
            "url": models_url,
            "model_id": model_id,
            "model_available": model_available,
            "models_seen": len(model_ids),
            "reason": "selected model listed by endpoint"
            if model_available
            else "selected model is not listed by endpoint",
        }

    def plan(
        self,
        name: str,
        framework: str = "langgraph",
        model: str | None = None,
        runtime: str | None = None,
        provider: str | None = None,
        endpoint: str | None = None,
        api_key_env: str | None = None,
        instruction: str | None = None,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        selection = self._selection(
            name,
            framework,
            model=model,
            runtime=runtime,
            provider=provider,
            endpoint=endpoint,
            api_key_env=api_key_env,
        )
        spec = AGENT_FRAMEWORKS[framework]
        root = agent_artifacts_root(output_dir)
        target_dir = root / name
        return {
            "name": "agent_plan",
            "agent": name,
            "framework": framework,
            "profile": self.profile.name,
            "artifact_root": str(root),
            "target_dir": str(target_dir),
            "selection": selection.__dict__,
            "instruction": instruction
            or "You are a focused coding assistant. Keep answers concise and ask before destructive actions.",
            "files": spec["files"],
            "packages": spec["packages"],
            "endpoint_smoke_packages": ["openai"],
            "next_steps": [
                "Export and run endpoint-smoke.py first to verify the selected OpenAI-compatible endpoint.",
                "Review the framework configuration before translating it into a framework-native project.",
                "Install requirements in an isolated environment.",
                "Set the API-key environment variable when the selected endpoint requires one.",
                "Run aiplane environment doctor before using local runtimes.",
            ],
            "notes": [
                "An agent application is the code that owns prompts, state, tools, and the model call loop.",
                "aiplane selects and documents the model endpoint; the exported app is where agent behavior lives.",
                "This plan/export path does not write files or run the agent unless you redirect output and execute it yourself.",
                "Agent artifacts are planned outside profiles; use --output-dir or local config agent_artifacts_dir to choose the root.",
            ],
        }

    def manifest(
        self,
        name: str,
        *,
        stack: str | None = None,
        framework: str = "langgraph",
        model: str | None = None,
        runtime: str | None = None,
        provider: str | None = None,
        endpoint: str | None = None,
        api_key_env: str | None = None,
    ) -> dict[str, Any]:
        """Compile profile or stack configuration into a secret-free agent contract."""
        if stack:
            stack_plan = StackManager(self.profile).plan(stack)
            orchestrator = normalize_framework(str(stack_plan.get("orchestrator") or framework))
            source_roles = stack_plan.get("roles") if isinstance(stack_plan.get("roles"), dict) else {}
            tools = stack_plan.get("tools") if isinstance(stack_plan.get("tools"), dict) else {}
            limits = stack_plan.get("limits") if isinstance(stack_plan.get("limits"), dict) else {}
            approval_mode = stack_plan.get("approval_mode") or "ask"
            audit_label = stack_plan.get("audit_label") or stack
        else:
            selection = self._selection(name, framework, model, runtime, provider, endpoint, api_key_env)
            orchestrator = normalize_framework(framework)
            source_roles = {
                "primary": {
                    "model": selection.model_alias,
                    "provider": selection.provider,
                    "runtime": selection.runtime,
                    "endpoint": selection.endpoint,
                    "approval_mode": "ask",
                    "audit_label": f"{name}.primary",
                    "limits": {},
                    "tools": {},
                }
            }
            tools, limits, approval_mode, audit_label = {}, {}, "ask", name
        catalog = ModelCatalog(self.profile)
        roles = {}
        for role_name, binding in sorted(source_roles.items()):
            if not isinstance(binding, dict):
                raise ValueError(f"agent role {role_name!r} must be a mapping")
            alias = str(binding.get("model") or "")
            model_config = catalog.show(alias)
            provider_config = (
                model_config.get("provider_config") if isinstance(model_config.get("provider_config"), dict) else {}
            )
            credential_ref = provider_config.get("credential_ref")
            key_env = provider_config.get("api_key_env")
            roles[str(role_name)] = {
                "model_alias": alias,
                "model_id": model_config.get("model"),
                "provider": binding.get("provider") or model_config.get("provider"),
                "ownership": binding.get("ownership") or model_config.get("ownership"),
                "runtime": binding.get("runtime"),
                "endpoint": binding.get("endpoint"),
                "endpoint_protocol": "openai_compatible",
                "model_roles": model_config.get("roles", []),
                "capabilities": model_config.get("capabilities", {}),
                "tools": binding.get("tools") if isinstance(binding.get("tools"), dict) else tools,
                "limits": binding.get("limits") if isinstance(binding.get("limits"), dict) else limits,
                "approval_mode": binding.get("approval_mode") or approval_mode,
                "audit_label": binding.get("audit_label") or f"{audit_label}.{role_name}",
                "credential": {
                    "required": bool(credential_ref or key_env),
                    "credential_ref": credential_ref,
                    "api_key_env": key_env,
                },
            }
        readiness = framework_readiness(orchestrator, roles, str(approval_mode))
        framework_metadata = {
            "name": name,
            "profile": self.profile.name,
            "runtime": next(iter(roles.values())).get("runtime") if roles else None,
            "endpoint": next(iter(roles.values())).get("endpoint") if roles else None,
            "roles": roles,
            "tools": tools,
            "limits": limits,
            "approval_mode": approval_mode,
            "audit_label": audit_label,
        }
        framework_config = render_framework_starter(orchestrator, framework_metadata)
        return {
            "$schema": "schemas/aiplane-agent-environment-v1.schema.json",
            "schema_version": "1.0",
            "record_type": "agent_environment",
            "render_only": True,
            "name": name,
            "profile": self.profile.name,
            "source_stack": stack,
            "orchestrator": orchestrator,
            "framework": {
                "name": orchestrator,
                "packages": readiness["packages"],
                "config_format": "aiplane_agent_framework_starter_v1",
            },
            "roles": roles,
            "readiness": readiness,
            "control_enforcement": readiness["control_enforcement"],
            "framework_config": framework_config,
            "tools": tools,
            "limits": limits,
            "approval_mode": approval_mode,
            "audit_label": audit_label,
            "execution_boundary": {
                "runs_agents": False,
                "writes_credentials": False,
                "applies_configuration": False,
            },
            "notes": [
                "Review this manifest and generated framework configuration before use.",
                "Credential references contain names only; secret values are never rendered.",
            ],
        }

    def job(
        self,
        name: str,
        *,
        stack: str,
        task: str,
        roles: list[str] | None = None,
        job_workspace: str = ".",
    ) -> dict[str, Any]:
        """Render a secret-free job handoff for an already configured stack."""
        manifest = self.manifest(name, stack=stack)
        return self._job_from_manifest(manifest, task=task, roles=roles, job_workspace=job_workspace)

    def handoff(
        self,
        name: str,
        *,
        stack: str,
        task: str,
        roles: list[str] | None = None,
        job_workspace: str = ".",
    ) -> dict[str, Any]:
        """Render one checksummed environment-and-job artifact without executing it."""
        manifest = self.manifest(name, stack=stack)
        job = self._job_from_manifest(manifest, task=task, roles=roles, job_workspace=job_workspace)
        return {
            "$schema": "schemas/aiplane-agent-handoff-v1.schema.json",
            "schema_version": "1.0",
            "record_type": "agent_handoff",
            "render_only": True,
            "name": name,
            "environment": manifest,
            "job": job,
            "checksums": {
                "environment_sha256": _canonical_sha256(manifest),
                "job_sha256": _canonical_sha256(job),
            },
            "execution_boundary": {
                "submits_jobs": False,
                "runs_agents": False,
                "writes_credentials": False,
                "applies_configuration": False,
            },
            "notes": [
                "This is a render-only handoff bundle; give it to the selected framework or reviewed wrapper to execute.",
                "The bundle contains endpoint and credential-reference metadata only, never credential values.",
            ],
        }

    def validate_job_file(self, source: Path | str, *, handoff: bool = False) -> dict[str, Any]:
        path, payload = self._read_job_file(source)
        errors = _validate_handoff(payload) if handoff else _validate_job(payload)
        return {
            "record_type": "agent_handoff_validation" if handoff else "agent_job_validation",
            "path": str(path.relative_to(self.profile.workspace)),
            "valid": not errors,
            "errors": errors,
            "mutates": False,
        }

    def _job_from_manifest(
        self,
        manifest: dict[str, Any],
        *,
        task: str,
        roles: list[str] | None,
        job_workspace: str,
    ) -> dict[str, Any]:
        task = task.strip()
        if not task:
            raise ValueError("job task must be non-empty")
        if len(task) > _MAX_TASK_CHARS:
            raise ValueError(f"job task exceeds the {_MAX_TASK_CHARS}-character review limit")
        if contains_secret(task):
            raise ValueError(
                "job task contains secret-like material; use an ignored local file or credential reference instead"
            )
        workspace = _safe_job_workspace(job_workspace)
        available_roles = manifest.get("roles") if isinstance(manifest.get("roles"), dict) else {}
        selected_roles = roles or sorted(available_roles)
        if not selected_roles:
            raise ValueError("agent environment has no roles to receive a job")
        if len(selected_roles) != len(set(selected_roles)):
            raise ValueError("job target roles must not contain duplicates")
        unknown_roles = sorted(set(selected_roles) - set(available_roles))
        if unknown_roles:
            raise ValueError(f"job targets unknown stack roles: {', '.join(unknown_roles)}")
        environment_sha256 = _canonical_sha256(manifest)
        control_enforcement = framework_control_enforcement(
            str(manifest["orchestrator"]),
            available_roles,
            str(manifest.get("approval_mode") or "ask"),
            job_workspace=True,
        )
        return {
            "$schema": "schemas/aiplane-agent-job-v1.schema.json",
            "schema_version": "1.0",
            "record_type": "agent_job",
            "render_only": True,
            "name": manifest["name"],
            "environment": {
                "name": manifest["name"],
                "profile": manifest["profile"],
                "source_stack": manifest["source_stack"],
                "orchestrator": manifest["orchestrator"],
                "sha256": environment_sha256,
            },
            "task": task,
            "target_roles": selected_roles,
            "workspace": {"path": workspace, "policy": "workspace_only"},
            "control_enforcement": control_enforcement,
            "limits": manifest.get("limits", {}),
            "approval_mode": manifest.get("approval_mode", "ask"),
            "audit_label": manifest.get("audit_label", manifest["name"]),
            "execution_boundary": {
                "submits_jobs": False,
                "runs_agents": False,
                "writes_credentials": False,
                "applies_configuration": False,
            },
            "notes": [
                "Task execution belongs to the selected framework or a reviewed wrapper, not aiplane.",
                "Target roles and controls are handoff metadata; verify framework enforcement before execution.",
            ],
        }

    def _read_job_file(self, source: Path | str) -> tuple[Path, dict[str, Any]]:
        path = Path(source)
        if not path.is_absolute():
            path = self.profile.workspace / path
        path = path.resolve()
        workspace = self.profile.workspace.resolve()
        if workspace not in path.parents:
            raise PermissionError("agent artifact path escapes workspace boundary")
        if not path.is_file():
            raise ValueError("agent artifact path must be an existing regular file inside the workspace")
        if path.stat().st_size > _MAX_JOB_FILE_BYTES:
            raise ValueError(f"agent artifact exceeds the {_MAX_JOB_FILE_BYTES}-byte review limit")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("agent artifact must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("agent artifact root must be a JSON object")
        if _artifact_contains_secret(payload):
            raise ValueError("agent artifact contains secret-like material and cannot be validated through aiplane")
        return path, payload

    def export(
        self,
        name: str,
        framework: str = "langgraph",
        model: str | None = None,
        runtime: str | None = None,
        provider: str | None = None,
        endpoint: str | None = None,
        api_key_env: str | None = None,
        instruction: str | None = None,
        file: str | None = None,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        if framework not in AGENT_FRAMEWORKS:
            raise ValueError(f"unknown agent framework: {framework}")
        file = file or ("agent.py" if framework in {"langgraph", "simple-openai"} else "endpoint-smoke.py")
        selection = self._selection(
            name,
            framework,
            model=model,
            runtime=runtime,
            provider=provider,
            endpoint=endpoint,
            api_key_env=api_key_env,
        )
        instruction = (
            instruction
            or "You are a focused coding assistant. Keep answers concise and ask before destructive actions."
        )
        if file == "agent.py":
            if framework not in {"langgraph", "simple-openai"}:
                raise ValueError(
                    f"{framework} has no native executable scaffold; export endpoint-smoke.py and framework-config.yaml"
                )
            content = (
                _langgraph_agent(selection, instruction)
                if framework == "langgraph"
                else _simple_openai_agent(selection, instruction)
            )
        elif file == "endpoint-smoke.py":
            content = _endpoint_smoke(selection, instruction)
        elif file == "endpoint-smoke-requirements.txt":
            content = "openai\n"
        elif file == "requirements.txt":
            content = "\n".join(AGENT_FRAMEWORKS[framework]["packages"]) + "\n"
        elif file == ".env.example":
            content = _env_example(selection)
        elif file == "README.md":
            content = _readme(name, framework, selection)
        elif file in {"agent-environment.json", "agent-environment.yaml", "framework-config.yaml"}:
            manifest = self.manifest(
                name,
                framework=framework,
                model=model,
                runtime=runtime,
                provider=provider,
                endpoint=endpoint,
                api_key_env=api_key_env,
            )
            content = (
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
                if file.endswith(".json")
                else manifest["framework_config"]
                if file == "framework-config.yaml"
                else dump_yaml(manifest)
            )
        else:
            raise ValueError(
                "file must be agent.py, endpoint-smoke.py, endpoint-smoke-requirements.txt, requirements.txt, .env.example, README.md, agent-environment.json, agent-environment.yaml, or framework-config.yaml"
            )
        return {
            "name": "agent_export",
            "agent": name,
            "framework": framework,
            "file": file,
            "artifact_root": str(agent_artifacts_root(output_dir)),
            "target_dir": str(agent_artifacts_root(output_dir) / name),
            "selection": selection.__dict__,
            "content": content,
            "notes": [
                "This command prints one scaffold file to stdout; it does not create a project directory.",
                "Use agents plan with the same flags to inspect the model endpoint decision.",
            ],
        }

    def _selection(
        self,
        name: str,
        framework: str,
        model: str | None,
        runtime: str | None,
        provider: str | None,
        endpoint: str | None,
        api_key_env: str | None,
    ) -> AgentSelection:
        if framework not in AGENT_FRAMEWORKS:
            raise ValueError(f"unknown agent framework: {framework}")
        plan = self.integrations.plan(
            "openai-compatible",
            model_name=model,
            provider=provider,
            runtime=runtime,
            select_best=model is None,
            endpoint=endpoint,
            api_key_env=api_key_env,
        )
        row = plan["selection"]["primary"]
        if not row.get("endpoint"):
            raise ValueError(
                "selected model does not have an endpoint; pass --endpoint or configure the provider endpoint"
            )
        return AgentSelection(
            name=name,
            framework=framework,
            model_alias=str(row["name"]),
            model=str(row["model"]),
            provider=str(row["provider"]),
            runtime=str(row["runtime"]),
            endpoint=validate_http_endpoint(row["endpoint"], "selected agent endpoint"),
            api_key_env=row.get("api_key_env"),
        )


def _endpoint_smoke(selection: AgentSelection, instruction: str) -> str:
    return _simple_openai_agent(selection, instruction)


def _models_probe_url(endpoint: str) -> str:
    validated = validate_http_endpoint(endpoint, "agent endpoint")
    parsed = urlsplit(validated)
    path = parsed.path.rstrip("/")
    if not path.endswith("/models"):
        path = f"{path}/models" if path else "/models"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _env_example(selection: AgentSelection) -> str:
    key_env = selection.api_key_env or "OPENAI_API_KEY"
    key_value = "replace-me" if selection.api_key_env else "dummy-local-key"
    return (
        f"AIPLANE_AGENT_NAME={selection.name}\n"
        f"AIPLANE_MODEL={selection.model}\n"
        f"OPENAI_BASE_URL={selection.endpoint}\n"
        f"{key_env}={key_value}\n"
    )


def _readme(name: str, framework: str, selection: AgentSelection) -> str:
    key_env = selection.api_key_env or "OPENAI_API_KEY"
    entrypoint = "agent.py" if framework in {"langgraph", "simple-openai"} else "endpoint-smoke.py"
    framework_note = (
        '`agent.py` is a small executable starter for this framework. After verifying the endpoint, run `pip install -r requirements.txt` and `python agent.py "Summarize this repository"`.'
        if entrypoint == "agent.py"
        else "`endpoint-smoke.py` is a directly runnable endpoint check; translate `framework-config.yaml` into the selected framework's native project shape before building a workflow."
    )
    return f"""# {name}

Generated starter agent scaffold for `{framework}`.

Selected model alias: `{selection.model_alias}`
Model id/deployment: `{selection.model}`
Endpoint: `{selection.endpoint}`
API key env: `{key_env}`

{framework_note}

## Verify the endpoint

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r endpoint-smoke-requirements.txt
export OPENAI_BASE_URL={selection.endpoint}
export AIPLANE_MODEL={selection.model}
export {key_env}=replace-me
python endpoint-smoke.py "Summarize this repository"
```

For `langgraph` and `simple-openai`, install `requirements.txt` after the endpoint check and then run `agent.py` if you want the native executable starter. For other frameworks, `requirements.txt` is for the reviewed framework translation, not a requirement of the endpoint smoke path.

For local OpenAI-compatible endpoints, a dummy API key is often accepted. The starter does not install packages, write credentials, enforce tool policy, or run a background agent.
"""


def _simple_openai_agent(selection: AgentSelection, instruction: str) -> str:
    key_env = selection.api_key_env or "OPENAI_API_KEY"
    return f"""from __future__ import annotations

import os
import sys
from openai import OpenAI

MODEL = os.getenv("AIPLANE_MODEL", {selection.model!r})
BASE_URL = os.getenv("OPENAI_BASE_URL", {selection.endpoint!r})
API_KEY = os.getenv({key_env!r}, "dummy-local-key")
SYSTEM_PROMPT = {instruction!r}


def main() -> int:
    prompt = " ".join(sys.argv[1:]).strip() or "Say hello and describe your configured model."
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {{"role": "system", "content": SYSTEM_PROMPT}},
            {{"role": "user", "content": prompt}},
        ],
    )
    print(response.choices[0].message.content or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _langgraph_agent(selection: AgentSelection, instruction: str) -> str:
    key_env = selection.api_key_env or "OPENAI_API_KEY"
    return f"""from __future__ import annotations

import os
import sys
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

MODEL = os.getenv("AIPLANE_MODEL", {selection.model!r})
BASE_URL = os.getenv("OPENAI_BASE_URL", {selection.endpoint!r})
API_KEY = os.getenv({key_env!r}, "dummy-local-key")
SYSTEM_PROMPT = {instruction!r}


class AgentState(TypedDict):
    task: str
    answer: str


def call_model(state: AgentState) -> AgentState:
    llm = ChatOpenAI(model=MODEL, base_url=BASE_URL, api_key=API_KEY)
    response = llm.invoke([
        ("system", SYSTEM_PROMPT),
        ("user", state["task"]),
    ])
    return {{"task": state["task"], "answer": str(response.content)}}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.set_entry_point("call_model")
    graph.add_edge("call_model", END)
    return graph.compile()


def main() -> int:
    task = " ".join(sys.argv[1:]).strip() or "Say hello and describe your configured model."
    result = build_graph().invoke({{"task": task, "answer": ""}})
    print(result["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _artifact_contains_secret(value: object) -> bool:
    """Check artifact values without mistaking credential-reference field names for secrets."""
    if isinstance(value, dict):
        return any(_artifact_contains_secret(inner) for inner in value.values())
    if isinstance(value, (list, tuple)):
        return any(_artifact_contains_secret(item) for item in value)
    return isinstance(value, str) and contains_secret(value)


def _validate_environment(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["environment must be a JSON object"]
    errors: list[str] = []
    expected = {
        "$schema": "schemas/aiplane-agent-environment-v1.schema.json",
        "schema_version": "1.0",
        "record_type": "agent_environment",
        "render_only": True,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            errors.append(f"{key} must equal {value!r}")
    for key in ("name", "profile", "orchestrator"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            errors.append(f"{key} must be a non-empty string")
    if not isinstance(payload.get("source_stack"), str) or not payload["source_stack"].strip():
        errors.append("source_stack must be a non-empty string for a job handoff")
    roles = payload.get("roles")
    if not isinstance(roles, dict) or not roles:
        errors.append("roles must be a non-empty object")
    ce = payload.get("control_enforcement")
    if not isinstance(ce, dict):
        errors.append("control_enforcement must be an object")
    else:
        for key in _CONTROL_ENFORCEMENT_REQUIRED_KEYS:
            if key not in ce:
                errors.append(f"control_enforcement missing required key {key!r}")
    if not isinstance(payload.get("execution_boundary"), dict):
        errors.append("execution_boundary must be an object")
    return errors


def _validate_job(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["job must be a JSON object"]
    errors: list[str] = []
    expected = {
        "$schema": "schemas/aiplane-agent-job-v1.schema.json",
        "schema_version": "1.0",
        "record_type": "agent_job",
        "render_only": True,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            errors.append(f"{key} must equal {value!r}")
    if not isinstance(payload.get("name"), str) or not payload["name"].strip():
        errors.append("name must be a non-empty string")
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip():
        errors.append("task must be a non-empty string")
    elif len(task) > _MAX_TASK_CHARS:
        errors.append(f"task exceeds the {_MAX_TASK_CHARS}-character review limit")
    roles = payload.get("target_roles")
    if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or not role.strip() for role in roles):
        errors.append("target_roles must be a non-empty list of role names")
    elif len(roles) != len(set(roles)):
        errors.append("target_roles must not contain duplicates")
    workspace = payload.get("workspace")
    if not isinstance(workspace, dict) or workspace.get("policy") != "workspace_only":
        errors.append("workspace must declare workspace_only policy")
    elif not isinstance(workspace.get("path"), str):
        errors.append("workspace path must be a string")
    else:
        try:
            _safe_job_workspace(workspace["path"])
        except ValueError as exc:
            errors.append(str(exc))
    environment = payload.get("environment")
    if not isinstance(environment, dict) or not all(
        isinstance(environment.get(key), str) and environment[key]
        for key in ("name", "profile", "source_stack", "orchestrator", "sha256")
    ):
        errors.append("environment must identify name, profile, source_stack, orchestrator, and sha256")
    ce = payload.get("control_enforcement")
    if not isinstance(ce, dict):
        errors.append("control_enforcement must be an object")
    else:
        for key in _CONTROL_ENFORCEMENT_REQUIRED_KEYS:
            if key not in ce:
                errors.append(f"control_enforcement missing required key {key!r}")
    if not isinstance(payload.get("execution_boundary"), dict):
        errors.append("execution_boundary must be an object")
    return errors


def _validate_handoff(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["handoff must be a JSON object"]
    errors: list[str] = []
    expected = {
        "$schema": "schemas/aiplane-agent-handoff-v1.schema.json",
        "schema_version": "1.0",
        "record_type": "agent_handoff",
        "render_only": True,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            errors.append(f"{key} must equal {value!r}")
    environment = payload.get("environment")
    job = payload.get("job")
    errors.extend(f"environment: {error}" for error in _validate_environment(environment))
    errors.extend(f"job: {error}" for error in _validate_job(job))
    if isinstance(environment, dict) and isinstance(job, dict):
        reference = job.get("environment")
        if isinstance(reference, dict):
            for key in ("name", "profile", "source_stack", "orchestrator"):
                if reference.get(key) != environment.get(key):
                    errors.append(f"job environment {key} does not match")
    checksums = payload.get("checksums")
    if not isinstance(checksums, dict):
        errors.append("checksums must be an object")
    else:
        if isinstance(environment, dict) and checksums.get("environment_sha256") != _canonical_sha256(environment):
            errors.append("environment checksum does not match")
        if isinstance(job, dict) and checksums.get("job_sha256") != _canonical_sha256(job):
            errors.append("job checksum does not match")
        if isinstance(environment, dict) and isinstance(job, dict):
            reference = job.get("environment")
            if not isinstance(reference, dict) or reference.get("sha256") != _canonical_sha256(environment):
                errors.append("job environment reference does not match")
    return errors
