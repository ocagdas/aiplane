from __future__ import annotations

import argparse
import sys
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from .boundaries import CommandRunner, SubprocessCommandRunner
from .config import load_profile, local_config_path, provider_helper_path, resolve_output_format
from .model_catalog import ModelCatalog
from .platform_support import detect_host_platform
from .runtime_catalog import RuntimeCatalog
from .docker_model_runner import DockerModelRunner

_COMMAND_RUNNER: CommandRunner = SubprocessCommandRunner()


def add_runtimes_parser(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    runtimes_cmd = command_factory(
        subparsers,
        "runtimes",
        "Map model sources to local runtimes",
        "Inspect which runtimes can run which configured models, and set a preferred runtime for a model.",
        (
            "Examples:\n"
            "  aiplane runtimes map\n"
            "  aiplane runtimes list\n"
            "  aiplane runtimes models vllm\n"
            "  aiplane runtimes model MODEL_ALIAS\n"
            "  aiplane runtimes use MODEL_ALIAS vllm\n"
            "  aiplane runtimes update-installed all --dry-run\n"
            "  aiplane runtimes repull ollama --dry-run"
        ),
    )
    runtimes_sub = runtimes_cmd.add_subparsers(dest="runtimes_command", required=True, metavar="command")
    runtimes_map = runtimes_sub.add_parser(
        "map",
        help="Show catalog-to-runtime diagram",
        description="Show a Mermaid diagram plus source/runtime metadata.",
        formatter_class=formatter_class,
    )
    profile_arg(runtimes_map)
    runtimes_map.add_argument(
        "--include-gui",
        action="store_true",
        help="Include GUI-managed runtimes such as LM Studio",
    )
    runtimes_list = runtimes_sub.add_parser(
        "list",
        help="List known runtimes",
        description="List configured and known runtimes, omitting GUI-managed runtimes unless --include-gui is used.",
        formatter_class=formatter_class,
    )
    profile_arg(runtimes_list)
    runtimes_list.add_argument(
        "--include-gui",
        action="store_true",
        help="Include GUI-managed runtimes such as LM Studio",
    )
    runtimes_list.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. Text is a lean table, JSON is for scripts.",
    )
    runtimes_sources = runtimes_sub.add_parser(
        "sources",
        help="List model catalogs/sources",
        description="List model sources such as Ollama library, Hugging Face Hub, and GGUF files.",
        formatter_class=formatter_class,
    )
    profile_arg(runtimes_sources)
    runtimes_models = runtimes_sub.add_parser(
        "models",
        help="Group configured models by runtime",
        description="Show models grouped by runtime, or only models for one runtime.",
        formatter_class=formatter_class,
    )
    profile_arg(runtimes_models)
    runtimes_models.add_argument(
        "runtime",
        nargs="?",
        help="Optional runtime name, such as ollama, vllm, llamacpp, tgi, transformers, or localai",
    )
    runtimes_models.add_argument(
        "--include-gui",
        action="store_true",
        help="Include GUI-managed runtimes such as LM Studio",
    )
    runtimes_model = runtimes_sub.add_parser(
        "model",
        help="Show runtimes for one model",
        description="Show supported runtimes, preferred runtime, and current availability for one model alias.",
        formatter_class=formatter_class,
    )
    profile_arg(runtimes_model)
    runtimes_model.add_argument("name", help="Model alias from models.yaml")
    runtimes_model.add_argument(
        "--include-gui",
        action="store_true",
        help="Include GUI-managed runtimes such as LM Studio",
    )
    runtimes_use = runtimes_sub.add_parser(
        "use",
        help="Set preferred runtime for one model",
        description="Persist a preferred runtime on a model without changing the immutable templates.",
        formatter_class=formatter_class,
    )
    profile_arg(runtimes_use)
    runtimes_use.add_argument("name", help="Model alias from models.yaml")
    runtimes_use.add_argument(
        "runtime",
        help="Runtime to prefer for this model, such as ollama, vllm, llamacpp, tgi, transformers, or localai",
    )
    runtimes_doctor = runtimes_sub.add_parser(
        "doctor",
        help="Check runtime availability",
        description="Check availability for one runtime, or all non-GUI runtimes when omitted.",
        formatter_class=formatter_class,
    )
    profile_arg(runtimes_doctor)
    runtimes_doctor.add_argument("runtime", nargs="?", help="Optional runtime name")
    runtimes_prereqs = runtimes_sub.add_parser(
        "prerequisites",
        help="Check runtime installer prerequisites",
        description="Report host tools needed before helper-managed runtime install/start actions can work. Ubuntu/Debian package hints are included when known.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane runtimes prerequisites ollama\n  aiplane runtimes prerequisites vllm\n  aiplane runtimes prerequisites all",
    )
    profile_arg(runtimes_prereqs)
    runtimes_prereqs.add_argument(
        "runtime",
        help="Runtime name, such as ollama, vllm, tgi, transformers, localai, llamacpp, lmstudio, or all",
    )
    runtimes_bundle = runtimes_sub.add_parser(
        "bundle",
        help="Render runtime bundle files",
        description="Render a Dockerfile or Conda environment plan for a selected runtime/model. This does not build images, create environments, or pull weights.",
        formatter_class=formatter_class,
        epilog=(
            "Examples:\n"
            "  aiplane runtimes bundle vllm --model MODEL_ALIAS --mode docker --format dockerfile\n"
            "  aiplane runtimes bundle transformers --model MODEL_ALIAS --mode conda --format conda-yaml\n"
            "  aiplane runtimes bundle ollama --model MODEL_ALIAS --format json"
        ),
    )
    profile_arg(runtimes_bundle)
    runtimes_bundle.add_argument(
        "runtime",
        help="Runtime name, such as ollama, vllm, tgi, transformers, llamacpp, localai, faster_whisper, or diffusers",
    )
    runtimes_bundle.add_argument(
        "--model",
        required=True,
        help="Configured model alias to include in the rendered plan",
    )
    runtimes_bundle.add_argument(
        "--mode",
        choices=["docker", "conda"],
        default="docker",
        help="Bundle target mode to plan",
    )
    runtimes_bundle.add_argument(
        "--format",
        choices=["json", "dockerfile", "conda-yaml"],
        default="json",
        help="Output the whole JSON plan or only one rendered file",
    )
    for lifecycle_action in [
        "configure",
        "install",
        "update",
        "update-installed",
        "start",
        "stop",
        "restart",
        "status",
        "pull",
        "repull",
        "remove",
        "clear",
        "runtime-list",
        "benchmark",
        "inspect",
    ]:
        command_name = "list-runtime-models" if lifecycle_action == "runtime-list" else lifecycle_action
        lifecycle = runtimes_sub.add_parser(
            command_name,
            help=f"Run provider helper {lifecycle_action.replace('-', ' ')}",
            description=(
                "Delegate runtime lifecycle/download operations to scripts/provider_helper.sh. "
                "Install and update helpers support native Ubuntu/Debian; use the runtime "
                "vendor's installer on WSL, other Linux distributions, macOS, or Windows."
            ),
            formatter_class=formatter_class,
        )
        profile_arg(lifecycle)
        lifecycle.add_argument(
            "runtime",
            help="Runtime/provider name, such as ollama, vllm, tgi, transformers, localai, llamacpp, lmstudio, or all where supported",
        )
        lifecycle.add_argument(
            "--model",
            default="all",
            help="Configured model alias, raw runtime model id, direct GGUF URL, or all where supported",
        )
        lifecycle.add_argument(
            "--substrate",
            choices=["native", "docker"],
            help="Override the profile runtime substrate; Ollama supports native and docker",
        )
        lifecycle.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the helper command and delegated runtime commands without executing changes",
        )
        lifecycle.add_argument(
            "--yes",
            action="store_true",
            help="Confirm destructive runtime actions such as remove or clear",
        )


