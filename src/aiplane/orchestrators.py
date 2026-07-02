from __future__ import annotations

import importlib.util
import subprocess
from typing import Any

from .config import dump_yaml
from .env import EnvironmentManager
from .model_catalog import ModelCatalog
from .models import Profile
from .runtime_catalog import RuntimeCatalog, RUNTIME_DEFINITIONS


ORCHESTRATOR_DEFINITIONS: dict[str, dict[str, Any]] = {
    "langgraph": {
        "description": "Stateful graph-based agent/workflow orchestration from the LangChain ecosystem.",
        "priority": 1,
        "packages": ["langgraph", "langchain-openai"],
        "good_for": [
            "bounded agent trees",
            "state machines",
            "reviewable workflows",
            "human checkpoints",
        ],
        "config_style": "python_graph",
        "endpoint_protocols": ["openai_compatible"],
    },
    "crewai": {
        "description": "Role/task oriented multi-agent framework with simple crew and flow abstractions.",
        "priority": 2,
        "packages": ["crewai"],
        "good_for": [
            "role-based task teams",
            "business workflows",
            "simple declarative agent crews",
        ],
        "config_style": "python_or_yaml",
        "endpoint_protocols": ["openai_compatible"],
    },
    "autogen": {
        "description": "Microsoft-origin multi-agent conversation/workflow framework.",
        "priority": 3,
        "packages": ["autogen-agentchat", "autogen-ext[openai]"],
        "good_for": [
            "multi-agent conversations",
            "human-in-the-loop workflows",
            "Microsoft/Azure-aligned experiments",
        ],
        "config_style": "python_or_json",
        "endpoint_protocols": ["openai_compatible"],
    },
    "openhands": {
        "description": "Software-engineering agent platform with sandboxed developer workflows; heavier than a library orchestrator.",
        "priority": 4,
        "packages": [],
        "good_for": [
            "software engineering agents",
            "sandboxed coding workloads",
            "browser/terminal style agent environments",
        ],
        "config_style": "container_or_service",
        "endpoint_protocols": ["openai_compatible"],
        "install_hint": "Prefer the project Docker/service install path rather than a small pip-only environment.",
    },
    "semantic_kernel": {
        "description": "Microsoft SDK for agent/application orchestration and planners, useful for Azure-heavy applications.",
        "priority": 5,
        "packages": ["semantic-kernel"],
        "good_for": [
            "Azure-aligned apps",
            "planner-style orchestration",
            "application SDK integration",
        ],
        "config_style": "python_sdk",
        "endpoint_protocols": ["openai_compatible"],
    },
    "llamaindex_workflows": {
        "description": "Workflow layer in the LlamaIndex ecosystem, strongest for retrieval/data-heavy agent flows.",
        "priority": 6,
        "packages": ["llama-index"],
        "good_for": [
            "retrieval workflows",
            "document/data agents",
            "RAG-heavy task flows",
        ],
        "config_style": "python_workflow",
        "endpoint_protocols": ["openai_compatible"],
    },
}


