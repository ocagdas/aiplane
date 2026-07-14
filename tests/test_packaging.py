from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, (
        f"command failed: {command!r}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    return completed


def test_wheel_install_includes_templates_helpers_and_preserves_profiles(tmp_path: Path) -> None:
    repository = Path.cwd()
    build_root = tmp_path / "source"
    build_root.mkdir()
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(repository / filename, build_root / filename)
    for directory in ("src", "scripts", "profile-templates", "config-templates", "schemas"):
        shutil.copytree(repository / directory, build_root / directory)

    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    _run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "-w", str(wheel_dir)],
        cwd=build_root,
    )
    wheel = next(wheel_dir.glob("aiplane-*.whl"))

    venv = tmp_path / "venv"
    _run([sys.executable, "-m", "venv", str(venv)], cwd=tmp_path)
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    aiplane = bin_dir / ("aiplane.exe" if os.name == "nt" else "aiplane")
    helper = bin_dir / "provider_helper.sh"
    _run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], cwd=tmp_path)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = os.environ.copy()
    env.pop("AIPLANE_PROFILES_DIR", None)
    env.pop("AIPLANE_CONFIG", None)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    assert _run([str(aiplane), "profiles", "templates"], cwd=workspace, env=env).stdout.splitlines() == ["local-dev"]
    assert "local" in _run([str(aiplane), "config", "templates"], cwd=workspace, env=env).stdout.splitlines()
    schema = json.loads(_run([str(aiplane), "profiles", "schema"], cwd=workspace, env=env).stdout)
    assert schema["$id"] == "https://aiplane.dev/schemas/profile/v1"
    _run(
        [
            str(aiplane),
            "profiles",
            "bootstrap-local",
            "--no-discovery",
            "--no-hardware-discovery",
        ],
        cwd=workspace,
        env=env,
    )
    sentinel_path = workspace / "profiles" / "local-dev" / "user-customization.txt"
    sentinel_path.write_text("keep me\n", encoding="utf-8")
    _run(
        [
            str(aiplane),
            "profiles",
            "bootstrap-local",
            "--no-discovery",
            "--no-hardware-discovery",
        ],
        cwd=workspace,
        env=env,
    )
    assert sentinel_path.read_text(encoding="utf-8") == "keep me\n"

    _run([str(aiplane), "config", "init", "--template", "local"], cwd=workspace, env=env)
    helper_path = _run(
        [str(python), "-c", "from aiplane.config import provider_helper_path; print(provider_helper_path())"],
        cwd=workspace,
        env=env,
    ).stdout.strip()
    assert Path(helper_path) == helper.resolve()
    assert helper.is_file()
    if os.name == "nt":
        assert "Usage: scripts/provider_helper.sh" in helper.read_text(encoding="utf-8")
    else:
        assert "Usage: scripts/provider_helper.sh" in _run([str(helper), "--help"], cwd=workspace, env=env).stdout
        helper_status = _run(
            [str(helper), "--provider", "ollama", "--action", "status", "--dry-run"],
            cwd=workspace,
            env=env,
        )
        assert "ollama" in helper_status.stdout.lower()

    _run(
        [sys.executable, str(repository / "scripts" / "verify_install_channels.py"), str(wheel), "--channel", "pip"],
        cwd=repository,
    )
