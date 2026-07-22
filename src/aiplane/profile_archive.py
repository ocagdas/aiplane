from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .config import CONFIG_FILES, parse_yaml, profiles_root
from .persistence import atomic_write_text, file_lock
from .secrets import contains_secret


PROFILE_ARCHIVE_KIND = "aiplane.profile-archive"
PROFILE_ARCHIVE_VERSION = "1.0"
PROVIDER_CONFIG_FILE = "model-providers.yaml"
PORTABLE_PROFILE_FILES = tuple(sorted((*CONFIG_FILES.values(), PROVIDER_CONFIG_FILE)))
REQUIRED_PROFILE_FILES = frozenset(CONFIG_FILES.values())
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_PROFILE_FILE_BYTES = 2 * 1024 * 1024

EXCLUDED_PROFILE_STATE = (
    {
        "path": "models.discovered.yaml",
        "reason": "generated provider discovery cache; recreate it with models refresh",
    },
    {
        "path": "model-providers.user.yaml",
        "reason": "ignored machine-local provider overrides; review and recreate them separately",
    },
    {
        "path": ".aiplane/**",
        "reason": "credentials, audit records, sessions, tunnels, and local CLI state are machine-owned",
    },
    {
        "path": "runtime/model data",
        "reason": "model weights, runtime caches, and runtime lifecycle state remain with their owning runtime",
    },
    {
        "path": "generated exports",
        "reason": "regenerate target-tool configuration from the restored profile",
    },
)

_RAW_SECRET_KEYS = {
    "apikey",
    "accesstoken",
    "refreshtoken",
    "token",
    "bearertoken",
    "password",
    "secret",
    "clientsecret",
    "privatekey",
    "authorization",
    "connectionstring",
    "sastoken",
}


