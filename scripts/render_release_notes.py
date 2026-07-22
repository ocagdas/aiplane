#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


class ReleaseNotesError(ValueError):
    pass


def unreleased_notes(changelog: str) -> str:
    match = re.search(r"(?ms)^## Unreleased\s*\n(?P<body>.*?)(?=^## |\Z)", changelog)
    if not match:
        raise ReleaseNotesError("CHANGELOG.md must contain an Unreleased section")
    body = match.group("body").strip()
    if not body or not re.search(r"(?m)^- \S", body):
        raise ReleaseNotesError("the Unreleased section must contain at least one change")
    return body


def render_notes(tag: str, change_kind: str, commit: str, changelog: str, checksums: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag):
        raise ReleaseNotesError(f"invalid release tag: {tag}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseNotesError("commit must be a full lowercase Git SHA")
    manifest_rows = [line for line in checksums.splitlines() if line.strip()]
    if len(manifest_rows) != 2:
        raise ReleaseNotesError("SHA256SUMS must identify exactly one wheel and one source distribution")
    changes = unreleased_notes(changelog)
    return f"""# aiplane {tag}

Validated {change_kind} release artifacts for `{tag}` from commit `{commit}`.

> aiplane is pre-1.0. Review the changes and preserve your profile YAML before upgrading.

## Changes

{changes}

## Verify before installation

Download the wheel, source distribution, and `SHA256SUMS` from this release, then run:

```bash
python scripts/verify_release_manifest.py .
gh attestation verify aiplane-* --repo ocagdas/aiplane
```

The checksum manifest verifies file integrity. The GitHub artifact attestation separately verifies the repository and workflow that built the distributions.

## Upgrade and rollback

Use the same installation owner for install, upgrade, and uninstall. The complete pip, pipx, and uv commands plus the rollback procedure are in `docs/user/setup.md`; release operations and recovery rules are in `docs/project/ci-and-release-process.md`.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render deterministic release notes from the tracked changelog")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--change-kind", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = render_notes(
        args.tag,
        args.change_kind,
        args.commit,
        args.changelog.read_text(encoding="utf-8"),
        args.checksums.read_text(encoding="utf-8"),
    )
    args.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
