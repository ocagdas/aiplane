"""File-based human judgments bound to saved benchmark outputs and rubrics."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from .benchmark_evidence import validate_measurement_record
from .persistence import atomic_write_text
from .secrets import contains_secret


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def answer_artifact(prompt: str, output: str) -> dict[str, str]:
    return {
        "prompt": prompt,
        "output": output,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def validate_artifact(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(value.get(key), str) for key in ("prompt", "output")):
        raise ValueError("benchmark artifact requires prompt and output text")
    expected = answer_artifact(value["prompt"], value["output"])
    if value != expected:
        raise ValueError("benchmark artifact hash or fields mismatch")
    return expected


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark review inputs must be JSON objects")
    if contains_secret(value):
        raise ValueError("benchmark review input contains secret material")
    return value


def _rubric(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if set(value) != {"name", "version", "instructions", "score_min", "score_max"}:
        raise ValueError("rubric requires name, version, instructions, score_min and score_max only")
    for key in ("name", "version", "instructions"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"rubric {key} must be non-empty text")
    for key in ("score_min", "score_max"):
        if not _number(value[key]):
            raise ValueError(f"rubric {key} must be finite numeric data")
    if value["score_min"] >= value["score_max"]:
        raise ValueError("rubric score_max must exceed score_min")
    return value


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def review_template(records: list[Path], rubric_path: Path, mode: str = "score") -> dict[str, Any]:
    if mode not in {"score", "pairwise"}:
        raise ValueError("review mode must be score or pairwise")
    if not records or (mode == "pairwise" and len(records) != 2):
        raise ValueError("review requires records; pairwise mode requires exactly two records")
    rubric = _rubric(rubric_path)
    items = []
    bindings = []
    groups: list[dict[tuple[str, int], dict[str, Any]]] = []
    seen_records = set()
    for path in records:
        raw = read_json(path)
        record = validate_measurement_record(raw, source=str(path))
        record_hash = digest(raw)
        if record_hash in seen_records:
            raise ValueError("duplicate source record")
        seen_records.add(record_hash)
        if record["dry_run"]:
            raise ValueError("cannot review a dry-run record")
        bindings.append({"sha256": record_hash, "model_name": record["model_name"], "suite": record["suite"]})
        group = {}
        for run in record["runs"]:
            if run.get("error"):
                raise ValueError("cannot review failed model calls")
            key = (run["task"], run["repeat_index"])
            if key in group:
                raise ValueError("duplicate task/repeat in source record")
            artifact = validate_artifact(run.get("artifact"))
            item = {
                "id": digest([record_hash, *key]),
                "record_sha256": record_hash,
                "model_name": record["model_name"],
                "task": key[0],
                "repeat_index": key[1],
                **artifact,
            }
            items.append(item)
            group[key] = item
        groups.append(group)
    judgments: list[dict[str, Any]]
    if mode == "score":
        judgments = [{"id": item["id"], "score": None, "passed": None, "notes": ""} for item in items]
    else:
        if bindings[0]["suite"] != bindings[1]["suite"] or groups[0].keys() != groups[1].keys():
            raise ValueError("pairwise review requires matching suites and task/repeat sets")
        judgments = []
        for key, left in groups[0].items():
            right = groups[1][key]
            if left["prompt_sha256"] != right["prompt_sha256"]:
                raise ValueError("pairwise review requires identical prompts")
            judgments.append({"left": left["id"], "right": right["id"], "preference": None, "notes": ""})
    return {
        "contract_version": "1.0",
        "record_type": "benchmark_review",
        "mode": mode,
        "rubric": rubric,
        "rubric_sha256": digest(rubric),
        "records": bindings,
        "items": items,
        "reviewer": "",
        "reviewed_at": "",
        "judgments": judgments,
    }


def export_review(records: list[Path], rubric: Path, output: Path, *, mode: str = "score", dry_run: bool = True):
    review = review_template(records, rubric, mode)
    if output.exists():
        raise ValueError("review export refuses to overwrite an existing file")
    if output.resolve() in {p.resolve() for p in [*records, rubric]}:
        raise ValueError("review export cannot replace an input")
    if not dry_run:
        atomic_write_text(output, json.dumps(review, indent=2, ensure_ascii=False))
    return {"name": "benchmark_review_export", "written": not dry_run, "destination": str(output), "review": review}


def import_review(workspace: Path, path: Path, records: list[Path], rubric: Path, *, dry_run: bool = True):
    review = read_json(path)
    expected = review_template(records, rubric, str(review.get("mode")))
    mutable = {"reviewer", "reviewed_at", "judgments"}
    if set(review) != set(expected) or any(review[key] != expected[key] for key in expected if key not in mutable):
        raise ValueError("review source/output/rubric identity mismatch; export a new review")
    if not isinstance(review["reviewer"], str) or not review["reviewer"].strip():
        raise ValueError("reviewer must be non-empty text")
    try:
        timestamp = datetime.fromisoformat(review["reviewed_at"])
        if timestamp.utcoffset() is None:
            raise ValueError("missing timezone")
    except (ValueError, TypeError) as exc:
        raise ValueError("reviewed_at must be an ISO timestamp with timezone") from exc
    judgments = review["judgments"]
    if not isinstance(judgments, list) or len(judgments) != len(expected["judgments"]):
        raise ValueError("missing or extra review judgments")
    for actual, template in zip(judgments, expected["judgments"], strict=True):
        if not isinstance(actual, dict) or set(actual) != set(template):
            raise ValueError("review judgment fields mismatch")
        if not isinstance(actual["notes"], str):
            raise ValueError("review notes must be text")
        if review["mode"] == "score":
            if actual["id"] != template["id"]:
                raise ValueError("duplicate, reordered or mismatched review judgment")
            score, passed = actual["score"], actual["passed"]
            if score is None and passed is None:
                raise ValueError("missing score/pass judgment")
            if score is not None and (
                not _number(score) or not review["rubric"]["score_min"] <= score <= review["rubric"]["score_max"]
            ):
                raise ValueError("review score must be finite and within rubric bounds")
            if passed is not None and not isinstance(passed, bool):
                raise ValueError("review passed must be true, false or null")
        else:
            if any(actual[key] != template[key] for key in ("left", "right")):
                raise ValueError("mismatched pairwise output references")
            if actual["preference"] not in ("left", "right", "tie", "abstain"):
                raise ValueError("pairwise preference must be left, right, tie or abstain")
    destination = workspace / ".aiplane" / "reviews" / f"{digest(review)}.json"
    if not dry_run:
        atomic_write_text(destination, json.dumps(review, indent=2, ensure_ascii=False))
    return {
        "name": "benchmark_review_import",
        "written": not dry_run,
        "destination": str(destination),
        "judgment_count": len(judgments),
        "review": review,
        "notes": ["Human judgments remain separate from automatic scores and controlled metric leaders."],
    }
