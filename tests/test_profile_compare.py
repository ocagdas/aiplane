from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiplane.cli import main as cli_main
from aiplane.config import create_profile, dump_yaml, load_profile, parse_yaml
from aiplane.integrations import IntegrationManager
from aiplane.profile_archive import archive_profile, restore_profile_archive
from aiplane.profile_compare import assess_profile_drift, check_profile_replays, compare_profile_sources

from .profile_fixtures import _materialize_test_models


def _profiles(tmp_path: Path) -> Path:
    root = tmp_path / "profiles"
    create_profile("left", profiles_dir=root)
    create_profile("right", profiles_dir=root)
    return root


def _configure(
    root: Path,
    name: str,
    *,
    ram: int | str = 32,
    vram: int | str = 12,
    selected: bool = True,
    min_ram: int = 16,
    min_vram: int = 8,
) -> None:
    profile = root / name
    hardware_path = profile / "hardware.yaml"
    hardware = parse_yaml(hardware_path.read_text(encoding="utf-8"))
    hardware["active"] = "portable"
    hardware["selected"] = {
        "origin": "portable",
        "custom": True,
        "values": {
            "machine_tag": "portable",
            "memory_gb": ram,
            "gpu_vendor": "nvidia",
            "gpu_count": 1,
            "vram_gb": vram,
            "total_vram_gb": vram,
            "accelerator_apis": ["cuda"],
        },
    }
    hardware_path.write_text(dump_yaml(hardware), encoding="utf-8")

    models_path = profile / "models.yaml"
    models = parse_yaml(models_path.read_text(encoding="utf-8"))
    models["defaults"] = {"chat_model": "portable-chat"} if selected else {}
    models["models"] = {
        "portable-chat": {
            "model": "portable-chat:latest",
            "provider": "ollama",
            "local": True,
            "roles": ["chat"],
            "supported_runtimes": ["ollama"],
            "min_ram_gb": min_ram,
            "min_vram_gb": min_vram,
            "required_gpu_vendor": "nvidia",
            "required_accelerator_apis": ["cuda"],
        }
    }
    models_path.write_text(dump_yaml(models), encoding="utf-8")


def _discovery(*, ram: int | None, vram: int = 12, vendor: str = "nvidia") -> dict[str, object]:
    return {
        "machine": "x86_64",
        "cpu_count": 16,
        "memory_gb": ram,
        "gpus": ([{"vendor": vendor, "name": "Fixture GPU", "vram_mb": vram * 1024}] if vendor != "none" else []),
        "platform_support": {"os": "linux"},
        "notes": [],
        "closest_profiles": [],
    }


def test_compare_profile_and_archive_are_exact(tmp_path: Path) -> None:
    root = _profiles(tmp_path)
    archive = tmp_path / "left.json"
    archive_profile("left", archive, profiles_dir=root)

    result = compare_profile_sources(
        "left",
        str(archive),
        right_source="archive",
        profiles_dir=root,
    )

    assert result["classification"] == "exact"
    assert result["equivalent"] is True
    assert result["canonical_equal"] is True
    assert result["byte_equal"] is True
    assert result["right"]["provenance"].startswith("validated portable archive")


def test_compare_classifies_hardware_variance_and_material_shortfall(tmp_path: Path) -> None:
    root = _profiles(tmp_path)
    _configure(root, "left", ram=32, vram=12)
    _configure(root, "right", ram=64, vram=24)

    equivalent = compare_profile_sources("left", "right", profiles_dir=root)

    assert equivalent["classification"] == "capability_equivalent"
    assert equivalent["equivalent"] is True
    assert {row["state"] for row in equivalent["evidence"]["left_fit"]} == {"pass"}
    assert any(change["path"] == "hardware.ram_gb" for change in equivalent["changes"])

    _configure(root, "right", ram=8, vram=4)
    incompatible = compare_profile_sources("left", "right", profiles_dir=root)

    assert incompatible["classification"] == "materially_incompatible"
    assert incompatible["equivalent"] is False
    assert incompatible["evidence"]["right_fit"][0]["state"] == "fail"
    assert "below minimum" in incompatible["evidence"]["right_fit"][0]["reason"]


def test_compare_is_unresolved_without_selection_and_material_for_config_change(tmp_path: Path) -> None:
    root = _profiles(tmp_path)
    _configure(root, "left", ram=32, selected=False)
    _configure(root, "right", ram=64, selected=False)

    unresolved = compare_profile_sources("left", "right", profiles_dir=root)
    assert unresolved["classification"] == "unresolved"
    assert unresolved["equivalent"] is None

    targets = root / "right" / "targets.yaml"
    config = parse_yaml(targets.read_text(encoding="utf-8"))
    config["comparison_fixture"] = True
    targets.write_text(dump_yaml(config), encoding="utf-8")
    material = compare_profile_sources("left", "right", profiles_dir=root)
    assert material["classification"] == "materially_incompatible"
    assert "targets.yaml" in material["evidence"]["semantic_changed_files"]


