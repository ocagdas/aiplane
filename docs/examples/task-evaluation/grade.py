"""Example user-authored grader; compares the category value, not its presence."""

import json
import sys
from pathlib import Path


def grade(output: str, expected: str, urgent: bool) -> dict:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = None
    passed = (
        isinstance(parsed, dict)
        and parsed.get("category") == expected
        and isinstance(parsed.get("urgent"), bool)
        and parsed["urgent"] == urgent
    )
    return {"score": 100 if passed else 0, "passed": passed}


if __name__ == "__main__":
    print(json.dumps(grade(Path(sys.argv[1]).read_text(encoding="utf-8"), sys.argv[2], sys.argv[3] == "true")))
