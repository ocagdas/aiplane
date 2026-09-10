"""Exercise release shell failure propagation without network calls or credentials."""

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux release workflow shell")


def step_script(workflow, name):
    text = Path(".github/workflows", workflow).read_text(encoding="utf-8")
    step = text.split(f"- name: {name}\n", 1)[1].split("\n      - ", 1)[0]
    return textwrap.dedent(step.split("run: |\n", 1)[1])


def test_pr_lookup_failure_stops_the_step(tmp_path):
    fake = tmp_path / "python"
    fake.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    fake.chmod(0o755)
    output = tmp_path / "output"
    result = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            step_script("version.yml", "Detect merged pull request on selected trunk"),
        ],
        env=os.environ
        | {
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "GITHUB_OUTPUT": str(output),
            "GITHUB_SHA": "a" * 40,
            "TRUNK": "main",
        },
        capture_output=True,
    )
    assert result.returncode == 7
    assert not output.exists()


@pytest.mark.parametrize("workflow,folder", [("release.yml", "dist"), ("verify-release.yml", "release")])
@pytest.mark.parametrize("fail", [False, True])
def test_attestation_verifies_one_asset_per_call_and_fails_closed(tmp_path, workflow, folder, fail):
    artifacts = tmp_path / folder
    artifacts.mkdir()
    for name in ("aiplane-1.2.3.whl", "aiplane-1.2.3.tar.gz", "provenance.json"):
        (artifacts / name).write_text("fixture", encoding="utf-8")
    fake = tmp_path / "gh"
    fake.write_text(
        f"#!{sys.executable}\nimport json,os,sys\n"
        "assert len(sys.argv) == 6, sys.argv\n"
        "with open(os.environ['CALLS'], 'a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(9 if os.environ['FAIL'] == 'true' and sys.argv[3].endswith('.tar.gz') else 0)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    calls = tmp_path / "calls"
    result = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            step_script(workflow, "Verify release build provenance"),
        ],
        cwd=tmp_path,
        env=os.environ
        | {
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "GITHUB_REPOSITORY": "owner/repo",
            "CALLS": str(calls),
            "FAIL": str(fail).lower(),
        },
        capture_output=True,
    )
    assert result.returncode == (9 if fail else 0), result.stderr
    records = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
    assert len(records) == (2 if fail else 3)
    assert all(row[:2] == ["attestation", "verify"] and row[-2:] == ["--repo", "owner/repo"] for row in records)
