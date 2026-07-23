from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiplane.cli import main as cli_main
from aiplane.config import CONFIG_FILES, create_profile
from aiplane.profile_archive import (
    EXCLUDED_PROFILE_STATE,
    PROFILE_ARCHIVE_KIND,
    PROFILE_ARCHIVE_EXCLUSION_CONTRACT_VERSION,
    PROFILE_ARCHIVE_VERSION,
    archive_profile,
    load_profile_archive,
    restore_profile_archive,
)


def _profile_fixture(tmp_path: Path, name: str = "source") -> tuple[Path, Path]:
    profiles_dir = tmp_path / "profiles"
    profile = create_profile(name, profiles_dir=profiles_dir)
    (profile / "models.discovered.yaml").write_text("generated: true\n", encoding="utf-8")
    (profile / "model-providers.user.yaml").write_text("local_override: true\n", encoding="utf-8")
    (profile / ".models.yaml.lock").write_text("lock", encoding="utf-8")
    return profiles_dir, profile


def test_archive_is_deterministic_checksummed_and_explicitly_excludes_machine_state(tmp_path: Path) -> None:
    profiles_dir, _ = _profile_fixture(tmp_path)
    first = tmp_path / "first.aiplane-profile.json"
    second = tmp_path / "second.aiplane-profile.json"

    first_result = archive_profile("source", first, profiles_dir=profiles_dir)
    second_result = archive_profile("source", second, profiles_dir=profiles_dir)

    assert first.read_bytes() == second.read_bytes()
    assert first_result["archive_sha256"] == second_result["archive_sha256"]
    archive = load_profile_archive(first)
    assert archive["kind"] == PROFILE_ARCHIVE_KIND
    assert archive["schema_version"] == PROFILE_ARCHIVE_VERSION
    included = {entry["path"] for entry in archive["manifest"]["included"]}
    assert set(CONFIG_FILES.values()) <= included
    assert "model-providers.yaml" in included
    assert archive["manifest"]["excluded_contract_version"] == PROFILE_ARCHIVE_EXCLUSION_CONTRACT_VERSION
    assert archive["manifest"]["excluded"] == list(EXCLUDED_PROFILE_STATE)
    archived_paths = {entry["path"] for entry in archive["files"]}
    assert archived_paths.isdisjoint({"models.discovered.yaml", "model-providers.user.yaml", ".models.yaml.lock"})


def test_archive_dry_run_validates_manifest_without_writing(tmp_path: Path) -> None:
    profiles_dir, _ = _profile_fixture(tmp_path)
    output = tmp_path / "source.aiplane-profile.json"

    result = archive_profile("source", output, profiles_dir=profiles_dir, dry_run=True)

    assert result["dry_run"]
    assert result["would_write"]
    assert not result["written"]
    assert not output.exists()
    assert len(result["manifest"]["included"]) == 10


