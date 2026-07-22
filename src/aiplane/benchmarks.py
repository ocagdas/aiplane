from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .boundaries import CommandRunner, SubprocessCommandRunner
from .persistence import atomic_write_text
from .config import parse_yaml
from .env import EnvironmentManager
from .model_catalog import ModelCatalog, capability_profile
from .models import Profile


BENCHMARK_TASKS = {
    "analysis": {
        "prompt": "Explain what this Python function does and identify one edge case.\n\n```python\ndef add(a, b):\n    return a + b\n```",
        "expected_terms": ["add", "edge"],
    },
    "completion": {
        "prompt": "Complete this Python function. Return only code.\n\n```python\ndef is_even(value):\n",
        "expected_terms": ["return", "%"],
    },
    "generation": {
        "prompt": "Write a small Python function named clamp(value, low, high). Return only code.",
        "expected_terms": ["clamp", "return"],
    },
    "reasoning": {
        "prompt": "A service handles 12 requests per second. How many requests in 5 minutes? Explain briefly.",
        "expected_terms": ["3600"],
    },
}


@dataclass(frozen=True)
class BenchmarkRun:
    model_name: str
    task: str
    dry_run: bool = False
    save: bool = True


class BenchmarkRunner:
    def __init__(self, profile: Profile, command_runner: CommandRunner | None = None):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.catalog = ModelCatalog(profile)
        self.environment = EnvironmentManager(profile)

    def run(
        self,
        model_name: str,
        task: str = "analysis",
        dry_run: bool = False,
        save: bool = True,
        spec_path: Path | None = None,
        environment_mode: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        spec = load_benchmark_spec(spec_path) if spec_path else {"name": "builtin-smoke", "tasks": BENCHMARK_TASKS}
        tasks = _select_tasks(spec, task)
        model = self.catalog.show(model_name)
        results = [
            self._run_task(
                model_name,
                model,
                task_name,
                task_spec,
                dry_run,
                environment_mode,
                timeout_seconds,
            )
            for task_name, task_spec in tasks
        ]
        payload = {
            "name": str(spec.get("name") or "benchmark"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "profile": self.profile.name,
            "model_name": model_name,
            "provider": model.get("provider"),
            "model": model.get("model"),
            "environment_mode": environment_mode or self.environment.active_mode(),
            "dry_run": dry_run,
            "score_scale": "0-100",
            "score_notes": "Scores are measured for this benchmark spec only. Built-in checks use deterministic term matching, latency, and response length; custom command evaluators may define their own score.",
            "capabilities": capability_profile(model),
            "results": results,
            "summary": _summary(results),
        }
        if spec_path:
            payload["spec_path"] = str(spec_path)
        if save:
            payload["saved_to"] = str(self._save(payload, model_name))
        return payload

    def _run_task(
        self,
        model_name: str,
        model: dict[str, Any],
        task: str,
        spec: dict[str, Any],
        dry_run: bool,
        environment_mode: str | None,
        timeout_seconds: int | None,
    ) -> dict[str, Any]:
        prompt = str(spec.get("prompt") or "")
        expected_terms = [str(term).lower() for term in _list_value(spec.get("expected_terms"))]
        evaluator = spec.get("evaluator") if isinstance(spec.get("evaluator"), dict) else {}
        timeout = int(timeout_seconds or spec.get("timeout_seconds") or 60)
        started = time.perf_counter()
        error = None
        if dry_run:
            text = prompt
            backend = "dry_run"
        else:
            try:
                result = self.catalog.complete(model_name, prompt)
                text = result.text
                backend = result.backend
            except Exception as exc:  # noqa: BLE001 - benchmark should report failures, not crash mid-suite.
                text = ""
                backend = str(model.get("provider", "unknown"))
                error = str(exc)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        output_length = len(text)
        lower = text.lower()
        matched_terms = [term for term in expected_terms if term in lower] if not dry_run else []
        evaluation = (
            self._evaluate(task, prompt, text, evaluator, dry_run, environment_mode, timeout)
            if not error
            else {"type": "skipped", "passed": False, "score": 0, "reason": error}
        )
        if not evaluator:
            task_passed = (
                None
                if dry_run
                else error is None and bool(text.strip()) and len(matched_terms) >= max(1, len(expected_terms) // 2)
            )
            score = _task_score(task_passed, elapsed_ms, output_length, dry_run)
            evaluation = {
                "type": "expected_terms",
                "passed": task_passed,
                "score": score,
                "matched_terms": matched_terms,
                "expected_terms": expected_terms,
            }
        else:
            task_passed = None if dry_run else bool(evaluation.get("passed"))
            score = int(evaluation.get("score", 0)) if not dry_run else 0
        return {
            "name": task,
            "task": task,
            "backend": backend,
            "passed": task_passed,
            "score": score,
            "elapsed_ms": elapsed_ms,
            "output_chars": output_length,
            "matched_terms": matched_terms,
            "expected_terms": expected_terms,
            "evaluation": evaluation,
            "error": error,
        }

    def _evaluate(
        self,
        task: str,
        prompt: str,
        output: str,
        evaluator: dict[str, Any],
        dry_run: bool,
        environment_mode: str | None,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        command = _list_value(evaluator.get("command"))
        if not command:
            return {
                "type": "expected_terms",
                "passed": True,
                "score": 100,
                "reason": "no custom evaluator command",
            }
        workdir = self.profile.workspace / ".aiplane" / "benchmarks" / "work"
        workdir.mkdir(parents=True, exist_ok=True)
        safe_task = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in task) or "task"
        prompt_file = workdir / f"{safe_task}-prompt.txt"
        output_file = workdir / f"{safe_task}-output.txt"
        atomic_write_text(prompt_file, prompt)
        atomic_write_text(output_file, output)
        replacements = {
            "{prompt_file}": str(prompt_file),
            "{output_file}": str(output_file),
        }
        planned_command = [replacements.get(str(part), str(part)) for part in command]
        plan = self.environment.plan(planned_command, mode=environment_mode)
        if dry_run:
            return {
                "type": "command",
                "passed": None,
                "score": 0,
                "command": plan.command,
                "cwd": str(plan.cwd),
                "reason": "dry run",
            }
        completed = self.command_runner.run(
            plan.command,
            cwd=plan.cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        stdout = completed.stdout.strip()
        parsed = _json_object(stdout)
        if parsed and "score" in parsed:
            score = _clamp_score(parsed.get("score"))
            passed = bool(parsed.get("passed", score > 0)) and completed.returncode == 0
        else:
            passed = completed.returncode == 0
            score = 100 if passed else 0
        return {
            "type": "command",
            "passed": passed,
            "score": score,
            "command": plan.command,
            "cwd": str(plan.cwd),
            "returncode": completed.returncode,
            "stdout": stdout[-4000:],
            "stderr": completed.stderr.strip()[-4000:],
        }

    def _save(self, payload: dict[str, Any], model_name: str) -> Path:
        root = self.profile.workspace / ".aiplane" / "benchmarks"
        root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = root / f"{timestamp}-{model_name}.json"
        atomic_write_text(path, json.dumps(payload, indent=2))
        self.catalog.rebuild_materialized()
        return path


def load_benchmark_spec(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = parse_yaml(text)
    if not isinstance(payload, dict):
        raise ValueError("benchmark spec must be a mapping/object")
    tasks = payload.get("tasks")
    if not isinstance(tasks, dict) or not tasks:
        raise ValueError("benchmark spec must contain a non-empty tasks mapping")
    return payload


def latest_benchmark_summaries(profile: Profile) -> dict[str, dict[str, Any]]:
    root = profile.workspace / ".aiplane" / "benchmarks"
    if not root.exists():
        return {}
    candidates = sorted(
        root.glob("*.json"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    summaries: dict[str, dict[str, Any]] = {}
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        model_name = str(payload.get("model_name") or "")
        if not model_name and "-" in path.stem:
            model_name = path.stem.split("-", 1)[1]
        summary = payload.get("summary")
        if model_name and model_name not in summaries and isinstance(summary, dict):
            summaries[model_name] = {"path": str(path), **summary}
    return summaries


def latest_benchmark_summary(profile: Profile, model_name: str) -> dict[str, Any] | None:
    return latest_benchmark_summaries(profile).get(model_name)


def _select_tasks(spec: dict[str, Any], task: str) -> list[tuple[str, dict[str, Any]]]:
    raw_tasks = spec.get("tasks") if isinstance(spec.get("tasks"), dict) else {}
    tasks = {str(name): value for name, value in raw_tasks.items() if isinstance(value, dict)}
    if task == "all":
        return sorted(tasks.items())
    if task not in tasks:
        raise ValueError("task must be one of: " + ", ".join([*sorted(tasks), "all"]))
    return [(task, tasks[task])]


def _task_score(passed: bool | None, elapsed_ms: float, output_length: int, dry_run: bool) -> int:
    if dry_run:
        return 0
    if not passed:
        return 0
    score = 60
    if elapsed_ms <= 5_000:
        score += 25
    elif elapsed_ms <= 15_000:
        score += 15
    elif elapsed_ms <= 30_000:
        score += 5
    if 20 <= output_length <= 4000:
        score += 15
    elif output_length > 0:
        score += 5
    return min(100, score)


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"passed": 0, "failed": 0, "average_score": 0, "average_elapsed_ms": 0}
    if all(row.get("passed") is None for row in results):
        return {
            "previewed": len(results),
            "passed": 0,
            "failed": 0,
            "average_score": 0,
            "average_elapsed_ms": 0,
        }
    scored_results = [row for row in results if row.get("passed") is not None]
    scores = [float(row.get("score", 0)) for row in scored_results]
    elapsed = [float(row.get("elapsed_ms", 0)) for row in scored_results]
    passed = sum(1 for row in scored_results if row.get("passed"))
    return {
        "passed": passed,
        "failed": len(scored_results) - passed,
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "average_elapsed_ms": round(sum(elapsed) / len(elapsed), 2) if elapsed else 0,
    }


def _list_value(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _clamp_score(value: object) -> int:
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return 0
