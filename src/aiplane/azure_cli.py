from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from .boundaries import CommandRunner, SubprocessCommandRunner

AZURE_CLI_TIMEOUT_SECONDS = 10


def run_az(
    command: list[str],
    verbosity: int = 0,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    runner: CommandRunner | None = None,
):
    runner = runner or SubprocessCommandRunner()
    if event_sink:
        event_sink({"phase": "start", "command": command})
    try:
        completed = runner.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=AZURE_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        completed = AzureTimeoutResult(command, AZURE_CLI_TIMEOUT_SECONDS)
    if event_sink:
        event: dict[str, Any] = {"phase": "complete", "command": command, "returncode": completed.returncode}
        if verbosity >= 1:
            event["stdout"] = completed.stdout
            event["stderr"] = completed.stderr
        event_sink(event)
    return completed


def account_status(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if completed.returncode != 0:
        return {"ok": False, "reason": f"az account show failed (exit {completed.returncode})"}
    try:
        account = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "reason": "az account show returned non-JSON output"}
    if not isinstance(account, dict):
        return {"ok": False, "reason": "az account show returned unexpected JSON shape"}
    user = account.get("user") if isinstance(account.get("user"), dict) else {}
    subscription_id = str(account.get("id") or "")
    tenant_id = str(account.get("tenantId") or "")
    user_name = str(user.get("name") or "")
    return {
        "ok": True,
        "environment": account.get("environmentName"),
        "state": account.get("state"),
        "is_default": account.get("isDefault"),
        "subscription_name": _redacted(str(account.get("name") or "")),
        "subscription_id": _redacted(subscription_id),
        "subscription_id_hint": _last4(subscription_id),
        "tenant_id": _redacted(tenant_id),
        "tenant_id_hint": _last4(tenant_id),
        "user_name": _redacted(user_name),
        "user_name_hint": _redacted(user_name),
        "user_type": user.get("type"),
        "redacted": True,
    }


def command_status(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    ok = completed.returncode == 0 and bool((completed.stdout or "").strip())
    return {
        "ok": ok,
        "returncode": completed.returncode,
        "reason": "query succeeded" if ok else f"query failed or returned no output (exit {completed.returncode})",
    }


class AzureTimeoutResult:
    def __init__(self, command: list[str], timeout_seconds: int):
        self.returncode = 124
        self.stdout = ""
        self.stderr = f"command timed out after {timeout_seconds}s: {chr(32).join(command)}"


def _redacted(value: str) -> str | None:
    return "[redacted]" if value else None


def _last4(value: str) -> str | None:
    return f"...{value[-4:]}" if len(value) >= 4 else None