def handle_runtimes_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
) -> int | None:
    if args.command == "runtimes":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        catalog = RuntimeCatalog(profile)
        if args.runtimes_command == "map":
            print(json_dumps(catalog.map(include_gui=args.include_gui), indent=2))
            return 0
        if args.runtimes_command == "list":
            rows = catalog.list(include_gui=args.include_gui)
            output_format = resolve_output_format(
                args.format,
                profile=effective_profile,
                path=local_config_path(),
            )
            if output_format == "text":
                print(_runtimes_list_text(rows))
            else:
                print(json_dumps(rows, indent=2))
            return 0
        if args.runtimes_command == "sources":
            print(json_dumps(catalog.sources(), indent=2))
            return 0
        if args.runtimes_command == "models":
            print(
                json_dumps(
                    catalog.models_by_runtime(args.runtime, include_gui=args.include_gui),
                    indent=2,
                )
            )
            return 0
        if args.runtimes_command == "model":
            print(
                json_dumps(
                    catalog.runtimes_by_model(args.name, include_gui=args.include_gui),
                    indent=2,
                )
            )
            return 0
        if args.runtimes_command == "use":
            print(json_dumps(catalog.set_preferred_runtime(args.name, args.runtime), indent=2))
            return 0
        if args.runtimes_command == "bundle":
            plan = catalog.bundle_plan(args.runtime, model_name=args.model, mode=args.mode)
            if args.format == "dockerfile":
                print(plan["files"]["Dockerfile"], end="")
            elif args.format == "conda-yaml":
                print(plan["files"]["environment.yaml"], end="")
            else:
                print(json_dumps(plan, indent=2))
            return 0
        if args.runtimes_command == "prerequisites":
            payload = catalog.prerequisites(args.runtime)
            print(json_dumps(payload, indent=2))
            return 0 if payload.get("ok") else 2
        lifecycle_actions = {
            "configure",
            "install",
            "update",
            "update-installed",
            "start",
            "stop",
            "restart",
            "status",
            "pull",
            "repull",
            "remove",
            "clear",
            "list-runtime-models",
            "benchmark",
            "inspect",
        }
        if args.runtimes_command in lifecycle_actions:
            if args.runtime == "docker_model_runner":
                payload, returncode = DockerModelRunner(_COMMAND_RUNNER).run(
                    args.runtimes_command, model=args.model, yes=args.yes, dry_run=args.dry_run
                )
                print(json_dumps(payload, indent=2))
                return 0 if returncode == 0 else 2
            helper_runtimes = {
                "ollama",
                "ollama_cloud",
                "openai",
                "anthropic",
                "azure_openai",
                "vllm",
                "tgi",
                "transformers",
                "localai",
                "lmstudio",
                "llamacpp",
                "all",
            }
            runtime_rows = {row["name"]: row for row in catalog.list(include_gui=True)}
            if args.runtime not in helper_runtimes:
                row = runtime_rows.get(args.runtime)
                payload = {
                    "name": "runtime_helper_unavailable",
                    "runtime": args.runtime,
                    "action": args.runtimes_command,
                    "supported_by_aiplane_helper": False,
                    "reason": "aiplane does not currently automate this runtime lifecycle action",
                    "install_hint": row.get("install_hint") if row else None,
                    "known_runtime": bool(row),
                    "supported_helper_runtimes": sorted(helper_runtimes),
                }
                if not row:
                    payload["reason"] = "unknown runtime; use aiplane runtimes list --include-gui to see known runtimes"
                print(json_dumps(payload, indent=2))
                return 2
            helper_action = "list" if args.runtimes_command == "list-runtime-models" else args.runtimes_command
            if args.runtimes_command in {"remove", "clear"} and not args.dry_run and not args.yes:
                print(
                    json_dumps(
                        {
                            "name": "runtime_destructive_confirmation_required",
                            "runtime": args.runtime,
                            "action": args.runtimes_command,
                            "model": args.model,
                            "reason": "runtime model deletion requires --yes; use --dry-run to preview",
                        },
                        indent=2,
                    )
                )
                return 2
            host_platform = detect_host_platform()
            if (
                args.runtimes_command in {"install", "update", "update-installed"}
                and not host_platform.runtime_helper_supported
            ):
                payload = host_platform.unsupported(
                    "runtime_helper_install",
                    ["Ubuntu Linux", "Debian Linux"],
                    "runtime install/update helpers are not supported here; they require native Ubuntu/Debian Linux, while WSL, non-Linux, and other Linux distributions must use the runtime vendor installer",
                )
                payload.update(
                    {
                        "runtime": args.runtime,
                        "action": args.runtimes_command,
                        "next_steps": [
                            "Install the runtime with the platform-native or vendor installer.",
                            "Use aiplane discover, doctor, recommend, and export after the runtime is installed.",
                        ],
                    }
                )
                print(json_dumps(payload, indent=2))
                return 2
            install_reporter: Any | None = None
            if args.runtimes_command == "install" and not args.dry_run:
                install_reporter = _RuntimeInstallReporter()
                install_reporter.step(
                    "checking prerequisites", command=f"internal: runtimes prerequisites {args.runtime}"
                )
                prerequisites = catalog.prerequisites(args.runtime)
                if not prerequisites.get("ok"):
                    install_reporter.complete(f"prerequisites failed: {args.runtime}")
                    print(json_dumps(prerequisites, indent=2))
                    return 2
            substrate = _runtime_helper_substrate(profile, args.runtime, args.substrate)
            helper_command = _provider_helper_command(
                args.runtime,
                helper_action,
                effective_profile,
                args.model,
                substrate=substrate,
                dry_run=args.dry_run,
            )
            if install_reporter:
                install_reporter.step(f"running helper action: {helper_action}", command=helper_command)
                preview = _run_provider_helper(
                    args.runtime,
                    helper_action,
                    effective_profile,
                    args.model,
                    substrate=substrate,
                    dry_run=True,
                    profiles_dir=profiles_dir,
                )
                preview_command = _extract_helper_inner_command(preview)
                if preview_command:
                    install_reporter.step("running runtime install command", command=preview_command)
            completed = _run_provider_helper(
                args.runtime,
                helper_action,
                effective_profile,
                args.model,
                substrate=substrate,
                dry_run=args.dry_run,
                profiles_dir=profiles_dir,
            )
            if install_reporter:
                install_reporter.complete(f"install finished (exit {completed.returncode}): {args.runtime}")
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            return completed.returncode
        runtimes = [args.runtime] if args.runtime else [row["name"] for row in catalog.list()]
        print(json_dumps([catalog.runtime_available(runtime) for runtime in runtimes], indent=2))
        return 0

    return None


