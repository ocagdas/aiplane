from __future__ import annotations

import os
import random
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_HELD_PATHS = threading.local()
_DEFAULT_LOCK_TIMEOUT = 10.0
_DEFAULT_LOCK_POLL = 0.05


class ConcurrentWriteError(RuntimeError):
    pass


class PersistenceLockTimeout(TimeoutError):
    pass


class NestedPersistenceLockError(RuntimeError):
    pass


@contextmanager
def file_lock(
    path: Path,
    *,
    timeout: float = _DEFAULT_LOCK_TIMEOUT,
    poll_interval: float = _DEFAULT_LOCK_POLL,
) -> Iterator[None]:
    if timeout < 0 or poll_interval <= 0:
        raise ValueError("lock timeout must be non-negative and poll interval must be positive")
    path = Path(path).resolve()
    resolved = path
    deadline = time.monotonic() + timeout
    held = getattr(_HELD_PATHS, "value", set())
    if held:
        raise NestedPersistenceLockError("nested persistence locks are forbidden to prevent lock-order deadlocks")
    with _LOCKS_GUARD:
        thread_lock = _LOCKS.setdefault(resolved, threading.RLock())
    if not thread_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise PersistenceLockTimeout(f"timed out waiting for in-process persistence lock: {path}")
    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock_path.open("a+b") as stream:
            while not _try_lock_stream(stream):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PersistenceLockTimeout(f"timed out waiting for persistence lock: {path}")
                time.sleep(min(remaining, poll_interval + random.uniform(0, poll_interval * 0.2)))
            _HELD_PATHS.value = {resolved}
            try:
                yield
            finally:
                _HELD_PATHS.value = set()
                _unlock_stream(stream)
    finally:
        thread_lock.release()


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        _atomic_write_text_unlocked(path, text, encoding=encoding)


def locked_append_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        with path.open("a", encoding=encoding) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())


def atomic_update_json(path: Path, transform: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON state file {path} is invalid") from exc
        else:
            current = {}
        if not isinstance(current, dict):
            raise ValueError(f"JSON state file {path} must contain an object")
        updated = transform(current)
        result = current if updated is None else updated
        if not isinstance(result, dict):
            raise TypeError("JSON transaction must return an object or None")
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        _atomic_write_text_unlocked(path, text, encoding="utf-8")
        return result


def atomic_update_yaml(path: Path, transform: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    from .config import dump_yaml, parse_yaml

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        current = parse_yaml(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(current, dict):
            raise ValueError(f"configuration file {path} must contain a mapping")
        updated = transform(current)
        result = current if updated is None else updated
        if not isinstance(result, dict):
            raise TypeError("YAML transaction must return a mapping or None")
        _atomic_write_text_unlocked(path, dump_yaml(result), encoding="utf-8")
        return result


def atomic_compare_and_swap_text(path: Path, expected: str | None, replacement: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != expected:
            raise ConcurrentWriteError(f"configuration changed concurrently: {path}")
        _atomic_write_text_unlocked(path, replacement, encoding="utf-8")


def _atomic_write_text_unlocked(path: Path, text: str, *, encoding: str) -> None:
    existing_mode = path.stat().st_mode & 0o777 if path.exists() else None
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if existing_mode is not None:
            os.chmod(temporary, existing_mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _try_lock_stream(stream) -> bool:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        if stream.read(1) == b"":
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    import fcntl

    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _unlock_stream(stream) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
