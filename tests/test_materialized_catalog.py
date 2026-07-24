from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from aiplane import config as agent_config
from aiplane.cli import main as cli_main
from aiplane.model_catalog import ModelCatalog
from aiplane.providers import ProviderModelsResult, ProviderRegistry
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile


def _write_discovered_model(profile_root: Path, *, quantization: str = "q4") -> None:
    payload = {
        "models": {
            "ollama-synthetic-chat": {
                "provider": "ollama",
                "source": "ollama",
                "model": "example/synthetic-7b",
                "roles": ["chat", "analysis"],
                "supported_runtimes": ["ollama", "vllm"],
                "preferred_runtime": "ollama",
                "enabled": True,
                "quantization": quantization,
                "context_tokens": 32768,
                "min_ram_gb": 16,
                "min_vram_gb": 6,
                "capability_scores": {"analysis": 4, "tool_use": 3},
                "capability_score_source": "configured",
                "source_metadata": {"likes": 500, "downloads": 5000, "pipeline_tag": "text-generation"},
                "api_key": "must-not-be-materialized",
                "api_key_env": "SYNTHETIC_API_KEY",
            }
        }
    }
    (profile_root / "models.discovered.yaml").write_text(agent_config.dump_yaml(payload), encoding="utf-8")


def _write_benchmark(workspace: Path) -> None:
    root = workspace / ".aiplane" / "benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    (root / "20260101T000000Z-ollama-synthetic-chat.json").write_text(
        json.dumps(
            {
                "model_name": "ollama-synthetic-chat",
                "summary": {"average_score": 96, "passed": 3, "failed": 0},
            }
        ),
        encoding="utf-8",
    )


def test_materialized_catalog_matches_fallback_for_indexed_and_numeric_filters(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        _write_discovered_model(profile.root)
        _write_benchmark(tmp_path)
        catalog = ModelCatalog(profile)
        filters = {
            "name": "ollama-synthetic-chat",
            "model": "example/synthetic-7b",
            "provider": "ollama",
            "runtime": "ollama",
            "roles": ["chat"],
            "min_parameters_b": 7,
            "max_parameters_b": 8,
            "min_benchmark_score": 95,
            "min_likes": 100,
            "properties": {
                "quantization": "q4",
                "context_tokens": 32768,
                "source_metadata.pipeline_tag": "text-generation",
            },
        }
        fallback = catalog.filter(filters, use_materialized=False)
        indexed = catalog.filter(filters)
        assert indexed == fallback
        assert [row["name"] for row in indexed] == ["ollama-synthetic-chat"]
        assert catalog.materialized.path.is_file()
        payload = json.loads(catalog.materialized.path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload["row_count"] >= 1
        assert payload["indexes"]["provider"][json.dumps("ollama")]
        serialized = catalog.materialized.path.read_text(encoding="utf-8")
        assert "must-not-be-materialized" not in serialized
        assert "SYNTHETIC_API_KEY" in serialized
        assert '"context_tokens":32768' in serialized


def test_materialized_catalog_rebuilds_when_sources_change_or_cache_is_corrupt(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        _write_discovered_model(profile.root, quantization="q4")
        first_catalog = ModelCatalog(profile)
        assert first_catalog.filter({"properties": {"quantization": "q4"}})
        first_status = first_catalog.materialized_status()
        assert first_status["freshness"] == "current"
        assert first_status["generated_at"]
        assert first_status["provenance"]["secret_policy"] == "secret-bearing properties are excluded"

        _write_discovered_model(profile.root, quantization="q8")
        second_catalog = ModelCatalog(profile)
        q8_rows = second_catalog.filter({"properties": {"quantization": "q8"}})
        assert [row["name"] for row in q8_rows] == ["ollama-synthetic-chat"]
        second_status = second_catalog.materialized_status()
        assert second_status["input_digest"] != first_status["input_digest"]

        second_catalog.materialized.path.write_text("{broken", encoding="utf-8")
        recovered = ModelCatalog(profile).filter({"name": "ollama-synthetic-chat"})
        assert [row["name"] for row in recovered] == ["ollama-synthetic-chat"]
        assert json.loads(second_catalog.materialized.path.read_text(encoding="utf-8"))["schema_version"] == "1.0"
        stale = ModelCatalog(profile).materialized_status()
        assert stale["freshness"] == "current"


def test_materialized_catalog_treats_pre_provenance_cache_as_stale(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        _write_discovered_model(profile.root)
        catalog = ModelCatalog(profile)
        catalog.filter({"name": "ollama-synthetic-chat"})
        payload = json.loads(catalog.materialized.path.read_text(encoding="utf-8"))
        payload.pop("generated_at")
        catalog.materialized.path.write_text(json.dumps(payload), encoding="utf-8")
        status = ModelCatalog(profile).materialized_status()
        assert status["freshness"] == "stale_or_incompatible"
        assert status["next_command"] == "aiplane models catalog-cache rebuild"


def test_refresh_write_generates_materialized_catalog(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:7b"], "synthetic refresh")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            result = ModelCatalog(profile).refresh("ollama", write=True)
        cache = result["materialized_catalog"]
        assert cache["persisted"] is True
        assert cache["rebuilt"] is True
        assert Path(cache["path"]).is_file()
        rows = ModelCatalog(profile).filter({"model": "new-model:7b"})
        assert len(rows) == 1


def test_models_cli_queries_materialized_properties_and_manages_cache(tmp_path: Path, capsys) -> None:
    with _isolated_profiles_dir() as profiles_dir:
        profile_root = profiles_dir / "local-dev"
        _write_discovered_model(profile_root)
        common = ["--profiles-dir", str(profiles_dir)]
        assert (
            cli_main(
                common
                + [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--alias",
                    "ollama-synthetic-chat",
                    "--model-id",
                    "example/synthetic-7b",
                    "--runner",
                    "ollama",
                    "--property",
                    "quantization=q4",
                ]
            )
            == 0
        )
        rows = json.loads(capsys.readouterr().out)
        assert [row["name"] for row in rows] == ["ollama-synthetic-chat"]

        assert cli_main(common + ["models", "catalog-cache", "--profile", "local-dev", "status"]) == 0
        assert json.loads(capsys.readouterr().out)["current"] is True
        assert cli_main(common + ["models", "catalog-cache", "--profile", "local-dev", "clear"]) == 0
        assert json.loads(capsys.readouterr().out)["removed"] is True
        assert cli_main(common + ["models", "catalog-cache", "--profile", "local-dev", "rebuild"]) == 0
        assert json.loads(capsys.readouterr().out)["persisted"] is True
