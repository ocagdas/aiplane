from __future__ import annotations

import io
from contextlib import redirect_stderr
from unittest.mock import patch

from aiplane.cli import main
from aiplane.secrets import REDACTED


class UnexpectedFailure(Exception):
    pass


def _run_with_failure(error: BaseException, argv: list[str] | None = None) -> tuple[int, str]:
    stderr = io.StringIO()
    with patch("aiplane.cli._main", side_effect=error), redirect_stderr(stderr):
        code = main([] if argv is None else argv)
    return code, stderr.getvalue()


def test_expected_error_message_is_redacted() -> None:
    secret = "synthetic-secret-123456"
    code, stderr = _run_with_failure(ValueError(f"api_key={secret}"))
    assert code == 1
    assert secret not in stderr
    assert REDACTED in stderr
    assert "Traceback" not in stderr


def test_unexpected_error_is_type_only_without_debug() -> None:
    secret = "opaque-internal-value-123456"
    code, stderr = _run_with_failure(UnexpectedFailure(secret))
    assert code == 1
    assert secret not in stderr
    assert "unexpected UnexpectedFailure" in stderr
    assert "--debug" in stderr
    assert "Traceback" not in stderr


def test_debug_is_explicit_and_prints_traceback() -> None:
    secret = "explicit-debug-context-123456"
    code, stderr = _run_with_failure(UnexpectedFailure(secret), ["--debug"])
    assert code == 1
    assert "Traceback" in stderr
    assert secret in stderr


def test_debug_environment_opt_in_prints_traceback(monkeypatch) -> None:
    monkeypatch.setenv("AIPLANE_DEBUG", "true")
    code, stderr = _run_with_failure(UnexpectedFailure("debug-environment-context"))
    assert code == 1
    assert "Traceback" in stderr


def test_broken_pipe_exits_cleanly_without_error_text() -> None:
    code, stderr = _run_with_failure(BrokenPipeError())
    assert code == 0
    assert stderr == ""


def test_keyboard_interrupt_uses_conventional_exit_status() -> None:
    code, stderr = _run_with_failure(KeyboardInterrupt())
    assert code == 130
    assert stderr == "error: interrupted\n"
