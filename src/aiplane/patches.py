"""Review-first application of user-supplied Git patches.

This module never generates patches or calls a model. It validates a patch already
reviewed by the operator and applies it only through Git after explicit approval.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import AuditLogger
from .boundaries import CommandRunner, SubprocessCommandRunner
from .models import AuditEvent, Profile
from .policy import PolicyEngine
from .secrets import contains_secret

_MAX_PATCH_BYTES = 1_048_576
_PREVIEW_LINES = 20


class PatchManager:
    def __init__(
        self,
        profile: Profile,
        audit: AuditLogger | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.profile = profile
        self.audit = audit or AuditLogger(profile)
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.policy = PolicyEngine(profile)

    def inspect(self, source: Path | str) -> dict[str, Any]:
        path, text = self._read_patch(source)
        files = _patch_paths(text)
        check = self._git_apply_check(path)
        return {
            "contract_version": "1.0",
            "record_type": "patch_proposal",
            "mutates": False,
            "path": str(path.relative_to(self.profile.workspace)),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "size_bytes": len(text.encode("utf-8")),
            "files": files,
            "summary": _change_summary(text),
            "validation": check,
            "preview": text.splitlines()[:_PREVIEW_LINES],
            "next_action": "aiplane patches apply PATH --yes" if check["ok"] else None,
            "notes": [
                "This inspects a user-supplied patch; it does not generate code or change files.",
                "Patch content is restricted to the selected workspace and rejected when it contains secret-like material.",
                "Apply rechecks Git validation, requires --yes, uses the existing local write policy, and never stages or commits changes.",
            ],
        }

    def apply(self, source: Path | str, *, yes: bool) -> dict[str, Any]:
        inspection = self.inspect(source)
        action = "patch:apply"
        validation = inspection["validation"]
        if not bool(validation["ok"]):
            self._audit(action, "validation_failed", inspection)
            return {**inspection, "status": "validation_failed", "mutates": False}

        decision = self.policy.tool_decision("write_file")
        if not decision.allowed:
            self._audit(action, "blocked", inspection, reason=decision.reason)
            return {**inspection, "status": "policy_blocked", "mutates": False, "reason": decision.reason}
        if not yes:
            self._audit(action, "confirmation_required", inspection)
            return {
                **inspection,
                "status": "confirmation_required",
                "mutates": False,
                "reason": "patch application requires --yes after review",
            }

        path = self.profile.workspace / str(inspection["path"])
        result = self.command_runner.run(
            ["git", "apply", "--whitespace=error", "--", str(path)],
            cwd=self.profile.workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            self._audit(action, "failed", inspection, error_type="GitApplyFailed")
            return {
                **inspection,
                "status": "apply_failed",
                "mutates": False,
                "reason": "Git rejected the patch during apply; inspect the current workspace and validate again.",
            }
        self._audit(action, "allowed", inspection)
        return {
            **inspection,
            "status": "applied",
            "mutates": True,
            "notes": [
                *inspection["notes"],
                "Git applied the reviewed patch to the working tree. No files were staged or committed.",
            ],
        }

    def _read_patch(self, source: Path | str) -> tuple[Path, str]:
        path = Path(source)
        if not path.is_absolute():
            path = self.profile.workspace / path
        path = path.resolve()
        if not self.policy.path_decision(path).allowed:
            raise PermissionError("patch path escapes workspace boundary")
        if not path.is_file():
            raise ValueError("patch path must be an existing regular file inside the workspace")
        size = path.stat().st_size
        if size > _MAX_PATCH_BYTES:
            raise ValueError(f"patch exceeds the {_MAX_PATCH_BYTES}-byte review limit")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError("patch is empty")
        if contains_secret(text):
            raise ValueError("patch contains secret-like material and cannot be applied through aiplane")
        return path, text

    def _git_apply_check(self, path: Path) -> dict[str, Any]:
        result = self.command_runner.run(
            ["git", "apply", "--check", "--verbose", "--", str(path)],
            cwd=self.profile.workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "command": ["git", "apply", "--check", "--verbose", "--", str(path.relative_to(self.profile.workspace))],
            "ok": result.returncode == 0,
            "reason": (
                "git apply --check passed"
                if result.returncode == 0
                else "git apply --check failed; the patch does not match the current workspace"
            ),
        }

    def _audit(
        self,
        action: str,
        decision: str,
        inspection: dict[str, Any],
        *,
        reason: str | None = None,
        error_type: str | None = None,
    ) -> None:
        details: dict[str, Any] = {
            "path": inspection["path"],
            "sha256": inspection["sha256"],
            "file_count": len(inspection["files"]),
        }
        if reason:
            details["reason"] = reason
        if error_type:
            details["error_type"] = error_type
        self.audit.record(AuditEvent("patch", self.profile.name, action, decision, details))


def _patch_paths(text: str) -> list[str]:
    paths: set[str] = set()
    for line in text.splitlines():
        if not line.startswith(("--- ", "+++ ")):
            continue
        raw = line[4:].split("\t", 1)[0].strip()
        if raw == "/dev/null":
            continue
        if not raw.startswith(("a/", "b/")):
            raise ValueError("patch paths must use standard a/ or b/ prefixes")
        relative = raw[2:]
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or not relative or any(part in {"", ".", "..", ".git"} for part in candidate.parts):
            raise ValueError("patch contains an unsafe target path")
        paths.add(relative)
    if not paths:
        raise ValueError("patch does not contain standard file headers")
    return sorted(paths)


def _change_summary(text: str) -> dict[str, int]:
    added = 0
    removed = 0
    for line in text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {"added_lines": added, "removed_lines": removed}
