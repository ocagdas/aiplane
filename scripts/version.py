#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from . import repository_release as shared
else:
    import repository_release as shared

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PACKAGE_INIT = ROOT / "src" / "aiplane" / "__init__.py"
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
VERSION_FILES = {"pyproject.toml", "src/aiplane/__init__.py"}
VERSIONING_ACTOR = "aiplane-versioning[bot]"


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        shared.parse(value)
        match = VERSION_RE.fullmatch(value)
        if not match:
            raise ValueError(f"unsupported version {value!r}; expected MAJOR.MINOR.PATCH")
        return cls(*(int(part) for part in match.groups()))

    def bump_patch(self) -> "Version":
        return Version(self.major, self.minor, self.patch + 1)

    def bump_minor(self) -> "Version":
        return Version(self.major, self.minor + 1, 0)

    def bump_major(self) -> "Version":
        return Version(self.major + 1, 0, 0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def classify_version_change(previous: str, current: str) -> str:
    before = Version.parse(previous)
    after = Version.parse(current)
    before_parts = (before.major, before.minor, before.patch)
    after_parts = (after.major, after.minor, after.patch)
    if after_parts <= before_parts:
        return "invalid"
    if after.major != before.major:
        return "major"
    if after.minor != before.minor:
        return "minor"
    return "patch"


def release_plan(previous: str, current: str) -> dict[str, object]:
    change_kind = classify_version_change(previous, current)
    if change_kind == "invalid":
        raise ValueError(f"release version must increase: previous={previous}, current={current}")
    return {
        "previous_version": previous,
        "current_version": current,
        "change_kind": change_kind,
        "automatic_publish": change_kind in {"minor", "major"},
        "tag": f"v{current}",
    }


def run(command: list[str], *, expected: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode not in expected:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def pyproject_version() -> str:
    return pyproject_version_from_text(PYPROJECT.read_text(encoding="utf-8"))


def init_version() -> str:
    text = PACKAGE_INIT.read_text(encoding="utf-8")
    match = re.search(r'(?m)^__version__ = "([^"]+)"$', text)
    if not match:
        raise ValueError("src/aiplane/__init__.py does not contain __version__")
    Version.parse(match.group(1))
    return match.group(1)


def pyproject_version_from_text(text: str) -> str:
    value = tomllib.loads(text)["project"]["version"]
    Version.parse(value)
    return value


def version_at_ref(ref: str) -> str | None:
    completed = run(["git", "show", f"{ref}:pyproject.toml"], expected=(0, 128))
    if completed.returncode != 0:
        return None
    return pyproject_version_from_text(completed.stdout)


def check_versions() -> str:
    project = pyproject_version()
    package = init_version()
    if project != package:
        raise ValueError(f"version mismatch: pyproject.toml={project}, __version__={package}")
    return project


def check_pr_version(base_ref: str) -> str:
    current = check_versions()
    merge_base = run(["git", "merge-base", base_ref, "HEAD"]).stdout.strip()
    base = version_at_ref(merge_base)
    if base is None:
        raise ValueError(f"cannot read base version from {base_ref}")
    if current != base:
        raise ValueError(
            f"pull requests must not change package version: {base_ref}={base}, current={current}; "
            "merge ordinary changes for an automatic patch bump, or have an authorized maintainer "
            "run scripts/version.py minor|major|set directly on the configured trunk"
        )
    return current


def write_version(version: str, *, dry_run: bool = False) -> None:
    Version.parse(version)
    old = check_versions()
    if classify_version_change(old, version) == "invalid":
        raise ValueError(f"version must increase: current={old}, requested={version}")
    if dry_run:
        print(json.dumps({"old_version": old, "new_version": version, "changed": True}, indent=2))
        return
    pyproject_text = PYPROJECT.read_text(encoding="utf-8")
    init_text = PACKAGE_INIT.read_text(encoding="utf-8")
    pyproject_text = re.sub(r'(?m)^version = "[^"]+"$', f'version = "{version}"', pyproject_text, count=1)
    init_text = re.sub(r'(?m)^__version__ = "[^"]+"$', f'__version__ = "{version}"', init_text, count=1)
    PYPROJECT.write_text(pyproject_text, encoding="utf-8")
    PACKAGE_INIT.write_text(init_text, encoding="utf-8")
    print(json.dumps({"old_version": old, "new_version": version, "changed": old != version}, indent=2))


def head_parent_count() -> int:
    parents = run(["git", "rev-list", "--parents", "-n", "1", "HEAD"]).stdout.strip().split()
    if not parents:
        raise RuntimeError("cannot inspect HEAD parents")
    return len(parents) - 1


def head_message() -> str:
    return run(["git", "log", "-1", "--pretty=%B"]).stdout


def head_author() -> str:
    return run(["git", "log", "-1", "--pretty=%an <%ae>"]).stdout.strip()


def changed_files_at_head() -> set[str]:
    if head_parent_count() == 0:
        output = run(["git", "show", "--pretty=", "--name-only", "HEAD"]).stdout
    else:
        output = run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD^1", "HEAD"]).stdout
    return {line.strip() for line in output.splitlines() if line.strip()}


def tag_points_at_head(tag: str) -> bool:
    completed = run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{}}"], expected=(0, 1))
    if completed.returncode != 0:
        return False
    tagged = completed.stdout.strip()
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    return tagged == head


def tag_exists(tag: str) -> bool:
    return run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], expected=(0, 1)).returncode == 0


