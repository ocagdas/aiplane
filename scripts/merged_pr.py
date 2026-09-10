"""Detect a merged PR for the exact repository, commit and selected trunk."""

import argparse
import json
import os
import re
import subprocess


def merged(pages, repository, trunk):
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("Expected paginated PR arrays")
    found = False
    for page in pages:
        for item in page:
            if not isinstance(item, dict) or not isinstance(item.get("base"), dict):
                raise ValueError("Malformed PR response")
            base = item["base"]
            owner = base.get("repo")
            if not isinstance(owner, dict):
                raise ValueError("Missing PR base repository")
            found |= bool(item.get("merged_at")) and base.get("ref") == trunk and owner.get("full_name") == repository
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--trunk", required=True)
    args = parser.parse_args()
    repository = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.source):
        raise ValueError("Invalid repository or source identity")
    response = subprocess.check_output(
        ["gh", "api", "--paginate", "--slurp", f"/repos/{repository}/commits/{args.source}/pulls"],
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    print(str(merged(json.loads(response), repository, args.trunk)).lower())


if __name__ == "__main__":
    main()
