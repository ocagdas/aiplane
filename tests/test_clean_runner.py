"""The clean test launcher preserves personal profiles and cleans up on failure."""

from pathlib import Path
import os
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX shell launcher")


@pytest.mark.parametrize("exit_code", [0, 7])
def test_runner_preserves_profiles_and_cleans_workspace(tmp_path, exit_code):
    root = tmp_path / "repository"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(Path("scripts/test-clean.sh"), root / "scripts/test-clean.sh")
    (root / "profile-templates/local-dev").mkdir(parents=True)
    (root / "profile-templates/local-dev/default.txt").write_text("template", encoding="utf-8")
    (root / "profiles/local-dev").mkdir(parents=True)
    personal = root / "profiles/local-dev/personal.txt"
    personal.write_text("preserve", encoding="utf-8")
    interpreter = tmp_path / "fake-python"
    interpreter.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    interpreter.chmod(0o755)
    result = subprocess.run(
        ["bash", str(root / "scripts/test-clean.sh")],
        env=os.environ | {"PYTHON": str(interpreter), "TMPDIR": str(tmp_path)},
        capture_output=True,
    )
    assert result.returncode == exit_code
    assert personal.read_text(encoding="utf-8") == "preserve"
    assert not list(tmp_path.glob("aiplane-test-clean.*"))


def test_runner_rejects_profile_path_traversal(tmp_path):
    result = subprocess.run(
        ["bash", "scripts/test-clean.sh"],
        env=os.environ | {"AIPLANE_TEST_PROFILE_NAME": "../outside", "TMPDIR": str(tmp_path)},
        capture_output=True,
    )
    assert result.returncode == 2
    assert not list(tmp_path.iterdir())
