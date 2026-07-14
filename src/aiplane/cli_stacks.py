from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .config import load_profile
from .orchestrators import OrchestratorCatalog
from .stacks import StackManager


def add_stack_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    orchestrators_cmd = command_factory(
        subparsers,
        "orchestrators",
        "Inspect agent/workflow orchestrator options",
        "List, inspect, and health-check orchestrator frameworks such as LangGraph, CrewAI, AutoGen, and OpenHands. Operational setup happens through stacks.",
        "Examples:\n  aiplane orchestrators list\n  aiplane orchestrators show langgraph\n  aiplane orchestrators setup langgraph --runtime ollama --model MODEL_ALIAS --dry-run\n  aiplane orchestrators doctor langgraph",
    )
    orchestrators_sub = orchestrators_cmd.add_subparsers(dest="orchestrators_command", required=True, metavar="command")
    orchestrators_list = orchestrators_sub.add_parser(
        "list",
        help="List supported orchestrators",
        description="List known orchestrator frameworks and where they fit. Filter by provider/runtime or group by provider/runtime for discovery.",
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog="Examples:\n  aiplane orchestrators list\n  aiplane orchestrators list --provider ollama\n  aiplane orchestrators list --runtime ollama --runtime vllm\n  aiplane orchestrators list --group-by provider",
    )
    profile_arg(orchestrators_list)
    orchestrators_list.add_argument(
        "--provider",
        action="append",
        default=[],
        help="Only show orchestrators compatible with this provider; can be repeated",
    )
    orchestrators_list.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="Only show orchestrators compatible with all listed runtimes; can be repeated",
    )
    orchestrators_list.add_argument(
        "--group-by",
        choices=["provider", "runtime"],
        help="Group orchestrators by compatible provider or runtime",
    )
    orchestrators_show = orchestrators_sub.add_parser(
        "show",
        help="Show one orchestrator",
        description="Show one orchestrator definition and any profile config.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(orchestrators_show)
    orchestrators_show.add_argument(
        "name",
        help="Orchestrator name, such as langgraph, crewai, autogen, or openhands",
    )
    orchestrators_setup = orchestrators_sub.add_parser(
        "setup",
        help="Configure one orchestrator",
        description="Write profile-specific orchestrator settings to orchestrators.yaml. Use --dry-run to preview without writing or installing.",
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog="Examples:\n  aiplane orchestrators setup langgraph --runtime ollama --model MODEL_ALIAS --dry-run\n  aiplane orchestrators setup langgraph --runtime ollama --model MODEL_ALIAS --approval-mode ask\n  aiplane orchestrators setup langgraph --runtime vllm --model MODEL_ALIAS --endpoint http://localhost:8000/v1 --limit timeout=30m --tool shell=guarded",
    )
    profile_arg(orchestrators_setup)
    orchestrators_setup.add_argument(
        "name",
        help="Orchestrator name, such as langgraph, crewai, autogen, or openhands",
    )
    orchestrators_setup.add_argument(
        "--runtime",
        help="Runtime to pair with the orchestrator, such as ollama or vllm",
    )
    orchestrators_setup.add_argument("--model", help="Configured model alias to pair with the orchestrator")
    orchestrators_setup.add_argument("--endpoint", help="Endpoint URL to pass to the orchestrator config")
    orchestrators_setup.add_argument(
        "--environment",
        help="Environment mode to use, such as system, venv, conda, or docker",
    )
    orchestrators_setup.add_argument(
        "--approval-mode",
        help="Free-form approval mode hint, such as ask, guarded, or auto",
    )
    orchestrators_setup.add_argument(
        "--limit",
        action="append",
        default=[],
        help="Pass-through limit key=value, such as timeout=30m; can be repeated",
    )
    orchestrators_setup.add_argument(
        "--tool",
        action="append",
        default=[],
        help="Pass-through tool policy key=value, such as shell=guarded; can be repeated",
    )
    orchestrators_setup.add_argument(
        "--install",
        action="store_true",
        help="Also install the orchestrator packages into the selected environment",
    )
    orchestrators_setup.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing orchestrators.yaml or installing packages",
    )
    orchestrators_doctor = orchestrators_sub.add_parser(
        "doctor",
        help="Check orchestrator config/install state",
        description="Check that an orchestrator is known, configured, and that its Python packages are importable in the current Python process.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(orchestrators_doctor)
    orchestrators_doctor.add_argument("name", help="Orchestrator name")

    stacks_cmd = command_factory(
        subparsers,
        "stacks",
        "Plan orchestrator/runtime/model/machine deployments",
        "Bind an optional orchestrator, runtime, model, machine, and access policy into a stack that can be planned, checked, exported, and later deployed.",
        "Examples:\n  aiplane stacks setup coding_agents --orchestrator langgraph --runtime vllm --model MODEL_ALIAS --machine gpu_box_01 --dry-run\n  aiplane stacks plan coding_agents\n  aiplane stacks export continue coding_agents",
    )
    stacks_sub = stacks_cmd.add_subparsers(dest="stacks_command", required=True, metavar="command")
    stacks_list = stacks_sub.add_parser(
        "list",
        help="List stacks",
        description="List configured model/runtime/machine stacks.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_list)
    stacks_show = stacks_sub.add_parser(
        "show",
        help="Show one stack",
        description="Show one stack definition.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_show)
    stacks_show.add_argument("name", help="Stack name")
    stacks_setup = stacks_sub.add_parser(
        "setup",
        help="Write or preview a stack",
        description="Persist an orchestrator + runtime + model + machine + access binding in hardware.yaml. Use --dry-run to preview without writing.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_setup)
    stacks_setup.add_argument("name", help="Stack name")
    stacks_setup.add_argument(
        "--orchestrator",
        help="Optional orchestrator name, such as langgraph, crewai, autogen, or openhands",
    )
    stacks_setup.add_argument("--runtime", required=True, help="Runtime name")
    stacks_setup.add_argument("--model", required=True, help="Configured model alias")
    stacks_setup.add_argument(
        "--machine",
        required=True,
        help="Machine name from aiplane machines list; export/import a real machine profile first with hardware export-machine and machines import",
    )
    stacks_setup.add_argument(
        "--target",
        help="Explicit ssh_tunnel target name from targets.yaml when access=ssh_tunnel",
    )
    stacks_setup.add_argument(
        "--access",
        default="ssh_tunnel",
        help="Access mode, such as same_host, ssh_tunnel, lan_http, or gateway",
    )
    stacks_setup.add_argument(
        "--endpoint-policy",
        default="private",
        choices=["private", "vpn", "gateway", "public", "shared"],
        help="Endpoint exposure policy; shared/public/gateway require auth/TLS planning before team use",
    )
    stacks_setup.add_argument("--endpoint", help="Endpoint URL override")
    stacks_setup.add_argument(
        "--endpoint-auth",
        choices=[
            "none",
            "bearer",
            "api_key",
            "basic",
            "oauth2",
            "oidc",
            "mtls",
            "gateway",
        ],
        help="Auth method expected at the endpoint gateway/reverse proxy",
    )
    stacks_setup.add_argument(
        "--endpoint-auth-env",
        help="Environment variable that will hold the endpoint/gateway credential for bearer or api_key auth",
    )
    stacks_setup.add_argument(
        "--endpoint-tls",
        choices=["required", "terminated", "not_configured", "not_required"],
        help="TLS posture for endpoint planning; use terminated when TLS is handled by a gateway",
    )
    stacks_setup.add_argument(
        "--gateway",
        help="Gateway/reverse proxy pattern or name, such as caddy, nginx, traefik, apim, or kubernetes-gateway",
    )
    stacks_setup.add_argument(
        "--limit",
        action="append",
        default=[],
        help="Pass-through limit key=value, such as timeout=30m or max_parallel_agents=3; can be repeated",
    )
    stacks_setup.add_argument(
        "--tool",
        action="append",
        default=[],
        help="Pass-through tool policy key=value, such as shell=guarded or filesystem=workspace_only; can be repeated",
    )
    stacks_setup.add_argument(
        "--role",
        action="append",
        default=[],
        help="Optional orchestrator role binding ROLE=MODEL_ALIAS, such as planner=local_chat; can be repeated",
    )
    stacks_setup.add_argument(
        "--approval-mode",
        help="Approval policy label for orchestrator role metadata, such as ask, guarded, or manual",
    )
    stacks_setup.add_argument(
        "--audit-label",
        help="Audit label prefix for orchestrator role metadata",
    )
    stacks_setup.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the stack without writing hardware.yaml",
    )
    stacks_plan = stacks_sub.add_parser(
        "plan",
        help="Plan a stack",
        description="Render the checks and actions needed to run a stack.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_plan)
    stacks_plan.add_argument("name", help="Stack name")
    stacks_doctor = stacks_sub.add_parser(
        "doctor",
        help="Check a stack",
        description="Check machine fit, runtime availability, preflight checks, role endpoint bindings, and risky role tool-policy combinations for a stack.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_doctor)
    stacks_doctor.add_argument("name", help="Stack name")
    stacks_endpoint_plan = stacks_sub.add_parser(
        "endpoint-plan",
        help="Plan endpoint auth and gateway controls",
        description="Render a non-mutating endpoint security plan for a stack, including TLS, auth, gateway, and private/shared exposure checks.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_endpoint_plan)
    stacks_endpoint_plan.add_argument("name", help="Stack name")
    stacks_export = stacks_sub.add_parser(
        "export",
        help="Export stack artifacts",
        description="Export IDE config or packaging artifacts for a stack endpoint.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_export)
    stacks_export.add_argument(
        "artifact",
        choices=[
            "continue",
            "openai-compatible",
            "dockerfile",
            "conda-yaml",
            "compose",
            "langgraph",
            "crewai",
            "autogen",
            "semantic-kernel",
            "llamaindex-workflows",
            "openhands",
        ],
        help="Artifact format to export",
    )
    stacks_export.add_argument("name", help="Stack name")
    for lifecycle_action in ["prepare", "start", "stop", "restart"]:
        lifecycle = stacks_sub.add_parser(
            lifecycle_action,
            help=f"{lifecycle_action.capitalize()} stack components",
            description="Run the stack lifecycle action. Use --dry-run to preview commands without executing them.",
            formatter_class=formatter_class,
            allow_abbrev=False,
        )
        profile_arg(lifecycle)
        lifecycle.add_argument("name", help="Stack name")
        lifecycle.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview commands without executing them",
        )
    stacks_status = stacks_sub.add_parser(
        "status",
        help="Show stack runtime/orchestrator status",
        description="Check stack runtime and orchestrator status without mutating anything.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(stacks_status)
    stacks_status.add_argument("name", help="Stack name")


def handle_stack_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
    parse_settings: Callable[[list[str]], dict[str, object]],
) -> int | None:
    if args.command == "orchestrators":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        catalog = OrchestratorCatalog(profile)
        if args.orchestrators_command == "list":
            print(
                json_dumps(
                    catalog.list(
                        providers=args.provider,
                        runtimes=args.runtime,
                        group_by=args.group_by,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.orchestrators_command == "show":
            print(json_dumps(catalog.show(args.name), indent=2))
            return 0
        if args.orchestrators_command == "setup":
            print(
                json_dumps(
                    catalog.setup(
                        args.name,
                        runtime=args.runtime,
                        model=args.model,
                        endpoint=args.endpoint,
                        environment=args.environment,
                        approval_mode=args.approval_mode,
                        limits=parse_settings(args.limit),
                        tools=parse_settings(args.tool),
                        dry_run=args.dry_run,
                        yes=not args.dry_run,
                        install=args.install,
                    ),
                    indent=2,
                )
            )
            return 0
        print(json_dumps(catalog.doctor(args.name), indent=2))
        return 0

    if args.command == "stacks":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = StackManager(profile)
        if args.stacks_command == "list":
            print(json_dumps(manager.list(), indent=2))
            return 0
        if args.stacks_command == "show":
            print(json_dumps(manager.show(args.name), indent=2))
            return 0
        if args.stacks_command == "setup":
            print(
                json_dumps(
                    manager.setup(
                        args.name,
                        orchestrator=args.orchestrator,
                        runtime=args.runtime,
                        model=args.model,
                        machine=args.machine,
                        access=args.access,
                        target=args.target,
                        endpoint_policy=args.endpoint_policy,
                        endpoint=args.endpoint,
                        endpoint_auth={
                            key: value
                            for key, value in {
                                "method": args.endpoint_auth,
                                "api_key_env": args.endpoint_auth_env,
                                "tls": args.endpoint_tls,
                                "gateway": args.gateway,
                            }.items()
                            if value
                        },
                        limits=parse_settings(args.limit),
                        tools=parse_settings(args.tool),
                        roles={key: str(value) for key, value in parse_settings(args.role).items()},
                        approval_mode=args.approval_mode,
                        audit_label=args.audit_label,
                        dry_run=args.dry_run,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.stacks_command == "plan":
            print(json_dumps(manager.plan(args.name), indent=2))
            return 0
        if args.stacks_command == "doctor":
            print(json_dumps(manager.doctor(args.name), indent=2))
            return 0
        if args.stacks_command == "endpoint-plan":
            print(json_dumps(manager.endpoint_plan(args.name), indent=2))
            return 0
        if args.stacks_command == "export":
            exported = manager.export(args.artifact, args.name)
            print(exported["content"])
            if exported.get("notes"):
                print("\n# Notes")
                for note in exported["notes"]:
                    print(f"# - {note}")
            return 0
        if args.stacks_command == "prepare":
            print(json_dumps(manager.prepare(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "start":
            print(json_dumps(manager.start(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "stop":
            print(json_dumps(manager.stop(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "restart":
            print(json_dumps(manager.restart(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "status":
            print(json_dumps(manager.status(args.name), indent=2))
            return 0
        return None
