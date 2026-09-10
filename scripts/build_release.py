"""Build and verify aiplane's immutable wheel/source distribution adapter; never publish."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__:
    from . import version
    from .repository_provenance import write_provenance
    from .verify_release_manifest import ManifestError, sha256, verify_directory
else:
    import version
    from repository_provenance import write_provenance
    from verify_release_manifest import ManifestError, sha256, verify_directory


def build(tag: str, output: Path) -> dict[str, object]:
    version.require_clean_tree()
    current = version.check_versions()
    if tag != f"v{current}" or not version.tag_points_at_head(tag):
        raise ValueError("tag must match package version and HEAD")
    if output.exists() and any(output.iterdir()):
        raise ValueError("build output must be empty")
    if version.run(["git", "cat-file", "-t", f"refs/tags/{tag}"]).stdout.strip() != "tag":
        raise ValueError("Release requires an annotated tag")
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(output)], cwd=version.ROOT, check=True)
    write_provenance(output, version=current, commit=version.run(["git", "rev-parse", "HEAD"]).stdout.strip(), tag=tag)
    artifacts = sorted(output.iterdir())
    (output / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in artifacts), encoding="utf-8")
    entries = verify_directory(output)
    if set(entries) != {f"aiplane-{current}-py3-none-any.whl", f"aiplane-{current}.tar.gz", "provenance.json"}:
        raise ValueError("release artifact names do not match the tested package version")
    return {
        "schema_version": 1,
        "version": current,
        "tag": tag,
        "commit": version.run(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "artifacts": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = args.output.expanduser().resolve()
        if args.verify_only:
            result = {"schema_version": 1, "artifacts": verify_directory(output)}
        else:
            if not args.tag:
                raise ValueError("--tag is required for builds")
            result = build(args.tag, output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, RuntimeError, ManifestError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
