from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts import publish_version, version


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    repo = tmp_path / "checkout"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    git(repo, "init", "-b", "trunk")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "src/aiplane").mkdir(parents=True)
    (repo / "pyproject.toml").write_text('[project]\nname = "aiplane"\nversion = "0.2.18"\n')
    (repo / "src/aiplane/__init__.py").write_text('__version__ = "0.2.18"\n')
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    git(repo, "init", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "trunk")
    monkeypatch.setattr(version, "ROOT", repo)
    monkeypatch.setattr(version, "PYPROJECT", repo / "pyproject.toml")
    monkeypatch.setattr(version, "PACKAGE_INIT", repo / "src/aiplane/__init__.py")
    monkeypatch.setenv("GITHUB_SHA", git(repo, "rev-parse", "HEAD"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/trunk")
    monkeypatch.setenv("AIPLANE_TRUNK", "trunk")
    return repo, remote


def test_atomic_patch_and_source_rerun(repository):
    repo, remote = repository
    source = git(repo, "rev-parse", "HEAD")
    result = publish_version.publish(source, "trunk", merged=True)
    assert result["status"] == "published"
    assert result["version"] == "0.2.19"
    assert git(remote, "rev-parse", "trunk") == result["version_commit"]
    assert git(remote, "rev-parse", "v0.2.19^{commit}") == result["version_commit"]
    assert git(remote, "cat-file", "-t", "v0.2.19") == "tag"
    git(repo, "checkout", "--detach", source)
    assert publish_version.publish(source, "trunk", merged=True)["status"] == "superseded"


def test_stale_remote_does_not_version_untested_code(repository):
    repo, remote = repository
    source = git(repo, "rev-parse", "HEAD")
    (repo / "code.txt").write_text("new code")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "newer code")
    latest = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "origin", "trunk")
    git(repo, "checkout", "--detach", source)
    assert publish_version.publish(source, "trunk", merged=True)["status"] == "superseded"
    assert git(remote, "rev-parse", "trunk") == latest
    assert git(remote, "tag", "--list") == ""


def test_conflicting_tag_prevents_branch_publication(repository):
    repo, remote = repository
    source = git(repo, "rev-parse", "HEAD")
    git(repo, "tag", "-a", "v0.2.19", "-m", "collision")
    git(repo, "push", "origin", "v0.2.19")
    with pytest.raises(RuntimeError, match="already exists"):
        publish_version.publish(source, "trunk", merged=True)
    assert git(remote, "rev-parse", "trunk") == source
    assert git(remote, "rev-parse", "v0.2.19^{commit}") == source


def test_remote_tag_race_rejects_both_atomic_updates(repository, monkeypatch):
    repo, remote = repository
    source = git(repo, "rev-parse", "HEAD")
    original = publish_version.git

    def race(*args):
        if args[:2] == ("push", "--atomic"):
            git(remote, "tag", "v0.2.19", source)
        return original(*args)

    monkeypatch.setattr(publish_version, "git", race)
    with pytest.raises(RuntimeError, match="command failed"):
        publish_version.publish(source, "trunk", merged=True)
    assert git(remote, "rev-parse", "trunk") == source
    assert git(remote, "rev-parse", "v0.2.19^{commit}") == source


def test_publication_rejects_dirty_or_wrong_revision(repository, monkeypatch):
    repo, _ = repository
    source = git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("GITHUB_SHA", "wrong")
    with pytest.raises(ValueError, match="exact tested"):
        publish_version.publish(source, "trunk", merged=True)
    monkeypatch.setenv("GITHUB_SHA", source)
    (repo / "untracked").write_text("dirty")
    with pytest.raises(RuntimeError, match="clean"):
        publish_version.publish(source, "trunk", merged=True)


def test_direct_version_tags_once_and_code_only_push_is_unchanged(repository, monkeypatch):
    repo, remote = repository
    source = git(repo, "rev-parse", "HEAD")
    assert publish_version.publish(source, "trunk")["status"] == "unchanged"
    version.write_version("0.3.0")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "select minor")
    git(repo, "push", "origin", "trunk")
    source = git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("GITHUB_SHA", source)
    assert publish_version.publish(source, "trunk")["status"] == "published"
    assert publish_version.publish(source, "trunk")["status"] == "unchanged"
    assert git(remote, "rev-parse", "v0.3.0^{commit}") == source


def test_stale_pr_guard_compares_merge_base(repository):
    repo, _ = repository
    base = git(repo, "rev-parse", "HEAD")
    version.write_version("0.2.19")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "trunk version")
    git(repo, "checkout", "-b", "feature", base)
    (repo / "feature").write_text("feature")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "feature")
    assert version.check_pr_version("trunk") == "0.2.18"
    version.write_version("0.2.20")
    with pytest.raises(ValueError, match="must not change"):
        version.check_pr_version("trunk")


def test_tag_dry_run_detects_collision_and_dirty_tree(repository):
    repo, _ = repository
    git(repo, "tag", "v0.2.18")
    (repo / "feature").write_text("new")
    with pytest.raises(RuntimeError, match="clean"):
        version.create_tag(dry_run=True)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "feature")
    with pytest.raises(RuntimeError, match="already exists"):
        version.create_tag(dry_run=True)


def test_release_identity_is_checked(repository):
    repo, _ = repository
    with pytest.raises(ValueError, match="tag must match"):
        version.classify_release("HEAD^1", tag="v99.0.0")
    assert os.environ["GITHUB_SHA"] == git(repo, "rev-parse", "HEAD")
