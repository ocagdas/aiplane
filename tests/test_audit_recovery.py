from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile

import pytest

from aiplane.audit import AuditLogger
from aiplane.cli import main as cli_main
from aiplane.config import load_profile


def _event(action: str) -> str:
    return json.dumps(
        {
            "timestamp": "2026-07-14T12:00:00+00:00",
            "event_type": "test",
            "profile": "local-dev",
            "action": action,
            "decision": "allowed",
            "details": {},
        },
        sort_keys=True,
    )


def test_tail_skips_malformed_records_and_returns_requested_valid_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        profile = load_profile("local-dev", Path(tmp))
        audit = AuditLogger(profile)
        audit.path.write_text(
            f"{_event('first')}\n{{not-json}}\n{_event('second')}\n",
            encoding="utf-8",
        )

        report = audit.tail_report(2)

        assert [event["action"] for event in report.events] == ["first", "second"]
        assert report.malformed_records == 1
        assert report.warnings == [{"line": 2, "kind": "malformed_record", "error": "JSONDecodeError"}]
        assert audit.tail(2) == report.events


def test_tail_classifies_unterminated_malformed_final_record_as_truncated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        profile = load_profile("local-dev", Path(tmp))
        audit = AuditLogger(profile)
        audit.path.write_text(f'{_event("complete")}\n{{"timestamp":', encoding="utf-8")

        report = audit.tail_report(1)

        assert [event["action"] for event in report.events] == ["complete"]
        assert report.warnings[0]["kind"] == "truncated_final_record"
        assert report.warnings[0]["line"] == 2


def test_tail_rejects_non_object_json_and_invalid_limits() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        profile = load_profile("local-dev", Path(tmp))
        audit = AuditLogger(profile)
        audit.path.write_text(f"{_event('complete')}\n[]\n", encoding="utf-8")

        report = audit.tail_report(1)

        assert [event["action"] for event in report.events] == ["complete"]
        assert report.warnings == [{"line": 2, "kind": "malformed_record", "error": "ValueError"}]
        with pytest.raises(ValueError, match="zero or greater"):
            audit.tail_report(-1)
        with pytest.raises(ValueError, match="zero or greater"):
            audit.tail_report(1, warning_limit=-1)


def test_audit_tail_cli_keeps_stdout_machine_readable_and_warns_on_stderr() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir()
        profiles_dir = root / "profiles"
        shutil.copytree(Path.cwd() / "profile-templates" / "local-dev", profiles_dir / "local-dev")
        profile = load_profile("local-dev", workspace, profiles_dir=profiles_dir)
        audit = AuditLogger(profile)
        secret_fragment = "sensitive-corrupt-content"
        audit.path.write_text(f"{_event('visible')}\n{{{secret_fragment}", encoding="utf-8")
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(
                [
                    "--workspace",
                    str(workspace),
                    "--profiles-dir",
                    str(profiles_dir),
                    "audit",
                    "tail",
                    "--profile",
                    "local-dev",
                    "--limit",
                    "1",
                ]
            )

        assert code == 0
        assert json.loads(stdout.getvalue())["action"] == "visible"
        assert "truncated_final_record at line 2" in stderr.getvalue()
        assert secret_fragment not in stderr.getvalue()
