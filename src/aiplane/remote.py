from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Any, Protocol

from .boundaries import CommandRunner, SubprocessCommandRunner
from .models import Profile
from .network_validation import (
    ssh_forward_host,
    validate_http_endpoint,
    validate_port,
    validate_ssh_host,
    validate_ssh_user,
)

_STATE_VERSION = 1


class ProcessInspector(Protocol):
    def capture(self, pid: int) -> dict[str, Any] | None: ...

    def matches(self, pid: int, identity: dict[str, Any]) -> bool: ...

    def terminate_if_matches(self, pid: int, identity: dict[str, Any]) -> bool: ...


class SystemProcessInspector:
    """Capture and verify process identity before signalling a stored PID."""

    def __init__(self, command_runner: CommandRunner | None = None):
        self.command_runner = command_runner or SubprocessCommandRunner()

    def capture(self, pid: int) -> dict[str, Any] | None:
        if pid <= 0:
            return None
        proc_identity = _linux_proc_identity(pid)
        if proc_identity is not None:
            return proc_identity
        if os.name == "posix":
            return self._ps_identity(pid)
        return None

    def matches(self, pid: int, identity: dict[str, Any]) -> bool:
        current = self.capture(pid)
        return current is not None and current == identity

    def terminate_if_matches(self, pid: int, identity: dict[str, Any]) -> bool:
        pidfd_open = getattr(os, "pidfd_open", None)
        pidfd_send_signal = getattr(signal, "pidfd_send_signal", None)
        if callable(pidfd_open) and callable(pidfd_send_signal):
            try:
                pidfd = pidfd_open(pid)
            except OSError:
                return False
            try:
                if not self.matches(pid, identity):
                    return False
                pidfd_send_signal(pidfd, signal.SIGTERM)
                return True
            except OSError:
                return False
            finally:
                os.close(pidfd)

        if not self.matches(pid, identity):
            return False
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except OSError:
            return False

    def _ps_identity(self, pid: int) -> dict[str, Any] | None:
        try:
            result = self.command_runner.run(
                ["ps", "-p", str(pid), "-o", "lstart=", "-o", "command="],
                check=False,
                text=True,
                capture_output=True,
            )
        except OSError:
            return None
        output = str(result.stdout or "").strip()
        if result.returncode != 0 or not output:
            return None
        return {"source": "posix_ps", "fingerprint": hashlib.sha256(output.encode("utf-8")).hexdigest()}


