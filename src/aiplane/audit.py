from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AuditEvent, Profile
from .secrets import redact


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
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]


def audit_path(profile: Profile) -> Path:
    return profile.workspace / ".aiplane" / "audit" / f"{profile.name}.jsonl"
