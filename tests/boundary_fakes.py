from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any


class FakeCommandRunner:
    """Deterministic command boundary that records every requested operation."""

    def __init__(
        self,
        *,
        stdout: str = "{}",
        stderr: str = "",
        returncode: int = 0,
        run_handler: Callable[[list[str], dict[str, Any]], subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.run_handler = run_handler
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    @property
    def commands(self) -> list[list[str]]:
        return [command for command, _kwargs in self.calls]

    def run(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        if self.run_handler is not None:
            return self.run_handler(command, kwargs)
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)

    def popen(self, command: list[str], **kwargs: Any):
        raise AssertionError(f"popen was not expected: {command!r}")


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class FakeHttpTransport:
    """Deterministic HTTP boundary with request recording and queued payloads."""

    def __init__(self, *payloads: object) -> None:
        self.payloads = list(payloads) or [{"data": [{"id": "synthetic-model"}]}]
        self.requests: list[tuple[object, float]] = []

    def open(self, request: object, *, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        if not self.payloads:
            raise AssertionError("unexpected HTTP request: no synthetic payload remains")
        return FakeResponse(self.payloads.pop(0))
