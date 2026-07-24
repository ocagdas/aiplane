from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts.verify_install_channels import verify_platform_contracts, verify_replacement_cli


class RecordingCli:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], tuple[int, ...]]] = []

    def __call__(self, *arguments: str, expected: tuple[int, ...] = (0,)):
        self.calls.append((arguments, expected))
        if arguments[:3] == ("remote", "tunnel", "plan"):
            payload = {"type": "ssh_tunnel", "command": ["ssh", "-N"]}
        else:
            payload = {"name": "unsupported_platform"}
        return SimpleNamespace(stdout=json.dumps(payload))


@pytest.mark.parametrize(
    ("system", "expected_commands"),
    [
        ("Linux", [("remote", "tunnel", "plan")]),
        (
            "Darwin",
            [
                ("remote", "tunnel", "plan"),
                ("runtimes", "install", "ollama", "--dry-run"),
            ],
        ),
        (
            "Windows",
            [
                ("remote", "tunnel", "plan"),
                ("runtimes", "install", "ollama", "--dry-run"),
                ("remote", "tunnel", "start"),
            ],
        ),
    ],
)
def test_platform_contracts_never_start_supported_tunnels(
    system: str,
    expected_commands: list[tuple[str, ...]],
) -> None:
    cli = RecordingCli()

    verify_platform_contracts(cli, system=system)

    commands = [arguments for arguments, _ in cli.calls]
    for expected in expected_commands:
        assert any(arguments[: len(expected)] == expected for arguments in commands)
    assert any(arguments[:3] == ("remote", "tunnel", "plan") for arguments in commands)
    if system != "Windows":
        assert not any(arguments[:3] == ("remote", "tunnel", "start") for arguments in commands)


def test_platform_contracts_require_expected_unsupported_exit_codes() -> None:
    cli = RecordingCli()

    verify_platform_contracts(cli, system="Windows")

    expected_by_command = {arguments[:3]: expected for arguments, expected in cli.calls}
    assert expected_by_command[("runtimes", "install", "ollama")] == (2,)
    assert expected_by_command[("remote", "tunnel", "start")] == (2,)


class ReplacementCli:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command, *, env, cwd, expected=(0,)):
        arguments = tuple(command[1:])
        self.calls.append(arguments)
        if arguments == ("--version",):
            output = "aiplane 0.0.0\ninstall_type: wheel\n"
        elif arguments == ("profiles", "templates"):
            output = "local-dev\n"
        elif arguments == ("profiles", "validate", "local-dev"):
            assert expected == (0, 1)
            output = json.dumps(
                {
                    "name": "local-dev",
                    "ok": False,
                    "checks": [
                        {"name": "schema:hardware", "ok": True},
                        {"name": "schema:models", "ok": True},
                        {"name": "model_default:chat_model", "ok": True},
                        {"name": "contract:model_model:portable_smoke", "ok": True},
                    ],
                }
            )
        elif arguments == ("mcp", "manifest"):
            output = json.dumps({"name": "aiplane-mcp", "transport": "stdio"})
        else:
            raise AssertionError(arguments)
        return SimpleNamespace(stdout=output)


def test_replacement_smoke_uses_installed_entrypoint_and_persisted_profile(tmp_path, monkeypatch) -> None:
    cli = ReplacementCli()
    monkeypatch.setattr("scripts.verify_install_channels.run", cli)
    command = tmp_path / "aiplane"
    verify_replacement_cli(command, env={}, workspace=tmp_path / "workspace")
    assert cli.calls == [
        ("--version",),
        ("profiles", "templates"),
        ("profiles", "validate", "local-dev"),
        ("mcp", "manifest"),
    ]
