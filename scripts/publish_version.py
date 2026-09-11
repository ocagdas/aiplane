"""Publish only a tested trunk tip, using one atomic branch/tag push in disposable CI."""

from __future__ import annotations

import argparse
import json
import sys

if __package__:
    from . import version
else:
    import version


def git(*args: str) -> str:
    return version.run(["git", *args]).stdout.strip()


def publish(source: str, trunk: str, *, merged: bool = False) -> dict[str, object]:
    version.require_clean_tree()
    return version.shared.publish(
        source,
        trunk,
        git=git,
        current=version.check_versions,
        classify=lambda value: version.classify_ci(merged=value),
        write=version.write_version,
        tag=version.create_tag,
        files=version.VERSION_FILES,
        merged=merged,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--trunk", required=True)
    parser.add_argument("--merged", action="store_true")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = publish(args.source, args.trunk, merged=args.merged)
        print(json.dumps(result, sort_keys=True))
        if args.github_output:
            version.write_github_outputs(result)
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
