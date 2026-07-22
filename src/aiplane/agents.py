from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .config import agent_artifacts_root, dump_yaml
from .integrations import IntegrationManager
from .model_catalog import ModelCatalog
from .stacks import StackManager
from .models import Profile


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


class AgentManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.integrations = IntegrationManager(profile)

    def templates(self) -> list[dict[str, Any]]:
        return [{"name": name, **spec} for name, spec in sorted(AGENT_FRAMEWORKS.items())]

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
            "next_steps": [
                "Review the exported agent code before running it.",
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
            orchestrator = stack_plan.get("orchestrator") or framework
            source_roles = stack_plan.get("roles") if isinstance(stack_plan.get("roles"), dict) else {}
            tools = stack_plan.get("tools") if isinstance(stack_plan.get("tools"), dict) else {}
            limits = stack_plan.get("limits") if isinstance(stack_plan.get("limits"), dict) else {}
            approval_mode = stack_plan.get("approval_mode") or "ask"
            audit_label = stack_plan.get("audit_label") or stack
        else:
            selection = self._selection(name, framework, model, runtime, provider, endpoint, api_key_env)
            orchestrator = framework
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
                "capabilities": model_config.get("capabilities", []),
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
        return {
            "$schema": "schemas/aiplane-agent-environment-v1.schema.json",
            "schema_version": "1.0",
            "record_type": "agent_environment",
            "render_only": True,
            "name": name,
            "profile": self.profile.name,
            "source_stack": stack,
            "orchestrator": orchestrator,
            "roles": roles,
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
        file: str = "agent.py",
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        if framework not in AGENT_FRAMEWORKS:
            raise ValueError(f"unknown agent framework: {framework}")
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
            content = (
                _langgraph_agent(selection, instruction)
                if framework == "langgraph"
                else _simple_openai_agent(selection, instruction)
            )
        elif file == "requirements.txt":
            content = "\n".join(AGENT_FRAMEWORKS[framework]["packages"]) + "\n"
        elif file == ".env.example":
            content = _env_example(selection)
        elif file == "README.md":
            content = _readme(name, framework, selection)
        elif file in {"agent-environment.json", "agent-environment.yaml"}:
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
                json.dumps(manifest, indent=2, sort_keys=True) + "\n" if file.endswith(".json") else dump_yaml(manifest)
            )
        else:
            raise ValueError(
                "file must be agent.py, requirements.txt, .env.example, README.md, agent-environment.json, or agent-environment.yaml"
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
            endpoint=str(row["endpoint"]),
            api_key_env=row.get("api_key_env"),
        )


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
    return f"""# {name}

Generated starter agent scaffold for `{framework}`.

Selected model alias: `{selection.model_alias}`
Model id/deployment: `{selection.model}`
Endpoint: `{selection.endpoint}`
API key env: `{key_env}`

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export OPENAI_BASE_URL={selection.endpoint}
export AIPLANE_MODEL={selection.model}
export {key_env}=replace-me
python agent.py "Summarize this repository"
```

For local Ollama/OpenAI-compatible endpoints, a dummy API key is often accepted.
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
