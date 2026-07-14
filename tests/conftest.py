from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest


_TEST_PROFILES_TEMP = tempfile.TemporaryDirectory(prefix="aiplane-tests-")
_TEST_PROFILES_ROOT = Path(_TEST_PROFILES_TEMP.name) / "profiles"
shutil.copytree(Path.cwd() / "profile-templates", _TEST_PROFILES_ROOT)
os.environ["AIPLANE_TEST_PROFILES_DIR"] = str(_TEST_PROFILES_ROOT)


def _is_loopback_host(host: str) -> bool:
    candidate = host.strip().lower()
    if candidate in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_create_connection = socket.create_connection

    def guarded_create_connection(address, *args, **kwargs):
        host = str(address[0] if isinstance(address, tuple) else address)
        if not _is_loopback_host(host):
            raise OSError(f"external network access blocked during tests: {host}")
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
