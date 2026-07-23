from __future__ import annotations

from pathlib import Path
from typing import Callable
from datetime import datetime

from .models import Decision, Profile
from .policy_state import PolicyGrantStore, utc_now


READ_ONLY_TOOLS = {"read_file", "grep", "git_status", "git_diff"}
RISKY_TOOLS = {"write_file", "run_tests", "build", "lint", "docker_exec", "git_commit"}


class PolicyEngine:
    def __init__(self, profile: Profile, *, clock: Callable[[], datetime] = utc_now):
        self.profile = profile
        self.grants = PolicyGrantStore(profile, clock=clock)

    def _decision(
        self,
        allowed: bool,
        requires_approval: bool = False,
        reason: str = "",
        matched_rule: str = "",
        outcome: str | None = None,
    ) -> Decision:
        if outcome is None:
            outcome = "blocked" if not allowed else "approval_required" if requires_approval else "allowed"
        return Decision(allowed, requires_approval, reason, matched_rule, outcome)

    def explain(self, action: str) -> Decision:
        return self._apply_grant(action, self.explain_base(action))

    def explain_base(self, action: str) -> Decision:
        if action.startswith("tool:"):
            return self._tool_base(action.split(":", 1)[1])
        if action.startswith("provider:"):
            return self._provider_base(action.split(":", 1)[1])
        if action.startswith("model:"):
            return self._model_base(action.split(":", 1)[1])
        if action in {"backend:cloud", "cloud_escalation"}:
            return self._cloud_base()
        if action == "backend:local":
            return self._decision(True, False, "local backends are allowed by default", "backend.local")
        return self._decision(False, False, f"unknown action {action!r}", "unknown")

    def model_decision(self, model_name: str) -> Decision:
        action = f"model:{model_name}"
        return self._apply_grant(action, self._model_base(model_name))

    def provider_decision(self, provider_name: str) -> Decision:
        action = f"provider:{provider_name}"
        return self._apply_grant(action, self._provider_base(provider_name))

    def cloud_decision(self) -> Decision:
        return self._apply_grant("backend:cloud", self._cloud_base())

    def tool_decision(self, tool_name: str) -> Decision:
        action = f"tool:{tool_name}"
        return self._apply_grant(action, self._tool_base(tool_name))

    def _model_base(self, model_name: str) -> Decision:
        models = self.profile.models.get("models", {}) if isinstance(self.profile.models, dict) else {}
        model = models.get(str(model_name)) if isinstance(models, dict) else None
        if not isinstance(model, dict):
            return self._decision(False, False, f"unknown model {model_name!r}", "models.catalog")
        if not bool(model.get("enabled", True)):
            return self._decision(False, False, f"model {model_name!r} is disabled", "model.enabled")
        provider_name = str(model.get("provider") or "")
        if not provider_name:
            return self._decision(False, False, f"model {model_name!r} is missing provider", "model.provider")
        provider_decision = self._provider_base(provider_name)
        if not provider_decision.allowed:
            return self._decision(False, False, provider_decision.reason, provider_decision.matched_rule)
        if bool(model.get("local", False)):
            return self._decision(True, False, f"model {model_name!r} is allowed", "model.provider")
        cloud_decision = self._cloud_base()
        if not cloud_decision.allowed:
            return self._decision(False, False, cloud_decision.reason, cloud_decision.matched_rule)
        return self._decision(True, False, f"model {model_name!r} is allowed", "model.provider")

    def _provider_base(self, provider_name: str) -> Decision:
        allowed_providers = self._allowed_providers()
        if allowed_providers is not None and str(provider_name) not in allowed_providers:
            return self._decision(
                False,
                False,
                f"provider {provider_name!r} is not allowed by repository policy",
                "repository.allowed_providers",
            )
        return self._decision(True, False, f"provider {provider_name!r} is allowed", "repository.allowed_providers")

    def _cloud_base(self) -> Decision:
        repo_class = self.profile.repository.get("classification", "private")
        cloud_allowed = bool(self.profile.repository.get("allow_cloud", False))
        if repo_class == "client_sensitive":
            return self._decision(
                False, False, "client-sensitive repositories cannot use cloud backends", "repository.classification"
            )
        if not cloud_allowed:
            return self._decision(False, False, "repository policy disables cloud backends", "repository.allow_cloud")
        return self._decision(True, False, "repository policy allows cloud backends", "repository.allow_cloud")

    def _tool_base(self, tool_name: str) -> Decision:
        allowed = set(self.profile.tools.get("allowed", []))
        if tool_name not in allowed:
            return self._decision(False, False, f"tool {tool_name!r} is not allowed", "tools.allowed")
        mode = self.profile.tools.get("mode", "read_only")
        if mode == "read_only" and tool_name not in READ_ONLY_TOOLS:
            return self._decision(False, False, "read-only tool mode blocks mutating tools", "tools.mode")
        risk = "read_only" if tool_name in READ_ONLY_TOOLS else "risky"
        approval_required = tool_name in RISKY_TOOLS and bool(self.profile.approvals.get("risk_based", True))
        if tool_name in set(self.profile.approvals.get("always_require", [])):
            approval_required = True
        return self._decision(True, approval_required, f"tool is allowed with {risk} risk", "tools.allowed")

    def _apply_grant(self, action: str, decision: Decision) -> Decision:
        try:
            grants = self.grants.active(action)
        except ValueError as exc:
            return self._decision(False, False, str(exc), "policy.local_state")
        for grant in reversed(grants):
            if grant.kind == "temporary_approval" and decision.allowed and decision.requires_approval:
                return self._decision(
                    True,
                    False,
                    f"temporarily approved until {grant.expires_at}: {grant.reason}",
                    f"policy.local_state.{grant.grant_id}",
                    "temporarily_approved",
                )
            if grant.kind == "override" and not decision.allowed:
                return self._decision(
                    True,
                    False,
                    f"overridden until {grant.expires_at}: {grant.reason}",
                    f"policy.local_state.{grant.grant_id}",
                    "overridden",
                )
        return decision

    def drift(self) -> dict[str, object]:
        records = self.grants.list(include_expired=True)
        findings: list[dict[str, str]] = []
        for record in records:
            base = self.explain_base(str(record["action"]))
            if record["expired"]:
                findings.append(
                    {
                        "id": str(record["id"]),
                        "action": str(record["action"]),
                        "kind": "expired",
                        "reason": "grant has expired",
                    }
                )
            elif record["kind"] == "temporary_approval" and not base.requires_approval:
                findings.append(
                    {
                        "id": str(record["id"]),
                        "action": str(record["action"]),
                        "kind": "stale",
                        "reason": "action no longer requires approval",
                    }
                )
            elif record["kind"] == "override" and base.allowed:
                findings.append(
                    {
                        "id": str(record["id"]),
                        "action": str(record["action"]),
                        "kind": "stale",
                        "reason": "action is no longer blocked",
                    }
                )
        return {"schema_version": "1.0", "profile": self.profile.name, "findings": findings, "ok": not findings}

    def _allowed_providers(self) -> set[str] | None:
        allowed_raw = self.profile.repository.get("allowed_providers")
        if not isinstance(allowed_raw, list):
            return None
        return {str(value).strip() for value in allowed_raw if str(value).strip()}

    def path_decision(self, path: Path) -> Decision:
        resolved = path.resolve()
        workspace = self.profile.workspace.resolve()
        if resolved == workspace or workspace in resolved.parents:
            return self._decision(True, False, "path is inside workspace", "workspace")
        return self._decision(False, False, "path escapes workspace boundary", "workspace")