class RemoteManager:
    def __init__(
        self,
        profile: Profile,
        command_runner: CommandRunner | None = None,
        process_inspector: ProcessInspector | None = None,
    ):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.process_inspector = process_inspector or SystemProcessInspector(self.command_runner)
        self.config = profile.targets or {}

    def tunnel_plan(self, name: str) -> dict[str, Any]:
        target = self._target(name)
        if target.get("type") != "ssh_tunnel":
            raise ValueError(f"target {name!r} is not an ssh_tunnel target")

        ssh = _dict(target.get("ssh"))
        forward = _dict(target.get("forward"))

        host = validate_ssh_host(ssh.get("host"), "ssh.host")
        user = validate_ssh_user(ssh.get("user"), "ssh.user")
        ssh_port = validate_port(ssh.get("port"), "ssh.port", default=22)
        local_host = validate_ssh_host(forward.get("local_host"), "forward.local_host", default="127.0.0.1")
        local_port = validate_port(forward.get("local_port"), "forward.local_port", default=11434)
        remote_host = validate_ssh_host(forward.get("remote_host"), "forward.remote_host", default="127.0.0.1")
        remote_port = validate_port(forward.get("remote_port"), "forward.remote_port", default=11434)

        endpoint = validate_http_endpoint(
            target.get("endpoint") or f"http://localhost:{local_port}/v1",
            f"ssh_tunnel target {name!r} endpoint",
        )

        destination = f"{user + '@' if user else ''}{host}"
        command = [
            "ssh",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
            "-L",
            f"{ssh_forward_host(local_host)}:{local_port}:{ssh_forward_host(remote_host)}:{remote_port}",
            "-p",
            str(ssh_port),
            destination,
        ]
        return {
            "target": name,
            "type": "ssh_tunnel",
            "required_tools": ["ssh"],
            "tool_available": shutil.which("ssh") is not None,
            "command": command,
            "state_file": str(self._state_file(name)),
            "endpoint": endpoint,
            "connection": {
                "local_bind": f"{local_host}:{local_port}",
                "remote_service": f"{remote_host}:{remote_port}",
                "ide_endpoint": endpoint,
                "ssh_destination": destination,
                "ssh_port": ssh_port,
            },
            "notes": [
                "This is SSH local port forwarding (-L), not a reverse tunnel.",
                "Your IDE connects to ide_endpoint on this machine; ssh forwards traffic to remote_service from the remote machine's point of view.",
                "Keep the tunnel process running while using the forwarded endpoint.",
                "Use this for individual access; use VPN/gateway/APIM for shared team endpoints.",
            ],
        }

    def tunnel_status(self, name: str) -> dict[str, Any]:
        plan = self.tunnel_plan(name)
        state_file = self._state_file(name)
        try:
            state = _read_state(state_file, expected_target=name)
        except ValueError as exc:
            return {
                "target": name,
                "running": False,
                "pid": None,
                "state": "invalid",
                "state_error": str(exc),
                "state_file": str(state_file),
                "endpoint": plan["endpoint"],
                "command": plan["command"],
            }
        if state is None:
            state_name = "absent"
            running = False
            pid = None
        else:
            stored_pid = int(state["pid"])
            running = self.process_inspector.matches(stored_pid, state["identity"])
            pid = stored_pid if running else None
            state_name = "running" if running else "stale_or_reused"
        return {
            "target": name,
            "running": running,
            "pid": pid,
            "state": state_name,
            "state_file": str(state_file),
            "endpoint": plan["endpoint"],
            "command": plan["command"],
        }

    def tunnel_start(self, name: str, yes: bool = False) -> dict[str, Any]:
        if not yes:
            raise PermissionError(
                "remote tunnel start is mutating; run remote tunnel plan first or use the CLI start command when ready"
            )
        status = self.tunnel_status(name)
        if status["state"] == "invalid":
            raise RuntimeError(f"tunnel state is invalid; inspect or remove {status['state_file']}")
        if status["running"]:
            return {"target": name, "status": "already_running", **status}

        plan = self.tunnel_plan(name)
        if not plan["tool_available"]:
            raise RuntimeError("ssh is not available on PATH")

        state_file = self._state_file(name)
        log_file = self._log_file(name)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("ab") as log:
            process = self.command_runner.popen(
                plan["command"],
                cwd=self.profile.workspace,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        identity = self.process_inspector.capture(process.pid)
        if identity is None:
            terminate = getattr(process, "terminate", None)
            if callable(terminate):
                terminate()
            raise RuntimeError("could not capture SSH process identity; tunnel was terminated and state was not saved")
        state = {
            "version": _STATE_VERSION,
            "target": name,
            "pid": process.pid,
            "identity": identity,
            "command": plan["command"],
        }
        _write_state(state_file, state)
        return {
            "target": name,
            "status": "started",
            "pid": process.pid,
            "state": "running",
            "state_file": str(state_file),
            "log_file": str(log_file),
            "endpoint": plan["endpoint"],
            "command": plan["command"],
        }

    def tunnel_stop(self, name: str, yes: bool = False) -> dict[str, Any]:
        if not yes:
            raise PermissionError("remote tunnel stop is mutating; use the CLI stop command when ready")
        state_file = self._state_file(name)
        try:
            state = _read_state(state_file, expected_target=name)
        except ValueError as exc:
            raise RuntimeError(f"tunnel state is invalid; refusing to signal any process: {exc}") from exc
        if state is None:
            return {"target": name, "status": "not_running", "state_file": str(state_file)}

        pid = int(state["pid"])
        stopped = self.process_inspector.terminate_if_matches(pid, state["identity"])
        status = "stopped" if stopped else "stale_or_reused_state_removed"
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass
        return {"target": name, "status": status, "pid": pid, "state_file": str(state_file)}

    def _state_dir(self) -> Path:
        return self.profile.workspace / ".aiplane" / "remote"

    def _state_file(self, name: str) -> Path:
        return self._state_dir() / f"{_state_name(name)}.json"

    def _log_file(self, name: str) -> Path:
        return self._state_dir() / f"{_state_name(name)}.log"

    def _target(self, name: str) -> dict[str, Any]:
        targets = self.config.get("targets", {})
        if not isinstance(targets, dict):
            raise ValueError("profile has no targets")
        target = targets.get(name)
        if not isinstance(target, dict):
            raise ValueError(f"unknown remote target: {name}")
        return target


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _linux_proc_identity(pid: int) -> dict[str, Any] | None:
    stat_path = Path("/proc") / str(pid) / "stat"
    cmdline_path = Path("/proc") / str(pid) / "cmdline"
    try:
        stat = stat_path.read_text(encoding="utf-8")
        close_paren = stat.rfind(")")
        if close_paren < 0:
            return None
        fields = stat[close_paren + 2 :].split()
        if len(fields) <= 19 or fields[0] == "Z":
            return None
        start_time_ticks = fields[19]
        command = [part.decode("utf-8", errors="replace") for part in cmdline_path.read_bytes().split(b"\0") if part]
    except OSError:
        return None
    if not command:
        return None
    return {"source": "linux_proc", "start_time_ticks": start_time_ticks, "command": command}


def _read_state(path: Path, *, expected_target: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(state, dict):
        raise ValueError(f"state file {path} is not a JSON object")
    if state.get("version") != _STATE_VERSION:
        raise ValueError(f"state file {path} has unsupported version")
    if state.get("target") != expected_target:
        raise ValueError(f"state file {path} belongs to a different target")
    pid = state.get("pid")
    identity = state.get("identity")
    command = state.get("command")
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError(f"state file {path} has an invalid pid")
    if not isinstance(identity, dict) or not identity:
        raise ValueError(f"state file {path} has no process identity")
    if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
        raise ValueError(f"state file {path} has an invalid command")
    return state


def _write_state(path: Path, state: dict[str, Any]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _state_name(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "tunnel"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:48]}-{digest}"
