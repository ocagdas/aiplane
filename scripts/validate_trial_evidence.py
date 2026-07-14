#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

CLASSIFICATIONS = {"rehearsal", "independent"}
WORKFLOWS = {"primary-adoption", "local-only-replay", "remote-gpu", "no-clone-install"}
CHANNELS = {"pip", "pipx", "uv-tool"}
SANITIZATION_FIELDS = {
    "no_credentials_or_tokens",
    "no_personal_identifiers",
    "no_private_hosts_or_account_ids",
    "relative_written_paths_only",
    "human_reviewed",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|token|secret)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~-]{8,}"),
)


class EvidenceError(ValueError):
    pass


def object_at(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{field} must be an object")
    return value


def text_at(mapping: dict[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be non-empty text")
    return value


def number_at(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise EvidenceError(f"{field} must be a non-negative number")


def strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def validate_record(value: Any) -> None:
    record = object_at(value, "record")
    if record.get("record_version") != 1:
        raise EvidenceError("record_version must be 1")
    text_at(record, "trial_id")
    if record.get("classification") not in CLASSIFICATIONS:
        raise EvidenceError("invalid classification")
    if record.get("workflow") not in WORKFLOWS:
        raise EvidenceError("invalid workflow")
    artifact = object_at(record.get("artifact"), "artifact")
    url = artifact.get("release_url")
    if url is not None:
        parsed = urlsplit(url) if isinstance(url, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise EvidenceError("artifact.release_url must be a credential-free HTTPS URL or null")
    text_at(artifact, "version")
    if not re.fullmatch(r"[0-9a-f]{64}", text_at(artifact, "sha256")):
        raise EvidenceError("artifact.sha256 must be 64 lowercase hexadecimal characters")
    if not re.fullmatch(r"[0-9a-f]{40}", text_at(artifact, "commit")):
        raise EvidenceError("artifact.commit must be a full lowercase commit SHA")
    environment = object_at(record.get("environment"), "environment")
    for field in ("os", "os_version", "architecture", "python", "runtime", "model"):
        text_at(environment, field)
    if environment.get("install_channel") not in CHANNELS:
        raise EvidenceError("invalid install channel")
    start = object_at(record.get("start_state"), "start_state")
    for field in ("clean_machine_or_vm", "repository_checkout_present", "existing_profile"):
        if not isinstance(start.get(field), bool):
            raise EvidenceError(f"start_state.{field} must be boolean")
    text_at(start, "notes")
    timing = object_at(record.get("timing"), "timing")
    text_at(timing, "started_at")
    text_at(timing, "ended_at")
    number_at(timing.get("elapsed_seconds"), "timing.elapsed_seconds")
    commands = record.get("commands")
    if not isinstance(commands, list) or not commands:
        raise EvidenceError("commands must be a non-empty list")
    for index, raw in enumerate(commands):
        command = object_at(raw, f"commands[{index}]")
        text_at(command, "command")
        text_at(command, "outcome")
        if isinstance(command.get("exit_code"), bool) or not isinstance(command.get("exit_code"), int):
            raise EvidenceError(f"commands[{index}].exit_code must be an integer")
        number_at(command.get("elapsed_seconds"), f"commands[{index}].elapsed_seconds")
        paths = command.get("written_paths")
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            raise EvidenceError(f"commands[{index}].written_paths must be strings")
        if any(PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute() for path in paths):
            raise EvidenceError("written_paths must be relative")
    failure = record.get("first_failure")
    if failure is not None:
        failure = object_at(failure, "first_failure")
        for field in ("stage", "category", "sanitized_message"):
            text_at(failure, field)
        index = failure.get("command_index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(commands):
            raise EvidenceError("first_failure.command_index must identify a recorded command")
    assistance = object_at(record.get("assistance"), "assistance")
    if not isinstance(assistance.get("beyond_written_workflow"), bool):
        raise EvidenceError("assistance flag must be boolean")
    text_at(assistance, "details")
    outcome = object_at(record.get("outcome"), "outcome")
    for field in ("completed", "files_written_understood", "export_non_mutating_understood"):
        if not isinstance(outcome.get(field), bool):
            raise EvidenceError(f"outcome.{field} must be boolean")
    text_at(outcome, "feedback")
    sanitization = object_at(record.get("sanitization"), "sanitization")
    if set(sanitization) != SANITIZATION_FIELDS or not all(value is True for value in sanitization.values()):
        raise EvidenceError("all canonical sanitization assertions must be present and true")
    for text in strings(record):
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise EvidenceError("record contains likely secret material")
        if re.search(r"(?:^|\s)(?:/Users/|/home/|[A-Za-z]:\\Users\\)", text):
            raise EvidenceError("record contains an apparent personal home path")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate sanitized aiplane trial evidence.")
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    try:
        validate_record(json.loads(args.record.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        parser.error(str(exc))
    print(f"valid trial evidence: {args.record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
