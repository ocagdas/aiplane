"""Portable CLI conformance checks; reads a target checkout and mutates only temporary fixtures.

Requires jsonschema in the current maintenance environment, never a sibling import.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
STANDARD = ROOT / "standards/repository/v1"


def verify_bundle():
    manifest = json.loads((STANDARD / "bundle.json").read_text(encoding="utf-8"))
    if manifest["contract_version"] != "1.0.0" or not manifest["files"]:
        raise ValueError("Invalid shared bundle manifest")
    for name, expected in manifest["files"].items():
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink():
            raise ValueError("Invalid shared bundle path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Shared bundle drift: {name}")


def validate(kind, value):
    schema = json.loads((STANDARD / f"{kind}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)


def safe_repo_relative_path(repo: Path, value: str) -> Path:
    mirror = Path(value)
    if mirror.is_absolute():
        raise ValueError("version_mirror must be a safe repository-relative path")
    resolved_repo = repo.resolve()
    resolved = (resolved_repo / mirror).resolve()
    if not resolved.is_relative_to(resolved_repo):
        raise ValueError("version_mirror must be a safe repository-relative path")
    return resolved.relative_to(resolved_repo)


def check(repo):
    contract = json.loads((STANDARD / "contract.json").read_text(encoding="utf-8"))
    adapter = json.loads((repo / "repository-standard.json").read_text(encoding="utf-8"))
    validate("adapter", adapter)
    if adapter["contract_version"] != contract["contract_version"]:
        raise ValueError("Adapter contract version differs")
    for name in contract["required_documents"]:
        if not (repo / name).is_file():
            raise ValueError(f"Missing document: {name}")
    for name in contract["canonical_workflows"]:
        if not (repo / ".github/workflows" / name).is_file():
            raise ValueError(f"Missing workflow: {name}")
    for name in contract["shared_github_files"]:
        if (repo / name).read_bytes() != (ROOT / name).read_bytes():
            raise ValueError(f"Shared GitHub scaffolding differs: {name}")
    for name in ("bug_report.md", "feature_request.md"):
        if (repo / ".github/ISSUE_TEMPLATE" / name).exists():
            raise ValueError(f"Duplicate legacy issue template: {name}")
    for name in contract["required_helpers"]:
        if not (repo / "scripts" / name).is_file():
            raise ValueError(f"Missing helper: {name}")
    completed = []
    env = os.environ | {"PYTHONDONTWRITEBYTECODE": "1", "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "conformance"}
    for name in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"):
        env.pop(name, None)

    def run(args, cwd=repo, good=True):
        result = subprocess.run(args, cwd=cwd, env=env, text=True, encoding="utf-8", capture_output=True, timeout=120)
        if (result.returncode == 0) != good:
            raise ValueError(f"Command failed conformance: {args}: {result.stdout} {result.stderr}")
        return result.stdout.strip()

    for source, target, good in (
        ("dev/fix-config", "main", True),
        ("dependabot/pip/ruff", "main", True),
        ("develop/fix-config", "main", False),
        ("dev/fix-config", "develop", False),
        ("dev/../main", "main", False),
    ):
        run([sys.executable, "scripts/check_branch_policy.py", "--source", source, "--target", target], good=good)
    for target, good in (("master", True), ("main", False)):
        run(
            [
                sys.executable,
                "scripts/check_branch_policy.py",
                "--source",
                "dev/fix-config",
                "--target",
                target,
                "--trunk",
                "master",
            ],
            good=good,
        )
    completed.append("branch_policy")
    current = json.loads(run([sys.executable, "scripts/version.py", "current", "--json"]))["version"]
    if run([sys.executable, "scripts/version.py", "current", "--plain"]) != current:
        raise ValueError("Plain and JSON current disagree")
    completed.append("current_formats")
    with tempfile.TemporaryDirectory(prefix="repository-conformance-") as temp:
        folder = Path(temp)
        for case in contract["gate_cases"]:
            results = {name: {"result": "success"} for name in adapter["required_jobs"]}
            change = case["change"]
            if change == "missing":
                results.pop(adapter["required_jobs"][0])
            elif change in ("failure", "cancelled", "skipped"):
                results[adapter["required_jobs"][0]] = {"result": change}
            elif change:
                results["additional"] = {"result": "success" if change == "extra_success" else "failure"}
            jobs, report = folder / "jobs.json", folder / "report.json"
            jobs.write_text(json.dumps(results), encoding="utf-8")
            run(
                [sys.executable, "scripts/ci_gate.py", "--results", str(jobs), "--report", str(report)],
                good=case["expected"],
            )
            value = json.loads(report.read_text(encoding="utf-8"))
            validate("quality-gate", value)
            if (
                value["go"] is not case["expected"]
                or value["commit"] != env["GITHUB_SHA"]
                or value["run_id"] != "conformance"
            ):
                raise ValueError("Gate decision/identity differs")
            completed.append("gate_" + case["name"])
        # Build a clean synthetic repository, never tag the target checkout.
        fixture = folder / "fixture"
        fixture.mkdir()
        shutil.copytree(repo / "scripts", fixture / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(repo / "pyproject.toml", fixture / "pyproject.toml")
        mirror = safe_repo_relative_path(repo, adapter["version_mirror"])
        (fixture / mirror).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / mirror, fixture / mirror)
        (fixture / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        env.update(
            GIT_AUTHOR_NAME="Conformance",
            GIT_AUTHOR_EMAIL="conformance@example.invalid",
            GIT_COMMITTER_NAME="Conformance",
            GIT_COMMITTER_EMAIL="conformance@example.invalid",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GITHUB_EVENT_NAME="push",
            GITHUB_REF="refs/heads/release/test",
            GITHUB_ACTOR="maintainer",
        )
        env[adapter["trunk_variable"]] = "release/test"

        def git(*args):
            return run(["git", *args], fixture)

        def cli(*args, good=True):
            return run([sys.executable, "scripts/version.py", *args], fixture, good)

        git("init", "-b", "release/test")
        git("add", ".")
        git("commit", "-m", "baseline")
        git("commit", "--allow-empty", "-m", "merged source")
        env["GITHUB_SHA"] = git("rev-parse", "HEAD")
        env.pop("GITHUB_EVENT_NAME", None)
        env.pop("GITHUB_REF", None)
        plan = json.loads(cli("classify-ci", "--merged"))
        validate("ci-plan", plan)
        if plan["mode"] != "patch" or plan["source_commit"] != env["GITHUB_SHA"]:
            raise ValueError("Merged source plan differs")
        completed.append("merge_plan")
        cli("set", current, good=False)
        cli("set", "01.2.3", good=False)
        cli("patch")
        git("add", ".")
        git("commit", "-m", "version bump")
        cli("tag")
        selected = json.loads(cli("classify-release", "--tag", plan["tag"]))
        validate("release-plan", selected)
        if selected["source_commit"] != git("rev-parse", "HEAD") or selected["publish"] is not False:
            raise ValueError("Patch release identity/policy differs")
        completed.append("release_plan")
        cli("tag")
        completed.append("tag_rerun")
        git("commit", "--allow-empty", "-m", "another merged source")
        source = git("rev-parse", "HEAD")
        env["GITHUB_SHA"] = source
        remote = folder / "remote.git"
        git("init", "--bare", str(remote))
        git("remote", "add", "origin", str(remote))
        git("push", "origin", "HEAD:refs/heads/release/test", "--tags")
        command = [
            sys.executable,
            "scripts/publish_version.py",
            "--source",
            source,
            "--trunk",
            "release/test",
            "--merged",
        ]
        published = json.loads(run(command, fixture))
        validate("publication", published)
        if published["status"] != "published" or published["source_commit"] != source:
            raise ValueError("Atomic publication result differs")
        git("checkout", "--detach", source)
        again = json.loads(run(command, fixture))
        validate("publication", again)
        if again["status"] != "superseded":
            raise ValueError("An advanced remote must report superseded, even for a prior publication")
        completed.append("publication_and_advanced_tip")
    return completed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-bundle-only", action="store_true")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=ROOT / ".quality/repository-standard.json")
    args = parser.parse_args(argv)
    report = {"contract_version": "1.0.0", "go": False, "checks": []}
    try:
        verify_bundle()
        report["checks"] = ["bundle_integrity"]
        if not args.verify_bundle_only:
            pins = subprocess.run(
                [sys.executable, str(args.repo / "scripts/check_workflow_pins.py"), "--repo", str(args.repo)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if pins.returncode:
                raise ValueError(pins.stderr.strip() or "Workflow pin checks failed")
            report["checks"].append("workflow_pins")
            report["checks"] += check(args.repo.resolve())
        report["go"] = True
    except Exception as error:
        report["error"] = str(error)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["go"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