class OrchestratorCatalog:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.config = profile.orchestrators or {}
        self.environment = EnvironmentManager(profile)

    def list(
        self,
        providers: list[str] | None = None,
        runtimes: list[str] | None = None,
        group_by: str | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        configured = self._configured()
        provider_filter = {str(value) for value in providers or [] if value}
        runtime_filter = {str(value) for value in runtimes or [] if value}
        rows = []
        for name, spec in ORCHESTRATOR_DEFINITIONS.items():
            row = {
                "name": name,
                "configured": name in configured,
                "description": spec["description"],
                "priority": spec["priority"],
                "supported_providers": self._supported_providers(spec),
                "supported_runtimes": self._supported_runtimes(spec),
                "packages": spec.get("packages", []),
                "good_for": spec.get("good_for", []),
                "config_style": spec.get("config_style"),
                "endpoint_protocols": spec.get("endpoint_protocols", []),
            }
            if provider_filter and not provider_filter.intersection(row["supported_providers"]):
                continue
            if runtime_filter and not runtime_filter.issubset(set(row["supported_runtimes"])):
                continue
            rows.append(row)
        rows = sorted(rows, key=lambda row: int(row["priority"]))
        if group_by:
            key_filter = provider_filter if group_by == "provider" else runtime_filter
            return self._group(rows, group_by, key_filter)
        return rows

    def show(self, name: str) -> dict[str, Any]:
        spec = self._definition(name)
        return {"name": name, **spec, "configured": self._configured().get(name)}

    def bundle_plan(self, name: str, mode: str = "docker") -> dict[str, Any]:
        spec = self._definition(name)
        if mode not in {"docker", "conda"}:
            raise ValueError("mode must be docker or conda")
        packages = [str(item) for item in spec.get("packages", [])]
        files = {
            "Dockerfile": _dockerfile(name, packages),
            "environment.yaml": _conda_yaml(name, packages),
        }
        selected_file = "Dockerfile" if mode == "docker" else "environment.yaml"
        return {
            "name": f"{name}-{mode}",
            "orchestrator": name,
            "mode": mode,
            "packages": packages,
            "files": files,
            "selected_file": selected_file,
            "notes": [
                "This renders a starter environment for the orchestrator library only.",
                "Runtime/model endpoints are configured separately and passed into the orchestrator config.",
            ],
        }

    def setup(
        self,
        name: str,
        runtime: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        environment: str | None = None,
        approval_mode: str | None = None,
        limits: dict[str, object] | None = None,
        tools: dict[str, object] | None = None,
        dry_run: bool = True,
        yes: bool = False,
        install: bool = False,
    ) -> dict[str, Any]:
        spec = self._definition(name)
        if runtime and runtime not in {row["name"] for row in RuntimeCatalog(self.profile).list(include_gui=True)}:
            raise ValueError(f"unknown runtime: {runtime}")
        if model:
            ModelCatalog(self.profile).get(model)
        env_mode = environment or self.environment.active_mode()
        packages = [str(item) for item in spec.get("packages", [])]
        config = {
            "name": name,
            "runtime": runtime,
            "model": model,
            "endpoint": endpoint,
            "environment": env_mode,
            "approval_mode": approval_mode or "ask",
            "limits": limits or {},
            "tools": tools or {},
        }
        install_command = ["python", "-m", "pip", "install", *packages] if packages else []
        install_plan = self.environment.plan(install_command, mode=env_mode) if install_command else None
        payload: dict[str, Any] = {
            "name": name,
            "dry_run": dry_run or not yes,
            "install": install,
            "config": config,
            "actions": [],
            "notes": [
                "Setup writes orchestrator configuration and can optionally install Python packages.",
                "Limits and tool policies are passed through as structured config; enforcement belongs to the orchestrator/runtime.",
            ],
        }
        if install_plan:
            payload["actions"].append(
                {
                    "name": "install orchestrator packages",
                    "command": install_plan.command,
                    "cwd": str(install_plan.cwd),
                    "mutates": True,
                }
            )
        payload["actions"].append(
            {
                "name": "write orchestrator config",
                "path": str(self.profile.root / "orchestrators.yaml"),
                "mutates": True,
            }
        )
        if dry_run or not yes:
            return payload
        results = []
        if install and install_plan:
            completed = subprocess.run(
                install_plan.command,
                cwd=install_plan.cwd,
                text=True,
                capture_output=True,
                check=False,
            )
            results.append(
                {
                    "name": "install orchestrator packages",
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                }
            )
            if completed.returncode != 0:
                payload["results"] = results
                return payload
        self.config.setdefault("orchestrators", {})[name] = config
        self._write_config()
        results.append(
            {
                "name": "write orchestrator config",
                "returncode": 0,
                "path": str(self.profile.root / "orchestrators.yaml"),
            }
        )
        payload["results"] = results
        return payload

    def doctor(self, name: str) -> dict[str, Any]:
        spec = self._definition(name)
        configured = self._configured().get(name, {})
        env_mode = (
            str(configured.get("environment") or self.environment.active_mode())
            if isinstance(configured, dict)
            else self.environment.active_mode()
        )
        package_checks = []
        for package in spec.get("packages", []):
            module = _module_name(str(package))
            package_checks.append(
                {
                    "name": str(package),
                    "module": module,
                    "ok": _module_available(module),
                    "detail": "importable" if _module_available(module) else "not importable",
                }
            )
        checks = [
            {"name": "known_orchestrator", "ok": True, "detail": name},
            {
                "name": "configured",
                "ok": bool(configured),
                "detail": "configured in orchestrators.yaml" if configured else "not configured yet",
            },
            {
                "name": "environment_known",
                "ok": env_mode in self.environment.modes(),
                "detail": env_mode,
            },
            *package_checks,
        ]
        return {
            "name": name,
            "checks": checks,
            "configured": configured,
            "definition": spec,
        }

    def _supported_providers(self, spec: dict[str, Any]) -> list[str]:
        protocols = set(str(value) for value in spec.get("endpoint_protocols", []))
        providers = ModelCatalog(self.profile).providers()
        supported = []
        for name, provider in providers.items():
            provider_protocols = self._provider_protocols(name, provider)
            if protocols.intersection(provider_protocols):
                supported.append(name)
        return sorted(supported)

    def _supported_runtimes(self, spec: dict[str, Any]) -> list[str]:
        protocols = set(str(value) for value in spec.get("endpoint_protocols", []))
        supported = []
        for name, runtime in RUNTIME_DEFINITIONS.items():
            protocol = str(runtime.get("protocol") or "")
            if protocol in protocols or (name == "ollama" and "openai_compatible" in protocols):
                supported.append(name)
        return sorted(supported)

    def _provider_protocols(self, name: str, provider: dict[str, Any]) -> set[str]:
        protocols = set()
        configured = provider.get("protocol")
        if configured:
            protocols.add(str(configured))
        runtime_name = str(provider.get("runtime") or name)
        runtime = RUNTIME_DEFINITIONS.get(runtime_name, {})
        if runtime.get("protocol"):
            protocols.add(str(runtime.get("protocol")))
        endpoint = str(provider.get("endpoint") or "")
        if endpoint.endswith("/v1") or name in {
            "ollama",
            "openai",
            "azure_openai",
            "ollama_cloud",
        }:
            protocols.add("openai_compatible")
        return protocols

    def _group(
        self,
        rows: list[dict[str, Any]],
        group_by: str,
        key_filter: set[str] | None = None,
    ) -> dict[str, Any]:
        if group_by not in {"provider", "runtime"}:
            raise ValueError("group_by must be provider or runtime")
        key_name = "supported_providers" if group_by == "provider" else "supported_runtimes"
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            keys = [str(value) for value in row.get(key_name) or ["none"]]
            if key_filter:
                keys = [key for key in keys if key in key_filter]
            for key in keys:
                groups.setdefault(str(key), []).append(row)
        return {
            "name": "orchestrators",
            "group_by": group_by,
            "groups": {
                key: sorted(value, key=lambda item: int(item["priority"])) for key, value in sorted(groups.items())
            },
        }

    def _definition(self, name: str) -> dict[str, Any]:
        if name not in ORCHESTRATOR_DEFINITIONS:
            raise ValueError(f"unknown orchestrator: {name}")
        return ORCHESTRATOR_DEFINITIONS[name]

    def _configured(self) -> dict[str, Any]:
        configured = self.config.get("orchestrators", {})
        return configured if isinstance(configured, dict) else {}

    def _write_config(self) -> None:
        path = self.profile.root / "orchestrators.yaml"
        path.write_text(dump_yaml(self.config), encoding="utf-8")


def _dockerfile(name: str, packages: list[str]) -> str:
    install = " ".join(packages) if packages else ""
    lines = [
        "FROM python:3.13-slim",
        "WORKDIR /workspace",
        "RUN python -m pip install --upgrade pip",
    ]
    if install:
        lines.append(f"RUN python -m pip install {install}")
    else:
        lines.append(f"# Install {name} using its project-specific container/service instructions")
    lines.append('CMD ["python", "-c", "print("orchestrator environment ready")"]')
    return "\n".join(lines) + "\n"


def _conda_yaml(name: str, packages: list[str]) -> str:
    pip_lines = [f"      - {package}" for package in packages] or [
        f"      - # install {name} using project-specific instructions"
    ]
    return (
        "\n".join(
            [
                "name: aiplane-orchestrator",
                "channels:",
                "  - conda-forge",
                "dependencies:",
                "  - python=3.13",
                "  - pip",
                "  - pip:",
                *pip_lines,
            ]
        )
        + "\n"
    )


def _module_name(package: str) -> str:
    base = package.split("[", 1)[0].replace("-", "_")
    aliases = {
        "autogen_agentchat": "autogen_agentchat",
        "autogen_ext": "autogen_ext",
        "semantic_kernel": "semantic_kernel",
    }
    return aliases.get(base, base)


def _module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None
