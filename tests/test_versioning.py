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
        author="github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>",
        changed_files={"pyproject.toml"},
    )
    assert result["mode"] == "validate_only"
    assert result["next_version"] == "0.1.0"


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
