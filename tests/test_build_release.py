from __future__ import annotations

import pytest

from scripts import build_release
from scripts.repository_provenance import write_provenance
from scripts.verify_release_manifest import ManifestError, sha256, verify_directory


@pytest.fixture
def artifacts(tmp_path):
    for name in ["aiplane-0.2.18-py3-none-any.whl", "aiplane-0.2.18.tar.gz"]:
        (tmp_path / name).write_bytes(b"synthetic distribution")
    write_provenance(tmp_path, version="0.2.18", commit="a" * 40, tag="v0.2.18")
    (tmp_path / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in sorted(tmp_path.iterdir())))
    return tmp_path


def test_verify_only_accepts_complete_set_and_rejects_corruption(artifacts):
    assert build_release.main(["--verify-only", "--output", str(artifacts)]) == 0
    next(artifacts.glob("*.whl")).write_bytes(b"corrupt download")
    assert build_release.main(["--verify-only", "--output", str(artifacts)]) == 1


def test_unlisted_missing_and_wrong_version_artifacts_fail(artifacts):
    extra = artifacts / "aiplane-0.2.19.tar.gz"
    extra.write_bytes(b"extra")
    with pytest.raises(ManifestError, match="unlisted"):
        verify_directory(artifacts)
    extra.unlink()
    next(artifacts.glob("*.tar.gz")).unlink()
    with pytest.raises(ManifestError):
        verify_directory(artifacts)


def test_build_requires_tag_and_empty_output(artifacts, monkeypatch):
    monkeypatch.setattr(build_release.version, "require_clean_tree", lambda: None)
    monkeypatch.setattr(build_release.version, "check_versions", lambda: "0.2.18")
    monkeypatch.setattr(build_release.version, "tag_points_at_head", lambda _: True)
    with pytest.raises(ValueError, match="tag must match"):
        build_release.build("v0.2.17", artifacts)
    with pytest.raises(ValueError, match="empty"):
        build_release.build("v0.2.18", artifacts)


@pytest.mark.parametrize("name", ["extra.txt", "payload.exe", "second.whl"])
def test_complete_set_rejects_extra_downloads(artifacts, name):
    (artifacts / name).write_bytes(b"unexpected")
    with pytest.raises(ManifestError, match="unlisted"):
        verify_directory(artifacts)


@pytest.mark.parametrize("name", ["../outside", "a\\b.whl", "C:payload.whl", "/absolute"])
def test_manifest_paths_are_portable_and_contained(name):
    from scripts.verify_release_manifest import parse_manifest

    with pytest.raises(ManifestError, match="unsafe"):
        parse_manifest(f"{'a' * 64}  {name}\n")
