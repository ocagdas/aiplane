#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path, PurePosixPath

LINE_RE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


class ManifestError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = LINE_RE.fullmatch(line)
        if not match:
            raise ManifestError(f"invalid SHA256SUMS line {number}")
        digest, name = match.groups()
        path = PurePosixPath(name)
        if path.is_absolute() or len(path.parts) != 1 or name in {".", ".."}:
            raise ManifestError(f"unsafe manifest path on line {number}")
        if name in entries:
            raise ManifestError(f"duplicate manifest entry: {name}")
        entries[name] = digest
    if not entries:
        raise ManifestError("SHA256SUMS is empty")
    return entries


def verify_directory(directory: Path, *, require_release_pair: bool = True) -> dict[str, str]:
    manifest = directory / "SHA256SUMS"
    if not manifest.is_file():
        raise ManifestError("SHA256SUMS is missing")
    entries = parse_manifest(manifest.read_text(encoding="utf-8"))
    wheels = [name for name in entries if name.endswith(".whl")]
    sdists = [name for name in entries if name.endswith(".tar.gz")]
    if require_release_pair and (len(wheels) != 1 or len(sdists) != 1):
        raise ManifestError("release manifest must contain exactly one wheel and one source distribution")
    for name, expected in entries.items():
        path = directory / name
        if not path.is_file():
            raise ManifestError(f"manifest artifact is missing: {name}")
        actual = sha256(path)
        if actual != expected:
            raise ManifestError(f"checksum mismatch: {name}")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an aiplane release SHA256SUMS manifest portably.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--wheel-only", action="store_true", help="Do not require a source distribution")
    args = parser.parse_args()
    try:
        entries = verify_directory(args.directory, require_release_pair=not args.wheel_only)
    except (OSError, ManifestError) as exc:
        parser.error(str(exc))
    print(f"verified {len(entries)} release artifact(s) in {args.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
