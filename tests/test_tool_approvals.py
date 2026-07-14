from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

from aiplane.audit import AuditLogger
from aiplane.cli import main as cli_main
from aiplane.config import load_profile


def _profile_fixture(root: Path) -> tuple[Path, Path]:
    workspace = root / "workspace"
    workspace.mkdir()
    profiles_dir = root / "profiles"
    shutil.copytree(Path.cwd() / "profile-templates" / "local-dev", profiles_dir / "local-dev")
    return workspace, profiles_dir


def _tool_args(workspace: Path, profiles_dir: Path, *args: str) -> list[str]:
    return [
        "--workspace",
        str(workspace),
        "--profiles-dir",
        str(profiles_dir),
        "tool",
        "--profile",
        "local-dev",
        *args,
    ]


def test_risky_tool_fails_closed_without_explicit_approval() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace, profiles_dir = _profile_fixture(Path(tmp))
        stderr = StringIO()
        with patch("aiplane.approvals.sys.stdin.isatty", return_value=False), redirect_stderr(stderr):
            code = cli_main(_tool_args(workspace, profiles_dir, "write_file", "note.txt", "blocked"))

        assert code == 1
        assert "approval denied" in stderr.getvalue()
        assert not (workspace / "note.txt").exists()
        profile = load_profile("local-dev", workspace, profiles_dir=profiles_dir)
        assert AuditLogger(profile).tail(1)[0]["decision"] == "approval_denied"


def test_yes_explicitly_approves_one_risky_tool_invocation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace, profiles_dir = _profile_fixture(Path(tmp))
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(_tool_args(workspace, profiles_dir, "--yes", "write_file", "note.txt", "approved"))

        assert code == 0
        assert (workspace / "note.txt").read_text(encoding="utf-8") == "approved"
        assert "wrote" in stdout.getvalue()


def test_read_only_tool_does_not_require_yes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace, profiles_dir = _profile_fixture(Path(tmp))
        (workspace / "note.txt").write_text("safe read", encoding="utf-8")
        stdout = StringIO()
        with patch("aiplane.approvals.sys.stdin.isatty", return_value=False), redirect_stdout(stdout):
            code = cli_main(_tool_args(workspace, profiles_dir, "read_file", "note.txt"))

        assert code == 0
        assert stdout.getvalue().strip() == "safe read"
