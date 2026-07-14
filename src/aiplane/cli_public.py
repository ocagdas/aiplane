from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .config import load_profile, local_config_path, resolve_output_format, resolve_profile_name
from .hardware import HardwareManager
from .local_doctor import local_coding_doctor, local_coding_doctor_text


def add_public_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    integration_selection_args: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
    integration_tools: tuple[str, ...],
) -> None:
    discover_cmd = command_factory(
        subparsers,
        "discover",
        "Discover the local AI workflow environment",
        "Read the current profile and detect hardware, runtime/provider configuration, local model aliases, endpoint configuration, and supported coding-tool exports. This command is read-only.",
        "Examples:\n  aiplane discover\n  aiplane discover --format json",
    )
    profile_arg(discover_cmd)
    discover_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. Text is human-readable; JSON is for scripts.",
    )

    recommend_cmd = command_factory(
        subparsers,
        "recommend",
        "Recommend models for this machine",
        "Rank local model aliases against the active hardware selection, runtime compatibility, and policy. This command is read-only.",
        "Examples:\n  aiplane recommend\n  aiplane recommend --include-not-recommended\n  aiplane recommend --format json",
    )
    profile_arg(recommend_cmd)
    recommend_cmd.add_argument(
        "--include-not-recommended",
        action="store_true",
        help="Include models rejected by hardware, runtime, or policy constraints",
    )
    recommend_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. Text is human-readable; JSON is for scripts.",
    )

    export_cmd = command_factory(
        subparsers,
        "export",
        "Export configuration for coding tools",
        "Print configuration for Continue, Aider, Cline, Zed, OpenAI-compatible clients, or MCP clients. This does not edit target tool files.",
        "Examples:\n  aiplane export continue\n  aiplane export aider --model MODEL_ALIAS\n  aiplane export vscode-mcp",
    )
    profile_arg(export_cmd)
    integration_selection_args(export_cmd)
    export_cmd.add_argument(
        "--model",
        help="Single model alias to export. For Continue, omit this to export chat/autocomplete/embedding selections",
    )
    export_cmd.add_argument("--from-plan", help="Path to a JSON file produced by integrations plan")
    export_cmd.add_argument("--endpoint", help="Override provider endpoint/base URL")
    export_cmd.add_argument(
        "--api-key-env", help="Environment variable name the target tool should read for an API key"
    )
    export_cmd.add_argument("tool", choices=integration_tools, help="Export format to print")

    doctor_cmd = command_factory(
        subparsers,
        "doctor",
        "Check the local AI coding stack",
        "Aggregate the local/hybrid AI coding stack readiness checks: profile files, required environment tools, model defaults, provider state, integration roles, and MCP manifest.",
        "Examples:\n  aiplane doctor\n  aiplane doctor --format json\n  aiplane doctor --include-optional",
    )
    profile_arg(doctor_cmd)
    doctor_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. Text is human-readable; JSON is for scripts.",
    )
    doctor_cmd.add_argument(
        "--include-optional",
        action="store_true",
        help="Include optional external workflow tools in the environment section",
    )

    quickstart_cmd = command_factory(
        subparsers,
        "quickstart",
        "Start a guided local AI coding setup",
        "Run a focused environment-doctor workflow that discovers, validates, and compiles reproducible local/hybrid AI coding profiles.",
        "Examples:\n  aiplane quickstart local-coding\n  aiplane quickstart local-coding --dry-run\n  aiplane quickstart local-coding --no-discovery",
    )
    quickstart_sub = quickstart_cmd.add_subparsers(dest="quickstart_command", required=True, metavar="command")
    local_coding = quickstart_sub.add_parser(
        "local-coding",
        help="Bootstrap and inspect the local AI coding profile",
        description=(
            "Create or refresh a local-dev style profile using the existing profile bootstrap path, "
            "then print the local coding stack doctor summary and exact next commands. If --pull-model "
            "is supplied, the selected model is pulled through the existing runtime helper unless "
            "--dry-run is also supplied; it does not install runtimes, edit IDE config, or mutate cloud resources."
        ),
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    local_coding.add_argument("--name", default="local-dev", help="Editable profile name to create or inspect")
    local_coding.add_argument(
        "--template",
        default="local-dev",
        help="Profile template to use when creating the profile",
    )
    local_coding.add_argument(
        "--overwrite",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Replace an existing profile directory first; existing profiles are preserved by default",
    )
    local_coding.add_argument(
        "--no-discovery",
        action="store_true",
        help="Skip provider model discovery refresh",
    )
    local_coding.add_argument(
        "--no-hardware-discovery",
        action="store_true",
        help="Skip local hardware discovery",
    )
    local_coding.add_argument(
        "--select-closest-hardware",
        action="store_true",
        help="Set active hardware to the closest discovered template during bootstrap",
    )
    local_coding.add_argument("--provider", default="all", help="Model provider to refresh, or all")
    local_coding.add_argument("--query", help="Optional provider catalog search query")
    local_coding.add_argument(
        "--limit",
        type=int,
        help="Maximum model ids to read per provider catalog; when omitted, uses the models refresh command default",
    )
    local_coding.add_argument(
        "--provider-limit",
        action="append",
        default=[],
        metavar="PROVIDER=COUNT",
        help="Override --limit for one model provider",
    )
    local_coding.add_argument(
        "--disable-new",
        action="store_true",
        help="Write newly discovered entries as disabled",
    )
    local_coding.add_argument(
        "--verbosity",
        type=int,
        choices=[0, 1, 2],
        default=0,
        help="Discovery output detail: 0=top-level summary, 1=provider summary, 2=full per-model change rows",
    )
    local_coding.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview bootstrap/discovery without writing",
    )
    local_coding.add_argument(
        "--pull-model",
        help="Optional configured model alias to pull through the existing runtime helper after bootstrap",
    )
    local_coding.add_argument(
        "--pull-runtime",
        help="Runtime/provider to use for --pull-model. Defaults to the model preferred/runtime selection.",
    )
    local_coding.add_argument(
        "--pull-substrate",
        choices=["native", "docker"],
        help="Override the runtime helper substrate for --pull-model; Ollama supports native and docker",
    )
    local_coding.add_argument(
        "--format",
        choices=["json", "text"],
        default=None,
        help="Output format. Text is the default human-readable summary; use json for scripts.",
    )


