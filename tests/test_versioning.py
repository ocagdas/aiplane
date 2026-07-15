from __future__ import annotations

import importlib.util
import sys

import pytest
from pathlib import Path


def load_script(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


version_script = load_script("aiplane_version_script", "scripts/version.py")
local_wheel_script = load_script("aiplane_local_wheel_script", "scripts/build_local_wheel.py")


def classify(**overrides):
    values = {
        "event": "push",
        "ref": "refs/heads/main",
        "version": "0.1.0",
        "parent_count": 1,
        "message": "regular commit",
        "author": "Human <human@example.com>",
        "changed_files": set(),
        "matching_tag_points_at_head": False,
        "associated_pull_request": False,
        "parent_version": "0.1.0",
        "actor": "Human",
    }
    values.update(overrides)
    return version_script.classify_from_data(**values)


def test_ci_version_classification_bumps_only_main_merge_commits() -> None:
    result = classify(parent_count=2, message="Merge pull request #12")
    assert result["mode"] == "ci_patch_after_merge"
    assert result["next_version"] == "0.1.1"
    assert result["tag"] == "v0.1.1"


def test_ci_version_classification_does_not_recurse_on_ci_version_commit() -> None:
    result = classify(
        message="chore(release): v0.1.1 [skip ci-version]",
        author="aiplane-versioning[bot] <aiplane-versioning[bot]@users.noreply.github.com>",
        changed_files={"pyproject.toml"},
        actor="aiplane-versioning[bot]",
    )
    assert result["mode"] == "validate_only"
    assert result["next_version"] == "0.1.0"
    assert result["actor"] == "aiplane-versioning[bot]"


def test_ci_version_classification_does_not_honor_human_skip_marker() -> None:
    result = classify(
        parent_count=2,
        message="Merge feature [skip ci-version]",
        author="Human <human@example.com>",
    )
    assert result["mode"] == "ci_patch_after_merge"


def test_ci_version_classification_respects_direct_maintainer_version_commit() -> None:
    result = classify(
        version="0.2.0",
        parent_version="0.1.0",
        changed_files={"pyproject.toml", "src/aiplane/__init__.py"},
    )
    assert result["mode"] == "maintainer_direct_main_version_commit"
    assert result["next_version"] == "0.2.0"
    assert result["tag"] == "v0.2.0"
    assert result["version_change"] == "minor"


def test_ci_version_classification_rejects_version_change_merged_through_pr() -> None:
    result = classify(
        version="1.0.0",
        parent_version="0.1.7",
        parent_count=2,
        associated_pull_request=True,
        changed_files={"pyproject.toml", "src/aiplane/__init__.py"},
    )
    assert result["mode"] == "invalid_pr_version_change"
    assert result["reason"] == "pull-request merge changed tracked version value"


def test_ci_version_classification_does_not_treat_unchanged_version_file_as_user_versioning() -> None:
    result = classify(changed_files={"pyproject.toml", "src/aiplane/__init__.py"}, parent_version="0.1.0")
    assert result["mode"] == "validate_only"
    assert result["version_changed"] is False


def test_ci_version_classification_skips_when_matching_tag_already_points_at_head() -> None:
    result = classify(parent_count=2, matching_tag_points_at_head=True)
    assert result["mode"] == "validate_only"
    assert result["reason"] == "matching version tag already points at HEAD"


def test_ci_version_classification_ignores_pr_events_and_feature_branches() -> None:
    assert classify(event="pull_request")["mode"] == "none"
    assert classify(ref="refs/heads/feature/demo")["mode"] == "none"


def test_ci_version_classification_validates_direct_main_non_version_commits_without_bump() -> None:
    result = classify(parent_count=1, changed_files={"README.md"})
    assert result["mode"] == "validate_only"
    assert result["next_version"] == "0.1.0"
    assert result["tag"] == "v0.1.0"


def test_ci_version_classification_distinguishes_main_merge_from_pr_branch_build() -> None:
    main_merge = classify(event="push", ref="refs/heads/main", parent_count=2)
    squash_merge = classify(event="push", ref="refs/heads/main", parent_count=1, associated_pull_request=True)
    pr_branch = classify(event="push", ref="refs/heads/feature/demo", parent_count=2, associated_pull_request=True)
    pull_request = classify(
        event="pull_request", ref="refs/pull/12/merge", parent_count=2, associated_pull_request=True
    )
    assert main_merge["mode"] == "ci_patch_after_merge"
    assert squash_merge["mode"] == "ci_patch_after_merge"
    assert pr_branch["mode"] == "none"
    assert pull_request["mode"] == "none"


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ("0.1.2", "0.1.3", "patch"),
        ("0.1.9", "0.2.0", "minor"),
        ("0.8.7", "1.0.0", "major"),
        ("0.1.0", "0.3.0", "minor"),
        ("0.9.9", "2.0.0", "major"),
    ],
)
def test_release_change_classification(previous: str, current: str, expected: str) -> None:
    assert version_script.classify_version_change(previous, current) == expected