def test_drift_classifies_exact_equivalent_material_and_unresolved(tmp_path: Path) -> None:
    root = _profiles(tmp_path)
    _configure(root, "left", ram=32, vram=12)

    exact = assess_profile_drift(
        "left",
        profiles_dir=root,
        current_discovery=_discovery(ram=32, vram=12),
    )
    assert exact["classification"] == "exact"

    equivalent = assess_profile_drift(
        "left",
        profiles_dir=root,
        current_discovery=_discovery(ram=64, vram=24),
    )
    assert equivalent["classification"] == "capability_equivalent"
    assert equivalent["evidence"]["current_fit"][0]["state"] == "pass"

    incompatible = assess_profile_drift(
        "left",
        profiles_dir=root,
        current_discovery=_discovery(ram=8, vram=4),
    )
    assert incompatible["classification"] == "materially_incompatible"
    assert incompatible["evidence"]["current_fit"][0]["state"] == "fail"

    unresolved = assess_profile_drift(
        "left",
        profiles_dir=root,
        current_discovery=_discovery(ram=None, vram=12),
    )
    assert unresolved["classification"] == "unresolved"
    assert "RAM is unknown" in unresolved["evidence"]["current_fit"][0]["reason"]


def test_compare_and_drift_cli_are_read_only_json_contracts(tmp_path: Path, capsys, monkeypatch) -> None:
    root = _profiles(tmp_path)
    _configure(root, "left", ram=32, vram=12)
    _configure(root, "right", ram=64, vram=24)
    before = {path: path.read_bytes() for path in root.rglob("*.yaml")}

    assert cli_main(["--profiles-dir", str(root), "profiles", "compare", "left", "right"]) == 0
    compared = json.loads(capsys.readouterr().out)
    assert compared["classification"] == "capability_equivalent"

    monkeypatch.setattr(
        "aiplane.profile_compare.HardwareManager.discover",
        lambda self: _discovery(ram=64, vram=24),
    )
    assert cli_main(["--profiles-dir", str(root), "profiles", "drift", "left"]) == 0
    drifted = json.loads(capsys.readouterr().out)
    assert drifted["classification"] == "capability_equivalent"
    assert before == {path: path.read_bytes() for path in root.rglob("*.yaml")}


def test_multi_client_replay_check_proves_two_restores_and_exports_are_identical(tmp_path: Path, capsys) -> None:
    source_root = tmp_path / "source-profiles"
    source_path = create_profile("approved", profiles_dir=source_root)
    _materialize_test_models(source_path)
    approved = load_profile("approved", tmp_path, profiles_dir=source_root)
    approved_export = IntegrationManager(approved).export("continue").content
    approved_archive = tmp_path / "approved.json"
    archive_profile("approved", approved_archive, profiles_dir=source_root)

    client_archives: list[Path] = []
    client_exports: list[str] = []
    for client_name in ("laptop-client", "desktop-client"):
        client_root = tmp_path / client_name / "profiles"
        restore_profile_archive(
            approved_archive,
            name="replayed",
            profiles_dir=client_root,
            yes=True,
        )
        replayed = load_profile("replayed", tmp_path / client_name, profiles_dir=client_root)
        client_exports.append(IntegrationManager(replayed).export("continue").content)
        client_archive = tmp_path / f"{client_name}.json"
        archive_profile("replayed", client_archive, profiles_dir=client_root)
        client_archives.append(client_archive)

    before = {path: path.read_bytes() for path in (approved_archive, *client_archives)}
    result = check_profile_replays(
        str(approved_archive),
        [str(path) for path in client_archives],
        source_type="archive",
    )

    assert result["name"] == "profile_replay_check"
    assert result["read_only"] is True
    assert result["client_count"] == 2
    assert result["classification"] == "exact"
    assert result["counts"]["exact"] == 2
    assert result["replay_ready"] is True
    assert {row["classification"] for row in result["clients"]} == {"exact"}
    assert all(row["evidence"]["artifact_locks"]["left"] for row in result["clients"])
    assert all(row["evidence"]["artifact_locks"]["right"] for row in result["clients"])
    assert client_exports == [approved_export, approved_export]
    assert before == {path: path.read_bytes() for path in (approved_archive, *client_archives)}

    assert (
        cli_main(
            [
                "profiles",
                "replay-check",
                str(approved_archive),
                "--source",
                "archive",
                "--client-archive",
                str(client_archives[0]),
                "--client-archive",
                str(client_archives[1]),
            ]
        )
        == 0
    )
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["replay_ready"] is True


def test_multi_client_replay_check_requires_distinct_multiple_archives(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least two"):
        check_profile_replays("source", [str(tmp_path / "only.json")])
    duplicate = str(tmp_path / "same.json")
    with pytest.raises(ValueError, match="must be distinct"):
        check_profile_replays("source", [duplicate, duplicate])


def test_restore_replays_canonical_profile_and_supported_export_bytes(tmp_path: Path) -> None:
    root = tmp_path / "profiles"
    source = create_profile("source", profiles_dir=root)
    _materialize_test_models(source)
    original = load_profile("source", tmp_path, profiles_dir=root)
    original_export = IntegrationManager(original).export("continue").content
    archive = tmp_path / "source.json"

    archive_profile("source", archive, profiles_dir=root)
    restore_profile_archive(archive, name="restored", profiles_dir=root, yes=True)

    comparison = compare_profile_sources("source", "restored", profiles_dir=root)
    restored = load_profile("restored", tmp_path, profiles_dir=root)
    restored_export = IntegrationManager(restored).export("continue").content
    assert comparison["classification"] == "exact"
    assert comparison["byte_equal"] is True
    assert restored_export == original_export
