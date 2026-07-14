from __future__ import annotations

from pathlib import Path
import multiprocessing
import stat
import tempfile
import threading

import pytest

from aiplane.config import parse_yaml
from aiplane.persistence import (
    NestedPersistenceLockError,
    PersistenceLockTimeout,
    atomic_update_yaml,
    atomic_write_text,
    file_lock,
)


def test_atomic_write_preserves_permissions_and_leaves_no_temporary_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("old: true\n", encoding="utf-8")
        path.chmod(0o640)

        atomic_write_text(path, "new: true\n")

        assert path.read_text(encoding="utf-8") == "new: true\n"
        assert stat.S_IMODE(path.stat().st_mode) == 0o640
        assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_transactional_yaml_updates_do_not_lose_concurrent_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        atomic_write_text(path, "values:\n  seed: false\n")
        barrier = threading.Barrier(3)
        errors: list[BaseException] = []

        def update(name: str) -> None:
            try:
                barrier.wait()

                def transform(config):
                    config.setdefault("values", {})[name] = True
                    return config

                atomic_update_yaml(path, transform)
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=update, args=(name,)) for name in ("first", "second")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=5)

        assert not errors
        assert not any(thread.is_alive() for thread in threads)
        assert parse_yaml(path.read_text(encoding="utf-8"))["values"] == {"first": True, "second": True, "seed": False}


def _hold_process_lock(path: str, entered, release) -> None:
    with file_lock(Path(path)):
        entered.set()
        release.wait(timeout=5)


def test_ipc_lock_timeout_is_bounded_and_recovers_after_process_exit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        context = multiprocessing.get_context("spawn")
        entered = context.Event()
        release = context.Event()
        process = context.Process(target=_hold_process_lock, args=(str(path), entered, release))
        process.start()
        try:
            assert entered.wait(timeout=3)
            with pytest.raises(PersistenceLockTimeout):
                with file_lock(path, timeout=0.1, poll_interval=0.01):
                    pass
        finally:
            release.set()
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        assert process.exitcode == 0
        with file_lock(path, timeout=0.2):
            pass


def test_lock_timeout_is_bounded_and_lock_recovers_after_release() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        entered = threading.Event()
        release = threading.Event()

        def holder() -> None:
            with file_lock(path):
                entered.set()
                release.wait(timeout=5)

        thread = threading.Thread(target=holder)
        thread.start()
        assert entered.wait(timeout=2)
        with pytest.raises(PersistenceLockTimeout):
            with file_lock(path, timeout=0.05, poll_interval=0.01):
                pass
        release.set()
        thread.join(timeout=2)
        assert not thread.is_alive()
        with file_lock(path, timeout=0.2):
            pass


def test_nested_locks_are_rejected_instead_of_deadlocking() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        first = Path(tmp) / "first.yaml"
        second = Path(tmp) / "second.yaml"
        with file_lock(first):
            with pytest.raises(NestedPersistenceLockError):
                with file_lock(second):
                    pass


def test_production_code_does_not_bypass_atomic_text_persistence() -> None:
    violations = []
    for path in Path("src/aiplane").glob("*.py"):
        if path.name == "persistence.py":
            continue
        if ".write_text(" in path.read_text(encoding="utf-8"):
            violations.append(str(path))
    assert violations == []
