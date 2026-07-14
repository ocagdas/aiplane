from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from aiplane.config import load_profile
from aiplane.machines import MachineManager
from aiplane.network_validation import (
    ssh_forward_host,
    validate_http_endpoint,
    validate_port,
    validate_ssh_host,
    validate_ssh_user,
)
from aiplane.remote import RemoteManager


@pytest.mark.parametrize("value", ["-oProxyCommand=evil", "host name", "user@host", "bad_name", "host/command", ""])
def test_ssh_host_rejects_option_like_and_malformed_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_ssh_host(value)


@pytest.mark.parametrize("value", ["example.com", "host-1.internal", "127.0.0.1", "2001:db8::1", "[2001:db8::1]"])
def test_ssh_host_accepts_and_canonicalizes_supported_host_forms(value: str) -> None:
    assert validate_ssh_host(value)


@pytest.mark.parametrize("value", ["-root", "bad user", "user@host", "user:pass", "user/part"])
def test_ssh_user_rejects_option_like_and_separator_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_ssh_user(value)


def test_port_rejects_boolean_float_and_out_of_range_values() -> None:
    for value in (True, "22.0", 0, 65536):
        with pytest.raises(ValueError):
            validate_port(value, "ssh.port")


@pytest.mark.parametrize(
    "value",
    [
        "ssh://host:22/v1",
        "file:///tmp/socket",
        "http://user:secret@host/v1",
        "http://-option/v1",
        "http://host:70000/v1",
        "http://host/v1#secret",
        "http://host name/v1",
    ],
)
def test_endpoint_rejects_non_http_credentials_and_malformed_authorities(value: str) -> None:
    with pytest.raises(ValueError):
        validate_http_endpoint(value)


@pytest.mark.parametrize("value", ["http://localhost:11434/v1", "https://api.example.com/v1?mode=chat"])
def test_endpoint_accepts_http_and_https_paths(value: str) -> None:
    assert validate_http_endpoint(value) == value


def test_ipv6_forward_hosts_are_bracketed() -> None:
    assert ssh_forward_host("2001:db8::1") == "[2001:db8::1]"
    assert ssh_forward_host("example.com") == "example.com"


def test_tunnel_plan_rejects_option_like_host_before_building_command() -> None:
    profile = load_profile("local-dev", Path.cwd())
    profile.targets["targets"]["gpu_workstation_ssh"]["ssh"]["host"] = "-Fmalicious-config"
    with pytest.raises(ValueError, match="must not start"):
        RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")


def test_remote_profile_plan_validates_destination_and_quotes_remote_name() -> None:
    profile = load_profile("local-dev", Path.cwd())
    manager = MachineManager(profile)
    with pytest.raises(ValueError, match="must not start"):
        manager.profile_remote_plan("gpu", "-Fmalicious-config", "dev")

    plan = manager.profile_remote_plan("gpu; echo unsafe", "gpu.example.com", "dev")
    remote_command = plan["steps"][1]["command"][-1]
    assert shlex.split(remote_command)[-1] == "gpu; echo unsafe"
    assert remote_command != "aiplane hardware export-machine --profile local-dev --name gpu; echo unsafe"
    assert plan["steps"][1]["command"][-2] == "dev@gpu.example.com"
