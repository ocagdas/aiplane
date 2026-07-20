from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib


PACKAGE = "aiplane"


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    expected: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, env=env, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode not in expected:
        rendered = " ".join(command)
        raise RuntimeError(
            f"command failed ({completed.returncode}): {rendered}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def executable(directory: Path) -> Path:
    return directory / ("aiplane.exe" if os.name == "nt" else "aiplane")


def _mcp_request(process: subprocess.Popen[bytes], payload: dict[str, object]) -> dict[str, object]:
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("MCP process pipes are unavailable")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    process.stdin.flush()
    content_length = None
    while True:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout before returning a response")
        if line in {b"\r\n", b"\n"}:
            break
        name, _, value = line.decode("ascii").partition(":")
        if name.lower() == "content-length":
            content_length = int(value.strip())
    if content_length is None:
        raise RuntimeError("MCP response omitted Content-Length")
    return json.loads(process.stdout.read(content_length).decode("utf-8"))


def verify_tier1_exports(
    command: Path,
    *,
    cli,
    env: dict[str, str],
    workspace: Path,
) -> None:
    def content(*arguments: str) -> str:
        output = cli("integrations", "export", *arguments).stdout
        return output.partition("\n\n" + chr(35) + " Notes")[0]

    continue_config = content("continue")
    if "schema: v1" not in continue_config or "portable_smoke" not in continue_config:
        raise RuntimeError("installed Continue Tier-1 export is incomplete")
    aider_config = content("aider", "--model", "portable_smoke")
    if "OPENAI_API_BASE=" not in aider_config or "aider --model openai/" not in aider_config:
        raise RuntimeError("installed Aider Tier-1 export is incomplete")
    openai_config = json.loads(content("openai-compatible", "--model", "portable_smoke"))
    if openai_config.get("model") != "portable-smoke.gguf":
        raise RuntimeError(
            "installed OpenAI-compatible Tier-1 export is incomplete: "
            f"expected portable-smoke.gguf, got {openai_config.get('model')!r}"
        )
    mcp_config = json.loads(content("generic-mcp"))
    if mcp_config.get("mcpServers", {}).get("aiplane", {}).get("args") != ["mcp", "serve"]:
        raise RuntimeError("installed generic MCP Tier-1 export is incomplete")

    codex_config = tomllib.loads(
        content(
            "codex",
            "--model",
            "portable_smoke",
            "--endpoint",
            "http://127.0.0.1:8080/v1",
            "--api-type",
            "responses",
        )
    )
    if codex_config.get("profiles", {}).get("aiplane-portable_smoke", {}).get("model") != "portable-smoke.gguf":
        raise RuntimeError("installed Codex Tier-1 export is incomplete")
    copilot_config = json.loads(
        content(
            "copilot-cli",
            "--model",
            "portable_smoke",
            "--endpoint",
            "http://127.0.0.1:8080/v1",
            "--api-type",
            "chat-completions",
            "--format",
            "json",
        )
    )
    if copilot_config.get("alias") != "portable_smoke" or copilot_config.get("command") != ["copilot"]:
        raise RuntimeError("installed Copilot CLI Tier-1 export is incomplete")
    vscode_config = json.loads(
        content(
            "copilot-vscode",
            "--model",
            "portable_smoke",
            "--endpoint",
            "http://127.0.0.1:8080/v1",
            "--api-type",
            "chat-completions",
        )
    )
    if vscode_config[0].get("models", [{}])[0].get("id") != "portable-smoke.gguf":
        raise RuntimeError("installed Copilot-in-VS-Code Tier-1 export is incomplete")
    posix_config = content(
        "copilot-cli",
        "--model",
        "portable_smoke",
        "--endpoint",
        "http://127.0.0.1:8080/v1",
        "--api-type",
        "chat-completions",
        "--format",
        "posix",
    )
    powershell_config = content(
        "copilot-cli",
        "--model",
        "portable_smoke",
        "--endpoint",
        "http://127.0.0.1:8080/v1",
        "--api-type",
        "chat-completions",
        "--format",
        "powershell",
    )
    if "export COPILOT_MODEL=" not in posix_config or "$env:COPILOT_MODEL =" not in powershell_config:
        raise RuntimeError("installed Copilot CLI shell renderers are incomplete")
    process = subprocess.Popen(
        [str(command), "mcp", "serve"],
        env=env,
        cwd=workspace,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        initialized = _mcp_request(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "aiplane-tier1-verifier", "version": "1"},
                },
            },
        )
        if initialized.get("result", {}).get("serverInfo", {}).get("name") != "aiplane-mcp":
            raise RuntimeError("installed MCP server failed the initialize exchange")
        tools = _mcp_request(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {row.get("name") for row in tools.get("result", {}).get("tools", [])}
        if "aiplane.integrations.export" not in names:
            raise RuntimeError("installed MCP server failed the tools/list exchange")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def verify_platform_contracts(cli, *, system: str) -> None:
    tunnel_plan = json.loads(cli("remote", "tunnel", "plan", "--target", "gpu_workstation_ssh").stdout)
    if tunnel_plan.get("type") != "ssh_tunnel" or not tunnel_plan.get("command"):
        raise RuntimeError("portable SSH tunnel plan is incomplete")

    if system in {"Darwin", "Windows"}:
        unsupported = json.loads(cli("runtimes", "install", "ollama", "--dry-run", expected=(2,)).stdout)
        if unsupported.get("name") != "unsupported_platform":
            raise RuntimeError("unsupported runtime mutation did not fail with unsupported_platform")

    # Tunnel lifecycle is supported on macOS, so never call start there: an
    # installation verifier must not initiate a real SSH connection. Windows
    # is the only supported OS where lifecycle is expected to fail closed.
    if system == "Windows":
        tunnel = json.loads(
            cli(
                "remote",
                "tunnel",
                "start",
                "--target",
                "gpu_workstation_ssh",
                expected=(2,),
            ).stdout
        )
        if tunnel.get("name") != "unsupported_platform":
            raise RuntimeError("unsupported SSH lifecycle did not fail with unsupported_platform")


def verify_cli(command: Path, *, env: dict[str, str], workspace: Path) -> None:
    workspace.mkdir(parents=True)
    profiles = workspace / "profiles"
    isolated_env = env.copy()
    isolated_env.pop("AIPLANE_CONFIG", None)
    isolated_env.pop("AIPLANE_PROFILE", None)
    isolated_env["AIPLANE_PROFILES_DIR"] = str(profiles)

    def cli(*arguments: str, expected: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
        return run([str(command), *arguments], env=isolated_env, cwd=workspace, expected=expected)

    help_output = cli("--help").stdout
    if "environment doctor and configuration compiler" not in help_output:
        raise RuntimeError("installed CLI help does not contain the public product contract")
    if cli("profiles", "templates").stdout.splitlines() != ["local-dev"]:
        raise RuntimeError("installed CLI cannot load the packaged profile template")
    if "local" not in cli("config", "templates").stdout.splitlines():
        raise RuntimeError("installed CLI cannot load the packaged config template")

    cli("profiles", "bootstrap-local", "--no-discovery", "--no-hardware-discovery")
    validation = json.loads(cli("profiles", "validate", "local-dev").stdout)
    if not validation.get("ok"):
        raise RuntimeError("installed CLI cannot validate its packaged profile")

    model_path = workspace / "portable-smoke.gguf"
    model_path.write_bytes(b"synthetic portable smoke fixture\n")
    cli(
        "models",
        "add",
        "portable_smoke",
        "--provider",
        "local_file",
        "--model",
        model_path.name,
        "--role",
        "chat",
        "--role",
        "autocomplete",
        "--role",
        "embedding",
        "--runtime",
        "llamacpp",
    )
    for role in ("chat_model", "autocomplete_model", "embedding_model"):
        cli("models", "use", role, "portable_smoke")
    verify_tier1_exports(command, cli=cli, env=isolated_env, workspace=workspace)

    hardware = json.loads(cli("hardware", "discover").stdout)
    if hardware.get("platform_support", {}).get("system") != platform.system():
        raise RuntimeError("hardware discovery did not report the current platform")
    recommendation = json.loads(cli("recommend", "--format", "json").stdout)
    if "models" not in recommendation or "machine" not in recommendation:
        raise RuntimeError("portable recommendation output is incomplete")
    policy = json.loads(cli("policy", "explain", "--action", "provider:ollama").stdout)
    if "outcome" not in policy:
        raise RuntimeError("portable policy output is incomplete")
    exported = json.loads(
        cli(
            "integrations",
            "export",
            "openai-compatible",
            "--model",
            "portable_smoke",
            "--endpoint",
            "http://127.0.0.1:8080/v1",
        ).stdout.split("\n\n# Notes", 1)[0]
    )
    if exported.get("base_url") != "http://127.0.0.1:8080/v1":
        raise RuntimeError("portable export output is incomplete")

    verify_platform_contracts(cli, system=platform.system())


def verify_pip(wheel: Path, root: Path) -> None:
    venv = root / "pip-venv"
    run([sys.executable, "-m", "venv", str(venv)])
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    command = executable(bin_dir)
    env = os.environ.copy()
    run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], env=env)
    verify_cli(command, env=env, workspace=root / "pip-before")
    run([str(python), "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheel)], env=env)
    verify_cli(command, env=env, workspace=root / "pip-after")
    run([str(python), "-m", "pip", "uninstall", "-y", PACKAGE], env=env)
    if command.exists():
        raise RuntimeError("pip uninstall left the aiplane executable behind")


def verify_pipx(wheel: Path, root: Path) -> None:
    home = root / "pipx-home"
    bin_dir = root / "pipx-bin"
    env = os.environ.copy()
    env.update({"PIPX_HOME": str(home), "PIPX_BIN_DIR": str(bin_dir)})
    command = executable(bin_dir)
    run([sys.executable, "-m", "pipx", "install", str(wheel)], env=env)
    verify_cli(command, env=env, workspace=root / "pipx-before")
    run([sys.executable, "-m", "pipx", "uninstall", PACKAGE], env=env)
    run([sys.executable, "-m", "pipx", "install", str(wheel)], env=env)
    verify_cli(command, env=env, workspace=root / "pipx-after")
    run([sys.executable, "-m", "pipx", "uninstall", PACKAGE], env=env)
    if command.exists():
        raise RuntimeError("pipx uninstall left the aiplane executable behind")


def verify_uv(wheel: Path, root: Path) -> None:
    tool_dir = root / "uv-tools"
    bin_dir = root / "uv-bin"
    env = os.environ.copy()
    env.update({"UV_TOOL_DIR": str(tool_dir), "UV_TOOL_BIN_DIR": str(bin_dir)})
    command = executable(bin_dir)
    run(["uv", "tool", "install", str(wheel)], env=env)
    verify_cli(command, env=env, workspace=root / "uv-before")
    run(["uv", "tool", "install", "--force", str(wheel)], env=env)
    verify_cli(command, env=env, workspace=root / "uv-after")
    run(["uv", "tool", "uninstall", PACKAGE], env=env)
    if command.exists():
        raise RuntimeError("uv tool uninstall left the aiplane executable behind")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate isolated aiplane wheel installation channels.")
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--channel", choices=("all", "pip", "pipx", "uv"), default="all")
    args = parser.parse_args()
    wheel = args.wheel.expanduser().resolve()
    if wheel.is_dir():
        wheels = sorted(wheel.glob("aiplane-*.whl"))
        if len(wheels) != 1:
            parser.error(f"expected exactly one aiplane wheel in {wheel}, found {len(wheels)}")
        wheel = wheels[0]
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error(f"wheel does not exist: {wheel}")
    channels = ("pip", "pipx", "uv") if args.channel == "all" else (args.channel,)
    if "pipx" in channels:
        run([sys.executable, "-m", "pipx", "--version"])
    if "uv" in channels and shutil.which("uv") is None:
        parser.error("uv is required for the uv channel")
    with tempfile.TemporaryDirectory(prefix="aiplane-install-") as temporary:
        root = Path(temporary)
        validators = {"pip": verify_pip, "pipx": verify_pipx, "uv": verify_uv}
        for channel in channels:
            validators[channel](wheel, root)
            print(f"{channel}: install, verification, upgrade/replacement, and uninstall passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
