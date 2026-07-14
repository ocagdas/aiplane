from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from typing import Callable

from aiplane.cli import main as cli_main


@dataclass(frozen=True)
class CliResult:
    code: int
    stdout: str
    stderr: str


def run_cli(arguments: list[str], *, main: Callable[[list[str]], int] = cli_main) -> CliResult:
    """Run the in-process CLI while capturing both output streams."""
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(arguments)
    return CliResult(code=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())
