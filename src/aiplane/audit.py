from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AuditEvent, Profile
from .persistence import locked_append_text
from .secrets import redact


@dataclass(frozen=True)
class AuditTailResult:
    events: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    malformed_records: int


class AuditLogger:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.path = profile.workspace / ".aiplane" / "audit" / f"{profile.name}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: AuditEvent) -> None:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event.event_type,
            "profile": event.profile,
            "action": event.action,
            "decision": event.decision,
            "details": redact(event.details),
        }
        locked_append_text(self.path, json.dumps(payload, sort_keys=True) + "\n")

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.tail_report(limit).events

    def tail_report(self, limit: int = 20, *, warning_limit: int = 20) -> AuditTailResult:
        if limit < 0:
            raise ValueError("audit tail limit must be zero or greater")
        if warning_limit < 0:
            raise ValueError("audit warning limit must be zero or greater")
        if limit == 0 or not self.path.exists():
            return AuditTailResult([], [], 0)

        text = self.path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        unterminated_final_line = bool(text) and not text.endswith(("\n", "\r"))
        events: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        malformed_records = 0

        for index in range(len(lines) - 1, -1, -1):
            line = lines[index]
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("audit record is not a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                malformed_records += 1
                if len(warnings) < warning_limit:
                    final_truncated = index == len(lines) - 1 and unterminated_final_line
                    warnings.append(
                        {
                            "line": index + 1,
                            "kind": "truncated_final_record" if final_truncated else "malformed_record",
                            "error": type(exc).__name__,
                        }
                    )
                continue
            events.append(event)
            if len(events) >= limit:
                break

        events.reverse()
        warnings.reverse()
        return AuditTailResult(events, warnings, malformed_records)


def audit_path(profile: Profile) -> Path:
    return profile.workspace / ".aiplane" / "audit" / f"{profile.name}.jsonl"
