from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

from .models import Profile


class RemoteManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.config = profile.targets or {}

    def tunnel_plan(self, name: str) -> dict[str, Any]:
        target = self._target(name)
        if target.get("type") != "ssh_tunnel":
            raise ValueError(f"target {name!r} is not an ssh_tunnel target")
        ssh = _dict(target.get("ssh"))
        forward = _dict(target.get("forward"))
        host = str(ssh.get("host") or "")
        user = str(ssh.get("user") or "")
        ssh_port = int(ssh.get("port") or 22)
        local_host = str(forward.get("local_host") or "127.0.0.1")
        local_port = int(forward.get("local_port") or 11434)
        remote_host = str(forward.get("remote_host") or "127.0.0.1")
        remote_port = int(forward.get("remote_port") or 11434)
        if not host:
            raise ValueError(f"ssh_tunnel target {name!r} is missing ssh.host")
        destination = f"{user + '@' if user else ''}{host}"
        command = [
            "ssh",
            "-N",
            "-L",
            f"{local_host}:{local_port}:{remote_host}:{remote_port}",
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
            "pid_file": str(self._pid_file(name)),
            "endpoint": target.get("endpoint") or f"http://localhost:{local_port}/v1",
            "connection": {
                "local_bind": f"{local_host}:{local_port}",
                "remote_service": f"{remote_host}:{remote_port}",
                "ide_endpoint": target.get("endpoint") or f"http://localhost:{local_port}/v1",
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
        pid_file = self._pid_file(name)
        pid = _read_pid(pid_file)
        running = _pid_running(pid) if pid is not None else False
        return {
            "target": name,
            "running": running,
            "pid": pid if running else None,
            "pid_file": str(pid_file),
            "endpoint": plan["endpoint"],
            "command": plan["command"],
        }

    def tunnel_start(self, name: str, yes: bool = False) -> dict[str, Any]:
        if not yes:
            raise PermissionError("remote tunnel start is mutating; run remote tunnel plan first or use the CLI start command when ready")
        status = self.tunnel_status(name)
        if status["running"]:
            return {"target": name, "status": "already_running", **status}
        plan = self.tunnel_plan(name)
        if not plan["tool_available"]:
            raise RuntimeError("ssh is not available on PATH")
        pid_file = self._pid_file(name)
        log_file = self._log_file(name)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("ab") as log:
            process = subprocess.Popen(plan["command"], cwd=self.profile.workspace, stdout=log, stderr=log, start_new_session=True)
        pid_file.write_text(str(process.pid), encoding="utf-8")
        return {"target": name, "status": "started", "pid": process.pid, "pid_file": str(pid_file), "log_file": str(log_file), "endpoint": plan["endpoint"], "command": plan["command"]}

    def tunnel_stop(self, name: str, yes: bool = False) -> dict[str, Any]:
        if not yes:
            raise PermissionError("remote tunnel stop is mutating; use the CLI stop command when ready")
        pid_file = self._pid_file(name)
        pid = _read_pid(pid_file)
        if pid is None:
            return {"target": name, "status": "not_running", "pid_file": str(pid_file)}
        if _pid_running(pid):
            os.kill(pid, signal.SIGTERM)
            status = "stopped"
        else:
            status = "stale_pid_removed"
        try:
            pid_file.unlink()
        except FileNotFoundError:
            pass
        return {"target": name, "status": status, "pid": pid, "pid_file": str(pid_file)}

    def _state_dir(self) -> Path:
        return self.profile.workspace / ".aiplane" / "remote"

    def _pid_file(self, name: str) -> Path:
        return self._state_dir() / f"{_safe_name(name)}.pid"

    def _log_file(self, name: str) -> Path:
        return self._state_dir() / f"{_safe_name(name)}.log"

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


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "tunnel"
