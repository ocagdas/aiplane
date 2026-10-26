"""Grade supplied answers offline and retain native plus importable results.

This example does not call a model or claim inference timing. Replace its input
answers with outputs retained by your own provider SDK or agent harness.
"""

import argparse
import hashlib
import json
from pathlib import Path

from grade import grade

from aiplane.benchmark_review import answer_artifact, digest

PRODUCER_VERSION = "1.0"


def evaluate(suite: dict, answers: dict, model: str) -> tuple[dict, dict]:
    tasks = suite["tasks"]
    if set(answers) != set(tasks) or not all(isinstance(value, str) for value in answers.values()):
        raise ValueError("answers must contain exactly one text answer for each task")
    cases = []
    for name, task in tasks.items():
        expected = task["metadata"]["expected_category"]
        urgent = task["metadata"]["expected_urgent"]
        cases.append(
            {
                "task": name,
                "expected": {"category": expected, "urgent": urgent},
                "output": answers[name],
                **grade(answers[name], expected, urgent),
            }
        )
    native = {
        "producer": "support-category-example",
        "version": PRODUCER_VERSION,
        "suite_sha256": digest(suite),
        "answers_sha256": digest(answers),
        "cases": cases,
    }
    record = {
        "contract_version": "1.0",
        "record_type": "benchmark_measurements",
        "model_name": model,
        "suite": {
            "name": suite["name"],
            "version": suite["version"],
            "kind": "quality",
            "content_sha256": digest(tasks),
        },
        "calibration": {"status": "uncontrolled"},
        "runs": [
            {
                "task": case["task"],
                "repeat_index": 1,
                "passed": case["passed"],
                "score": case["score"],
                "quality_score": case["score"],
                "artifact": answer_artifact(tasks[case["task"]]["prompt"], case["output"]),
                "metadata": {"expected_answer": case["expected"]},
            }
            for case in cases
        ],
        "provenance": {
            "source": native["producer"],
            "tool_version": PRODUCER_VERSION,
            "native_result_sha256": digest(native),
            "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "grader_sha256": hashlib.sha256(Path(__file__).with_name("grade.py").read_bytes()).hexdigest(),
        },
    }
    return native, record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answers", type=Path)
    parser.add_argument(
        "--model", required=True, help="Actual profile model alias associated with the supplied outputs"
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="New directory; existing directories are refused"
    )
    args = parser.parse_args()
    suite = json.loads(Path(__file__).with_name("suite.json").read_text(encoding="utf-8"))
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    native, record = evaluate(suite, answers, args.model)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, value in (("native-results.json", native), ("measurements.json", record)):
        (args.output_dir / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps({"passed": sum(case["passed"] for case in native["cases"]), "total": len(native["cases"])}))
