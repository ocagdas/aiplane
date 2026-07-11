from __future__ import annotations

from pathlib import Path

from .models import Decision, Profile


READ_ONLY_TOOLS = {"read_file", "grep", "git_status", "git_diff"}
RISKY_TOOLS = {"write_file", "run_tests", "build", "lint", "docker_exec", "git_commit"}


class PolicyEngine:
    def _decision(
        self,
        allowed: bool,
        requires_approval: bool = False,
        reason: str = "",
        matched_rule: str = "",
        outcome: str | None = None,
    ) -> Decision:
        if outcome is None:
            if not allowed:
                outcome = "blocked"
            elif requires_approval:
                outcome = "approval_required"
            else:
                outcome = "allowed"
        return Decision(allowed, requires_approval, reason, matched_rule, outcome)

    def __init__(self, profile: Profile):
        self.profile = profile

    def explain(self, action: str) -> Decision:
        if action.startswith("tool:"):
            return self.tool_decision(action.split(":", 1)[1])
        if action.startswith("provider:"):
            return self.provider_decision(action.split(":", 1)[1])
        if action.startswith("model:"):
            return self.model_decision(action.split(":", 1)[1])
        if action == "backend:cloud":
            return self.cloud_decision()
        if action == "cloud_escalation":
            return self.cloud_decision()
        if action == "backend:local":
            return self._decision(True, False, "local backends are allowed by default", "backend.local")
        return self._decision(False, False, f"unknown action {action!r}", "unknown")

    def model_decision(self, model_name: str) -> Decision:
        models = self.profile.models.get("models", {}) if isinstance(self.profile.models, dict) else {}
        model = models.get(str(model_name)) if isinstance(models, dict) else None
        if not isinstance(model, dict):
            return self._decision(False, False, f"unknown model {model_name!r}", "models.catalog")

        if not bool(model.get("enabled", True)):
            return self._decision(False, False, f"model {model_name!r} is disabled", "model.enabled")

        provider_name = str(model.get("provider") or "")
        if not provider_name:
            return self._decision(False, False, f"model {model_name!r} is missing provider", "model.provider")

        provider_decision = self.provider_decision(provider_name)
        if not provider_decision.allowed:
            return self._decision(False, False, provider_decision.reason, provider_decision.matched_rule)

        local = bool(model.get("local", False))
        if local:
            return self._decision(True, False, f"model {model_name!r} is allowed", "model.provider")

        cloud_decision = self.cloud_decision()
        if not cloud_decision.allowed:
            return self._decision(False, False, cloud_decision.reason, cloud_decision.matched_rule)

        return self._decision(True, False, f"model {model_name!r} is allowed", "model.provider")

    def provider_decision(self, provider_name: str) -> Decision:
        allowed_providers = self._allowed_providers()
        if allowed_providers is not None and str(provider_name) not in allowed_providers:
            return self._decision(
                False,
                False,
                f"provider {provider_name!r} is not allowed by repository policy",
                "repository.allowed_providers",
            )
        return self._decision(True, False, f"provider {provider_name!r} is allowed", "repository.allowed_providers")

    def cloud_decision(self) -> Decision:
        repo_class = self.profile.repository.get("classification", "private")
        cloud_allowed = bool(self.profile.repository.get("allow_cloud", False))
        if repo_class == "client_sensitive":
            return self._decision(
                False,
                False,
                "client-sensitive repositories cannot use cloud backends",
                "repository.classification",
            )
        if not cloud_allowed:
            return self._decision(
                False,
                False,
                "repository policy disables cloud backends",
                "repository.allow_cloud",
            )
        return self._decision(
            True,
            False,
            "repository policy allows cloud backends",
            "repository.allow_cloud",
        )

    def tool_decision(self, tool_name: str) -> Decision:
        allowed = set(self.profile.tools.get("allowed", []))
        if tool_name not in allowed:
            return self._decision(False, False, f"tool {tool_name!r} is not allowed", "tools.allowed")

        mode = self.profile.tools.get("mode", "read_only")
        if mode == "read_only" and tool_name not in READ_ONLY_TOOLS:
            return self._decision(False, False, "read-only tool mode blocks mutating tools", "tools.mode")

        approval_required = False
        risk = "read_only" if tool_name in READ_ONLY_TOOLS else "risky"
        if tool_name in RISKY_TOOLS:
            approval_required = bool(self.profile.approvals.get("risk_based", True))
        if tool_name in set(self.profile.approvals.get("always_require", [])):
            approval_required = True

        return self._decision(
            True,
            approval_required,
            f"tool is allowed with {risk} risk",
            "tools.allowed",
        )

    def _allowed_providers(self) -> set[str] | None:
        allowed_raw = self.profile.repository.get("allowed_providers")
        if not isinstance(allowed_raw, list):
            return None
        trimmed = [str(value).strip() for value in allowed_raw if str(value).strip()]
        return {value for value in trimmed}

    def path_decision(self, path: Path) -> Decision:
        resolved = path.resolve()
        workspace = self.profile.workspace.resolve()
        if resolved == workspace or workspace in resolved.parents:
            return self._decision(True, False, "path is inside workspace", "workspace")
        return self._decision(False, False, "path escapes workspace boundary", "workspace")
