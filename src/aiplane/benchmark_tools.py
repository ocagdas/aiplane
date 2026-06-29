from __future__ import annotations

from typing import Any

from .models import Profile
from .tools import ToolchainManager


BENCHMARK_FRAMEWORKS: dict[str, dict[str, Any]] = {
    "aiplane-smoke": {
        "description": "Built-in smoke/custom benchmark runner for configured aiplane model aliases.",
        "kind": "quality_smoke",
        "tool": None,
        "install": "built_in",
        "best_for": ["quick local sanity checks", "custom evaluator specs", "code-generation smoke tests"],
    },
    "lm-evaluation-harness": {
        "description": "EleutherAI LM Evaluation Harness for standard academic and custom language-model evaluations.",
        "kind": "quality_standard",
        "tool": "lm-evaluation-harness",
        "install": "pip_helper",
        "best_for": ["standard benchmark tasks", "comparability", "HF/vLLM/API model evaluation"],
    },
    "vllm-serving": {
        "description": "vLLM serving benchmark commands for endpoint throughput/latency/concurrency checks.",
        "kind": "serving_performance",
        "tool": "vllm-benchmark-scripts",
        "install": "pip_helper_or_runtime_install",
        "best_for": ["tokens/sec", "latency", "concurrency", "runtime parameter sweeps"],
    },
    "locust-load": {
        "description": "Locust load testing for OpenAI-compatible endpoints and gateway throttling/fairness checks.",
        "kind": "endpoint_load",
        "tool": "locust",
        "install": "pip_helper",
        "best_for": ["multi-user load", "gateway rate limits", "queue behavior"],
    },
}


class BenchmarkToolManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.tools = ToolchainManager(profile)

    def list(self) -> list[dict[str, Any]]:
        return [self._row(name) for name in sorted(BENCHMARK_FRAMEWORKS)]

    def doctor(self, name: str | None = None) -> dict[str, Any]:
        names = [name] if name else sorted(BENCHMARK_FRAMEWORKS)
        rows = [self._row(item) for item in names]
        return {
            "name": "benchmark_tools_doctor",
            "ok": all(bool(row.get("available")) or row.get("install") == "built_in" for row in rows),
            "frameworks": rows,
            "notes": [
                "aiplane-smoke is built in and uses aiplane models benchmark.",
                "External benchmark tools are optional. Install them only in an environment where their dependencies make sense.",
                "GPU-heavy tools such as vLLM may need CUDA/PyTorch-compatible system setup beyond pip installation.",
            ],
        }

    def install(self, name: str, dry_run: bool = True) -> dict[str, Any]:
        row = self._row(name)
        tool_name = row.get("tool")
        if not tool_name:
            return {
                "name": name,
                "dry_run": dry_run,
                "installed": True,
                "results": [],
                "notes": ["This benchmark framework is built into aiplane; no external install is needed."],
            }
        return self.tools.install(str(tool_name), dry_run=dry_run, yes=not dry_run)

    def plan(self, name: str, model: str = "MODEL_ALIAS", endpoint: str | None = None, spec: str | None = None) -> dict[str, Any]:
        row = self._row(name)
        endpoint = endpoint or "http://localhost:8000/v1"
        if name == "aiplane-smoke":
            command = ["aiplane", "models", "benchmark", model]
            if spec:
                command.extend(["--spec", spec])
            return {"name": name, "framework": row, "commands": [{"name": "run", "command": command}], "notes": ["Use --dry-run on aiplane models benchmark to preview prompts/evaluators."]}
        if name == "lm-evaluation-harness":
            return {
                "name": name,
                "framework": row,
                "commands": [
                    {"name": "inspect_help", "command": ["lm_eval", "run", "-h"]},
                    {
                        "name": "template_openai_compatible_eval",
                        "command": [
                            "lm_eval",
                            "run",
                            "--model",
                            "local-completions",
                            "--model_args",
                            f"model={model},base_url={endpoint}",
                            "--tasks",
                            "hellaswag",
                        ],
                    },
                ],
                "notes": ["Treat this as a starting template; lm-evaluation-harness model names and args can vary by installed version and task."],
            }
        if name == "vllm-serving":
            return {
                "name": name,
                "framework": row,
                "commands": [
                    {"name": "inspect_help", "command": ["vllm", "bench", "serve", "--help"]},
                    {
                        "name": "template_serving_benchmark",
                        "command": ["vllm", "bench", "serve", "--backend", "openai", "--base-url", endpoint, "--model", model],
                    },
                ],
                "notes": ["Run against an already started vLLM/OpenAI-compatible endpoint. Confirm flags with the installed vLLM version before long runs."],
            }
        if name == "locust-load":
            return {
                "name": name,
                "framework": row,
                "commands": [
                    {"name": "inspect_help", "command": ["locust", "--help"]},
                    {"name": "template_load_test", "command": ["locust", "-f", "benchmarks/locust_openai.py", "--host", endpoint]},
                ],
                "notes": ["Requires a user-provided Locust file that calls the endpoint shape you want to test."],
            }
        raise ValueError(f"unknown benchmark framework: {name}")

    def _row(self, name: str) -> dict[str, Any]:
        if name not in BENCHMARK_FRAMEWORKS:
            raise ValueError(f"unknown benchmark framework: {name}")
        spec = BENCHMARK_FRAMEWORKS[name]
        tool_name = spec.get("tool")
        tool = self.tools.tool_status(str(tool_name)) if tool_name else None
        return {
            "name": name,
            "kind": spec.get("kind"),
            "description": spec.get("description"),
            "install": spec.get("install"),
            "tool": tool_name,
            "available": True if tool_name is None else bool(tool and tool.get("installed")),
            "tool_status": tool,
            "best_for": spec.get("best_for", []),
        }
