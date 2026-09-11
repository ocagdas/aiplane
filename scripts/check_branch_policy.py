"""Validate the shared main/dev pull-request policy without mutating Git."""

import argparse
import subprocess


def validate(source, target, trunk="main"):
    for branch in (source, target, trunk):
        subprocess.run(["git", "check-ref-format", f"refs/heads/{branch}"], check=True, capture_output=True)
    if target != trunk:
        raise ValueError(f"Pull requests must target {trunk}")
    # Dependency update branches are an explicit automation exception in every repo.
    if not (source.startswith("dev/") or source.startswith("dependabot/")):
        raise ValueError("Use dev/<topic> for development branches (for example dev/fix-config-loading)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--trunk", default="main")
    args = parser.parse_args()
    try:
        validate(args.source, args.target, args.trunk)
    except (ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Branch policy: {error}\n")
    print("Branch policy passed")


if __name__ == "__main__":
    main()
