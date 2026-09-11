from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.repository_provenance import write_provenance
from scripts.render_release_notes import ReleaseNotesError, render_notes, unreleased_notes
from scripts import verify_release as verify_release_script
from scripts.verify_release_manifest import ManifestError, parse_manifest, verify_directory
from scripts.write_release_evidence import main as write_evidence


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def release_directory(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    wheel = tmp_path / "aiplane-0.1.2-py3-none-any.whl"
    sdist = tmp_path / "aiplane-0.1.2.tar.gz"
    wheel.write_bytes(b"synthetic-wheel")
    sdist.write_bytes(b"synthetic-sdist")
    write_provenance(tmp_path, version="0.1.2", commit="a" * 40, tag="v0.1.2")
    (tmp_path / "SHA256SUMS").write_text(
        f"{digest((tmp_path / 'provenance.json').read_bytes())}  provenance.json\n"
        f"{digest(wheel.read_bytes())}  {wheel.name}\n{digest(sdist.read_bytes())}  {sdist.name}\n",
        encoding="utf-8",
    )
    return tmp_path


def test_release_manifest_requires_and_verifies_one_wheel_and_sdist(tmp_path: Path) -> None:
    directory = release_directory(tmp_path)
    entries = verify_directory(directory)
    assert set(entries) == {"aiplane-0.1.2-py3-none-any.whl", "aiplane-0.1.2.tar.gz", "provenance.json"}


def test_release_manifest_rejects_traversal_duplicates_and_checksum_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="unsafe"):
        parse_manifest(f"{'a' * 64}  ../outside.whl\n")
    with pytest.raises(ManifestError, match="duplicate"):
        parse_manifest(f"{'a' * 64}  a.whl\n{'b' * 64}  a.whl\n")
    directory = release_directory(tmp_path)
    (directory / "aiplane-0.1.2-py3-none-any.whl").write_bytes(b"changed")
    with pytest.raises(ManifestError, match="checksum mismatch"):
        verify_directory(directory)


def test_release_manifest_rejects_incomplete_public_artifact_set(tmp_path: Path) -> None:
    wheel = tmp_path / "aiplane-0.1.2-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    (tmp_path / "SHA256SUMS").write_text(f"{digest(b'wheel')}  {wheel.name}\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="exactly one wheel and one source distribution"):
        verify_directory(tmp_path)


def test_release_evidence_writer_emits_a_canonical_sanitized_record(tmp_path: Path, monkeypatch) -> None:
    directory = release_directory(tmp_path / "release")
    output = tmp_path / "evidence" / "record.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_release_evidence.py",
            "--release-dir",
            str(directory),
            "--release-url",
            "https://github.com/example/aiplane/releases/tag/v0.1.2",
            "--tag",
            "v0.1.2",
            "--commit",
            "a" * 40,
            "--channel",
            "pipx",
            "--elapsed-seconds",
            "12.5",
            "--output",
            str(output),
        ],
    )
    assert write_evidence() == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["classification"] == "rehearsal"
    assert record["artifact"]["version"] == "0.1.2"
    assert record["environment"]["install_channel"] == "pipx"
    assert record["outcome"]["completed"] is True


def test_release_notes_are_rendered_from_tracked_unreleased_changes() -> None:
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    checksums = f"{'a' * 64}  aiplane-0.2.0-py3-none-any.whl\n{'b' * 64}  aiplane-0.2.0.tar.gz\n"
    checksums += f"{'c' * 64}  provenance.json\n"
    notes = render_notes("v0.2.0", "minor", "c" * 40, changelog, checksums)
    assert unreleased_notes(changelog) in notes
    assert "pre-1.0" in notes
    assert "gh attestation verify" in notes
    assert "tar -xzf ./aiplane-0.2.0.tar.gz" in notes
    assert "python scripts/verify_release_manifest.py .." in notes
    assert "Upgrade and rollback" in notes


