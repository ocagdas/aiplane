"""Docker Model Runner command adapter with preview-first lifecycle changes."""

from __future__ import annotations

import json
from typing import Any

from .boundaries import CommandRunner, SubprocessCommandRunner

MUTATING_ACTIONS = {
    "install",
    "update",
    "update-installed",
    "start",
    "stop",
    "restart",
    "pull",
    "repull",
    "remove",
    "clear",
}


class DockerModelRunner:
    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self.command_runner = command_runner or SubprocessCommandRunner()

    def run(
        self,
        action: str,
        *,
        model: str = "all",
        yes: bool = False,
        dry_run: bool = False,
    ) -> tuple[dict[str, Any], int]:
        command = self.command(action, model=model)
        mutation = action in MUTATING_ACTIONS
        preview = dry_run or (mutation and not yes)
        payload: dict[str, Any] = {
            "runtime": "docker_model_runner",
            "action": action,
            "model": model,
            "command": command,
            "mutating": mutation,
            "preview": preview,
            "executed": False,
            "requires_yes": mutation and not yes,
        }
        if preview:
            if mutation and not yes:
                payload["reason"] = "Docker Model Runner lifecycle changes require --yes"
            return payload, 0 if dry_run else 2

        try:
            completed = self.command_runner.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except FileNotFoundError:
            payload.update(
                {
                    "available": False,
                    "reason": "docker is not installed or not on PATH",
                    "install_hint": "Install Docker Engine or Docker Desktop with Docker Model Runner support.",
                }
            )
            return payload, 2
        payload["executed"] = True
        payload["returncode"] = completed.returncode
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if stdout:
            payload["output"] = _decode_output(stdout)
        if stderr:
            payload["message"] = stderr
        unsupported_cli = completed.returncode != 0 and (
            "unknown command" in stderr.lower() or "unknown flag" in stderr.lower()
        )
        if unsupported_cli:
            payload["available"] = False
            payload["reason"] = "this Docker installation does not provide the docker model command"
            payload["install_hint"] = "Install Docker Engine or Docker Desktop with Docker Model Runner support."
        else:
            payload["available"] = completed.returncode == 0
        return payload, completed.returncode

    @staticmethod
    def command(action: str, *, model: str) -> list[str]:
        if action == "status":
            return ["docker", "model", "status", "--json"]
        if action == "list-runtime-models":
            return ["docker", "model", "list", "--format", "json"]
        if action == "inspect":
            _require_model(model, action)
            return ["docker", "model", "inspect", model]
        if action == "benchmark":
            _require_model(model, action)
            return ["docker", "model", "bench", model]
        if action == "install":
            return ["docker", "model", "install-runner"]
        if action in {"update", "update-installed"}:
            return ["docker", "model", "reinstall-runner"]
        if action == "start":
            return ["docker", "model", "start-runner"]
        if action == "stop":
            return ["docker", "model", "stop-runner"]
        if action == "restart":
            return ["docker", "model", "restart-runner"]
        if action in {"pull", "repull"}:
            _require_model(model, action)
            return ["docker", "model", "pull", model]
        if action == "remove":
            _require_model(model, action)
            return ["docker", "model", "rm", model]
        if action == "clear":
            return ["docker", "model", "purge"]
        raise ValueError(f"unsupported Docker Model Runner action: {action}")


def _require_model(model: str, action: str) -> None:
    if not model or model == "all":
        raise ValueError(f"Docker Model Runner {action} requires --model with a native model id")


def _decode_output(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                return text
        return rows
