import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aiplane.cli import main as cli_main
from aiplane.config import load_profile
from aiplane.role_routing import compare_role_models


def test_role_comparison_prioritizes_comparable_evidence_and_keeps_alternatives() -> None:
    profile = load_profile("local-dev", Path.cwd())
    models = profile.models["models"]
    models["fixture-analysis-small"]["roles"].append("chat")
    models["fixture-code-small"]["roles"].append("chat")
    assessment = {
        "machine": {"name": "synthetic"},
        "scoring": {"contract": "placement_readiness"},
        "models": {
            "recommended": [
                {
                    "name": "fixture-analysis-small",
                    "model": "native-a",
                    "provider": "ollama",
                    "level": "recommended",
                    "selection_score": 95,
                    "reason": "fits",
                    "policy_decision": {"allowed": True},
                    "capabilities": {"scores": {"general_chat": 4}},
                    "latest_benchmark": {
                        "benchmark_kind": "comparable_quality",
                        "quality_score": 70,
                        "sample_count": 5,
                    },
                    "score": {"components": {"team_score": {"value": 80, "source": "configured_extension"}}},
                    "runtime_recommendation": "ollama",
                    "provenance": {"method": "test"},
                },
                {
                    "name": "fixture-code-small",
                    "model": "native-b",
                    "provider": "ollama",
                    "level": "recommended",
                    "selection_score": 99,
                    "reason": "fits",
                    "policy_decision": {"allowed": True},
                    "capabilities": {"scores": {"general_chat": 5}},
                    "latest_benchmark": {
                        "benchmark_kind": "comparable_quality",
                        "quality_score": 60,
                        "sample_count": 5,
                    },
                    "score": {"components": {}},
                    "runtime_recommendation": "ollama",
                    "provenance": {"method": "test"},
                },
            ],
            "usable": [],
            "remote_or_cloud": [],
            "not_recommended": [],
        },
    }
    with patch("aiplane.role_routing.HardwareManager.recommend", return_value=assessment):
        result = compare_role_models(profile, "chat")

    assert result["recommended"]["name"] == "fixture-analysis-small"
    assert len(result["alternatives"]) == 2
    assert result["recommended"]["measured_quality"]["value"] == 70
    assert result["recommended"]["score_components"]["team_score"]["value"] == 80


def test_role_comparison_cli_dispatches_explicit_candidates() -> None:
    assessment = {
        "machine": {"name": "synthetic"},
        "scoring": {"contract": "placement_readiness"},
        "models": {
            "recommended": [
                {
                    "name": "fixture-analysis-small",
                    "model": "native-a",
                    "provider": "ollama",
                    "level": "recommended",
                    "selection_score": 90,
                    "reason": "fits",
                    "policy_decision": {"allowed": True},
                    "capabilities": {"scores": {"general_chat": 4}},
                    "score": {"components": {}},
                }
            ],
            "usable": [],
            "remote_or_cloud": [],
            "not_recommended": [],
        },
    }
    stdout = StringIO()
    with patch("aiplane.role_routing.HardwareManager.recommend", return_value=assessment):
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "route",
                    "--role",
                    "chat",
                    "--candidate",
                    "fixture-analysis-small",
                ]
            )
    assert code == 0
    assert json.loads(stdout.getvalue())["recommended"]["name"] == "fixture-analysis-small"
