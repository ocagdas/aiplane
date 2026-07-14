from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aiplane.audit import AuditLogger
from aiplane.cli import main as cli_main
from aiplane.config import load_profile
from aiplane.mcp import AiplaneMcpServer, MUTATING_TOOL_NAMES, TOOL_SCHEMAS


def _message(name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def test_every_mutating_schema_exposes_per_call_confirmation() -> None:
    assert MUTATING_TOOL_NAMES
    for name in MUTATING_TOOL_NAMES:
        confirm = TOOL_SCHEMAS[name]["properties"]["confirm"]
        assert confirm["type"] == "boolean"
        assert confirm["default"] is False


def test_read_only_server_blocks_mutation_before_manager_dispatch(tmp_path: Path, monkeypatch) -> None:
    server = AiplaneMcpServer(tmp_path, default_profile="local-dev")
    dispatched = False

    def dispatch(*args, **kwargs):
        nonlocal dispatched
        dispatched = True
        return {"unexpected": True}

    monkeypatch.setattr(server, "_call_profile_tool", dispatch)
    response = server.handle_message(_message("aiplane.models.use", {"role": "chat", "model": "x", "confirm": True}))

    assert response is not None
    assert response["error"]["message"].startswith("PermissionError")
    assert not dispatched
    profile = load_profile("local-dev", tmp_path)
    event = AuditLogger(profile).tail(1)[0]
    assert event["decision"] == "blocked"
    assert event["details"] == {"reason": "server_read_only"}


def test_write_enabled_server_still_requires_per_call_confirmation(tmp_path: Path, monkeypatch) -> None:
    server = AiplaneMcpServer(tmp_path, default_profile="local-dev", allow_writes=True)
    dispatched = False

    def dispatch(*args, **kwargs):
        nonlocal dispatched
        dispatched = True
        return {"unexpected": True}

    monkeypatch.setattr(server, "_call_profile_tool", dispatch)
    response = server.handle_message(_message("aiplane.hardware.use", {"template": "local_cpu"}))

    assert response is not None
    assert response["error"]["message"].startswith("PermissionError")
    assert not dispatched
    profile = load_profile("local-dev", tmp_path)
    event = AuditLogger(profile).tail(1)[0]
    assert event["details"] == {"reason": "confirmation_required"}


def test_both_guards_allow_dispatch_and_confirmation_is_not_forwarded(tmp_path: Path, monkeypatch) -> None:
    server = AiplaneMcpServer(tmp_path, default_profile="local-dev", allow_writes=True)
    received = None

    def dispatch(name, arguments, profile):
        nonlocal received
        received = arguments
        return {"ok": True}

    monkeypatch.setattr(server, "_call_profile_tool", dispatch)
    response = server.handle_message(
        _message("aiplane.models.use", {"role": "chat", "model": "fixture-chat-small", "confirm": True})
    )

    assert response is not None
    assert response["result"]["structuredContent"] == {"ok": True}
    assert received == {"role": "chat", "model": "fixture-chat-small"}
    profile = load_profile("local-dev", tmp_path)
    assert AuditLogger(profile).tail(1)[0]["decision"] == "allowed"


def test_refresh_dry_run_remains_available_on_read_only_server(tmp_path: Path, monkeypatch) -> None:
    server = AiplaneMcpServer(tmp_path, default_profile="local-dev")
    received = None

    def dispatch(name, arguments, profile):
        nonlocal received
        received = arguments
        return {"write": False}

    monkeypatch.setattr(server, "_call_profile_tool", dispatch)
    response = server.handle_message(_message("aiplane.models.refresh", {"provider": "all", "dry_run": True}))

    assert response is not None
    assert response["result"]["structuredContent"] == {"write": False}
    assert received == {"provider": "all", "dry_run": True}
    profile = load_profile("local-dev", tmp_path)
    assert AuditLogger(profile).tail() == []


@pytest.mark.parametrize(
    ("extra", "expected"),
    [([], False), (["--allow-writes"], True)],
)
def test_mcp_serve_cli_passes_operator_write_mode(extra: list[str], expected: bool) -> None:
    with patch("aiplane.cli_governance.serve_stdio", return_value=0) as serve:
        assert cli_main(["mcp", "serve", "--profile", "local-dev", *extra]) == 0
    assert serve.call_args.kwargs["allow_writes"] is expected
