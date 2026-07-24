from __future__ import annotations

import argparse

from .cli_config import add_config_parser
from .cli_deploy_remote import add_deploy_remote_parsers
from .cli_execution import add_execution_parsers
from .cli_governance import add_governance_parsers
from .cli_hardware import add_hardware_machine_parsers
from .cli_help import HelpFormatter
from .cli_integrations import add_integrations_parser
from .cli_models import add_models_parser
from .cli_profiles import add_profiles_parser
from .cli_providers import add_providers_parser
from .cli_public import add_public_parsers
from .cli_runtimes import add_runtimes_parser
from .cli_setup import add_setup_parsers
from .cli_stacks import add_stack_parsers
from .cli_support_catalog import add_support_parser
from .cli_version import add_version_argument
from .integration_contracts import ALL_INTEGRATION_TOOLS


BRIDGE_ACTIONS: dict[str, dict[str, object]] = {
    "ollama-launch": {
        "description": "Launch Ollama native app flow",
        "base_command": ["ollama", "launch"],
        "requires_model": False,
        "supports_prompt": False,
    },
    "ollama-list": {
        "description": "List local Ollama models",
        "base_command": ["ollama", "list"],
        "requires_model": False,
        "supports_prompt": False,
    },
    "ollama-ps": {
        "description": "List running Ollama models",
        "base_command": ["ollama", "ps"],
        "requires_model": False,
        "supports_prompt": False,
    },
    "ollama-run": {
        "description": "Run Ollama model by id/alias",
        "base_command": ["ollama", "run"],
        "requires_model": True,
        "supports_prompt": True,
    },
}

LAUNCH_TOOLS = ("aider", "codex", "continue", "ollama")


def _command(subparsers, name: str, help_text: str, description: str, epilog: str | None = None):
    return subparsers.add_parser(
        name,
        help=help_text,
        description=description,
        epilog=epilog,
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )


def _profile_arg(parser) -> None:
    parser.add_argument(
        "--profile",
        help="Profile name. Optional: defaults to AIPLANE_PROFILE, local config default_profile, or the only available profile",
    )


def _integration_selection_args(parser) -> None:
    parser.add_argument("--provider", help="Constrain model selection to a provider/source, such as ollama or vllm")
    parser.add_argument(
        "--runtime",
        help="Constrain model selection to a compatible runtime, such as ollama, vllm, or tgi",
    )
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Capability threshold used for selection, e.g. code_analysis>=3 or tool_use>=2; can be repeated",
    )
    parser.add_argument(
        "--select-best",
        action="store_true",
        help="Select best-fit catalog models instead of using profile defaults",
    )
    parser.add_argument("--chat", help="Force a model alias for Continue chat/edit/apply")
    parser.add_argument("--autocomplete", help="Force a model alias for Continue autocomplete")
    parser.add_argument("--embedding", help="Force a model alias for Continue embeddings/retrieval")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiplane",
        description=(
            "Diagnose and reproduce local and hybrid AI development environments.\n\n"
            "aiplane is an environment doctor and configuration compiler. Its doctor is a read-only readiness diagnosis that turns\n"
            "profile and environment facts into findings, hardware-aware recommendations, and deterministic exports."
        ),
        epilog=(
            "Outcome: a profile-aware readiness report with an exact next export step.\n\n"
            "Next command:\n"
            "  aiplane quickstart local-coding --dry-run\n\n"
            "Command maturity and coverage are documented in docs/project/project-plan.md#command-coverage.\n"
            "Docs: docs/user/index.md"
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show tracebacks for unexpected internal errors; may expose sensitive local context",
    )
    add_version_argument(parser)
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root for path checks, audit logs, benchmarks, and tool execution",
    )
    parser.add_argument(
        "--profiles-dir",
        help="Directory containing editable profiles. Defaults to AIPLANE_PROFILES_DIR when set, otherwise the repo-local profiles/ directory",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    common = {"command_factory": _command, "profile_arg": _profile_arg, "formatter_class": HelpFormatter}

    add_public_parsers(
        subparsers,
        **common,
        integration_selection_args=_integration_selection_args,
        integration_tools=ALL_INTEGRATION_TOOLS,
    )
    add_config_parser(subparsers, command_factory=_command, formatter_class=HelpFormatter)
    add_profiles_parser(subparsers, **common)
    add_execution_parsers(subparsers, **common, launch_tools=LAUNCH_TOOLS, bridge_actions=BRIDGE_ACTIONS)
    add_hardware_machine_parsers(subparsers, **common)
    add_stack_parsers(subparsers, **common)
    add_models_parser(subparsers, **common)
    add_integrations_parser(subparsers, **common, selection_args=_integration_selection_args)
    add_deploy_remote_parsers(subparsers, **common)
    add_runtimes_parser(subparsers, **common)
    add_providers_parser(subparsers, **common)
    add_setup_parsers(subparsers, **common)
    add_governance_parsers(subparsers, **common)
    add_support_parser(subparsers, command_factory=_command, formatter_class=HelpFormatter)
    return parser
