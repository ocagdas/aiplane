from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

import pytest


@pytest.mark.parametrize("version,allowed", [((3, 12, 9), False), ((3, 13, 0), True)])
def test_source_execution_enforces_minimum_python(version: tuple[int, ...], allowed: bool) -> None:
    source = Path("src/aiplane/__init__.py").resolve()
    command = f"import runpy, sys; sys.version_info = {version!r}; runpy.run_path({str(source)!r})"
    result = subprocess.run([sys.executable, "-c", command], text=True, capture_output=True, check=False)
    assert (result.returncode == 0) is allowed
    if not allowed:
        assert "requires Python 3.13 or newer" in result.stderr


def test_package_and_ci_require_the_supported_minimum() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())
    assert project["project"]["requires-python"] == ">=3.13"
    assert not any(classifier.endswith((":: 3.11", ":: 3.12")) for classifier in project["project"]["classifiers"])
    workflow = Path(".github/workflows/ci.yml").read_text()
    assert 'python-version: "3.13"' in workflow
    assert '"3.11"' not in workflow and '"3.12"' not in workflow


@pytest.mark.skipif(os.name == "nt", reason="POSIX setup helper; Windows uses native Python installation")
@pytest.mark.parametrize("mode", ["local", "venv", "conda"])
@pytest.mark.parametrize("action", ["install", "refresh", "doctor", "test"])
def test_setup_rejects_old_environment_before_install_or_workload(tmp_path: Path, mode: str, action: str) -> None:
    script = tmp_path / "scripts/setup_env.sh"
    script.parent.mkdir()
    shutil.copy2("scripts/setup_env.sh", script)
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    calls = tmp_path / "calls.jsonl"
    fake = bindir / "python"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "with Path(os.environ['AIPLANE_TEST_PYTHON_CALLS']).open('a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('Python 3.12.9'); sys.exit(0)\n"
        "if len(sys.argv) == 3 and sys.argv[1] == '-c':\n"
        "    sys.version_info = (3, 12, 9)\n"
        "    exec(sys.argv[2]); sys.exit(0)\n"
        "sys.exit('Unexpected command: setup reached a package install or workload')\n"
    )
    fake.chmod(0o755)
    venv_bin = tmp_path / ".venv/bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(fake)
    conda = bindir / "conda"
    conda.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1 $2" == "env list" ]]; then echo "aiplane /tmp/example"; exit 0; fi\n'
        'if [[ "$1" == "run" ]]; then shift 3; exec "$@"; fi\n'
        'echo "Unexpected Conda mutation" >&2; exit 99\n'
    )
    conda.chmod(0o755)
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    env["AIPLANE_TEST_PYTHON_CALLS"] = str(calls)
    result = subprocess.run(
        [str(script), "--mode", mode, "--action", action, "--python", str(fake)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "requires Python 3.13 or newer" in result.stderr
    invoked = [json.loads(line) for line in calls.read_text().splitlines()]
    assert all(args == ["--version"] or args[0] == "-c" for args in invoked)
    assert not (tmp_path / "profiles").exists()
    assert not (tmp_path / ".aiplane").exists()
