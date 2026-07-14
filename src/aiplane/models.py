from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Profile:
    name: str
    root: Path
    workspace: Path
    hardware: dict[str, Any]
    backends: dict[str, Any]
    repository: dict[str, Any]
    tools: dict[str, Any]
    approvals: dict[str, Any]
    environment: dict[str, Any]
    models: dict[str, Any]
    targets: dict[str, Any]
    orchestrators: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    matched_rule: str = ""
    outcome: str = "allowed"


@dataclass
class AuditEvent:
    event_type: str
    profile: str
    action: str
    decision: str
    details: dict[str, Any] = field(default_factory=dict)
