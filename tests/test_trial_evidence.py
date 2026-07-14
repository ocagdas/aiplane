from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validate_trial_evidence import EvidenceError, validate_record


def valid_record() -> dict:
    record = json.loads(Path("docs/project/trial-evidence/template.json").read_text(encoding="utf-8"))
    record["artifact"]["sha256"] = "a" * 64
    record["artifact"]["commit"] = "b" * 40
    return record


def test_completed_canonical_trial_template_validates() -> None:
    validate_record(valid_record())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda record: record.update(classification="internal"), "classification"),
        (lambda record: record["artifact"].update(release_url="http://example.test/release"), "HTTPS"),
        (lambda record: record["commands"][0]["written_paths"].append("/home/person/profile.yaml"), "relative"),
        (lambda record: record["commands"][0].update(command="tool --api-key=secret-value"), "secret"),
        (lambda record: record["sanitization"].update(human_reviewed=False), "sanitization"),
    ],
)
def test_trial_evidence_rejects_unsafe_or_noncanonical_records(mutation, message: str) -> None:
    record = copy.deepcopy(valid_record())
    mutation(record)
    with pytest.raises(EvidenceError, match=message):
        validate_record(record)


def test_failure_index_must_reference_a_recorded_command() -> None:
    record = valid_record()
    record["first_failure"] = {
        "stage": "install",
        "command_index": 4,
        "category": "packaging",
        "sanitized_message": "Installation failed.",
    }
    with pytest.raises(EvidenceError, match="recorded command"):
        validate_record(record)
