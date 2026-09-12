from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
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
    for filename in (
        "pyproject.toml",
        "MANIFEST.in",
        "LICENSE",
        "Makefile",
        "repository-standard.json",
        *[p.name for p in repository.glob("*.md")],
    ):
        shutil.copy2(repository / filename, build_root / filename)
    for directory in (
        "src",
        "scripts",
        "profile-templates",
        "config-templates",
        "schemas",
        "docs",
        "skills",
        "standards",
        ".github",
    ):
        shutil.copytree(repository / directory, build_root / directory)

    private = build_root / "docs/project/.strategy/private.md"
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_text("private sentinel", encoding="utf-8")
    _run([sys.executable, "-c", "from setuptools.build_meta import build_sdist; build_sdist('dist')"], cwd=build_root)
    archive = next((build_root / "dist").glob("*.tar.gz"))
    with tarfile.open(archive) as source:
        names = source.getnames()
        assert any(name.endswith("/skills/aiplane/agents/openai.yaml") for name in names)
        assert not any("/.strategy/" in name for name in names)

    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    _run(
        [sys.executable, "-m", "pip", "wheel", str(archive), "--no-deps", "--no-build-isolation", "-w", str(wheel_dir)],
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
    version_output = _run([str(aiplane), "--version"], cwd=tmp_path).stdout
    assert "aiplane " in version_output
    assert "metadata_version:" in version_output
    assert "module_version:" in version_output
    assert "install_type: wheel" in version_output

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = os.environ.copy()
    env.pop("AIPLANE_PROFILES_DIR", None)
    env.pop("AIPLANE_CONFIG", None)
    env.pop("PYTHONPATH", None)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    (workspace / "README.md").write_text("unrelated workspace sentinel", encoding="utf-8")
    installed_docs = _run(
        [
            str(python),
            "-c",
            """
import json
from pathlib import Path
from importlib.metadata import version
from aiplane.mcp import AiplaneMcpServer
server = AiplaneMcpServer(Path.cwd())
response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
assert response["result"]["serverInfo"]["version"] == version("aiplane")
response = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "aiplane.docs.list", "arguments": {}}})
paths = [row["path"] for row in response["result"]["structuredContent"]["docs"]]
for path in paths:
    response = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "aiplane.docs.read", "arguments": {"path": path}}})
    content = response["result"]["structuredContent"]["content"]
    assert content and "unrelated workspace sentinel" not in content
print(json.dumps(paths))
""",
        ],
        cwd=workspace,
        env=env,
    )
    from aiplane.documentation import documentation_paths

    assert json.loads(installed_docs.stdout) == documentation_paths(repository)

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

    # Upgrade/reinstall/uninstall lifecycle coverage belongs to
    # scripts/verify_install_channels.py and runs independently in the OS matrix
    # and release workflow. Do not invoke that full lifecycle again here: this
    # test already owns wheel contents, isolated installation, and first-run
    # preservation contracts.