@pytest.mark.parametrize(("previous", "current"), [("0.1.2", "0.1.2"), ("0.2.0", "0.1.9"), ("1.0.0", "0.9.9")])
def test_release_change_classification_rejects_equal_or_decreasing_versions(previous: str, current: str) -> None:
    assert version_script.classify_version_change(previous, current) == "invalid"
    with pytest.raises(ValueError, match="release version must increase"):
        version_script.release_plan(previous, current)


def test_release_plan_auto_publishes_only_minor_and_major_versions() -> None:
    assert version_script.release_plan("0.1.2", "0.1.3")["automatic_publish"] is False
    assert version_script.release_plan("0.1.3", "0.2.0")["automatic_publish"] is True
    assert version_script.release_plan("0.9.4", "1.0.0")["automatic_publish"] is True


def test_classify_release_reads_and_validates_the_previous_ref(monkeypatch) -> None:
    monkeypatch.setattr(version_script, "check_versions", lambda: "0.2.0")
    monkeypatch.setattr(version_script, "version_at_ref", lambda ref: "0.1.9" if ref == "HEAD^1" else None)
    assert version_script.classify_release("HEAD^1") == {
        "previous_version": "0.1.9",
        "current_version": "0.2.0",
        "change_kind": "minor",
        "automatic_publish": True,
        "tag": "v0.2.0",
    }
    with pytest.raises(ValueError, match="cannot read previous version"):
        version_script.classify_release("missing")


def test_ci_rejects_a_direct_version_decrease() -> None:
    result = classify(
        version="0.1.9",
        parent_version="0.2.0",
        changed_files={"pyproject.toml", "src/aiplane/__init__.py"},
    )
    assert result["mode"] == "invalid_direct_version_change"
    assert result["version_change"] == "invalid"


def test_skip_marker_requires_the_configured_versioning_app_actor() -> None:
    forged = classify(
        message="chore(release): v0.1.1 [skip ci-version]",
        author="aiplane-versioning[bot] <forged@example.com>",
        actor="Human",
        parent_count=2,
    )
    assert forged["mode"] == "ci_patch_after_merge"


def test_github_outputs_render_booleans_for_workflow_conditions(tmp_path, monkeypatch) -> None:
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    version_script.write_github_outputs({"automatic_publish": True, "other": False})
    assert output.read_text(encoding="utf-8") == "automatic_publish=true\nother=false\n"


def test_tag_plan_marks_ci_artifact_tags_without_touching_git() -> None:
    plan = version_script.tag_plan("0.1.7", ci_artifact=True)
    assert plan == {
        "version": "0.1.7",
        "tag": "v0.1.7",
        "message": "aiplane v0.1.7 [ci-artifact]",
        "ci_artifact": True,
    }


def test_local_snapshot_version_uses_base_sha_and_timestamp() -> None:
    from datetime import datetime, timezone

    version = local_wheel_script.local_snapshot_version(
        "0.1.0",
        "abcdef1234567890",
        datetime(2026, 7, 14, 15, 30, 0, tzinfo=timezone.utc),
    )
    assert version == "0.1.0+gabcdef1.20260714t153000z"


def test_version_writer_rejects_non_increasing_values_before_writing(tmp_path, monkeypatch) -> None:
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "__init__.py"
    pyproject.write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")
    package_init.write_text('__version__ = "0.2.0"\n', encoding="utf-8")
    monkeypatch.setattr(version_script, "PYPROJECT", pyproject)
    monkeypatch.setattr(version_script, "PACKAGE_INIT", package_init)

    for requested in ("0.2.0", "0.1.9"):
        with pytest.raises(ValueError, match="version must increase"):
            version_script.write_version(requested)
    assert version_script.check_versions() == "0.2.0"

    version_script.write_version("0.3.0")
    assert version_script.check_versions() == "0.3.0"


def test_pr_version_guard_accepts_unchanged_version(monkeypatch) -> None:
    monkeypatch.setattr(version_script, "check_versions", lambda: "0.1.2")
    monkeypatch.setattr(version_script, "version_at_ref", lambda _ref: "0.1.2")
    assert version_script.check_pr_version("origin/main") == "0.1.2"


def test_pr_version_guard_rejects_changed_or_unreadable_base(monkeypatch) -> None:
    monkeypatch.setattr(version_script, "check_versions", lambda: "1.0.0")
    monkeypatch.setattr(version_script, "version_at_ref", lambda _ref: "0.1.2")
    with pytest.raises(ValueError, match="pull requests must not change package version"):
        version_script.check_pr_version("origin/main")
    monkeypatch.setattr(version_script, "version_at_ref", lambda _ref: None)
    with pytest.raises(ValueError, match="cannot read base version"):
        version_script.check_pr_version("origin/main")
