from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .integration_contracts import ALL_INTEGRATION_TOOLS, SETUP_INTEGRATION_TOOLS
from .integrations import IntegrationManager
from .models import Profile

JsonDumps = Callable[..., str]
ProfileArg = Callable[[argparse.ArgumentParser], None]
SelectionArgs = Callable[[argparse.ArgumentParser], None]


def add_integrations_parser(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: ProfileArg,
    selection_args: SelectionArgs,
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    integrations_cmd = command_factory(
        subparsers,
        "integrations",
        "Plan, prepare, and export IDE/CLI configuration snippets",
        "Plan model selection, prepare runtimes/models, and generate config snippets for tools such as Continue, Cline, Zed, Aider, or generic OpenAI-compatible clients.",
        "Examples:\n"
        "  aiplane integrations list\n"
        "  aiplane integrations plan continue --select-best --runtime ollama\n"
        "  aiplane integrations setup continue --dry-run\n"
        "  aiplane integrations export continue\n"
        "  aiplane integrations export openai-compatible --model MODEL_ALIAS --endpoint http://localhost:8000/v1",
    )
    integrations_sub = integrations_cmd.add_subparsers(dest="integrations_command", required=True, metavar="command")
    integrations_list = integrations_sub.add_parser(
        "list",
        help="List supported export targets",
        description="List integration exporters currently supported by aiplane.",
        formatter_class=formatter_class,
    )
    profile_arg(integrations_list)

    integrations_roles = integrations_sub.add_parser(
        "roles",
        help="Show required model roles for a target",
        description="Show the model roles an integration target can use, plus the capability signals aiplane uses for filtering and ranking.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane integrations roles continue\n  aiplane integrations roles cline",
    )
    profile_arg(integrations_roles)
    integrations_roles.add_argument("tool", choices=ALL_INTEGRATION_TOOLS, help="Integration target to inspect")
    integrations_roles.add_argument(
        "--groups",
        action="store_true",
        help="Print compact required/optional role groups instead of JSON",
    )

    integrations_plan = integrations_sub.add_parser(
        "plan",
        help="Plan integration model selection",
        description="Explain which models/runtimes/endpoints would be used for an integration. This does not write config or start runtimes.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane integrations plan continue\n  aiplane integrations plan continue --select-best --runtime ollama\n  aiplane integrations plan continue --chat CHAT_ALIAS --autocomplete AUTOCOMPLETE_ALIAS --embedding EMBEDDING_ALIAS\n  aiplane integrations plan cline --model MODEL_ALIAS --endpoint http://localhost:8000/v1\n  aiplane integrations plan aider --select-best --runtime vllm --capability code_generation>=4",
    )
    profile_arg(integrations_plan)
    selection_args(integrations_plan)
    integrations_plan.add_argument(
        "--model",
        help="Single model alias for one-model targets such as Cline, Zed, Aider, or openai-compatible",
    )
    integrations_plan.add_argument("--endpoint", help="Endpoint override passed through to the plan")
    integrations_plan.add_argument("--api-key-env", help="API key env var override passed through to the plan")
    integrations_plan.add_argument("tool", choices=ALL_INTEGRATION_TOOLS, help="Integration target to plan")

    integrations_setup = integrations_sub.add_parser(
        "setup",
        help="Prepare models/runtimes for an integration",
        description="Use the integration plan to check/start runtimes and pull selected models. Use --dry-run to preview without executing helper actions.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane integrations setup continue --dry-run\n  aiplane integrations setup continue\n  aiplane integrations setup continue --select-best --runtime ollama\n  aiplane integrations setup cline --model MODEL_ALIAS --runtime vllm --dry-run",
    )
    profile_arg(integrations_setup)
    selection_args(integrations_setup)
    integrations_setup.add_argument(
        "--model",
        help="Single model alias for one-model targets such as Cline, Zed, Aider, or openai-compatible",
    )
    integrations_setup.add_argument("--endpoint", help="Endpoint override passed through to the plan")
    integrations_setup.add_argument("--api-key-env", help="API key env var override passed through to the plan")
    integrations_setup.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview runtime start/pull actions without executing them",
    )
    integrations_setup.add_argument("tool", choices=SETUP_INTEGRATION_TOOLS, help="Integration target to prepare")

    integrations_export = integrations_sub.add_parser(
        "export",
        help="Print a config snippet",
        description="Print configuration for an IDE/CLI target. This does not install extensions or edit settings files.",
        formatter_class=formatter_class,
        epilog="Endpoint examples:\n  http://localhost:11434/v1       local Ollama\n  http://localhost:8000/v1        local vLLM\n  https://llm.example.com/v1      remote gateway/shared endpoint",
    )
    profile_arg(integrations_export)
    selection_args(integrations_export)
    integrations_export.add_argument(
        "--model",
        help="Single model alias to export. For Continue, omit this to export chat/autocomplete/embedding selections",
    )
    integrations_export.add_argument(
        "--from-plan",
        help="Path to a JSON file produced by integrations plan. Exports from that saved decision instead of recomputing selection",
    )
    integrations_export.add_argument(
        "--endpoint",
        help="Override provider endpoint/base URL, useful for SSH tunnels, gateways, or remote runtimes",
    )
    integrations_export.add_argument(
        "--api-key-env",
        help="Environment variable name the target tool should read for an API key",
    )
    integrations_export.add_argument("tool", choices=ALL_INTEGRATION_TOOLS, help="Export format to print")


