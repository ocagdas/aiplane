from __future__ import annotations

from pathlib import Path
import tempfile

from aiplane.approvals import ApprovalHandler
from aiplane.audit import AuditLogger
from aiplane.config import load_profile
from aiplane.mcp import AiplaneMcpServer
from aiplane.secrets import REDACTED, contains_secret, redact
from aiplane.tools import ToolExecutor


def test_redact_handles_command_flags_assignments_tokens_and_nested_keys() -> None:
    opaque = "opaque-value-123456789"
    payload = {
        "args": ["client", "--api-key", opaque, "--access_token=second-secret-123", "safe"],
        "Authorization": "Bearer bearer-secret-123456",
        "nested": {"refresh-token": "refresh-secret-123456", "ordinary": "visible"},
        "provider": "sk-abcdefghijklmnop123456",
    }

    redacted = redact(payload)

    assert redacted["args"] == ["client", "--api-key", REDACTED, f"--access_token={REDACTED}", "safe"]
    assert redacted["Authorization"] == REDACTED
    assert redacted["nested"]["refresh-token"] == REDACTED
    assert redacted["nested"]["ordinary"] == "visible"
    assert redacted["provider"] == REDACTED
    assert opaque not in str(redacted)


def test_redact_suppresses_entire_pem_bearing_string() -> None:
    pem = "-----BEGIN PRIVATE KEY-----\nvery-sensitive-body\n-----END PRIVATE KEY-----"
    assert contains_secret(pem)
    assert redact(pem) == REDACTED


def test_tool_audit_redacts_arguments_and_does_not_store_command_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        profile = load_profile("local-dev", Path(tmp))
        audit = AuditLogger(profile)
        executor = ToolExecutor(profile, audit, ApprovalHandler(assume_yes=True))
        secret = "opaque-value-123456789"

        executor.run("write_file", ["note.txt", secret])
        event = audit.tail(1)[0]

        assert event["details"] == {"argument_count": 2, "target": "note.txt"}

        executor.run("run_tests", ["printf", "--api-key", secret])
        event = audit.tail(1)[0]
        assert event["details"] == {"argument_count": 3}
        assert secret not in audit.path.read_text(encoding="utf-8")


def test_mcp_error_response_and_failed_audit_do_not_expose_exception_text(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        server = AiplaneMcpServer(workspace, default_profile="local-dev")
        secret = "opaque-provider-secret-123456"

        def fail(*args, **kwargs):
            raise RuntimeError(f"provider rejected {secret}")

        monkeypatch.setattr(server, "_call_profile_tool", fail)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "aiplane.models.use", "arguments": {"role": "chat", "model": "x"}},
            }
        )

        assert response is not None
        assert secret not in str(response)
        assert "RuntimeError" in response["error"]["message"]
        profile = load_profile("local-dev", workspace)
        event = AuditLogger(profile).tail(1)[0]
        assert event["details"]["error_type"] == "RuntimeError"
        assert secret not in audit_text(profile)


def audit_text(profile) -> str:
    return AuditLogger(profile).path.read_text(encoding="utf-8")
