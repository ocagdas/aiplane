#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / ".aiplane" / "wheelhouse"
LOCAL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+\+g[0-9a-f]{7}\.[0-9]{8}t[0-9]{6}z$")


def run(command: list[str], *, expected: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode not in expected:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def project_version(source: Path = ROOT) -> str:
    return tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def local_snapshot_version(base_version: str, commit: str | None, built_at: datetime) -> str:
    sha = (commit or "0000000")[:7].lower()
    if not re.fullmatch(r"[0-9a-f]{7}", sha):
        sha = "0000000"
    stamp = built_at.strftime("%Y%m%dt%H%M%Sz").lower()
    version = f"{base_version}+g{sha}.{stamp}"
    if not LOCAL_VERSION_RE.fullmatch(version):
        raise ValueError(f"generated local snapshot version is invalid: {version}")
    return version


def patch_source_version(source: Path, version: str) -> None:
    pyproject = source / "pyproject.toml"
    package_init = source / "src" / "aiplane" / "__init__.py"
    pyproject_text = pyproject.read_text(encoding="utf-8")
    init_text = package_init.read_text(encoding="utf-8")
    pyproject.write_text(
        re.sub(r'(?m)^version = "[^"]+"$', f'version = "{version}"', pyproject_text, count=1), encoding="utf-8"
    )
    package_init.write_text(
        re.sub(r'(?m)^__version__ = "[^"]+"$', f'__version__ = "{version}"', init_text, count=1), encoding="utf-8"
    )


def copy_source_tree(destination: Path) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        ignored = {
            ".git",
            ".aiplane",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "__pycache__",
            "build",
            "dist",
            "htmlcov",
        }
        return {name for name in names if name in ignored or name.endswith(".egg-info")}

    shutil.copytree(ROOT, destination, ignore=ignore)


def git_output(args: list[str], fallback: str | None = None) -> str | None:
    completed = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return fallback
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256sums(paths: list[Path], output_dir: Path) -> Path:
    manifest = output_dir / "SHA256SUMS"
    lines = [f"{sha256(path)}  {path.name}" for path in sorted(paths)]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a local, ignored aiplane wheel snapshot.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help="Output directory for local wheel artifacts")
    parser.add_argument("--clean", action="store_true", help="Delete the output directory before building")
    parser.add_argument(
        "--validate-pip",
        action="store_true",
        help="Validate the built wheel through the pip install-channel verifier",
    )
    args = parser.parse_args(argv)

    try:
        output_dir = args.out_dir.expanduser().resolve()
        if args.clean and output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        base_version = project_version()
        commit = git_output(["rev-parse", "HEAD"], fallback=None)
        branch = git_output(["rev-parse", "--abbrev-ref", "HEAD"], fallback=None)
        status = git_output(["status", "--porcelain"], fallback="") or ""
        dirty = bool(status.strip())
        source = "local_dirty_checkout" if dirty else "local_clean_checkout"
        built_at = datetime.now(timezone.utc)
        version = local_snapshot_version(base_version, commit, built_at)

        run([sys.executable, "-m", "pip", "install", "build"])
        with tempfile.TemporaryDirectory(prefix="aiplane-local-wheel-") as tmp:
            build_source = Path(tmp) / "source"
            copy_source_tree(build_source)
            patch_source_version(build_source, version)
            completed = subprocess.run(
                [sys.executable, "-m", "build", "--wheel", "--outdir", str(output_dir)],
                cwd=build_source,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"command failed ({completed.returncode}): python -m build --wheel --outdir {output_dir}\n"
                    f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                )
        wheels = sorted(output_dir.glob("aiplane-*.whl"))
        if not wheels:
            raise RuntimeError(f"no wheel produced in {output_dir}")
        wheel = max(wheels, key=lambda path: path.stat().st_mtime)
        if f"-{version}-" not in wheel.name:
            raise RuntimeError(f"wheel filename {wheel.name!r} does not contain local snapshot version {version!r}")

        manifest = write_sha256sums([wheel], output_dir)
        provenance = {
            "base_version": base_version,
            "version": version,
            "version_source": source,
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
            "built_at": built_at.isoformat(),
            "wheel": wheel.name,
            "sha256sums": manifest.name,
            "output_dir": str(output_dir),
            "note": "Local wheel snapshot for developer testing; version uses PEP 440 local metadata from base version, git SHA, and UTC timestamp. Not a GitHub Release artifact and not an immutable CI artifact.",
        }
        (output_dir / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        if args.validate_pip:
            run([sys.executable, "scripts/verify_install_channels.py", str(output_dir), "--channel", "pip"])

        print(json.dumps(provenance, indent=2, sort_keys=True))
        print(f"\nWheel: {wheel}")
        print(f"Install with: python -m pip install --force-reinstall {wheel}")
        print(f"Or:          pipx install --force {wheel}")
        print(f"Or:          uv tool install --force {wheel}")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