def handle_public_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    requested_profile: str | None,
    json_dumps: Callable[..., str],
    quickstart: Callable[..., dict[str, object]],
    quickstart_text: Callable[[dict[str, object]], str],
    discover: Callable[[object], dict[str, object]],
    discover_text: Callable[[dict[str, object]], str],
    recommend_text: Callable[[dict[str, object]], str],
    print_export: Callable[[argparse.Namespace, object], None],
    doctor_exit_code: Callable[[dict[str, object]], int],
) -> int | None:
    if args.command == "quickstart":
        if args.quickstart_command == "local-coding":
            result = quickstart(args, workspace, profiles_dir)
            output_format = resolve_output_format(
                args.format,
                profile=args.name,
                path=local_config_path(),
            )
            if output_format == "text":
                print(quickstart_text(result))
            else:
                print(json_dumps(result, indent=2, sort_keys=True))
            validation = (
                result.get("bootstrap", {}).get("validation") if isinstance(result.get("bootstrap"), dict) else None
            )
            return 0 if validation is None or validation.get("ok", False) else 1

    effective_profile = resolve_profile_name(requested_profile, profiles_dir=profiles_dir)

    if args.command == "discover":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        payload = discover(profile)
        output_format = resolve_output_format(
            args.format,
            profile=effective_profile,
            command="discover",
            path=local_config_path(),
            default="text",
        )
        if output_format == "json":
            print(json_dumps(payload, indent=2, sort_keys=True))
        else:
            print(discover_text(payload))
        return 0

    if args.command == "recommend":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        payload = HardwareManager(profile).recommend(include_not_recommended=args.include_not_recommended)
        output_format = resolve_output_format(
            args.format,
            profile=effective_profile,
            command="recommend",
            path=local_config_path(),
            default="text",
        )
        if output_format == "json":
            print(json_dumps(payload, indent=2, sort_keys=True))
        else:
            print(recommend_text(payload))
        return 0

    if args.command == "export":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        print_export(args, profile)
        return 0

    if args.command == "doctor":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        payload = local_coding_doctor(profile, include_optional=args.include_optional)
        output_format = resolve_output_format(
            args.format,
            profile=effective_profile,
            path=local_config_path(),
        )
        if output_format == "json":
            print(json_dumps(payload, indent=2, sort_keys=True))
        else:
            print(local_coding_doctor_text(payload))
        return doctor_exit_code(payload)

    return None
