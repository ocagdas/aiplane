from __future__ import annotations

from pathlib import Path

from .models import Decision, Profile


READ_ONLY_TOOLS = {"read_file", "grep", "git_status", "git_diff"}
RISKY_TOOLS = {"write_file", "run_tests", "build", "lint", "docker_exec", "git_commit"}


class PolicyEngine:
    def __init__(self, profile: Profile):
        self.profile = profile

    def explain(self, action: str) -> Decision:
        if action.startswith("tool:"):
            return self.tool_decision(action.split(":", 1)[1])
        if action == "backend:cloud":
            return self.cloud_decision()
        if action == "backend:local":
            return Decision(True, False, "local backends are allowed by default", "backend.local")
        return Decision(False, False, f"unknown action {action!r}", "unknown")

    def cloud_decision(self) -> Decision:
        repo_class = self.profile.repository.get("classification", "private")
        cloud_allowed = bool(self.profile.repository.get("allow_cloud", False))
        if repo_class == "client_sensitive":
            return Decision(
                False,
                False,
                "client-sensitive repositories cannot use cloud backends",
                "repository.classification",
            )
        if not cloud_allowed:
            return Decision(
                False,
                False,
                "repository policy disables cloud backends",
                "repository.allow_cloud",
            )
        return Decision(
            True,
            False,
            "repository policy allows cloud backends",
            "repository.allow_cloud",
        )

    def tool_decision(self, tool_name: str) -> Decision:
        allowed = set(self.profile.tools.get("allowed", []))
        if tool_name not in allowed:
            return Decision(False, False, f"tool {tool_name!r} is not allowed", "tools.allowed")

        mode = self.profile.tools.get("mode", "read_only")
        if mode == "read_only" and tool_name not in READ_ONLY_TOOLS:
            return Decision(False, False, "read-only tool mode blocks mutating tools", "tools.mode")

        approval_required = False
        risk = "read_only" if tool_name in READ_ONLY_TOOLS else "risky"
        if tool_name in RISKY_TOOLS:
            approval_required = bool(self.profile.approvals.get("risk_based", True))
        if tool_name in set(self.profile.approvals.get("always_require", [])):
            approval_required = True

        return Decision(
            True,
            approval_required,
            f"tool is allowed with {risk} risk",
            "tools.allowed",
        )

    def path_decision(self, path: Path) -> Decision:
        resolved = path.resolve()
        workspace = self.profile.workspace.resolve()
        if resolved == workspace or workspace in resolved.parents:
            return Decision(True, False, "path is inside workspace", "workspace")
        return Decision(False, False, "path escapes workspace boundary", "workspace")
