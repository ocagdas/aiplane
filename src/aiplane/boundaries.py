from __future__ import annotations

import subprocess
from typing import Any, Protocol
from urllib.request import urlopen


class CommandRunner(Protocol):
    def run(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]: ...

    def popen(self, command: list[str], **kwargs: Any) -> subprocess.Popen[str]: ...


class SubprocessCommandRunner:
    """Production command boundary backed by the standard subprocess module."""

    def run(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, **kwargs)

    def popen(self, command: list[str], **kwargs: Any) -> subprocess.Popen[str]:
        return subprocess.Popen(command, **kwargs)


class HttpTransport(Protocol):
    def open(self, request: Any, *, timeout: float): ...


class UrllibHttpTransport:
    """Production HTTP boundary backed by urllib without imposing a client dependency."""

    def open(self, request: Any, *, timeout: float):
        return urlopen(request, timeout=timeout)
