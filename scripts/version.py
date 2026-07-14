#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PACKAGE_INIT = ROOT / "src" / "aiplane" / "__init__.py"
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
VERSION_FILES = {"pyproject.toml", "src/aiplane/__init__.py"}


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        match = VERSION_RE.fullmatch(value.strip())
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
    match = re.search(r'(?m)^version = "([^"]+)"$', text)
    if not match:
        raise ValueError("text does not contain a simple [project] version field")
    Version.parse(match.group(1))
    return match.group(1)


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


def write_version(version: str, *, dry_run: bool = False) -> None:
    Version.parse(version)
    old = check_versions()
    if dry_run:
        print(json.dumps({"old_version": old, "new_version": version, "changed": old != version}, indent=2))
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
        output = run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]).stdout
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
) -> dict[str, object]:
    current = Version.parse(version)
    version_files_changed = bool(changed_files & VERSION_FILES)
    version_value_changed = parent_version is not None and parent_version != version
    mode = "none"
    reason = "not a main push"
    if event == "push" and ref == "refs/heads/main":
        if "[skip ci-version]" in message:
            mode = "validate_only"
            reason = "version loop breaker in commit message"
        elif matching_tag_points_at_head:
            mode = "validate_only"
            reason = "matching version tag already points at HEAD"
        elif parent_count > 1 or associated_pull_request:
            mode = "ci_patch_after_merge"
            reason = "pull-request merge on main"
        elif version_files_changed and version_value_changed:
            mode = "maintainer_direct_main_version_commit"
            reason = "direct main commit changed tracked version value"
        else:
            mode = "validate_only"
            reason = "direct main commit without version change"
    next_version = str(current.bump_patch()) if mode == "ci_patch_after_merge" else version
    return {
        "mode": mode,
        "reason": reason,
        "current_version": version,
        "next_version": next_version,
        "tag": f"v{next_version}",
        "parent_count": parent_count,
        "author": author,
        "version_changed": version_value_changed,
        "version_files_changed": version_files_changed,
        "associated_pull_request": associated_pull_request,
        "parent_version": parent_version,
    }


def classify_ci() -> dict[str, object]:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    ref = os.environ.get("GITHUB_REF", "")
    version = check_versions()
    tag = f"v{version}"
    parent_count = head_parent_count()
    return classify_from_data(
        event=event,
        ref=ref,
        version=version,
        parent_count=parent_count,
        message=head_message(),
        author=head_author(),
        changed_files=changed_files_at_head(),
        matching_tag_points_at_head=tag_points_at_head(tag),
        associated_pull_request=os.environ.get("AIPLANE_ASSOCIATED_PR", "").lower() == "true",
        parent_version=version_at_ref("HEAD^1") if parent_count else None,
    )


def write_github_outputs(values: dict[str, object]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


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
    current_cmd.add_argument("--plain", action="store_true")
    tag_cmd = sub.add_parser("tag")
    tag_cmd.add_argument("--ci-artifact", action="store_true")
    tag_cmd.add_argument("--dry-run", action="store_true")
    classify_cmd = sub.add_parser("classify-ci")
    classify_cmd.add_argument("--github-output", action="store_true")

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
            next_version = {
                "patch": version.bump_patch,
                "minor": version.bump_minor,
                "major": version.bump_major,
            }[args.command]()
            write_version(str(next_version), dry_run=args.dry_run)
            return 0
        if args.command == "set":
            write_version(str(Version.parse(args.version)), dry_run=args.dry_run)
            return 0
        if args.command == "tag":
            create_tag(ci_artifact=args.ci_artifact, dry_run=args.dry_run)
            return 0
        if args.command == "classify-ci":
            result = classify_ci()
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