def handle_integrations_command(args: argparse.Namespace, profile: Profile, json_dumps: JsonDumps) -> int:
    manager = IntegrationManager(profile)
    if args.integrations_command == "list":
        print(json_dumps(manager.list(), indent=2, sort_keys=True))
        return 0
    if args.integrations_command == "roles":
        payload = manager.roles(args.tool)
        if args.groups:
            required = []
            optional = []
            for role in payload.get("roles", []):
                target = required if bool(role.get("required")) else optional
                target.append(str(role.get("name") or ""))
            print(f"required: {json.dumps(required)}")
            print(f"optional: {json.dumps(optional)}")
        else:
            print(json_dumps(payload, indent=2))
        return 0
    if args.integrations_command == "plan":
        print(json_dumps(_plan(manager, args), indent=2))
        return 0
    if args.integrations_command == "setup":
        print(
            json_dumps(
                manager.setup(
                    args.tool,
                    model_name=args.model,
                    provider=args.provider,
                    runtime=args.runtime,
                    capabilities=args.capability,
                    select_best=args.select_best,
                    chat=args.chat,
                    autocomplete=args.autocomplete,
                    embedding=args.embedding,
                    endpoint=args.endpoint,
                    api_key_env=args.api_key_env,
                    dry_run=args.dry_run,
                    yes=not args.dry_run,
                ),
                indent=2,
            )
        )
        return 0
    if args.integrations_command == "export":
        if args.from_plan:
            plan = json.loads(Path(args.from_plan).read_text(encoding="utf-8"))
            exported = manager.export_from_plan(plan)
        else:
            exported = manager.export(
                args.tool,
                args.model,
                endpoint=args.endpoint,
                api_key_env=args.api_key_env,
                provider=args.provider,
                runtime=args.runtime,
                capabilities=args.capability,
                select_best=args.select_best,
                chat=args.chat,
                autocomplete=args.autocomplete,
                embedding=args.embedding,
            )
        print(exported.content)
        if exported.notes:
            print("\n# Notes")
            for note in exported.notes:
                print(f"# - {note}")
        return 0
    raise ValueError(f"unknown integrations command: {args.integrations_command}")


def _plan(manager: IntegrationManager, args: argparse.Namespace) -> dict[str, Any]:
    return manager.plan(
        args.tool,
        model_name=args.model,
        provider=args.provider,
        runtime=args.runtime,
        capabilities=args.capability,
        select_best=args.select_best,
        chat=args.chat,
        autocomplete=args.autocomplete,
        embedding=args.embedding,
        endpoint=args.endpoint,
        api_key_env=args.api_key_env,
    )
