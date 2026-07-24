from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading

import pytest

from aiplane.config import load_profile
from aiplane.remote import RemoteManager, _state_name


class FakeInspector:
    def __init__(self) -> None:
        self.identity: dict[str, object] | None = {"source": "fake", "start": "original"}
        self.terminated: list[int] = []

    def capture(self, pid: int) -> dict[str, object] | None:
        return dict(self.identity) if self.identity is not None else None

    def matches(self, pid: int, identity: dict[str, object]) -> bool:
        return self.identity is not None and identity == self.identity

    def terminate_if_matches(self, pid: int, identity: dict[str, object]) -> bool:
        if not self.matches(pid, identity):
            return False
        self.terminated.append(pid)
        return True


class FakeProcess:
    pid = 4242

    def __init__(self) -> None:
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True


class FakeRunner:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process

    def popen(self, command: list[str], **kwargs):
        return self.process

    def run(self, command: list[str], **kwargs):  # pragma: no cover - inspector is injected
        raise AssertionError("unexpected command")


def _manager(workspace: Path, inspector: FakeInspector, process: FakeProcess | None = None) -> RemoteManager:
    profile = load_profile("local-dev", workspace)
    return RemoteManager(profile, command_runner=FakeRunner(process or FakeProcess()), process_inspector=inspector)


def test_reused_pid_is_never_signalled_and_stale_state_is_removed(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        inspector = FakeInspector()
        manager = _manager(Path(tmp), inspector)
        monkeypatch.setattr("aiplane.remote.shutil.which", lambda _: "/usr/bin/ssh")
        started = manager.tunnel_start("gpu_workstation_ssh", yes=True)
        inspector.identity = {"source": "fake", "start": "reused"}

        status = manager.tunnel_status("gpu_workstation_ssh")
        stopped = manager.tunnel_stop("gpu_workstation_ssh", yes=True)

        assert not status["running"]
        assert status["state"] == "stale_or_reused"
        assert stopped["status"] == "stale_or_reused_state_removed"
        assert inspector.terminated == []
        assert not Path(started["state_file"]).exists()


def test_invalid_state_is_preserved_and_stop_refuses_to_signal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        inspector = FakeInspector()
        manager = _manager(Path(tmp), inspector)
        state_file = manager._state_file("gpu_workstation_ssh")
        state_file.parent.mkdir(parents=True)
        state_file.write_text("{broken", encoding="utf-8")

        status = manager.tunnel_status("gpu_workstation_ssh")
        with pytest.raises(RuntimeError, match="refusing to signal"):
            manager.tunnel_stop("gpu_workstation_ssh", yes=True)

        assert status["state"] == "invalid"
        assert state_file.exists()
        assert inspector.terminated == []


def test_start_requires_captured_identity_and_cleans_up_unowned_process(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        inspector = FakeInspector()
        inspector.identity = None
        process = FakeProcess()
        manager = _manager(Path(tmp), inspector, process)
        monkeypatch.setattr("aiplane.remote.shutil.which", lambda _: "/usr/bin/ssh")

        with pytest.raises(RuntimeError, match="could not capture SSH process identity"):
            manager.tunnel_start("gpu_workstation_ssh", yes=True)

        assert process.terminated
        assert not manager._state_file("gpu_workstation_ssh").exists()


def test_state_names_are_collision_resistant_and_state_is_versioned_json(monkeypatch) -> None:
    assert _state_name("a-b") != _state_name("a_b")
    assert _state_name("same") == _state_name("same")

    with tempfile.TemporaryDirectory() as tmp:
        inspector = FakeInspector()
        manager = _manager(Path(tmp), inspector)
        monkeypatch.setattr("aiplane.remote.shutil.which", lambda _: "/usr/bin/ssh")
        started = manager.tunnel_start("gpu_workstation_ssh", yes=True)
        state = json.loads(Path(started["state_file"]).read_text(encoding="utf-8"))

        assert state["version"] == 1
        assert state["target"] == "gpu_workstation_ssh"
        assert state["pid"] == 4242
        assert state["identity"] == inspector.identity
        assert not list(Path(started["state_file"]).parent.glob("*.tmp"))


def test_concurrent_tunnel_starts_launch_only_one_process(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        inspector = FakeInspector()
        process = FakeProcess()
        manager = _manager(Path(tmp), inspector, process)
        calls = 0
        calls_lock = threading.Lock()
        original_popen = manager.command_runner.popen

        def counted_popen(command: list[str], **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            return original_popen(command, **kwargs)

        monkeypatch.setattr(manager.command_runner, "popen", counted_popen)
        monkeypatch.setattr("aiplane.remote.shutil.which", lambda _: "/usr/bin/ssh")
        barrier = threading.Barrier(3)
        results: list[dict[str, object]] = []

        def start() -> None:
            barrier.wait()
            results.append(manager.tunnel_start("gpu_workstation_ssh", yes=True))

        threads = [threading.Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=3)

        assert not any(thread.is_alive() for thread in threads)
        assert calls == 1
        assert sorted(result["status"] for result in results) == ["already_running", "started"]


def test_start_terminates_tunnel_when_state_write_fails(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        inspector = FakeInspector()
        process = FakeProcess()
        manager = _manager(Path(tmp), inspector, process)
        monkeypatch.setattr("aiplane.remote.shutil.which", lambda _: "/usr/bin/ssh")

        def fail_write(*_args, **_kwargs) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("aiplane.remote._write_state", fail_write)
        with pytest.raises(RuntimeError, match="could not persist SSH tunnel state"):
            manager.tunnel_start("gpu_workstation_ssh", yes=True)

        assert process.terminated
        assert not manager._state_file("gpu_workstation_ssh").exists()
