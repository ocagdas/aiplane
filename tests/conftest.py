from __future__ import annotations

import ipaddress
import socket

import pytest


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
