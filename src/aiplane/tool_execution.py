from __future__ import annotations

from pathlib import Path

from .approvals import ApprovalHandler
from .audit import AuditLogger
from .boundaries import CommandRunner, SubprocessCommandRunner
from .env import EnvironmentManager
from .models import AuditEvent, Profile
from .persistence import atomic_write_text
from .policy import PolicyEngine


class ToolExecutor:
    def __init__(
        self,
        profile: Profile,
        audit: AuditLogger,
        approvals: ApprovalHandler | None = None,
        command_runner: CommandRunner | None = None,
    ):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.audit = audit
        self.policy = PolicyEngine(profile)
        self.approvals = approvals or ApprovalHandler()
        self.environment = EnvironmentManager(profile)

    def run(self, tool_name: str, args: list[str]) -> str:
        decision = self.policy.tool_decision(tool_name)
        action = f"tool:{tool_name}"
        if not decision.allowed:
            self._audit(action, "blocked", {"reason": decision.reason})
            raise PermissionError(decision.reason)
        if not self.approvals.approve(action, decision):
            self._audit(action, "approval_denied", {"reason": decision.reason})
            raise PermissionError("approval denied")

        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            self._audit(action, "blocked", {"reason": "unknown tool"})
            raise ValueError(f"unknown tool: {tool_name}")
        try:
            output = handler(args)
            self._audit(action, "allowed", self._audit_details(tool_name, args))
            return output
        except Exception as exc:
            self._audit(action, "failed", {**self._audit_details(tool_name, args), "error_type": type(exc).__name__})
            raise

    def _tool_read_file(self, args: list[str]) -> str:
        path = self._workspace_path(_arg(args, 0, "path"))
        return path.read_text(encoding="utf-8")

    def _tool_write_file(self, args: list[str]) -> str:
        path = self._workspace_path(_arg(args, 0, "path"))
        content = _arg(args, 1, "content")
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content)
        return f"wrote {path}"

    def _tool_grep(self, args: list[str]) -> str:
        pattern = _arg(args, 0, "pattern")
        target = self._workspace_path(args[1] if len(args) > 1 else ".")
        return self._command(["rg", pattern, str(target)], allow_failure=True)

    def _tool_git_status(self, args: list[str]) -> str:
        return self._command(["git", "status", "--short"], allow_failure=True)

    def _tool_git_diff(self, args: list[str]) -> str:
        return self._command(["git", "diff"], allow_failure=True)

    def _tool_run_tests(self, args: list[str]) -> str:
        command = args or ["python", "-m", "pytest", "-q"]
        return self._command(command)

    def _tool_build(self, args: list[str]) -> str:
        command = args or ["python", "-m", "compileall", "src"]
        return self._command(command)

    def _tool_lint(self, args: list[str]) -> str:
        command = args or ["python", "-m", "ruff", "check", "src", "tests"]
        return self._command(command)

    def _tool_docker_exec(self, args: list[str]) -> str:
        if not args:
            raise ValueError("docker_exec requires docker arguments")
        return self._command(["docker", *args], allow_failure=True, use_environment=False)

    def _tool_git_commit(self, args: list[str]) -> str:
        message = " ".join(args).strip()
        if not message:
            raise ValueError("git_commit requires a commit message")
        return self._command(["git", "commit", "-m", message], allow_failure=True)

    def _workspace_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.profile.workspace / path
        decision = self.policy.path_decision(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return path.resolve()

    def _command(
        self,
        command: list[str],
        allow_failure: bool = False,
        use_environment: bool = True,
    ) -> str:
        plan = self.environment.plan(command) if use_environment else None
        actual_command = plan.command if plan else command
        cwd = plan.cwd if plan else self.profile.workspace
        result = self.command_runner.run(
            actual_command,
            cwd=cwd,
            check=False,
            text=True,
            capture_output=True,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode and not allow_failure:
            raise RuntimeError(output or f"command failed: {actual_command}")
        return output

    def _audit_details(self, tool_name: str, args: list[str]) -> dict[str, object]:
        details: dict[str, object] = {"argument_count": len(args)}
        if tool_name in {"read_file", "write_file"} and args:
            details["target"] = args[0]
        return details

    def _audit(self, action: str, decision: str, details: dict[str, object]) -> None:
        self.audit.record(AuditEvent("tool", self.profile.name, action, decision, details))


def _arg(args: list[str], index: int, name: str) -> str:
    try:
        return args[index]
    except IndexError as exc:
        raise ValueError(f"missing {name}") from exc