def classify_from_data(
    *,
    event: str,
    ref: str,
    version: str,
    parent_count: int,
    message: str,
    author: str,
    changed_files: set[str],
    matching_tag_points_at_head: bool,
    associated_pull_request: bool = False,
    parent_version: str | None = None,
    actor: str = "",
    trunk: str = "main",
) -> dict[str, object]:
    result = shared.plan(
        parent_version, version, merged=parent_count > 1 or associated_pull_request, tagged=matching_tag_points_at_head
    )
    return {**result, "schema_version": 1, "tag": f"v{result['version']}"}


def selected_trunk() -> str:
    override = os.environ.get("REPOSITORY_TRUNK")
    if override:
        return override
    result = run(["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], expected=(0, 1))
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    raise ValueError("set REPOSITORY_TRUNK or fetch the origin default branch")


def classify_ci(*, merged: bool = False, trunk: str | None = None) -> dict[str, object]:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    ref = os.environ.get("GITHUB_REF", "")
    version = check_versions()
    tag = f"v{version}"
    parent_count = head_parent_count()
    result = classify_from_data(
        event=event,
        ref=ref,
        version=version,
        parent_count=parent_count,
        message=head_message(),
        author=head_author(),
        changed_files=changed_files_at_head(),
        matching_tag_points_at_head=tag_points_at_head(tag),
        associated_pull_request=merged,
        parent_version=version_at_ref("HEAD^1") if parent_count else None,
        actor=os.environ.get("GITHUB_ACTOR", ""),
        trunk=trunk or "",
    )
    result["source_commit"] = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    return result


def write_github_outputs(values: dict[str, object]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            handle.write(f"{key}={rendered}\n")


def classify_release(previous_ref: str, *, tag: str) -> dict[str, object]:
    current = check_versions()
    if tag != f"v{current}" or not tag_points_at_head(tag):
        raise ValueError("release tag must match the package version and HEAD")
    previous = version_at_ref(previous_ref)
    if previous is None:
        raise ValueError(f"cannot read previous version from {previous_ref}")
    return {
        "schema_version": 1,
        **release_plan(previous, current),
        "version": current,
        "publish": release_plan(previous, current)["automatic_publish"],
        "source_commit": run(["git", "rev-parse", "HEAD"]).stdout.strip(),
    }


def require_clean_tree() -> None:
    status = run(["git", "status", "--porcelain"]).stdout.strip()
    if status:
        raise RuntimeError("working tree must be clean before tagging")


def tag_plan(version: str, *, ci_artifact: bool = False) -> dict[str, object]:
    Version.parse(version)
    tag = f"v{version}"
    message = f"aiplane {tag}"
    if ci_artifact:
        message += " [ci-artifact]"
    return {"version": version, "tag": tag, "message": message, "ci_artifact": ci_artifact}


def create_tag(*, ci_artifact: bool = False, dry_run: bool = False) -> str:
    version = check_versions()
    plan = tag_plan(version, ci_artifact=ci_artifact)
    tag = str(plan["tag"])
    require_clean_tree()
    if tag_exists(tag) and not tag_points_at_head(tag):
        raise RuntimeError(f"tag {tag} already exists and does not point at HEAD")
    if dry_run:
        print(json.dumps({**plan, "would_create": not tag_exists(tag)}, indent=2, sort_keys=True))
        return tag
    if tag_exists(tag):
        if tag_points_at_head(tag):
            print(tag)
            return tag
        raise RuntimeError(f"tag {tag} already exists and does not point at HEAD")
    require_clean_tree()
    run(["git", "tag", "-a", tag, "-m", str(plan["message"])])
    print(tag)
    return tag


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage aiplane tracked versions and CI version classification.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("patch", "minor", "major"):
        item = sub.add_parser(command)
        item.add_argument("--dry-run", action="store_true")
    set_cmd = sub.add_parser("set")
    set_cmd.add_argument("version")
    set_cmd.add_argument("--dry-run", action="store_true")
    sub.add_parser("check")
    current_cmd = sub.add_parser("current")
    current_format = current_cmd.add_mutually_exclusive_group()
    current_format.add_argument("--plain", action="store_true")
    current_format.add_argument("--json", action="store_true")
    tag_cmd = sub.add_parser("tag")
    tag_cmd.add_argument("--ci-artifact", action="store_true")
    tag_cmd.add_argument("--dry-run", action="store_true")
    classify_cmd = sub.add_parser("classify-ci")
    classify_cmd.add_argument("--github-output", action="store_true")
    classify_cmd.add_argument("--merged", action="store_true")
    check_pr_cmd = sub.add_parser("check-pr")
    check_pr_cmd.add_argument("--base-ref", required=True)
    classify_release_cmd = sub.add_parser("classify-release")
    classify_release_cmd.add_argument("--tag", required=True)
    classify_release_cmd.add_argument("--previous-ref", default="HEAD^1")
    classify_release_cmd.add_argument("--github-output", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            print(check_versions())
            return 0
        if args.command == "current":
            version = check_versions()
            print(version if args.plain else json.dumps({"version": version}, indent=2))
            return 0
        if args.command in {"patch", "minor", "major"}:
            version = Version.parse(check_versions())
            version = {
                "patch": version.bump_patch,
                "minor": version.bump_minor,
                "major": version.bump_major,
            }[args.command]()
            write_version(str(version), dry_run=args.dry_run)
            return 0
        if args.command == "set":
            write_version(str(Version.parse(args.version)), dry_run=args.dry_run)
            return 0
        if args.command == "tag":
            create_tag(ci_artifact=args.ci_artifact, dry_run=args.dry_run)
            return 0
        if args.command == "classify-ci":
            result = classify_ci(merged=args.merged)
            print(json.dumps(result, indent=2, sort_keys=True))
            if args.github_output:
                write_github_outputs(result)
            return 0
        if args.command == "check-pr":
            print(check_pr_version(args.base_ref))
            return 0
        if args.command == "classify-release":
            result = classify_release(args.previous_ref, tag=args.tag)
            print(json.dumps(result, indent=2, sort_keys=True))
            if args.github_output:
                write_github_outputs(result)
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
