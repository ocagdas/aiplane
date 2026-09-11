"""Verify downloaded assets against the selected tag and checkout; never publish.

MIT licensed; standards/repository/v1/LICENSE. Installation is a separate product job.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys


def verify(directory, tag, commit):
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(root / "scripts/build_release.py"), "--verify-only", "--output", str(directory)],
        check=True,
    )
    value = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if (
        value["build_kind"] != "release"
        or value["tag"] != tag
        or value["source_commit"] != commit
        or value["version_commit"] != commit
    ):
        raise ValueError("Downloaded release does not match selected tag/commit")
    return {
        "schema_version": 1,
        "tag": tag,
        "source_commit": commit,
        "checks": {"downloaded_artifacts": "success"},
        "artifacts": value["artifacts"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.directory.resolve(), args.tag, args.commit)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