def test_archive_rejects_raw_credentials_and_symlinked_profile_files(tmp_path: Path) -> None:
    profiles_dir, profile = _profile_fixture(tmp_path)
    models = profile / "models.yaml"
    models.write_text(models.read_text(encoding="utf-8") + "api_key: opaque-secret-value-123456\n", encoding="utf-8")

    with pytest.raises(ValueError, match="forbidden credential material.*models.yaml"):
        archive_profile("source", tmp_path / "unsafe.json", profiles_dir=profiles_dir)

    models.write_text("defaults: {}\nmodels: {}\n# token: opaque-comment-secret-123456\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"models.yaml at \$line"):
        archive_profile("source", tmp_path / "unsafe-comment.json", profiles_dir=profiles_dir)

    models.unlink()
    models.symlink_to(profile / "tools.yaml")
    with pytest.raises(ValueError, match="non-symlink file: models.yaml"):
        archive_profile("source", tmp_path / "symlink.json", profiles_dir=profiles_dir)


def test_restore_previews_then_atomically_creates_a_new_profile(tmp_path: Path) -> None:
    profiles_dir, source_profile = _profile_fixture(tmp_path)
    archive_path = tmp_path / "source.aiplane-profile.json"
    archive_profile("source", archive_path, profiles_dir=profiles_dir)

    preview = restore_profile_archive(archive_path, name="restored", profiles_dir=profiles_dir)

    assert preview["dry_run"]
    assert preview["requires_yes"]
    assert preview["would_restore"]
    assert not (profiles_dir / "restored").exists()

    result = restore_profile_archive(archive_path, name="restored", profiles_dir=profiles_dir, yes=True)

    restored = profiles_dir / "restored"
    assert result["restored"]
    assert restored.is_dir()
    for filename in (*CONFIG_FILES.values(), "model-providers.yaml"):
        assert (restored / filename).read_bytes() == (source_profile / filename).read_bytes()
    assert not (restored / "models.discovered.yaml").exists()
    assert not (restored / "model-providers.user.yaml").exists()
    assert not list(restored.glob("*.lock"))


def test_restore_preserves_existing_profiles_even_with_confirmation(tmp_path: Path) -> None:
    profiles_dir, _ = _profile_fixture(tmp_path)
    archive_path = tmp_path / "source.aiplane-profile.json"
    archive_profile("source", archive_path, profiles_dir=profiles_dir)
    existing = create_profile("existing", profiles_dir=profiles_dir)
    marker = existing / "models.yaml"
    before = marker.read_bytes()

    preview = restore_profile_archive(archive_path, name="existing", profiles_dir=profiles_dir)
    assert preview["conflicts"] == ["profile_exists"]
    assert not preview["would_restore"]

    with pytest.raises(ValueError, match="existing profiles are never overwritten"):
        restore_profile_archive(archive_path, name="existing", profiles_dir=profiles_dir, yes=True)
    assert marker.read_bytes() == before


def test_restore_rejects_tampered_checksums_and_unsupported_paths(tmp_path: Path) -> None:
    profiles_dir, _ = _profile_fixture(tmp_path)
    archive_path = tmp_path / "source.aiplane-profile.json"
    archive_profile("source", archive_path, profiles_dir=profiles_dir)
    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    payload["files"][0]["content"] += "tampered: true\n"
    archive_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum or size mismatch"):
        restore_profile_archive(archive_path, name="tampered", profiles_dir=profiles_dir, yes=True)

    archive_profile("source", archive_path, profiles_dir=profiles_dir, overwrite=True)
    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    payload["files"][0]["path"] = "../outside.yaml"
    archive_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported path"):
        restore_profile_archive(archive_path, name="traversal", profiles_dir=profiles_dir, yes=True)
    assert not (tmp_path / "outside.yaml").exists()


def test_restore_accepts_older_exclusion_manifest_rows(tmp_path: Path) -> None:
    profiles_dir, _ = _profile_fixture(tmp_path)
    archive_path = tmp_path / "source.aiplane-profile.json"
    archive_profile("source", archive_path, profiles_dir=profiles_dir)
    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    payload["manifest"]["excluded"] = payload["manifest"]["excluded"][:-1]
    payload["manifest"].pop("excluded_contract_version", None)
    archive_path.write_text(json.dumps(payload), encoding="utf-8")

    restored = restore_profile_archive(archive_path, name="restored", profiles_dir=profiles_dir, yes=True)
    assert restored["restored"]


def test_restore_rejects_exclusion_manifest_reason_mismatch(tmp_path: Path) -> None:
    profiles_dir, _ = _profile_fixture(tmp_path)
    archive_path = tmp_path / "source.aiplane-profile.json"
    archive_profile("source", archive_path, profiles_dir=profiles_dir)
    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    payload["manifest"]["excluded"][0]["reason"] = "unexpected"
    archive_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="reason mismatch"):
        restore_profile_archive(archive_path, name="restored", profiles_dir=profiles_dir, yes=True)


def test_profiles_archive_and_restore_cli_contract(tmp_path: Path, capsys) -> None:
    profiles_dir, _ = _profile_fixture(tmp_path)
    archive_path = tmp_path / "source.aiplane-profile.json"

    code = cli_main(
        [
            "--profiles-dir",
            str(profiles_dir),
            "profiles",
            "archive",
            "source",
            "--output",
            str(archive_path),
        ]
    )
    archived = json.loads(capsys.readouterr().out)
    assert code == 0
    assert archived["written"]

    code = cli_main(
        [
            "--profiles-dir",
            str(profiles_dir),
            "profiles",
            "restore",
            str(archive_path),
            "--as",
            "restored",
        ]
    )
    preview = json.loads(capsys.readouterr().out)
    assert code == 0
    assert preview["would_restore"]
    assert not (profiles_dir / "restored").exists()

    code = cli_main(
        [
            "--profiles-dir",
            str(profiles_dir),
            "profiles",
            "restore",
            str(archive_path),
            "--as",
            "restored",
            "--yes",
        ]
    )
    restored = json.loads(capsys.readouterr().out)
    assert code == 0
    assert restored["restored"]
    assert (profiles_dir / "restored").is_dir()
