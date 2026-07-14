from __future__ import annotations

import copy
import json

from aiplane.cli import main as cli_main
from aiplane.config import create_profile, load_profile
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
