from __future__ import annotations

import sys

from .models import Decision


class ApprovalHandler:
    def __init__(self, assume_yes: bool = False):
        self.assume_yes = assume_yes

    def approve(self, action: str, decision: Decision) -> bool:
        if not decision.requires_approval:
            return True
        if self.assume_yes:
            return True
        if not sys.stdin.isatty():
            return False
        answer = input(f"Approve {action}? {decision.reason} [y/N] ").strip().lower()
        return answer in {"y", "yes"}
