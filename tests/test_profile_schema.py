from __future__ import annotations

import copy
import json

import pytest

from aiplane.cli import main as cli_main
from aiplane.config import create_profile, dump_yaml, load_profile, parse_yaml
from aiplane.profile_schema import (
    PROFILE_SCHEMA_ID,
    PROFILE_SCHEMA_VERSION,
    canonical_profile,
    load_profile_schema,
    merge_profile_documents,
)


def test_profile_schema_v1_is_dependency_free_and_matches_canonical_document(tmp_path, capsys) -> None:
    profiles = tmp_path / "profiles"
    create_profile("schema-test", profiles_dir=profiles)
    profile = load_profile("schema-test", tmp_path, profiles_dir=profiles)
    document = canonical_profile(profile)
    schema = load_profile_schema()

    assert schema["$id"] == PROFILE_SCHEMA_ID
    assert document["$schema"] == PROFILE_SCHEMA_ID
    assert document["schema_version"] == PROFILE_SCHEMA_VERSION
    assert set(schema["required"]).issubset(document)
    for key in schema["required"]:
        expected = schema["properties"][key].get("type")
        if expected == "object":
            assert isinstance(document[key], dict)
        elif expected == "string":
            assert isinstance(document[key], str)

    assert cli_main(["--profiles-dir", str(profiles), "profiles", "schema"]) == 0
    cli_schema = json.loads(capsys.readouterr().out)
    assert cli_schema == schema


def test_profile_render_is_canonical_deterministic_and_read_only(tmp_path, capsys) -> None:
    profiles = tmp_path / "profiles"
    create_profile("render-test", profiles_dir=profiles)
    before = {path.name: path.read_bytes() for path in (profiles / "render-test").glob("*.yaml")}
    command = ["--profiles-dir", str(profiles), "profiles", "render", "render-test"]

    assert cli_main(command) == 0
    first = capsys.readouterr().out
    assert cli_main(command) == 0
    second = capsys.readouterr().out

    assert first == second
    document = json.loads(first)
    assert document["schema_version"] == "1.0"
    assert document["name"] == "render-test"
    after = {path.name: path.read_bytes() for path in (profiles / "render-test").glob("*.yaml")}
    assert after == before


def test_profile_merge_semantics_are_recursive_and_non_mutating() -> None:
    base = {
        "schema_version": "1.0",
        "models": {"defaults": {"chat_model": "small", "embedding_model": "embed"}, "tags": ["base"]},
        "repository": {"allow_cloud": True},
    }
    override = {
        "models": {"defaults": {"chat_model": "large"}, "tags": ["override"]},
        "repository": None,
    }
    original_base = copy.deepcopy(base)
    original_override = copy.deepcopy(override)

    merged = merge_profile_documents(base, override)

    assert merged["models"]["defaults"] == {"chat_model": "large", "embedding_model": "embed"}
    assert merged["models"]["tags"] == ["override"]
    assert merged["repository"] is None
    assert base == original_base
    assert override == original_override


def test_profile_validation_rejects_ambiguous_recommendation_fields(tmp_path, capsys) -> None:
    profiles = tmp_path / "profiles"
    create_profile("invalid-model", profiles_dir=profiles)
    models_path = profiles / "invalid-model" / "models.yaml"
    models = parse_yaml(models_path.read_text(encoding="utf-8"))
    models["defaults"] = {"chat_model": None}
    models["models"] = {
        "bad": {
            "model": "bad:latest",
            "provider": "ollama",
            "local": "yes",
            "min_ram_gb": -1,
            "min_vram_gb": 8,
            "recommended_vram_gb": 4,
            "supported_runtimes": ["ollama", "ollama"],
        }
    }
    models_path.write_text(dump_yaml(models), encoding="utf-8")

    assert cli_main(["--profiles-dir", str(profiles), "profiles", "validate", "invalid-model"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    failed = {check["path"]: check for check in payload["checks"] if not check["ok"]}
    assert "$.models.models.bad.local" in failed
    assert "$.models.models.bad.min_ram_gb" in failed
    assert "$.models.models.bad.recommended_vram_gb" in failed
    assert "$.models.models.bad.supported_runtimes" in failed
    assert all(check["remediation"] for check in failed.values())
    default = next(check for check in payload["checks"] if check["name"] == "model_default:chat_model")
    assert default["ok"] is True
    assert default["detail"] == "unset"


def test_profile_validation_reports_schema_version_paths_and_remedies(tmp_path, capsys) -> None:
    profiles = tmp_path / "profiles"
    create_profile("validate-test", profiles_dir=profiles)

    assert cli_main(["--profiles-dir", str(profiles), "profiles", "validate", "validate-test"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == "1.0"
    assert payload["ok"]
    assert any(check["name"] == "schema:version" for check in payload["checks"])
    assert all(check["path"] for check in payload["checks"])
    assert all(check["remediation"] for check in payload["checks"])


def test_profile_validation_rejects_invalid_placement_scoring(tmp_path, capsys) -> None:
    profiles = tmp_path / "profiles"
    create_profile("invalid-scoring", profiles_dir=profiles)
    hardware_path = profiles / "invalid-scoring" / "hardware.yaml"
    hardware = parse_yaml(hardware_path.read_text(encoding="utf-8"))
    hardware["placement_scoring"] = {
        "default_profile": "bad",
        "profiles": {"bad": {"weights": {"resource_fit": -0.1}}},
        "extensions": [{"name": "unsafe", "source_key": "unsafe", "weight": 2}],
    }
    hardware_path.write_text(dump_yaml(hardware), encoding="utf-8")

    assert cli_main(["--profiles-dir", str(profiles), "profiles", "validate", "invalid-scoring"]) == 1
    payload = json.loads(capsys.readouterr().out)
    failed = {check["path"]: check for check in payload["checks"] if not check["ok"]}

    assert "$.hardware.placement_scoring" in failed
    assert "between 0 and 1" in failed["$.hardware.placement_scoring"]["detail"]


def test_parse_yaml_rejects_dash_list_syntax_with_actionable_error() -> None:
    with pytest.raises(ValueError, match="dash-list syntax at line 2"):
        parse_yaml("models:\n  - fixture-chat-small\n")


def test_parse_yaml_rejects_document_markers_with_actionable_error() -> None:
    with pytest.raises(ValueError, match="document marker at line 1"):
        parse_yaml("---\nmodels: {}\n")


def test_parse_yaml_rejects_block_scalars_with_actionable_error() -> None:
    with pytest.raises(ValueError, match="block scalar at line 2"):
        parse_yaml("notes:\n  text: |\n")
