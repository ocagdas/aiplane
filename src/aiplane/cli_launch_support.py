from __future__ import annotations

import os
from pathlib import Path
import uuid

from .integrations import IntegrationManager
from .policy import PolicyEngine


def _launch_plan(
    profile,
    tool: str,
    model: str | None = None,
    app: str | None = None,
) -> dict[str, object]:
    if app and tool != "ollama":
        raise ValueError("--app is only supported with --tool ollama")
    manager = IntegrationManager(profile)
    plan_args: dict[str, object] = {}
    if tool == "continue":
        if model:
            plan_args["chat"] = model
    elif tool == "ollama":
        if model:
            plan_args["model_name"] = model
        plan_args["runtime"] = "ollama"
    else:
        if model:
            plan_args["model_name"] = model
    plan = manager.plan("openai-compatible" if tool == "ollama" else tool, **plan_args)
    selections = plan.get("selection", {})
    if not isinstance(selections, dict):
        raise ValueError("integration plan did not include a selection map")
    if tool == "continue":
        selected = selections.get("chat")
        if not isinstance(selected, dict):
            raise ValueError("integration plan is missing continue chat selection")
    else:
        selected = selections.get("primary")
        if not isinstance(selected, dict):
            raise ValueError("integration plan is missing primary selection")

    model_name = str(selected.get("name") or "")
    if not model_name:
        raise ValueError("selected model name is missing")

    decision = PolicyEngine(profile).model_decision(model_name)
    if not decision.allowed:
        raise ValueError(f"launch blocked: {decision.reason}")

    if tool == "ollama":
        model_id = str(selected.get("model") or "")
        command = ["ollama", "launch", model_id]
        if app:
            command.extend(["--app", app])
        return {
            "tool": tool,
            "selection": selected,
            "command": command,
        }

    if tool == "aider":
        api_key_env = str(selected.get("api_key_env") or "")
        model_id = str(selected.get("model") or "")
        if not model_id:
            raise ValueError("selected model has no model id")
        command = ["aider", "--model", f"openai/{model_id}"]
        launch_env: dict[str, str] = os.environ.copy()
        launch_env["OPENAI_API_BASE"] = str(selected.get("endpoint") or "")
        if api_key_env:
            if api_key_env not in launch_env:
                raise ValueError(f"required environment variable {api_key_env} for aider is not set")
            launch_env[api_key_env] = os.environ.get(api_key_env, "")
        return {
            "tool": tool,
            "selection": selected,
            "command": command,
            "env": launch_env,
        }

    if tool == "continue":
        return {
            "tool": tool,
            "selection": selected,
            "command": ["continue"],
        }

    raise ValueError(f"unsupported launch tool: {tool}")


def _new_session_id() -> str:
    return uuid.uuid4().hex


def _default_session_transcript(transcript_arg: str | Path | None, workspace: Path, session_id: str) -> Path:
    if transcript_arg:
        return Path(transcript_arg).expanduser()
    return workspace / ".aiplane" / "sessions" / f"{session_id}.log"


def _session_metadata_path(workspace: Path, session_id: str) -> Path:
    return workspace / ".aiplane" / "sessions" / f"{session_id}.json"
