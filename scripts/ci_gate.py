"""Fail closed on missing, unsuccessful or malformed CI dependencies."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

REQUIRED_JOBS = ("checks", "compatibility", "install-channels")


def evaluate(results: object) -> dict[str, object]:
    results = results if isinstance(results, dict) else {}
    checks = {}
    for name in dict.fromkeys((*REQUIRED_JOBS, *results)):
        value = results.get(name)
        value = value.get("result") if isinstance(value, dict) else None
        checks[name] = value if isinstance(value, str) else "missing"
    return {"schema_version": 1, "go": all(v == "success" for v in checks.values()), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        results = json.loads(
            args.results.read_text(encoding="utf-8") if args.results else os.getenv("NEEDS_JSON", "null")
        )
    except (OSError, ValueError):
        results = None
    report = {**evaluate(results), "commit": os.getenv("GITHUB_SHA"), "run_id": os.getenv("GITHUB_RUN_ID")}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if output := os.getenv("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"go={str(report['go']).lower()}\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["go"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
