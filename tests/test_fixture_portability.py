from __future__ import annotations

import json
import os
import subprocess
import sys

from .support import Path, _isolated_profiles_dir, load_profile


def test_isolated_profile_fixture_falls_back_to_repository_templates_outside_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AIPLANE_PROFILES_DIR", raising=False)

    with _isolated_profiles_dir() as profiles_dir:
        profile = load_profile("local-dev", tmp_path, profiles_dir=profiles_dir)

    assert profile.name == "local-dev"
    assert profile.workspace == tmp_path


def test_cli_profile_validation_runs_from_an_external_working_directory(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root / "src")

    completed = subprocess.run(
        [sys.executable, "-m", "aiplane", "profiles", "validate", "local-dev"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"] is True
