from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Setup install/refresh is Linux-only")


@pytest.fixture
def checkout(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "checkout with spaces"
    script = root / "scripts/setup_env.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2("scripts/setup_env.sh", script)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "example"\ndependencies = ["example>=1"]\n'
        '[project.optional-dependencies]\ndev = ["pytest==9.1.1"]\n'
    )
    (root / "profiles").mkdir()
    (root / "profiles/authored.yaml").write_text("user content\n")
    (root / ".d").write_text("Do not expand .[dev] as a shell glob\n")
    bindir = root / "fakebin"
    bindir.mkdir()
    program = (
        f"#!{sys.executable}\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "name = Path(sys.argv[0]).name\n"
        "with Path(os.environ['AIPLANE_TEST_REFRESH_LOG']).open('a') as out:\n"
        "    out.write(json.dumps([name, *sys.argv[1:]]) + '\\n')\n"
        "if name == 'conda':\n"
        "    if sys.argv[1:3] == ['env', 'list']:\n"
        "        if not os.environ.get('AIPLANE_TEST_MISSING_CONDA'): print('aiplane /tmp/example')\n"
        "        sys.exit(0)\n"
        "    if sys.argv[1] == 'run': sys.exit(subprocess.call(sys.argv[4:]))\n"
        "    sys.exit('Unexpected Conda mutation')\n"
        "if name == 'docker': sys.exit(0)\n"
        "if sys.argv[1:4] == ['-m', 'pip', 'check'] and os.environ.get('AIPLANE_TEST_FAIL_CHECK'):\n"
        "    sys.exit(7)\n"
        "if sys.argv[1] == '-c' or sys.argv[1:3] == ['-m', 'pip']: sys.exit(0)\n"
        "sys.exit('Unexpected bootstrap, activation or workload')\n"
    )
    for name in ["python", "conda", "docker"]:
        binary = bindir / name
        binary.write_text(program)
        binary.chmod(0o755)
    venv_bin = root / ".venv/bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(bindir / "python")
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    env["AIPLANE_TEST_REFRESH_LOG"] = str(root / "calls.jsonl")
    return root, env


def invoke(checkout: tuple[Path, dict[str, str]], *args: str) -> subprocess.CompletedProcess[str]:
    root, env = checkout
    return subprocess.run(
        [str(root / "scripts/setup_env.sh"), "--action", "refresh", *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def calls(checkout: tuple[Path, dict[str, str]]) -> list[list[str]]:
    path = Path(checkout[1]["AIPLANE_TEST_REFRESH_LOG"])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize("mode", ["local", "venv", "conda"])
@pytest.mark.parametrize("dev", [False, True])
def test_refresh_reconciles_selected_dependencies_and_preserves_profile(checkout, mode: str, dev: bool) -> None:
    root, _ = checkout
    result = invoke(checkout, "--mode", mode, *(["--dev"] if dev else []))
    assert result.returncode == 0, result.stdout + result.stderr
    pip = [row[1:] for row in calls(checkout) if row[0] == "python" and row[1:3] == ["-m", "pip"]]
    assert pip == [["-m", "pip", "install", "-e", ".[dev]" if dev else "."], ["-m", "pip", "check"]]
    assert (root / "profiles/authored.yaml").read_text() == "user content\n"
    assert not (root / ".aiplane").exists()


def test_refresh_upgrades_only_when_requested_and_static_does_not_link_source(checkout) -> None:
    result = invoke(checkout, "--mode", "venv", "--dev", "--upgrade-deps", "--upgrade-pip", "--static")
    assert result.returncode == 0, result.stdout + result.stderr
    pip = [row[1:] for row in calls(checkout) if row[0] == "python" and row[1:3] == ["-m", "pip"]]
    assert pip == [
        ["-m", "pip", "install", "--upgrade", "pip"],
        ["-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager", ".[dev]"],
        ["-m", "pip", "check"],
    ]


@pytest.mark.parametrize("mode", ["venv", "conda"])
def test_refresh_refuses_missing_environment_without_creation(checkout, mode: str) -> None:
    root, env = checkout
    if mode == "venv":
        shutil.rmtree(root / ".venv")
    else:
        env["AIPLANE_TEST_MISSING_CONDA"] = "1"
    result = invoke(checkout, "--mode", mode)
    assert result.returncode == 2
    assert "Use --action install first" in result.stderr
    assert all(row == ["conda", "env", "list"] for row in calls(checkout))
    assert not (root / ".aiplane").exists()


def test_refresh_propagates_dependency_conflict(checkout) -> None:
    checkout[1]["AIPLANE_TEST_FAIL_CHECK"] = "1"
    assert invoke(checkout, "--mode", "venv").returncode == 7


@pytest.mark.parametrize("mode", ["local", "venv", "conda", "docker"])
def test_refresh_preview_performs_no_package_or_docker_mutations(checkout, mode: str) -> None:
    root, _ = checkout
    result = invoke(checkout, "--mode", mode, "--dev", "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(row == ["conda", "env", "list"] for row in calls(checkout))
    assert not (root / ".aiplane").exists()
    assert (root / "profiles/authored.yaml").read_text() == "user content\n"


@pytest.mark.parametrize("static", [False, True])
def test_docker_refresh_build_options_and_declared_dependency_scope(checkout, static: bool) -> None:
    root, _ = checkout
    result = invoke(
        checkout,
        "--mode",
        "docker",
        "--dev",
        "--upgrade-deps",
        "--docker-pull",
        "--docker-no-cache",
        *(["--static"] if static else []),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    docker = [row for row in calls(checkout) if row[0] == "docker"]
    assert len(docker) == 1 and docker[0][1] == "build"
    assert "--pull" in docker[0] and "--no-cache" in docker[0]
    token = docker[0][docker[0].index("--build-arg") + 1]
    assert token.startswith("AIPLANE_DEPENDENCY_REFRESH=") and not token.endswith("=stable")
    content = (root / ".aiplane/docker/setup_env.Dockerfile").read_text()
    assert "--upgrade --upgrade-strategy eager" in content
    assert "pip install --upgrade pip" not in content
    if static:
        assert "'/opt/aiplane[dev]'" in content
        assert "pip install -e" not in content
    else:
        # Execute only the generated TOML-to-requirements converter, not Docker/pip.
        code = re.search(r'python -c "(import pathlib, tomllib;[^\"]+)"', content).group(1)
        output = root / "requirements.txt"
        code = code.replace("/tmp/aiplane-pyproject.toml", str(root / "pyproject.toml"))
        code = code.replace("/tmp/aiplane-requirements.txt", str(output))
        subprocess.run([sys.executable, "-c", code], check=True)
        assert output.read_text().splitlines() == ["example>=1", "pytest==9.1.1"]


def test_docker_preview_preserves_existing_dockerfile(checkout) -> None:
    root, _ = checkout
    dockerfile = root / ".aiplane/docker/setup_env.Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_bytes(b"previous Dockerfile\n")
    result = invoke(checkout, "--mode", "docker", "--dry-run")
    assert result.returncode == 0
    assert dockerfile.read_bytes() == b"previous Dockerfile\n"


def test_refresh_rejects_docker_options_in_a_python_environment(checkout) -> None:
    result = invoke(checkout, "--mode", "venv", "--docker-pull")
    assert result.returncode == 2
    assert "require --mode docker" in result.stderr
    assert not calls(checkout)