def _runtime_helper_substrate(profile: object, runtime: str, override: str | None = None) -> str:
    if override:
        return override
    provider = ModelCatalog(profile).providers().get(runtime, {}) if hasattr(profile, "models") else {}
    substrate = str(provider.get("substrate") or "native") if isinstance(provider, dict) else "native"
    return "docker" if substrate == "docker" else "native"


def _run_provider_helper(
    runtime: str,
    action: str,
    profile: str,
    model: str,
    substrate: str = "native",
    dry_run: bool = False,
    profiles_dir: Path | str | None = None,
    command_runner: CommandRunner | None = None,
) -> subprocess.CompletedProcess[str]:
    helper = provider_helper_path()
    if not helper.exists():
        raise FileNotFoundError(f"provider helper not found: {helper}")
    command = _provider_helper_command(runtime, action, profile, model, substrate=substrate, dry_run=dry_run)
    env = None
    if profiles_dir is not None:
        env = os.environ.copy()
        env["AIPLANE_PROFILES_DIR"] = str(profiles_dir)
    runner = command_runner or _COMMAND_RUNNER
    return runner.run(
        command,
        cwd=helper.parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _provider_helper_command(
    runtime: str,
    action: str,
    profile: str,
    model: str,
    substrate: str = "native",
    dry_run: bool = False,
) -> list[str]:
    helper = provider_helper_path()
    command = [
        str(helper),
        "--provider",
        runtime,
        "--action",
        action,
        "--profile",
        profile,
        "--model",
        model,
        "--substrate",
        substrate,
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def _extract_helper_inner_command(completed: subprocess.CompletedProcess[str]) -> str | None:
    output = f"{completed.stdout}\n{completed.stderr}".splitlines()
    for line in output:
        stripped = line.strip()
        if not stripped.startswith("+ "):
            continue
        command_text = stripped[2:].strip()
        if "provider_helper.sh" in command_text:
            continue
        return command_text
    return None


class _RuntimeInstallReporter:
    def __init__(self, dot_interval: float = 2.0):
        self._lock = threading.Lock()
        self._has_status_line = False
        self._dot_thread: threading.Thread | None = None
        self._dot_stop: threading.Event | None = None
        self._dot_interval = dot_interval

    def step(self, message: str, command: str | list[str] | None = None) -> None:
        self._stop_dot_line(clear_line=True)
        if self._has_status_line:
            self._write("\x1b[1A\r\x1b[2K")
        if isinstance(command, list):
            command_text = " ".join(str(part) for part in command)
        else:
            command_text = str(command or "").strip()
        if command_text:
            self._write(f"[runtime] {message}: {command_text}\n")
        else:
            self._write(f"[runtime] {message}\n")
        self._has_status_line = True
        self._start_dot_line()

    def complete(self, message: str) -> None:
        self._stop_dot_line(clear_line=True)
        if self._has_status_line:
            self._write("\x1b[1A\r\x1b[2K")
        self._write(f"[runtime] {message}\n")
        self._has_status_line = False

    def _start_dot_line(self) -> None:
        stop = threading.Event()
        self._dot_stop = stop
        thread = threading.Thread(target=self._dot_worker, args=(stop,), daemon=True)
        self._dot_thread = thread
        thread.start()

    def _dot_worker(self, stop: threading.Event) -> None:
        while not stop.wait(self._dot_interval):
            self._write(".")

    def _stop_dot_line(self, clear_line: bool) -> None:
        stop = self._dot_stop
        thread = self._dot_thread
        self._dot_stop = None
        self._dot_thread = None
        if stop:
            stop.set()
        if thread:
            thread.join(timeout=3)
        if clear_line:
            self._write("\r\x1b[2K\r")

    def _write(self, text: str) -> None:
        with self._lock:
            sys.stderr.write(text)
            sys.stderr.flush()


def _runtimes_list_text(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "runtimes: none"

    headers = {
        "name": "RUNTIME",
        "enabled": "ENABLED",
        "managed_by_helper": "CONTROL",
        "configured": "CONFIG",
        "mode": "MODE",
    }
    keys = list(headers)
    widths = {key: len(value) for key, value in headers.items()}
    normalized: list[dict[str, str]] = []
    for row in rows:
        managed = "helper" if bool(row.get("managed_by_helper")) else "manual"
        normalized.append(
            {
                "name": str(row.get("name") or ""),
                "enabled": "yes" if bool(row.get("enabled")) else "no",
                "managed_by_helper": managed,
                "configured": "yes" if bool(row.get("configured")) else "no",
                "mode": "gui" if bool(row.get("gui_required")) else "local",
            }
        )
    for row in normalized:
        for key in keys:
            widths[key] = max(widths[key], len(row.get(key, "")))

    lines = [
        "runtimes",
        "".join(headers[key].ljust(widths[key] + 2) for key in keys),
    ]
    for row in normalized:
        lines.append("".join(row[key].ljust(widths[key] + 2) for key in keys))
    return "\n".join(lines)
