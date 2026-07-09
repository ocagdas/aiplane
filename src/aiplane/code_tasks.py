from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audit import AuditLogger
from .backends import BackendResult
from .model_catalog import ModelCatalog
from .models import AuditEvent, Profile
from .policy import PolicyEngine


@dataclass(frozen=True)
class CodeTaskResult:
    task: str
    model: str
    prompt: str
    output: str
    dry_run: bool


class CodeTaskRunner:
    def __init__(self, profile: Profile, audit: AuditLogger):
        self.profile = profile
        self.audit = audit
        self.policy = PolicyEngine(profile)
        self.catalog = ModelCatalog(profile)

    def analyze(
        self,
        model_name: str,
        target: Path,
        dry_run: bool = False,
        timeout_seconds: int | None = None,
    ) -> CodeTaskResult:
        target = self._workspace_file(target)
        source = target.read_text(encoding="utf-8")
        prompt = build_analysis_prompt(target, source)
        return self._run(
            "analysis",
            model_name,
            prompt,
            dry_run,
            {"target": str(target)},
            timeout_seconds=timeout_seconds,
        )

    def complete(
        self,
        model_name: str,
        target: Path,
        line: int,
        dry_run: bool = False,
        timeout_seconds: int | None = None,
    ) -> CodeTaskResult:
        target = self._workspace_file(target)
        if line < 1:
            raise ValueError("line must be 1 or greater")
        lines = target.read_text(encoding="utf-8").splitlines()
        if line > len(lines) + 1:
            raise ValueError(f"line {line} is outside file with {len(lines)} lines")
        before = "\n".join(lines[: line - 1])
        after = "\n".join(lines[line - 1 :])
        prompt = build_completion_prompt(target, line, before, after)
        return self._run(
            "completion",
            model_name,
            prompt,
            dry_run,
            {"target": str(target), "line": line},
            timeout_seconds=timeout_seconds,
        )

    def write(
        self,
        model_name: str,
        task: str,
        dry_run: bool = False,
        timeout_seconds: int | None = None,
    ) -> CodeTaskResult:
        prompt = build_write_prompt(task)
        return self._run(
            "write",
            model_name,
            prompt,
            dry_run,
            {"request": task},
            timeout_seconds=timeout_seconds,
        )

    def _run(
        self,
        task: str,
        model_name: str,
        prompt: str,
        dry_run: bool,
        details: dict[str, object],
        timeout_seconds: int | None = None,
    ) -> CodeTaskResult:
        model = self.catalog.get(model_name)
        self.catalog.require_execution_capability(model_name, model, task)
        action = f"code:{task}"
        if dry_run:
            self.audit.record(
                AuditEvent(
                    "code",
                    self.profile.name,
                    action,
                    "dry_run",
                    {
                        "model": model_name,
                        **details,
                        **({"timeout_seconds": timeout_seconds} if timeout_seconds else {}),
                    },
                )
            )
            return CodeTaskResult(task, model_name, prompt, prompt, True)
        result = self._call_model(model_name, prompt, purpose=task, timeout_seconds=timeout_seconds)
        self.audit.record(
            AuditEvent(
                "code",
                self.profile.name,
                action,
                "allowed",
                {
                    "model": model_name,
                    **details,
                    **({"timeout_seconds": timeout_seconds} if timeout_seconds else {}),
                    "output": result.text[-1000:],
                },
            )
        )
        return CodeTaskResult(task, model_name, prompt, result.text, False)

    def _call_model(
        self,
        model_name: str,
        prompt: str,
        purpose: str,
        timeout_seconds: int | None = None,
    ) -> BackendResult:
        self.catalog.get(model_name)
        return self.catalog.complete(model_name, prompt, timeout_seconds=timeout_seconds, purpose=purpose)

    def _workspace_file(self, target: Path) -> Path:
        path = target if target.is_absolute() else self.profile.workspace / target
        decision = self.policy.path_decision(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(str(resolved))
        return resolved


def build_analysis_prompt(target: Path, source: str) -> str:
    return (
        f"Analyze this code file: {target.name}.\n"
        "Explain what it does, identify important functions/classes, point out one risk, "
        "and suggest one small improvement.\n\n"
        f"```\n{source}\n```"
    )


def build_completion_prompt(target: Path, line: int, before: str, after: str) -> str:
    return (
        f"Complete code in {target.name} at line {line}. Return only the code that should be inserted.\n\n"
        "Before cursor:\n"
        f"```\n{before}\n```\n\n"
        "After cursor:\n"
        f"```\n{after}\n```"
    )


def build_write_prompt(task: str) -> str:
    task = task.strip()
    if not task:
        raise ValueError("task cannot be empty")
    return (
        "Write Python code for the following request. Return only code, include a small unittest "
        "test case when appropriate, and avoid modifying files.\n\n"
        f"Request: {task}"
    )
