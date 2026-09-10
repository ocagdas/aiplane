"""Validate same-run, same-commit GO evidence before a completed-CI listener proceeds."""

import argparse
import json
from pathlib import Path
import re


def verify(value, *, commit, run_id, required):
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit) or not run_id or not required:
        raise ValueError("Expected commit, run and required jobs must be explicit")
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported evidence schema")
    if value.get("go") is not True or value.get("commit") != commit or value.get("run_id") != run_id:
        raise ValueError("Evidence is not GO for the expected commit/run")
    checks = value.get("checks")
    if (
        not isinstance(checks, dict)
        or not set(required) <= checks.keys()
        or any(v != "success" for v in checks.values())
    ):
        raise ValueError("Missing or unsuccessful quality dependency")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--required", nargs="+", required=True)
    args = parser.parse_args()
    verify(
        json.loads(args.report.read_text(encoding="utf-8")),
        commit=args.commit,
        run_id=args.run_id,
        required=args.required,
    )
    print("Quality evidence matches the expected successful run")


if __name__ == "__main__":
    main()
