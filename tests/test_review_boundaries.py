"""Public path regressions for safe search, imports, archives and disposable caches."""

import importlib.util
import json
import shutil
import sys
import pytest
from aiplane.audit import AuditLogger
from aiplane.models import Profile
from aiplane.tool_execution import ToolExecutor
from aiplane.integration_imports import import_client_config
from aiplane.profile_archive import archive_profile
from aiplane.config import create_profile
from aiplane.model_catalog import ModelCatalog
from aiplane.materialized_catalog import clear_materialized_memory_cache
from aiplane.secrets import REDACTED, contains_secret, redact
from tests.profile_fixtures import _isolated_test_profile


def _load_script(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_repository_standard = _load_script(
    "scripts.test_check_repository_standard",
    "/home/runner/work/aiplane/aiplane/scripts/check_repository_standard.py",
)


@pytest.mark.skipif(not shutil.which("rg"), reason="Requires ripgrep")
def test_read_only_search_treats_options_as_patterns(tmp_path):
    (tmp_path / "file.txt").write_text("--files\n--pre=not-a-command\n", encoding="utf-8")
    profile = Profile(
        name="review",
        root=tmp_path / "profile",
        workspace=tmp_path,
        hardware={},
        backends={},
        repository={},
        tools={"mode": "read_only", "allowed": ["grep"]},
        approvals={},
        environment={"active": "system"},
        models={},
        targets={},
    )
    executor = ToolExecutor(profile, AuditLogger(profile))
    assert "--files" in executor.run("grep", ["--files", "file.txt"])
    assert "--pre=not-a-command" in executor.run("grep", ["--pre=not-a-command", "file.txt"])


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:synthetic-password@example.invalid/v1",
        "https://example.invalid/v1?subscription_key=synthetic-value",
    ],
)
@pytest.mark.parametrize("yes", [False, True])
def test_import_rejects_url_credentials_before_any_write(tmp_path, endpoint, yes):
    source = tmp_path / "continue.json"
    source.write_text(
        json.dumps({"models": [{"title": "demo", "model": "demo", "provider": "openai", "apiBase": endpoint}]})
    )
    profiles = tmp_path / "profiles"
    with pytest.raises(ValueError, match="endpoint contains credentials") as error:
        import_client_config("continue", source, profile_name="draft", profiles_dir=profiles, yes=yes)
    assert "synthetic" not in str(error.value)
    assert not profiles.exists()


@pytest.mark.parametrize("key", ["subscription_key", "oauth_token"])
def test_archive_rejects_sensitive_mapping_keys(tmp_path, key):
    root = tmp_path / "profiles"
    profile = create_profile("test", profiles_dir=root)
    (profile / "model-providers.yaml").write_text(f"demo:\n  {key}: synthetic-value\n")
    with pytest.raises(ValueError, match="credential material"):
        archive_profile("test", tmp_path / "archive.json", profiles_dir=root)
    assert not (tmp_path / "archive.json").exists()


def test_corrupt_index_is_rebuilt_from_authoritative_models(tmp_path):
    with _isolated_test_profile(workspace=tmp_path) as profile:
        catalog = ModelCatalog(profile)
        expected = catalog.filter({}, use_materialized=False)
        catalog.rebuild_materialized()
        payload = json.loads(catalog.materialized.path.read_text())
        payload["indexes"]["name"] = {"invalid": [999999]}
        catalog.materialized.path.write_text(json.dumps(payload))
        clear_materialized_memory_cache()
        assert ModelCatalog(profile).filter({}) == expected
        assert json.loads(catalog.materialized.path.read_text())["indexes"]["name"] != {"invalid": [999999]}


def test_credentials_list_redacts_endpoint_and_notes(tmp_path, capsys):
    from aiplane.cli import main

    path = tmp_path / "credentials.yaml"
    path.write_text(
        "providers:\n  demo:\n    accounts:\n      test:\n"
        "        endpoint: https://user:synthetic-password@example.invalid\n"
        "        notes: 'oauth_token: synthetic-note-token'\n"
        "        api_key_env: DEMO_API_KEY\n",
        encoding="utf-8",
    )
    assert main(["credentials", "list", "--path", str(path)]) == 0
    output = capsys.readouterr().out
    assert "synthetic-password" not in output
    assert "synthetic-note-token" not in output
    assert "DEMO_API_KEY" in output
    assert "REDACTED" in output


def test_secret_detectors_cover_serialized_and_textual_token_spellings() -> None:
    assert contains_secret('{"subscription_key": "synthetic-secret"}')
    assert redact("oauth_token: synthetic-note-token") == REDACTED


def test_repository_standard_rejects_unsafe_version_mirror_paths(tmp_path) -> None:
    with pytest.raises(ValueError, match="version_mirror"):
        check_repository_standard.safe_repo_relative_path(tmp_path, "../../outside.txt")


@pytest.mark.parametrize(
    "field,value",
    [
        ("capability_avg_score", "not-a-number"),
        ("parameter_count_b", []),
        ("likes", float("nan")),
        ("likes", 10**1000),
        ("downloads", float("inf")),
        ("capabilities", None),
        ("capabilities", {"scores": {"analysis": "bad"}}),
        ("latest_benchmark", {"average_score": "bad"}),
        ("roles", None),
        ("supported_runtimes", {}),
    ],
)
def test_malformed_cached_rows_rebuild(tmp_path, field, value):
    with _isolated_test_profile(workspace=tmp_path) as profile:
        catalog = ModelCatalog(profile)
        expected = catalog.filter({}, use_materialized=False)
        catalog.rebuild_materialized()
        payload = json.loads(catalog.materialized.path.read_text(encoding="utf-8"))
        payload["rows"][0][field] = value
        # Keep indexes internally consistent: row validation must catch the corruption.
        payload["indexes"] = catalog.materialized.build_payload(payload["rows"], payload["input_digest"])["indexes"]
        catalog.materialized.path.write_text(json.dumps(payload), encoding="utf-8")
        clear_materialized_memory_cache()
        repaired = ModelCatalog(profile)
        assert repaired.filter({}) == expected
        assert repaired.ensure_materialized()[1]["rebuilt"] is False