def archive_profile(
    name: str,
    output: Path | str,
    *,
    profiles_dir: Path | str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    _validate_simple_name(name, "profile name")
    source = profiles_root(profiles_dir) / name
    if not source.is_dir():
        raise ValueError(f"unknown profile: {name}")

    output_path = Path(output).expanduser().resolve()
    if _is_within(output_path, source.resolve()):
        raise ValueError("profile archive output must be outside the source profile directory")

    archive = _build_archive(name, source)
    serialized = json.dumps(archive, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    digest = _sha256(serialized)
    conflicts = ["output_exists"] if output_path.exists() and not overwrite else []
    if conflicts and not dry_run:
        raise ValueError(f"archive output already exists: {output_path}; pass --overwrite to replace it")
    if not dry_run:
        atomic_write_text(output_path, serialized)

    return {
        "name": "profile_archive",
        "profile": name,
        "path": str(output_path),
        "schema_version": PROFILE_ARCHIVE_VERSION,
        "dry_run": dry_run,
        "overwrite": overwrite,
        "written": not dry_run,
        "would_write": dry_run and not conflicts,
        "conflicts": conflicts,
        "archive_sha256": digest,
        "manifest": archive["manifest"],
        "next_steps": (
            [f"Pass --overwrite to replace the existing archive at {output_path}."]
            if conflicts
            else (
                [f"Review {output_path} before storing or sharing it."]
                if not dry_run
                else [f"Run without --dry-run to write {output_path}."]
            )
        ),
    }


def snapshot_profile(
    name: str,
    *,
    profiles_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Return the validated portable archive document without writing it."""
    _validate_simple_name(name, "profile name")
    source = profiles_root(profiles_dir) / name
    if not source.is_dir():
        raise ValueError(f"unknown profile: {name}")
    return _build_archive(name, source)


def restore_profile_archive(
    archive_path: Path | str,
    *,
    name: str | None = None,
    profiles_dir: Path | str | None = None,
    dry_run: bool = False,
    yes: bool = False,
) -> dict[str, Any]:
    source = Path(archive_path).expanduser().resolve()
    archive = load_profile_archive(source)
    source_name = str(archive["profile"])
    target_name = name or source_name
    _validate_simple_name(target_name, "restored profile name")

    root = profiles_root(profiles_dir)
    destination = root / target_name
    preview = dry_run or not yes
    conflicts = ["profile_exists"] if destination.exists() else []
    if conflicts and yes and not dry_run:
        raise ValueError(
            f"profile already exists: {target_name}; existing profiles are never overwritten, so restore with --as NAME"
        )

    included = [entry["path"] for entry in archive["files"]]
    result = {
        "name": "profile_restore",
        "archive": str(source),
        "source_profile": source_name,
        "profile": target_name,
        "path": str(destination),
        "schema_version": PROFILE_ARCHIVE_VERSION,
        "dry_run": preview,
        "requires_yes": not yes,
        "restored": False,
        "would_restore": preview and not conflicts,
        "conflicts": conflicts,
        "included_files": included,
        "excluded": archive["manifest"]["excluded"],
        "next_steps": [],
    }
    if conflicts:
        result["next_steps"] = ["Choose a new destination with --as NAME; existing profiles are never overwritten."]
        return result
    if preview:
        result["next_steps"] = [f"Run with --yes to restore profile {target_name}."]
        return result

    root.mkdir(parents=True, exist_ok=True)
    with file_lock(destination):
        if destination.exists():
            raise ValueError(
                f"profile already exists: {target_name}; restore to a new name so the existing profile is preserved"
            )
        temporary = Path(tempfile.mkdtemp(prefix=f".{target_name}.restore.", dir=root))
        try:
            for entry in archive["files"]:
                _write_new_profile_file(temporary / entry["path"], entry["content"])
            os.rename(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    result["dry_run"] = False
    result["requires_yes"] = False
    result["restored"] = True
    result["would_restore"] = False
    result["next_steps"] = [
        f"Run aiplane profiles validate {target_name}.",
        f"Run aiplane doctor --profile {target_name} to assess destination drift.",
    ]
    return result


def load_profile_archive(path: Path | str) -> dict[str, Any]:
    archive_path = Path(path).expanduser().resolve()
    if not archive_path.is_file():
        raise ValueError(f"profile archive not found: {archive_path}")
    size = archive_path.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        raise ValueError(f"profile archive exceeds {MAX_ARCHIVE_BYTES} bytes")
    try:
        payload = json.loads(archive_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid profile archive JSON: {archive_path}") from exc
    return validate_profile_archive(payload)


def validate_profile_archive(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("profile archive must be a JSON object")
    if payload.get("kind") != PROFILE_ARCHIVE_KIND:
        raise ValueError(f"profile archive kind must be {PROFILE_ARCHIVE_KIND!r}")
    if payload.get("schema_version") != PROFILE_ARCHIVE_VERSION:
        raise ValueError(f"unsupported profile archive schema_version: {payload.get('schema_version')!r}")
    profile_name = payload.get("profile")
    if not isinstance(profile_name, str):
        raise ValueError("profile archive profile must be a string")
    _validate_simple_name(profile_name, "archived profile name")

    files = payload.get("files")
    manifest = payload.get("manifest")
    if not isinstance(files, list) or not isinstance(manifest, dict):
        raise ValueError("profile archive files must be a list and manifest must be an object")
    if manifest.get("excluded") != list(EXCLUDED_PROFILE_STATE):
        raise ValueError("profile archive exclusion manifest does not match the supported v1 contract")

    validated_files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise ValueError("profile archive file entries must be objects")
        filename = raw.get("path")
        content = raw.get("content")
        checksum = raw.get("sha256")
        size_bytes = raw.get("size_bytes")
        if not isinstance(filename, str) or filename not in PORTABLE_PROFILE_FILES:
            raise ValueError(f"profile archive contains unsupported path: {filename!r}")
        if filename in seen:
            raise ValueError(f"profile archive contains duplicate path: {filename}")
        if not isinstance(content, str) or not isinstance(checksum, str) or not isinstance(size_bytes, int):
            raise ValueError(f"profile archive file metadata is invalid: {filename}")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_PROFILE_FILE_BYTES:
            raise ValueError(f"profile archive file exceeds {MAX_PROFILE_FILE_BYTES} bytes: {filename}")
        if size_bytes != len(encoded) or checksum != _sha256(content):
            raise ValueError(f"profile archive checksum or size mismatch: {filename}")
        _validate_profile_content(filename, content)
        seen.add(filename)
        validated_files.append({"path": filename, "size_bytes": size_bytes, "sha256": checksum, "content": content})

    missing = sorted(REQUIRED_PROFILE_FILES - seen)
    if missing:
        raise ValueError(f"profile archive is missing required files: {', '.join(missing)}")
    validated_files.sort(key=lambda entry: entry["path"])
    expected_included = [_file_metadata(entry) for entry in validated_files]
    if manifest.get("included") != expected_included:
        raise ValueError("profile archive included-file manifest does not match file records")
    return {
        "kind": PROFILE_ARCHIVE_KIND,
        "schema_version": PROFILE_ARCHIVE_VERSION,
        "profile": profile_name,
        "manifest": {"included": expected_included, "excluded": list(EXCLUDED_PROFILE_STATE)},
        "files": validated_files,
    }


def _build_archive(name: str, source: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for filename in PORTABLE_PROFILE_FILES:
        path = source / filename
        if not path.exists() and filename not in REQUIRED_PROFILE_FILES:
            continue
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"portable profile file must be a regular non-symlink file: {filename}")
        content = path.read_text(encoding="utf-8")
        _validate_profile_content(filename, content)
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_PROFILE_FILE_BYTES:
            raise ValueError(f"profile file exceeds {MAX_PROFILE_FILE_BYTES} bytes: {filename}")
        records.append({"path": filename, "size_bytes": len(encoded), "sha256": _sha256(content), "content": content})
    missing = sorted(REQUIRED_PROFILE_FILES - {entry["path"] for entry in records})
    if missing:
        raise ValueError(f"profile is missing required portable files: {', '.join(missing)}")
    return {
        "kind": PROFILE_ARCHIVE_KIND,
        "schema_version": PROFILE_ARCHIVE_VERSION,
        "profile": name,
        "manifest": {
            "included": [_file_metadata(entry) for entry in records],
            "excluded": list(EXCLUDED_PROFILE_STATE),
        },
        "files": records,
    }


def _validate_profile_content(filename: str, content: str) -> None:
    try:
        parsed = parse_yaml(content)
    except ValueError as exc:
        raise ValueError(f"portable profile file is not valid YAML: {filename}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"portable profile file must contain a mapping: {filename}")
    credential_path = _raw_secret_path(parsed) or _embedded_credential_path(parsed) or _credential_line_path(content)
    if credential_path:
        raise ValueError(
            f"portable profile file contains forbidden credential material in {filename} at {credential_path}; "
            "use an environment-variable or credential reference"
        )


def _raw_secret_path(value: Any, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, inner in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            current = f"{path}.{key}"
            if normalized in _RAW_SECRET_KEYS and inner not in (None, "", [], {}):
                return current
            found = _raw_secret_path(inner, current)
            if found:
                return found
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found = _raw_secret_path(inner, f"{path}[{index}]")
            if found:
                return found
    return None


def _embedded_credential_path(value: Any, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, inner in value.items():
            found = _embedded_credential_path(inner, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found = _embedded_credential_path(inner, f"{path}[{index}]")
            if found:
                return found
    elif isinstance(value, str) and contains_secret(value):
        return path
    return None


def _credential_line_path(content: str) -> str | None:
    for line_number, line in enumerate(content.splitlines(), start=1):
        if contains_secret(line):
            return f"$line[{line_number}]"
    return None


def _file_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    return {"path": entry["path"], "size_bytes": entry["size_bytes"], "sha256": entry["sha256"]}


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"profile archive contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_simple_name(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a simple directory name")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_new_profile_file(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)