def test_release_notes_reject_missing_changes_and_incomplete_manifests() -> None:
    with pytest.raises(ReleaseNotesError, match="at least one change"):
        unreleased_notes("# Changelog\n\n## Unreleased\n")
    with pytest.raises(ReleaseNotesError, match="invalid SHA256SUMS line"):
        render_notes("v0.2.0", "minor", "c" * 40, "## Unreleased\n\n- change\n", "one row\n")
    with pytest.raises(ReleaseNotesError, match="exactly one wheel"):
        render_notes(
            "v0.2.0",
            "minor",
            "c" * 40,
            "## Unreleased\n\n- change\n",
            f"{'a' * 64}  first.whl\n{'b' * 64}  second.whl\n{'c' * 64}  provenance.json\n",
        )


def _write_downloaded_provenance(directory: Path, **overrides: object) -> None:
    payload = {
        "schema_version": 1,
        "build_kind": "release",
        "tag": "v0.1.2",
        "source_commit": "a" * 40,
        "version_commit": "a" * 40,
        "artifacts": {"aiplane-0.1.2-py3-none-any.whl": "digest"},
    }
    payload.update(overrides)
    (directory / "provenance.json").write_text(json.dumps(payload), encoding="utf-8")


def test_verify_release_checks_identity_and_emits_expected_report(monkeypatch, tmp_path: Path) -> None:
    _write_downloaded_provenance(tmp_path)

    def fake_run(command, check, capture_output, text):
        payload = {"schema_version": 1, "artifacts": {"aiplane-0.1.2-py3-none-any.whl": "digest"}}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(
        verify_release_script.subprocess,
        "run",
        fake_run,
    )
    assert verify_release_script.verify(tmp_path, "v0.1.2", "a" * 40) == {
        "schema_version": 1,
        "tag": "v0.1.2",
        "source_commit": "a" * 40,
        "checks": {"downloaded_artifacts": "success", "local_rebuild": "success"},
        "artifacts": {"aiplane-0.1.2-py3-none-any.whl": "digest"},
    }


@pytest.mark.parametrize(
    ("overrides", "tag", "commit"),
    [
        ({"build_kind": "candidate"}, "v0.1.2", "a" * 40),
        ({"tag": "v0.1.3"}, "v0.1.2", "a" * 40),
        ({"source_commit": "b" * 40}, "v0.1.2", "a" * 40),
        ({"version_commit": "b" * 40}, "v0.1.2", "a" * 40),
    ],
)
def test_verify_release_rejects_mismatched_or_nonrelease_provenance(
    monkeypatch, tmp_path: Path, overrides: dict[str, object], tag: str, commit: str
) -> None:
    _write_downloaded_provenance(tmp_path, **overrides)

    def fake_run(command, check, capture_output, text):
        payload = {"schema_version": 1, "artifacts": {"aiplane-0.1.2-py3-none-any.whl": "digest"}}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(
        verify_release_script.subprocess,
        "run",
        fake_run,
    )
    with pytest.raises(ValueError, match="does not match"):
        verify_release_script.verify(tmp_path, tag, commit)


def test_verify_release_rejects_downloaded_artifacts_that_do_not_match_local_rebuild(
    monkeypatch, tmp_path: Path
) -> None:
    _write_downloaded_provenance(tmp_path, artifacts={"aiplane-0.1.2-py3-none-any.whl": "downloaded"})

    def fake_run(command, check, capture_output, text):
        artifacts = {"aiplane-0.1.2-py3-none-any.whl": "downloaded"}
        if "--tag" in command:
            artifacts = {"aiplane-0.1.2-py3-none-any.whl": "rebuilt"}
        payload = {"schema_version": 1, "artifacts": artifacts}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(
        verify_release_script.subprocess,
        "run",
        fake_run,
    )
    with pytest.raises(ValueError, match="does not match"):
        verify_release_script.verify(tmp_path, "v0.1.2", "a" * 40)
