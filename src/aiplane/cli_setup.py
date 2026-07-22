from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .benchmark_evidence import import_measurement_record, load_suite
from .benchmark_tools import BenchmarkToolManager
from .config import load_profile
from .env import EnvironmentManager
from .tools import ToolchainManager


def add_setup_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    environment = command_factory(
        subparsers,
        "environment",
        "Show, check, or plan native/venv/conda/docker execution",
        "Inspect the active execution environment, check prerequisite tools, or render how a command would run in that mode.",
        "Examples:\n  aiplane environment list\n  aiplane environment active\n  aiplane environment doctor\n  aiplane environment use venv\n  aiplane environment plan python -m unittest",
    )
    env_sub = environment.add_subparsers(dest="environment_command", required=True, metavar="command")
    env_show = env_sub.add_parser(
        "show",
        help="Show environment config",
        description="Show configured native, venv, conda, or docker execution settings.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(env_show)
    env_list = env_sub.add_parser(
        "list",
        help="List available environment modes",
        description="List configured environment modes and mark the active one.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(env_list)
    env_active = env_sub.add_parser(
        "active",
        help="Show active environment mode",
        description="Show only the active environment mode, its config, and available modes.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(env_active)
    env_use = env_sub.add_parser(
        "use",
        help="Set active environment mode",
        description="Persist a new active environment mode in the profile environment.yaml file.",
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog="Examples:\n  aiplane environment use system\n  aiplane environment use venv\n  aiplane environment use conda\n  aiplane environment use docker",
    )
    profile_arg(env_use)
    env_use.add_argument("mode", help="Configured mode name, such as system, venv, conda, or docker")
    env_plan = env_sub.add_parser(
        "plan",
        help="Render command execution plan",
        description="Show the command aiplane would run under the active environment mode.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(env_plan)
    env_plan.add_argument(
        "env_command_args",
        nargs=argparse.REMAINDER,
        help="Command to plan after the command name, for example python -m unittest",
    )
    env_doctor = env_sub.add_parser(
        "doctor",
        help="Check environment and prerequisite tool readiness",
        description="Check the active aiplane execution environment plus external CLIs/frameworks used by runtime, cloud, benchmark, container, Kubernetes, and SSH workflows.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(env_doctor)
    env_doctor.add_argument(
        "--required-only",
        action="store_true",
        help="Only check a minimal required set instead of optional benchmark/cloud tools",
    )
    env_doctor.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. Text is the default human-readable aligned table; use json for scripts.",
    )

    benchmarks_cmd = command_factory(
        subparsers,
        "benchmarks",
        "Plan/install benchmark frameworks",
        "Inspect optional benchmark frameworks and render commands for aiplane smoke benchmarks, lm-evaluation-harness, vLLM serving benchmarks, and endpoint load tests.",
        "Examples:\n  aiplane benchmarks list\n  aiplane benchmarks doctor\n  aiplane benchmarks install lm-evaluation-harness --dry-run\n  aiplane benchmarks plan aiplane-smoke --model MODEL_ALIAS",
    )
    benchmarks_sub = benchmarks_cmd.add_subparsers(dest="benchmarks_command", required=True, metavar="command")
    benchmarks_list = benchmarks_sub.add_parser(
        "list",
        help="List benchmark frameworks",
        description="List built-in and optional external benchmark frameworks known to aiplane.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(benchmarks_list)
    benchmarks_doctor = benchmarks_sub.add_parser(
        "doctor",
        help="Check benchmark framework availability",
        description="Check which benchmark frameworks are available and which need install/manual setup.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(benchmarks_doctor)
    benchmarks_doctor.add_argument(
        "name",
        nargs="?",
        help="Optional framework name, such as aiplane-smoke, lm-evaluation-harness, vllm-serving, or locust-load",
    )
    benchmarks_install = benchmarks_sub.add_parser(
        "install",
        help="Plan or run benchmark framework install",
        description="Install optional benchmark tools where aiplane has a safe helper command. Use --dry-run first.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(benchmarks_install)
    benchmarks_install.add_argument(
        "name",
        help="Framework name, such as lm-evaluation-harness, vllm-serving, or locust-load",
    )
    benchmarks_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Print install commands without executing them",
    )
    benchmarks_plan = benchmarks_sub.add_parser(
        "plan",
        help="Render benchmark command templates",
        description="Render commands for running one benchmark framework against a selected model/endpoint. This does not execute the benchmark.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(benchmarks_plan)
    benchmarks_plan.add_argument(
        "name",
        help="Framework name, such as aiplane-smoke, lm-evaluation-harness, vllm-serving, or locust-load",
    )
    benchmarks_plan.add_argument(
        "--model",
        default="MODEL_ALIAS",
        help="Model alias or provider-native model id to include in the command template",
    )
    benchmarks_plan.add_argument(
        "--endpoint",
        help="OpenAI-compatible endpoint for external benchmark frameworks",
    )
    benchmarks_plan.add_argument("--spec", help="Custom aiplane benchmark spec path for aiplane-smoke")

    benchmarks_validate = benchmarks_sub.add_parser(
        "suite-validate",
        help="Validate and normalize a benchmark suite",
        description="Validate a versioned JSON/YAML benchmark suite without executing it.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(benchmarks_validate)
    benchmarks_validate.add_argument("path", help="Benchmark suite JSON/YAML path")
    benchmarks_import = benchmarks_sub.add_parser(
        "import",
        help="Preview or import external benchmark measurements",
        description="Validate provenance-bearing JSON/YAML measurements. Preview is the default; --yes writes only to the ignored workspace cache.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(benchmarks_import)
    benchmarks_import.add_argument("path", help="Benchmark measurement JSON/YAML path")
    benchmarks_import.add_argument(
        "--yes",
        action="store_true",
        help="Write the validated record under .aiplane/benchmarks",
    )

    tools_cmd = command_factory(
        subparsers,
        "tools",
        "Check and install external prerequisite CLIs",
        "Inspect and install the small external toolchain aiplane can use for cloud, container, Kubernetes, and remote operations.",
        "Examples:\n  aiplane tools doctor\n  aiplane tools matrix\n  aiplane tools doctor azure-cli\n  aiplane tools plan vagrant\n  aiplane tools export opentofu\n  aiplane tools install opentofu --dry-run\n  aiplane tools install azure-cli",
    )
    tools_sub = tools_cmd.add_subparsers(dest="tools_command", required=True, metavar="command")
    tools_list = tools_sub.add_parser(
        "list",
        help="List known prerequisite tools",
        description="List supported external CLIs, categories, install hints, and detected versions.",
        formatter_class=formatter_class,
    )
    profile_arg(tools_list)
    tools_matrix = tools_sub.add_parser(
        "matrix",
        help="Show the tool task matrix",
        description="Group known external tools by workflow category and show tasks, required/optional status, installability, and starter export availability.",
        formatter_class=formatter_class,
    )
    profile_arg(tools_matrix)
    tools_doctor = tools_sub.add_parser(
        "doctor",
        help="Check external toolchain health",
        description="Check whether prerequisite tools are installed and whether selected services are reachable, such as Azure login or Docker daemon status.",
        formatter_class=formatter_class,
    )
    profile_arg(tools_doctor)
    tools_doctor.add_argument(
        "name",
        nargs="?",
        help="Optional tool name, such as azure-cli, opentofu, docker, kubectl, helm, openssh-client, or ansible",
    )
    tools_plan = tools_sub.add_parser(
        "plan",
        help="Plan how a tool fits a workflow",
        description="Show prerequisites, safe commands, generated artifacts, and next steps for an external tool workflow without mutating anything.",
        formatter_class=formatter_class,
    )
    profile_arg(tools_plan)
    tools_plan.add_argument(
        "name",
        help="Tool name, such as vagrant, packer, opentofu, terraform, pulumi, devcontainer-cli, or ansible",
    )
    tools_export = tools_sub.add_parser(
        "export",
        help="Print a starter tool artifact",
        description="Print a starter Vagrantfile, Packer template, IaC module, Dev Container config, or Ansible playbook. Output is not written automatically.",
        formatter_class=formatter_class,
    )
    profile_arg(tools_export)
    tools_export.add_argument(
        "name",
        help="Tool name, such as vagrant, packer, opentofu, terraform, pulumi, devcontainer-cli, or ansible",
    )
    tools_install = tools_sub.add_parser(
        "install",
        help="Plan or run prerequisite tool install",
        description="Render and run platform-specific install commands where supported. Use --dry-run to inspect commands without executing them.",
        formatter_class=formatter_class,
    )
    profile_arg(tools_install)
    tools_install.add_argument(
        "name",
        help="Tool name, such as azure-cli, opentofu, docker, kubectl, helm, openssh-client, or ansible",
    )
    tools_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Print install commands without executing them",
    )


def handle_setup_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
    progress_factory: Callable[[], Callable[[str], None]],
    resolve_format: Callable[..., str],
    config_path: Path,
    environment_doctor_text: Callable[[dict[str, Any]], str],
) -> int | None:
    if args.command not in {"environment", "benchmarks", "tools"}:
        return None
    profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
    if args.command == "tools":
        manager = ToolchainManager(profile)
        if args.tools_command == "list":
            payload = manager.list()
        elif args.tools_command == "doctor":
            payload = manager.doctor(args.name)
        elif args.tools_command == "matrix":
            payload = manager.matrix()
        elif args.tools_command == "plan":
            payload = manager.plan(args.name)
        elif args.tools_command == "export":
            exported = manager.export(args.name)
            print(exported["content"])
            if exported.get("notes"):
                print("\\n# Notes")
                for note in exported["notes"]:
                    print(f"# - {note}")
            return 0
        else:
            payload = manager.install(args.name, dry_run=args.dry_run, yes=not args.dry_run)
        print(json_dumps(payload, indent=2))
        return 0
    if args.command == "benchmarks":
        manager = BenchmarkToolManager(profile)
        if args.benchmarks_command == "list":
            payload = manager.list()
        elif args.benchmarks_command == "doctor":
            payload = manager.doctor(args.name)
        elif args.benchmarks_command == "install":
            payload = manager.install(args.name, dry_run=args.dry_run)
        elif args.benchmarks_command == "plan":
            payload = manager.plan(args.name, model=args.model, endpoint=args.endpoint, spec=args.spec)
        elif args.benchmarks_command == "suite-validate":
            payload = load_suite(Path(args.path).resolve())
        else:
            from .model_catalog import ModelCatalog

            source = Path(args.path).resolve()
            payload = import_measurement_record(profile.workspace, source, dry_run=True)
            catalog = ModelCatalog(profile)
            catalog.show(payload["record"]["model_name"])
            if args.yes:
                payload = import_measurement_record(profile.workspace, source, dry_run=False)
                catalog.rebuild_materialized()
        print(json_dumps(payload, indent=2))
        return 0
    manager = EnvironmentManager(profile)
    if args.environment_command == "show":
        payload = manager.show()
    elif args.environment_command == "list":
        payload = manager.list_modes()
    elif args.environment_command == "active":
        payload = manager.active()
    elif args.environment_command == "use":
        payload = manager.use(args.mode)
    elif args.environment_command == "doctor":
        progress = progress_factory()
        payload = ToolchainManager(profile).environment_doctor(
            include_optional=not args.required_only, progress=progress
        )
        progress("")
        if resolve_format(args.format, profile=effective_profile, path=config_path) == "text":
            print(environment_doctor_text(payload))
        else:
            print(json_dumps(payload, indent=2))
        return 0
    else:
        command = (
            args.env_command_args[1:]
            if args.env_command_args and args.env_command_args[0] == "--"
            else args.env_command_args
        )
        if not command:
            raise ValueError("environment plan requires a command after plan")
        plan = manager.plan(command)
        payload = {"mode": plan.mode, "command": plan.command, "cwd": str(plan.cwd), "description": plan.description}
    print(json_dumps(payload, indent=2, sort_keys=True))
    return 0
