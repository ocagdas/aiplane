from __future__ import annotations

import json
import subprocess
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from aiplane.audit import AuditLogger
from aiplane.cli import main as cli_main
from aiplane.patches import PatchManager

from .profile_fixtures import load_profile


_PATCH = """diff --git a/example.txt b/example.txt
index 1111111..2222222 100644
--- a/example.txt
+++ b/example.txt
@@ -1 +1 @@
-old
+new
"""


class _Runner:
    def __init__(self, *returncodes: int) -> None:
        self.returncodes = list(returncodes) or [0]
        self.commands: list[list[str]] = []

    def run(self, command: list[str], **_kwargs):
        self.commands.append(command)
        returncode = self.returncodes.pop(0) if self.returncodes else 0
        return subprocess.CompletedProcess(command, returncode, "", "")


def _manager(tmp_path: Path, runner: _Runner) -> PatchManager:
    profile = load_profile("local-dev", tmp_path)
    return PatchManager(profile, AuditLogger(profile), command_runner=runner)


def test_inspect_is_workspace_bound_read_only_and_reports_patch_summary(tmp_path: Path) -> None:
    patch = tmp_path / "changes.patch"
    patch.write_text(_PATCH, encoding="utf-8")
    runner = _Runner()

    result = _manager(tmp_path, runner).inspect(patch)

    assert result["mutates"] is False
    assert result["files"] == ["example.txt"]
    assert result["summary"] == {"added_lines": 1, "removed_lines": 1}
    assert result["validation"]["ok"] is True
    assert result["next_action"] == "aiplane patches apply PATH --yes"
    assert runner.commands == [["git", "apply", "--check", "--verbose", "--", str(patch)]]
    assert not (tmp_path / ".aiplane" / "audit" / "local-dev.jsonl").exists()


def test_apply_requires_validation_policy_and_explicit_confirmation(tmp_path: Path) -> None:
    patch = tmp_path / "changes.patch"
    patch.write_text(_PATCH, encoding="utf-8")
    runner = _Runner()
    manager = _manager(tmp_path, runner)

    preview = manager.apply(patch, yes=False)

    assert preview["status"] == "confirmation_required"
    assert preview["mutates"] is False
    assert len(runner.commands) == 1
    audit = AuditLogger(manager.profile).tail()
    assert audit[-1]["decision"] == "confirmation_required"


def test_apply_rechecks_then_uses_git_without_staging_or_committing(tmp_path: Path) -> None:
    patch = tmp_path / "changes.patch"
    patch.write_text(_PATCH, encoding="utf-8")
    runner = _Runner()

    result = _manager(tmp_path, runner).apply(patch, yes=True)

    assert result["status"] == "applied"
    assert result["mutates"] is True
    assert runner.commands[1] == ["git", "apply", "--whitespace=error", "--", str(patch)]
    assert "--index" not in runner.commands[1]
    assert "commit" not in runner.commands[1]


def test_apply_returns_validation_failure_without_attempting_mutation(tmp_path: Path) -> None:
    patch = tmp_path / "changes.patch"
    patch.write_text(_PATCH, encoding="utf-8")
    runner = _Runner(1)

    result = _manager(tmp_path, runner).apply(patch, yes=True)

    assert result["status"] == "validation_failed"
    assert result["mutates"] is False
    assert len(runner.commands) == 1


def test_apply_returns_apply_failed_when_git_rejects_patch_during_apply(tmp_path: Path) -> None:
    patch = tmp_path / "changes.patch"
    patch.write_text(_PATCH, encoding="utf-8")
    runner = _Runner(0, 1)

    result = _manager(tmp_path, runner).apply(patch, yes=True)

    assert result["status"] == "apply_failed"
    assert result["mutates"] is False
    assert len(runner.commands) == 2


def test_apply_respects_local_write_policy_before_mutating(tmp_path: Path) -> None:
    patch = tmp_path / "changes.patch"
    patch.write_text(_PATCH, encoding="utf-8")
    runner = _Runner()
    manager = _manager(tmp_path, runner)
    manager.profile.tools["mode"] = "read_only"

    result = manager.apply(patch, yes=True)

    assert result["status"] == "policy_blocked"
    assert result["mutates"] is False
    assert len(runner.commands) == 1
    assert AuditLogger(manager.profile).tail()[-1]["decision"] == "blocked"


def test_patch_rejects_outside_workspace_unsafe_targets_and_secret_like_content(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.patch"
    outside.write_text(_PATCH, encoding="utf-8")
    with pytest.raises(PermissionError, match="escapes workspace"):
        _manager(tmp_path, _Runner()).inspect(outside)

    unsafe = tmp_path / "unsafe.patch"
    unsafe.write_text(_PATCH.replace("b/example.txt", "b/../outside.txt"), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe target path"):
        _manager(tmp_path, _Runner()).inspect(unsafe)

    git_target = tmp_path / "git-target.patch"
    git_target.write_text(_PATCH.replace("b/example.txt", "b/.git/config"), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe target path"):
        _manager(tmp_path, _Runner()).inspect(git_target)

    secret = tmp_path / "secret.patch"
    secret.write_text(_PATCH + "+api_key=sk-abcdefghijklmnop\n", encoding="utf-8")
    with pytest.raises(ValueError, match="secret-like"):
        _manager(tmp_path, _Runner()).inspect(secret)


def test_cli_exposes_json_inspection_without_apply(tmp_path: Path, monkeypatch) -> None:
    patch = tmp_path / "changes.patch"
    patch.write_text(_PATCH, encoding="utf-8")
    runner = _Runner()
    monkeypatch.setattr("aiplane.cli._COMMAND_RUNNER", runner)
    output = StringIO()

    with redirect_stdout(output):
        code = cli_main(["--workspace", str(tmp_path), "patches", "inspect", "changes.patch", "--profile", "local-dev"])

    assert code == 0
    payload = json.loads(output.getvalue())
    assert payload["record_type"] == "patch_proposal"
    assert payload["mutates"] is False
