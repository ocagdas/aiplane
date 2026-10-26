"""Explicit measurement definitions; missing controls never become matches."""

from __future__ import annotations

from typing import Any

METRIC_DEFINITIONS = {
    "server_tokens_per_second": {
        "unit": "tokens/s",
        "numerator": "provider_output_tokens",
        "denominator": "server_generation_seconds",
    },
    "client_tokens_per_second": {
        "unit": "tokens/s",
        "numerator": "provider_output_tokens",
        "denominator": "client_dispatch_to_body_parsed_seconds",
    },
    "average_tokens_per_second": {"unit": "tokens/s", "method": "mean_available_source_rates"},
    "elapsed_ms": {"unit": "ms", "interval": "client_dispatch_to_body_parsed"},
    "task_elapsed_ms": {"unit": "ms", "interval": "model_call_including_routing_excluding_grading"},
    "ttft_ms": {"unit": "ms", "interval": "client_dispatch_to_first_nonempty_content"},
    "quality_score": {"unit": "score_0_100", "method": "suite_evaluator"},
    "performance_score": {"unit": "score_0_100", "method": "suite_evaluator"},
}

REQUIRED_CONTEXT = {
    "workload": ("inputs", "rubric", "prompt", "harness"),
    "model": ("artifact", "tokenizer"),
    "runtime": ("build",),
    "execution": ("route", "cache", "concurrency", "tools"),
}


def known(value: Any) -> bool:
    if (
        value is None
        or value == ""
        or (isinstance(value, str) and value.lower() in {"unknown", "unverified", "unspecified"})
    ):
        return False
    if isinstance(value, dict):
        return bool(value) and all(known(item) for item in value.values())
    if isinstance(value, list):
        return bool(value) and all(known(item) for item in value)
    return True
