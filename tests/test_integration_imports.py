from __future__ import annotations

import json
from pathlib import Path

from aiplane.config import load_profile, parse_yaml
from aiplane.integration_imports import import_client_config
from aiplane.profile_schema import canonical_profile, structural_profile_findings


def test_continue_import_is_preview_first_and_secret_free(tmp_path: Path) -> None:
    config = tmp_path / "continue.json"
    env_reference = "$" + "{OPENAI_API_KEY}"
    config.write_text(
        json.dumps(
            {
                "models": [
                    {"title": "Local Chat", "provider": "ollama", "model": "qwen3:8b", "apiKey": "literal-secret"},
                    {"title": "Cloud Chat", "provider": "openai", "model": "gpt-example", "apiKey": env_reference},
                ]
            }
        )
    )
    profiles = tmp_path / "profiles"
    preview = import_client_config("continue", config, profile_name="imported", profiles_dir=profiles)
    assert preview["preview"] is True
    assert not (profiles / "imported").exists()

    written = import_client_config("continue", config, profile_name="imported", profiles_dir=profiles, yes=True)
    assert written["written"] is True
    serialized = (profiles / "imported" / "models.yaml").read_text()
    assert "literal-secret" not in serialized
    assert "OPENAI_API_KEY" in serialized
    repository = parse_yaml((profiles / "imported" / "repository.yaml").read_text())
    findings = structural_profile_findings(canonical_profile(load_profile("imported", tmp_path, profiles_dir=profiles)))
    assert all(finding["ok"] for finding in findings), findings
    assert repository["import_review"] == {
        "status": "unapproved",
        "source_tool": "continue",
        "secrets_copied": False,
        "review_required": True,
    }


def test_aider_yaml_import_preserves_environment_credential_reference(tmp_path: Path) -> None:
    config = tmp_path / "aider.yml"
    config.write_text("model: ollama_chat/qwen3:8b\nweak-model: openai/gpt-small\nopenai-api-key: $OPENAI_API_KEY\n")
    payload = import_client_config("aider", config, profile_name="draft", profiles_dir=tmp_path / "profiles")
    assert {row["model"] for row in payload["models"].values()} == {"qwen3:8b", "gpt-small"}
    assert all(row.get("api_key_env") == "OPENAI_API_KEY" for row in payload["models"].values())
