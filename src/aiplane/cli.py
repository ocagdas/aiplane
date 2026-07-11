from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import uuid

from .agents import AgentManager
from .approvals import ApprovalHandler
from .audit import AuditLogger
from .models import AuditEvent
from .benchmark_tools import BenchmarkToolManager
from .code_tasks import CodeTaskRunner
from .config import (
    agent_artifacts_root,
    clear_output_format,
    clear_output_verbosity,
    create_profile,
    default_local_config_path,
    default_profile,
    default_profiles_root,
    get_command_output_format,
    get_command_output_verbosity,
    get_local_config_value,
    get_output_format_override,
    get_output_verbosity_override,
    get_profile_output_format,
    get_profile_output_verbosity,
    init_local_config,
    list_config_templates,
    list_profile_templates,
    list_profiles,
    load_local_config,
    local_config_path,
    load_profile,
    profiles_root,
    remove_profile,
    repair_profile,
    resolve_profile_name,
    resolve_output_format,
    resolve_output_verbosity,
    set_default_profile,
    set_local_config_value,
    set_output_format,
    set_output_verbosity,
)
from .deploy import DeployManager
from .env import EnvironmentManager
from .hardware import HardwareManager
from .cli_integrations import add_integrations_parser, handle_integrations_command
from .cli_models import add_models_parser, handle_models_command, refresh_cli_payload
from .cli_support import (
    parse_provider_limits as _parse_provider_limits,
    parse_setting_value as _parse_setting_value,
    parse_settings as _parse_settings,
    refresh_progress as _refresh_progress,
)
from .integrations import IntegrationManager
from .integration_contracts import ALL_INTEGRATION_TOOLS
from .local_doctor import local_coding_doctor, local_coding_doctor_text
from .machines import MachineManager
from .mcp import mcp_manifest, serve_stdio
from .model_catalog import ModelCatalog
from .orchestrators import OrchestratorCatalog
from .output import json_dumps as _json
from .policy import PolicyEngine
from .providers import (
    ProviderRegistry,
    SUPPORTED_CATALOG_ADAPTERS,
    SUPPORTED_ENDPOINT_FAMILIES,
)
from .remote import RemoteManager
from .secrets import CredentialStore, credentials_path
from .router import Router
from .runtime_catalog import RuntimeCatalog
from .stacks import StackManager
from .tools import ToolExecutor, ToolchainManager


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


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


def _profiles_dir_from_env() -> Path | None:
    test_path = os.environ.get("AIPLANE_TEST_PROFILES_DIR")
    if test_path:
        return Path(test_path).expanduser().resolve()
    env_path = os.environ.get("AIPLANE_PROFILES_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return None


_BRIDGE_ACTIONS: dict[str, dict[str, object]] = {
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

_LAUNCH_TOOLS = ("aider", "continue", "ollama")


def _integration_selection_args(parser) -> None:
    parser.add_argument(
        "--provider",
        help="Constrain model selection to a provider/source, such as ollama or vllm",
    )
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


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aiplane",
        description=(
            "Configure, check, and connect local/cloud AI coding environments.\n\n"
            "aiplane is an environment-doctor and configuration compiler: it manages profiles, providers, models, hardware fit,\n"
            "IDE/CLI exports, remote endpoint plans, and MCP access. It does not replace IDE agents."
        ),
        epilog=(
            "Primary workflow:\n"
            "  aiplane discover\n"
            "  aiplane doctor\n"
            "  aiplane recommend\n"
            "  aiplane export continue\n"
            "  aiplane quickstart local-coding\n\n"
            "Advanced command categories are documented in docs/project/command-coverage.md.\n"
            "Docs: docs/user/index.md"
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root for path checks, audit logs, benchmarks, and tool execution",
    )
    parser.add_argument(
        "--profiles-dir",
        help="Directory containing editable profiles. Defaults to AIPLANE_PROFILES_DIR when set, otherwise the repo-local profiles/ directory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    discover_cmd = _command(
        subparsers,
        "discover",
        "Discover the local AI workflow environment",
        "Read the current profile and detect hardware, runtime/provider configuration, local model aliases, endpoint configuration, and supported coding-tool exports. This command is read-only.",
        "Examples:\n  aiplane discover\n  aiplane discover --format json",
    )
    _profile_arg(discover_cmd)
    discover_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. Text is human-readable; JSON is for scripts.",
    )

    recommend_cmd = _command(
        subparsers,
        "recommend",
        "Recommend models for this machine",
        "Rank local model aliases against the active hardware selection, runtime compatibility, and policy. This command is read-only.",
        "Examples:\n  aiplane recommend\n  aiplane recommend --include-not-recommended\n  aiplane recommend --format json",
    )
    _profile_arg(recommend_cmd)
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

    export_cmd = _command(
        subparsers,
        "export",
        "Export configuration for coding tools",
        "Print configuration for Continue, Aider, Cline, Zed, OpenAI-compatible clients, or MCP clients. This does not edit target tool files.",
        "Examples:\n  aiplane export continue\n  aiplane export aider --model MODEL_ALIAS\n  aiplane export vscode-mcp",
    )
    _profile_arg(export_cmd)
    _integration_selection_args(export_cmd)
    export_cmd.add_argument(
        "--model",
        help="Single model alias to export. For Continue, omit this to export chat/autocomplete/embedding selections",
    )
    export_cmd.add_argument("--from-plan", help="Path to a JSON file produced by integrations plan")
    export_cmd.add_argument("--endpoint", help="Override provider endpoint/base URL")
    export_cmd.add_argument(
        "--api-key-env", help="Environment variable name the target tool should read for an API key"
    )
    export_cmd.add_argument("tool", choices=ALL_INTEGRATION_TOOLS, help="Export format to print")

    doctor_cmd = _command(
        subparsers,
        "doctor",
        "Check the local AI coding stack",
        "Aggregate the local/hybrid AI coding stack readiness checks: profile files, required environment tools, model defaults, provider state, integration roles, and MCP manifest.",
        "Examples:\n  aiplane doctor\n  aiplane doctor --format json\n  aiplane doctor --include-optional",
    )
    _profile_arg(doctor_cmd)
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

    quickstart_cmd = _command(
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
        formatter_class=HelpFormatter,
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
        default=True,
        help="Replace an existing profile directory first; use --no-overwrite to keep an existing profile directory",
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

    config_cmd = _command(
        subparsers,
        "config",
        "Manage ignored local aiplane config",
        "Create and inspect the local .aiplane/config.yaml file used for machine/user-specific defaults.",
        "Examples:\n  aiplane config templates\n  aiplane config init --template local\n  aiplane config show\n  aiplane config default-profile\n  aiplane config default-profile my-local",
    )
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True, metavar="command")
    config_sub.add_parser(
        "templates",
        help="List local config templates",
        description="List checked-in local config templates under config-templates/.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_init = config_sub.add_parser(
        "init",
        help="Create local config from template",
        description="Copy a checked-in config template to .aiplane/config.yaml or AIPLANE_CONFIG. The copied file is ignored by git.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_init.add_argument(
        "--template",
        default="local",
        help="Config template name from aiplane config templates",
    )
    config_init.add_argument(
        "--path",
        help="Optional output path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
    )
    config_init.add_argument("--overwrite", action="store_true", help="Replace an existing local config file")
    config_show = config_sub.add_parser(
        "show",
        help="Show local config",
        description="Show the effective local config file path, parsed settings, and effective defaults. Missing config returns an empty settings object.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_show.add_argument(
        "--path",
        help="Optional config path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
    )
    config_default = config_sub.add_parser(
        "default-profile",
        help="Show or set default profile",
        description="Without NAME, show the effective default profile. With NAME, persist it in local config.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_default.add_argument("name", nargs="?", help="Profile name to persist as the default")
    config_default.add_argument(
        "--path",
        help="Optional config path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
    )
    config_get = config_sub.add_parser(
        "get",
        help="Read one local config value",
        description="Read one top-level key from the ignored local config file.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_get.add_argument("key", help="Top-level config key, such as profiles_dir or default_profile")
    config_get.add_argument(
        "--path",
        help="Optional config path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
    )
    config_set = config_sub.add_parser(
        "set",
        help="Write one local config value",
        description="Set one top-level key in the ignored local config file. Values are parsed as simple booleans, nulls, ints, floats, or strings.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_set.add_argument("key", help="Top-level config key, such as profiles_dir or default_profile")
    config_set.add_argument("value", help="Value to store")
    config_set.add_argument(
        "--path",
        help="Optional config path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
    )
    config_format = config_sub.add_parser(
        "format",
        help="Show or set output format defaults",
        description=(
            "Show effective output format configuration or set per-profile/per-command/default format. "
            "Command-line --format options still win on each command invocation."
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_format.add_argument(
        "value",
        nargs="?",
        choices=["text", "json"],
        help="Output format to persist. Omit to print resolved format values.",
    )
    config_format_scope = config_format.add_mutually_exclusive_group()
    config_format_scope.add_argument(
        "--profile",
        help="Persist/clear format only for this profile instead of the global default format.",
    )
    config_format_scope.add_argument(
        "--command",
        dest="format_command",
        help="Persist/clear format only for this command, for example `models list`.",
    )
    config_format.add_argument(
        "--path",
        help="Optional config path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
    )
    config_format.add_argument(
        "--clear",
        action="store_true",
        help="Clear selected format configuration entry (global/profile/command).",
    )

    config_verbosity = config_sub.add_parser(
        "verbosity",
        help="Show or set output verbosity defaults",
        description=(
            "Show effective output verbosity configuration or set per-profile/per-command/default verbosity. "
            "Command-line --verbosity options still win on each command invocation."
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    config_verbosity.add_argument(
        "value",
        nargs="?",
        type=int,
        choices=[0, 1, 2],
        help="Verbosity to persist. Omit to print resolved verbosity values.",
    )
    config_verbosity_scope = config_verbosity.add_mutually_exclusive_group()
    config_verbosity_scope.add_argument(
        "--profile",
        help="Persist/clear verbosity only for this profile instead of the global default verbosity.",
    )
    config_verbosity_scope.add_argument(
        "--command",
        dest="verbosity_command",
        help="Persist/clear verbosity only for this command, for example `models list`.",
    )
    config_verbosity.add_argument(
        "--path",
        help="Optional path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
    )
    config_verbosity.add_argument(
        "--clear",
        action="store_true",
        help="Clear selected verbosity configuration entry (global/profile/command).",
    )

    profiles = _command(
        subparsers,
        "profiles",
        "List and inspect profile configuration sets",
        (
            "Profiles are named YAML configuration sets under profiles/<name>. "
            "Hardware discovery lives under the hardware command family, and portable machine profiles live under machines."
        ),
        (
            "Examples:\n"
            "  aiplane profiles list\n"
            "  aiplane profiles templates\n"
            "  aiplane profiles create my-local --template local-dev\n"
            "  aiplane profiles remove old-local --dry-run\n"
            "  aiplane profiles show --selected\n"
            "  aiplane hardware discover\n"
            "  aiplane hardware active\n"
            "  aiplane hardware export-machine --name local_box > local_box.machine.yaml\n"
            "  aiplane machines import local_box.machine.yaml"
        ),
    )
    profile_sub = profiles.add_subparsers(dest="profile_command", required=True, metavar="command")
    profile_sub.add_parser(
        "list",
        help="List profile names",
        description="List available editable profile names under profiles/.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    profile_sub.add_parser(
        "templates",
        help="List shipped profile templates",
        description="List checked-in templates that can be copied into profiles/.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    create = profile_sub.add_parser(
        "create",
        help="Create a profile from a template",
        description="Copy a shipped profile template into profiles/<name> so it can be customized without changing the template.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Examples:\n  aiplane profiles create laptop --template local-dev\n  aiplane profiles create cloud-test --template local-dev --overwrite",
    )
    create.add_argument("name", help="New editable profile name to create under profiles/")
    create.add_argument(
        "--template",
        default="local-dev",
        help="Template name from aiplane profiles templates",
    )
    create.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing profile directory with a fresh copy of the template",
    )
    repair = profile_sub.add_parser(
        "repair",
        help="Restore missing profile files from a template",
        description=(
            "Copy missing YAML files from a shipped profile template into an existing editable profile. "
            "Existing local files are preserved unless --overwrite is passed."
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog=(
            "Examples:\n"
            "  aiplane profiles repair local-dev --file models.yaml\n"
            "  aiplane profiles repair local-dev --dry-run\n"
            "  aiplane profiles repair local-dev --template local-dev --overwrite --file models.yaml"
        ),
    )
    repair.add_argument(
        "name",
        nargs="?",
        help="Editable profile name to repair. If omitted, uses the effective default profile",
    )
    repair.add_argument(
        "--template",
        default="local-dev",
        help="Template name from aiplane profiles templates",
    )
    repair.add_argument(
        "--file",
        action="append",
        default=[],
        metavar="FILENAME",
        help="Profile YAML file to restore, such as models.yaml. Repeat to repair multiple files. Defaults to all missing profile files",
    )
    repair.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace selected existing profile files with the template copy",
    )
    repair.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which files would be copied without writing them",
    )
    remove = profile_sub.add_parser(
        "remove",
        help="Remove an editable profile directory",
        description=(
            "Delete profiles/<name> from the editable profiles directory. Without --yes, this only previews "
            "the profile directory that would be removed. Runtime caches, credentials, and model weights are not deleted."
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog=("Examples:\n  aiplane profiles remove old-local --dry-run\n  aiplane profiles remove old-local --yes"),
    )
    remove.add_argument("name", help="Editable profile name to remove")
    remove.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete the editable profile directory",
    )
    remove.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the profile directory that would be deleted",
    )
    bootstrap = profile_sub.add_parser(
        "bootstrap-local",
        help="Create and optionally discover a local-dev profile",
        description=(
            "Create a local editable profile from the shipped template, validate it, and optionally refresh "
            "provider model discovery into ignored models.discovered.yaml."
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog=(
            "Examples:\n"
            "  aiplane profiles bootstrap-local\n"
            "  aiplane profiles bootstrap-local --provider ollama --limit 25\n"
            "  aiplane profiles bootstrap-local --select-closest-hardware\n"
            "  aiplane profiles bootstrap-local --no-discovery\n"
            "  aiplane profiles bootstrap-local --dry-run"
        ),
    )
    bootstrap.add_argument(
        "--name",
        default="local-dev",
        help="Editable profile name to create or refresh; defaults to local-dev",
    )
    bootstrap.add_argument(
        "--template",
        default="local-dev",
        help="Template name from aiplane profiles templates; defaults to local-dev",
    )
    bootstrap.add_argument(
        "--overwrite",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Replace an existing profile directory with a fresh copy of the template before discovery; use --no-overwrite to keep an existing profile directory",
    )
    bootstrap.add_argument(
        "--no-discovery",
        action="store_true",
        help="Create and validate the profile without refreshing provider model discovery",
    )
    bootstrap.add_argument(
        "--no-hardware-discovery",
        action="store_true",
        help="Skip local hardware discovery during bootstrap",
    )
    bootstrap.add_argument(
        "--select-closest-hardware",
        action="store_true",
        help="Set active hardware to the closest discovered template during bootstrap",
    )
    bootstrap.add_argument(
        "--provider",
        default="all",
        help="Model provider to refresh after profile creation, or all for every configured provider",
    )
    bootstrap.add_argument("--query", help="Optional search query passed to provider catalog adapters")
    bootstrap.add_argument(
        "--limit",
        type=int,
        help="Maximum model ids to read per provider catalog during bootstrap discovery; when omitted, uses the models refresh command default",
    )
    bootstrap.add_argument(
        "--provider-limit",
        action="append",
        default=[],
        metavar="PROVIDER=COUNT",
        help="Override --limit for one model provider during bootstrap discovery",
    )
    bootstrap.add_argument(
        "--disable-new",
        action="store_true",
        help="Write newly discovered entries as disabled; by default they are enabled",
    )
    bootstrap.add_argument(
        "--verbosity",
        type=int,
        choices=[0, 1, 2],
        default=0,
        help="Discovery output detail: 0=top-level summary, 1=provider summary, 2=full per-model change rows",
    )
    bootstrap.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview create/discovery actions without writing profile files or discovered model cache",
    )
    show = profile_sub.add_parser(
        "show",
        help="Show profile config",
        description="Print profile config as JSON. Defaults to the effective default profile when NAME is omitted.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    show.add_argument(
        "name",
        nargs="?",
        help="Profile name. If omitted, uses the effective default profile",
    )
    show.add_argument(
        "--selected",
        action="store_true",
        help="Show only selected/default options from each profile block",
    )
    validate = profile_sub.add_parser(
        "validate",
        help="Validate a profile",
        description="Check required profile files and cross-references such as defaults, providers, targets, and environment modes.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    validate.add_argument(
        "name",
        nargs="?",
        help="Profile name. If omitted, uses the effective default profile",
    )

    run = _command(
        subparsers,
        "run",
        "Route a simple task through local/cloud policy",
        "Route a task through the profile policy and backend selection logic.",
        "Examples:\n  aiplane run --dry-run 'summarize repo status'\n  aiplane run --model MODEL_ALIAS 'explain this setup'\n  aiplane run --escalate 'needs cloud reasoning'",
    )
    _profile_arg(run)
    run.add_argument(
        "--model",
        help="Model alias to use. If omitted, aiplane selects an enabled local model, or an enabled non-local model with --escalate",
    )
    run.add_argument(
        "--escalate",
        action="store_true",
        help="Prefer an enabled non-local/cloud model when policy allows it",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selected model and prompt without calling the provider",
    )
    run.add_argument(
        "--ignore-hardware-fit",
        action="store_true",
        help="Allow a local model run even when active hardware minimums are not satisfied",
    )
    run.add_argument("task", help="Prompt/task text to send to the selected model")

    tool = _command(
        subparsers,
        "tool",
        "Run a configured local tool with approval checks",
        "Execute a configured tool through aiplane policy, workspace, and audit checks.",
        "Examples:\n  aiplane tool read_file README.md\n  aiplane tool write_file note.txt hello",
    )
    _profile_arg(tool)
    tool.add_argument("tool_name", help="Configured tool name, such as read_file or write_file")
    tool.add_argument(
        "tool_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the configured tool; captures options such as -m or -s",
    )

    hardware_cmd = _command(
        subparsers,
        "hardware",
        "Inspect hardware and choose resource templates",
        "Discover local CPU/RAM/GPU resources, manage active hardware config, and recommend models.",
        "Examples:\n  aiplane hardware discover\n  aiplane hardware templates\n  aiplane hardware use cpu_laptop --set memory_gb=32\n  aiplane hardware active\n  aiplane hardware recommend",
    )
    hardware_sub = hardware_cmd.add_subparsers(dest="hardware_command", required=True, metavar="command")
    hardware_show = hardware_sub.add_parser(
        "show",
        help="Show hardware summary and effective selection",
        description="Show the active hardware selection and effective machine. Add --list-types to list available template types.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(hardware_show)
    hardware_show.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. JSON is full payload; text is compact table view.",
    )
    hardware_show.add_argument(
        "--verbosity",
        type=int,
        choices=[0],
        default=0,
        help="Output detail level. 0 (default) keeps a short summary without template catalog values.",
    )
    hardware_show.add_argument(
        "--list-types",
        action="store_true",
        help="Show available hardware template types and exit.",
    )
    hardware_templates = hardware_sub.add_parser(
        "templates",
        help="List immutable hardware templates",
        description="Show hardware templates that can be copied into the active selected config.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(hardware_templates)
    hardware_schema = hardware_sub.add_parser(
        "schema",
        help="Show machine property schema",
        description="Show the editable machine fields used for hardware-aware recommendation: stock tag/SKU, CPU, RAM, GPU, VRAM, accelerator APIs, OS, placement, and substrate.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware schema",
    )
    _profile_arg(hardware_schema)
    hardware_active = hardware_sub.add_parser(
        "active",
        help="Show selected hardware config",
        description="Show the active copied/customized hardware config and template origin.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(hardware_active)
    hardware_use = hardware_sub.add_parser(
        "use",
        help="Copy a template into active hardware config",
        description="Select a hardware template by copying it into the mutable active config. Overrides do not modify the template.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware use nvidia_consumer_gpu --set vram_gb=16 --set memory_gb=64",
    )
    _profile_arg(hardware_use)
    hardware_use.add_argument("template", help="Template name from aiplane hardware templates")
    hardware_use.add_argument(
        "--set",
        dest="settings",
        action="append",
        default=[],
        help="Override a copied value as key=value; can be repeated",
    )
    hardware_set = hardware_sub.add_parser(
        "set",
        help="Customize active hardware config",
        description="Update values in the active selected hardware config without changing the source template.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware set memory_gb=64 vram_gb=24",
    )
    _profile_arg(hardware_set)
    hardware_set.add_argument(
        "settings",
        nargs="+",
        help="One or more key=value updates, such as memory_gb=64 vram_gb=24",
    )
    hardware_discover = hardware_sub.add_parser(
        "discover",
        help="Probe local CPU/RAM/GPU resources",
        description="Discover local hardware and show closest matching hardware templates. Optionally select the closest template.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(hardware_discover)
    hardware_discover.add_argument(
        "--select-closest",
        action="store_true",
        help="Update active hardware selection to the closest discovered template",
    )
    hardware_discover.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the closest-template selection without writing hardware.yaml",
    )
    hardware_clear = hardware_sub.add_parser(
        "clear",
        help="Reset selected hardware to local_auto",
        description="Clear the mutable selected hardware state and reset the profile to local_auto. Raw discovery is not cached.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(hardware_clear)
    hardware_clear.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the reset without writing hardware.yaml",
    )
    hardware_doctor = hardware_sub.add_parser(
        "doctor",
        help="Check hardware/model fit",
        description="Check whether configured local models fit the discovered or selected hardware.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(hardware_doctor)
    hardware_doctor.add_argument(
        "--model",
        help="Optional model alias to check, such as a discovered or promoted alias",
    )
    hardware_recommend = hardware_sub.add_parser(
        "recommend",
        help="Recommend models for active/discovered hardware",
        description="Return hardware- and policy-aware model recommendations using hardware fit, runtime compatibility, and ranking rationale.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(hardware_recommend)
    hardware_recommend.add_argument(
        "--include-not-recommended",
        action="store_true",
        help="Also show models below minimum local RAM/VRAM targets",
    )
    hardware_export = hardware_sub.add_parser(
        "export-machine",
        help="Export this machine profile",
        description="Probe this machine and print a normalized machine profile that can be imported on another control PC.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware export-machine --name gpu_box_01 > gpu_box_01.machine.yaml",
    )
    _profile_arg(hardware_export)
    hardware_export.add_argument(
        "--name",
        required=True,
        help="Machine name/label to embed in the exported profile",
    )
    hardware_export.add_argument(
        "--origin",
        default="local",
        help="Origin label, such as local, onprem, azure_vm, ssh_discovered, or manual",
    )
    hardware_export.add_argument("--format", choices=["json", "yaml"], default="yaml", help="Export format")
    hardware_export.add_argument(
        "--include-discovery",
        action="store_true",
        help="Include raw discovery details in the export",
    )

    machines_cmd = _command(
        subparsers,
        "machines",
        "Manage self-managed machine inventory",
        "Import, list, recommend, and discover self-managed machines that can run local runtimes on local PCs, shared workstations, or cloud VMs.",
        "Examples:\n  aiplane machines import gpu_box_01.machine.yaml\n  aiplane machines list\n  aiplane machines recommend --model MODEL_ALIAS --runtime vllm\n  aiplane machines discover azure --region uksouth --workload inference_large --gpu-vendor nvidia --min-vram-gb 48",
    )
    machines_sub = machines_cmd.add_subparsers(dest="machines_command", required=True, metavar="command")
    machines_list = machines_sub.add_parser(
        "list",
        help="List imported machines",
        description="List self-managed machines registered in the profile hardware inventory.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_list)
    machines_show = machines_sub.add_parser(
        "show",
        help="Show one imported machine",
        description="Show one machine profile from the self-managed inventory.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_show)
    machines_show.add_argument("name", help="Machine name")
    machines_validate = machines_sub.add_parser(
        "validate",
        help="Validate imported machine profiles",
        description="Validate required machine profile fields for one machine or all imported machines.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_validate)
    machines_validate.add_argument("name", nargs="?", help="Optional machine name")
    machines_cache_list = machines_sub.add_parser(
        "cache-list",
        help="List machine discovery cache entries",
        description="Inspect cached discovery results, including whether each entry came from live provider data or offline hints.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_cache_list)
    machines_cache_clear = machines_sub.add_parser(
        "cache-clear",
        help="Clear machine discovery cache",
        description="Clear all cached machine discovery results, or one cache key.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_cache_clear)
    machines_cache_clear.add_argument("--key", help="Specific cache key to clear")
    machines_azure_status = machines_sub.add_parser(
        "azure-status",
        help="Check Azure CLI login/query status",
        description="Report whether az is installed, az account show works, and optionally whether VM SKU query works for a region.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_azure_status)
    machines_azure_status.add_argument("--region", help="Region for optional SKU query probe, such as uksouth")
    machines_azure_status.add_argument(
        "--sku-query",
        action="store_true",
        help="Also run az vm list-skus as a live query probe",
    )
    machines_azure_status.add_argument(
        "--verbosity",
        type=int,
        default=0,
        choices=[0, 1],
        help="Azure CLI progress verbosity: 0 shows active command with dot progress, 1 also logs every command and redacted outputs",
    )
    machines_import = machines_sub.add_parser(
        "import",
        help="Import exported machine profile",
        description="Import a machine profile created by aiplane hardware export-machine. Overrides are applied to the imported copy only.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_import)
    machines_import.add_argument("path", help="Path to .machine.yaml or JSON export")
    machines_import.add_argument("--name", help="Override imported machine name")
    machines_import.add_argument(
        "--set",
        dest="settings",
        action="append",
        default=[],
        help="Override a machine field as key=value, such as memory_gb=128 or vram_gb=48; can be repeated",
    )
    machines_recommend = machines_sub.add_parser(
        "recommend",
        help="Recommend machines for model/runtime/workload",
        description="Rank imported machines against a model, runtime, or workload class.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_recommend)
    machines_recommend.add_argument("--model", help="Configured model alias, such as a discovered or promoted alias")
    machines_recommend.add_argument("--runtime", help="Runtime name, such as ollama, vllm, llamacpp, or tgi")
    machines_recommend.add_argument(
        "--workload",
        help="Workload class, such as inference_large, training_finetune, compile_build, or media_generation",
    )
    machines_recommend.add_argument("--limit", type=int, help="Maximum machines to return")
    machines_discover = machines_sub.add_parser(
        "discover",
        help="Discover machine candidates from a provider",
        description="Discover machine candidates from a provider catalog. Azure is the first supported provider.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_discover)
    machines_discover.add_argument("provider", choices=["azure"], help="Machine provider to discover")
    machines_discover.add_argument("--region", required=True, help="Provider region, such as uksouth")
    machines_discover.add_argument("--workload", help="Workload class filter")
    machines_discover.add_argument("--model", help="Configured model alias filter")
    machines_discover.add_argument("--gpu-vendor", help="GPU vendor filter, such as nvidia, amd, intel, apple, or none")
    machines_discover.add_argument("--min-cpu-cores", type=float, help="Minimum CPU cores filter")
    machines_discover.add_argument("--min-ram-gb", type=float, help="Minimum RAM (GB) filter")
    machines_discover.add_argument("--min-vram-gb", type=float, help="Minimum VRAM (GB) filter")
    machines_discover.add_argument("--limit", type=int, default=20, help="Maximum candidates to return")
    machines_discover.add_argument(
        "--verbosity",
        type=int,
        default=0,
        choices=[0, 1],
        help="Azure CLI progress verbosity: 0 shows active command with dot progress, 1 also logs every command and redacted outputs",
    )
    machines_import_azure = machines_sub.add_parser(
        "import-azure-sku",
        help="Import an Azure SKU as a machine",
        description="Create a self-managed machine entry from an Azure VM SKU hint. Verify exact quota/availability before provisioning.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_import_azure)
    machines_import_azure.add_argument("sku", help="Azure VM SKU, such as Standard_NC40ads_H100_v5")
    machines_import_azure.add_argument("--region", required=True, help="Azure region")
    machines_import_azure.add_argument("--name", help="Machine name to create")
    machines_import_azure.add_argument(
        "--set",
        dest="settings",
        action="append",
        default=[],
        help="Override a machine field as key=value",
    )
    machines_profile_remote = machines_sub.add_parser(
        "profile-remote-plan",
        help="Plan remote profiling over SSH",
        description="Render the commands needed to run aiplane on a remote self-managed machine and import the result locally.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(machines_profile_remote)
    machines_profile_remote.add_argument("--name", required=True, help="Machine name to assign to the remote export")
    machines_profile_remote.add_argument("--host", required=True, help="Remote hostname or IP")
    machines_profile_remote.add_argument("--user", help="SSH username")
    machines_profile_remote.add_argument("--port", type=int, default=22, help="SSH port")

    orchestrators_cmd = _command(
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Examples:\n  aiplane orchestrators list\n  aiplane orchestrators list --provider ollama\n  aiplane orchestrators list --runtime ollama --runtime vllm\n  aiplane orchestrators list --group-by provider",
    )
    _profile_arg(orchestrators_list)
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(orchestrators_show)
    orchestrators_show.add_argument(
        "name",
        help="Orchestrator name, such as langgraph, crewai, autogen, or openhands",
    )
    orchestrators_setup = orchestrators_sub.add_parser(
        "setup",
        help="Configure one orchestrator",
        description="Write profile-specific orchestrator settings to orchestrators.yaml. Use --dry-run to preview without writing or installing.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Examples:\n  aiplane orchestrators setup langgraph --runtime ollama --model MODEL_ALIAS --dry-run\n  aiplane orchestrators setup langgraph --runtime ollama --model MODEL_ALIAS --approval-mode ask\n  aiplane orchestrators setup langgraph --runtime vllm --model MODEL_ALIAS --endpoint http://localhost:8000/v1 --limit timeout=30m --tool shell=guarded",
    )
    _profile_arg(orchestrators_setup)
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(orchestrators_doctor)
    orchestrators_doctor.add_argument("name", help="Orchestrator name")

    stacks_cmd = _command(
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_list)
    stacks_show = stacks_sub.add_parser(
        "show",
        help="Show one stack",
        description="Show one stack definition.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_show)
    stacks_show.add_argument("name", help="Stack name")
    stacks_setup = stacks_sub.add_parser(
        "setup",
        help="Write or preview a stack",
        description="Persist an orchestrator + runtime + model + machine + access binding in hardware.yaml. Use --dry-run to preview without writing.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_setup)
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_plan)
    stacks_plan.add_argument("name", help="Stack name")
    stacks_doctor = stacks_sub.add_parser(
        "doctor",
        help="Check a stack",
        description="Check machine fit, runtime availability, preflight checks, role endpoint bindings, and risky role tool-policy combinations for a stack.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_doctor)
    stacks_doctor.add_argument("name", help="Stack name")
    stacks_endpoint_plan = stacks_sub.add_parser(
        "endpoint-plan",
        help="Plan endpoint auth and gateway controls",
        description="Render a non-mutating endpoint security plan for a stack, including TLS, auth, gateway, and private/shared exposure checks.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_endpoint_plan)
    stacks_endpoint_plan.add_argument("name", help="Stack name")
    stacks_export = stacks_sub.add_parser(
        "export",
        help="Export stack artifacts",
        description="Export IDE config or packaging artifacts for a stack endpoint.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_export)
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
            formatter_class=HelpFormatter,
            allow_abbrev=False,
        )
        _profile_arg(lifecycle)
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(stacks_status)
    stacks_status.add_argument("name", help="Stack name")
    environment = _command(
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(env_show)
    env_list = env_sub.add_parser(
        "list",
        help="List available environment modes",
        description="List configured environment modes and mark the active one.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(env_list)
    env_active = env_sub.add_parser(
        "active",
        help="Show active environment mode",
        description="Show only the active environment mode, its config, and available modes.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(env_active)
    env_use = env_sub.add_parser(
        "use",
        help="Set active environment mode",
        description="Persist a new active environment mode in the profile environment.yaml file.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
        epilog="Examples:\n  aiplane environment use system\n  aiplane environment use venv\n  aiplane environment use conda\n  aiplane environment use docker",
    )
    _profile_arg(env_use)
    env_use.add_argument("mode", help="Configured mode name, such as system, venv, conda, or docker")
    env_plan = env_sub.add_parser(
        "plan",
        help="Render command execution plan",
        description="Show the command aiplane would run under the active environment mode.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(env_plan)
    env_plan.add_argument(
        "env_command_args",
        nargs=argparse.REMAINDER,
        help="Command to plan after the command name, for example python -m unittest",
    )
    env_doctor = env_sub.add_parser(
        "doctor",
        help="Check environment and prerequisite tool readiness",
        description="Check the active aiplane execution environment plus external CLIs/frameworks used by runtime, cloud, benchmark, container, Kubernetes, and SSH workflows.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(env_doctor)
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

    benchmarks_cmd = _command(
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(benchmarks_list)
    benchmarks_doctor = benchmarks_sub.add_parser(
        "doctor",
        help="Check benchmark framework availability",
        description="Check which benchmark frameworks are available and which need install/manual setup.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(benchmarks_doctor)
    benchmarks_doctor.add_argument(
        "name",
        nargs="?",
        help="Optional framework name, such as aiplane-smoke, lm-evaluation-harness, vllm-serving, or locust-load",
    )
    benchmarks_install = benchmarks_sub.add_parser(
        "install",
        help="Plan or run benchmark framework install",
        description="Install optional benchmark tools where aiplane has a safe helper command. Use --dry-run first.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(benchmarks_install)
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
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    _profile_arg(benchmarks_plan)
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

    add_models_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )

    code_cmd = _command(
        subparsers,
        "code",
        "Run simple code analysis/completion/write prompts",
        "Use a configured model for small code tasks. Use --dry-run to inspect prompts before calling a runtime.",
        "Examples:\n  aiplane code analyze --model MODEL_ALIAS src/aiplane/cli.py --dry-run\n  aiplane code complete --model MODEL_ALIAS --line 20 src/app.py\n  aiplane code write --model MODEL_ALIAS --task 'add email validation' --dry-run",
    )
    code_sub = code_cmd.add_subparsers(dest="code_command", required=True, metavar="command")
    code_analyze = code_sub.add_parser(
        "analyze",
        help="Analyze a code file",
        description="Ask a model to explain a file, identify risk, and suggest an improvement.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(code_analyze)
    code_analyze.add_argument("--model", required=True, help="Model alias to use")
    code_analyze.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling the provider",
    )
    code_analyze.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider request timeout for this code task",
    )
    code_analyze.add_argument("target", help="File path inside the workspace")
    code_complete = code_sub.add_parser(
        "complete",
        help="Complete code at a line",
        description="Build a completion prompt using file context around the selected line.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(code_complete)
    code_complete.add_argument("--model", required=True, help="Model alias to use")
    code_complete.add_argument("--line", type=int, required=True, help="1-based cursor line number")
    code_complete.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling the provider",
    )
    code_complete.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider request timeout for this code task",
    )
    code_complete.add_argument("target", help="File path inside the workspace")
    code_write = code_sub.add_parser(
        "write",
        help="Generate a small code snippet",
        description="Ask a model to write code for a short task description.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(code_write)
    code_write.add_argument("--model", required=True, help="Model alias to use")
    code_write.add_argument("--task", required=True, help="Code-writing task description")
    code_write.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling the provider",
    )
    code_write.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider request timeout for this code task",
    )

    add_integrations_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        selection_args=_integration_selection_args,
        formatter_class=HelpFormatter,
    )

    agents_cmd = _command(
        subparsers,
        "agents",
        "Plan and export starter agent applications",
        "Create non-mutating plans and scaffold files for small agent applications that use configured aiplane model endpoints.",
        "Examples:\n  aiplane agents templates\n  aiplane agents plan repo-helper --framework langgraph --model MODEL_ALIAS\n  aiplane agents export repo-helper --framework langgraph --model MODEL_ALIAS --file agent.py",
    )
    agents_sub = agents_cmd.add_subparsers(dest="agents_command", required=True, metavar="command")
    agents_templates = agents_sub.add_parser(
        "templates",
        help="List starter agent frameworks",
        description="List agent application scaffold templates supported by aiplane.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(agents_templates)
    agents_plan = agents_sub.add_parser(
        "plan",
        help="Plan an agent application scaffold",
        description="Select a model endpoint and show the files/packages for an agent application scaffold. This does not write files or run the agent.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(agents_plan)
    agents_plan.add_argument("name", help="Agent application name, such as repo-helper")
    agents_plan.add_argument(
        "--framework",
        choices=["langgraph", "simple-openai"],
        default="langgraph",
        help="Agent scaffold framework",
    )
    agents_plan.add_argument(
        "--model",
        help="Model alias to use; if omitted, aiplane selects the best enabled chat model",
    )
    agents_plan.add_argument("--runtime", help="Runtime constraint, such as ollama or vllm")
    agents_plan.add_argument("--provider", help="Provider/source constraint, such as openai or ollama")
    agents_plan.add_argument("--endpoint", help="Endpoint/base URL override")
    agents_plan.add_argument("--api-key-env", help="API-key environment variable override")
    agents_plan.add_argument("--instruction", help="System instruction embedded in the scaffold")
    agents_plan.add_argument(
        "--output-dir",
        help="Agent artifact root. Defaults to AIPLANE_AGENT_ARTIFACTS_DIR, local config agent_artifacts_dir, or .aiplane/agents",
    )
    agents_export = agents_sub.add_parser(
        "export",
        help="Print one starter agent file",
        description="Print one scaffold file for an agent application. Output is not written automatically.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(agents_export)
    agents_export.add_argument("name", help="Agent application name, such as repo-helper")
    agents_export.add_argument(
        "--framework",
        choices=["langgraph", "simple-openai"],
        default="langgraph",
        help="Agent scaffold framework",
    )
    agents_export.add_argument(
        "--model",
        help="Model alias to use; if omitted, aiplane selects the best enabled chat model",
    )
    agents_export.add_argument("--runtime", help="Runtime constraint, such as ollama or vllm")
    agents_export.add_argument("--provider", help="Provider/source constraint, such as openai or ollama")
    agents_export.add_argument("--endpoint", help="Endpoint/base URL override")
    agents_export.add_argument("--api-key-env", help="API-key environment variable override")
    agents_export.add_argument("--instruction", help="System instruction embedded in the scaffold")
    agents_export.add_argument(
        "--output-dir",
        help="Agent artifact root. Defaults to AIPLANE_AGENT_ARTIFACTS_DIR, local config agent_artifacts_dir, or .aiplane/agents",
    )
    agents_export.add_argument(
        "--file",
        choices=["agent.py", "requirements.txt", ".env.example", "README.md"],
        default="agent.py",
        help="Scaffold file to print",
    )

    chat_cmd = _command(
        subparsers,
        "chat",
        "Run endpoint-backed chat for a model",
        "Resolve a chat-capable model alias and send prompts through its configured runtime/provider endpoint.",
        "Examples:\n  aiplane chat --model MODEL_ALIAS --prompt 'Say hello'\n  echo 'Say hello' | aiplane chat --model MODEL_ALIAS --stdin\n  aiplane chat --model MODEL_ALIAS --native-ollama",
    )
    _profile_arg(chat_cmd)
    chat_cmd.add_argument(
        "--model",
        help="Model alias to launch. If omitted, uses the profile chat_model default",
    )
    chat_cmd.add_argument(
        "--prompt",
        help="Prompt to send through the configured chat endpoint",
    )
    chat_cmd.add_argument(
        "--stdin",
        action="store_true",
        help="Read the chat prompt from standard input",
    )
    chat_cmd.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider/runtime request timeout for endpoint chat",
    )
    chat_cmd.add_argument(
        "--native-ollama",
        action="store_true",
        help="Use Ollama's native `ollama run` CLI instead of endpoint-backed chat; only works for Ollama-runnable aliases",
    )
    chat_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the endpoint chat plan, or the native Ollama command when --native-ollama is used",
    )

    bridge_cmd = _command(
        subparsers,
        "bridge",
        "Run allowlisted external runtime commands",
        "Run selected allowlisted runtime CLI commands without exposing arbitrary shell passthrough.",
        "Examples:\n  aiplane bridge list\n  aiplane bridge exec ollama-launch --dry-run\n  aiplane bridge exec ollama-run --model llama3.1:8b --prompt 'Say hello'",
    )
    bridge_sub = bridge_cmd.add_subparsers(dest="bridge_command", required=True, metavar="command")
    bridge_sub.add_parser(
        "list",
        help="List allowlisted bridge actions",
        description="List shorthand actions that aiplane can delegate to external runtime CLIs.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    bridge_exec = bridge_sub.add_parser(
        "exec",
        help="Execute one allowlisted bridge action",
        description="Run one allowlisted external command by shorthand action.",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    bridge_exec.add_argument("action", choices=sorted(_BRIDGE_ACTIONS), help="Bridge action shorthand")
    bridge_exec.add_argument("--model", help="Model id/alias for actions that require a model")
    bridge_exec.add_argument("--prompt", help="Prompt text for actions that support prompts")
    bridge_exec.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved external command without executing it",
    )

    launch_cmd = _command(
        subparsers,
        "launch",
        "Launch a configured assistant tool",
        "Launch a configured assistant tool with profile-driven model selection.",
        "Examples:\n  aiplane launch --tool aider --model fixture-chat-small\n  aiplane launch --tool ollama --app vscode\n  aiplane launch --tool continue --model fixture-chat-small --dry-run",
    )
    launch_cmd.add_argument(
        "--tool",
        choices=sorted(_LAUNCH_TOOLS),
        required=True,
        help="Target assistant/tool wrapper to launch",
    )
    _profile_arg(launch_cmd)
    launch_cmd.add_argument(
        "--model",
        help="Model alias to apply when building launch arguments and endpoint metadata. If omitted, defaults to chat_model.",
    )
    launch_cmd.add_argument(
        "--app",
        help="Target application name for `aiplane launch --tool ollama`",
    )
    launch_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the launch plan without starting any process",
    )

    session_cmd = _command(
        subparsers,
        "session",
        "Track a minimal model session",
        "Create thin, local session metadata for model-facing tooling without implementing a custom chat UI.",
        "Examples:\n  aiplane session start --tool aider --model fixture-chat-small\n  aiplane session start --tool ollama --app vscode --transcript /tmp/session.log\n  aiplane session start --tool continue --model fixture-chat-small --dry-run",
    )
    session_sub = session_cmd.add_subparsers(dest="session_command", required=True, metavar="command")
    session_start = session_sub.add_parser(
        "start",
        help="Start a minimal session metadata record",
        description="Start a minimal session metadata record (model, command, transcript path, audit metadata).",
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    session_start.add_argument(
        "--tool",
        choices=sorted(_LAUNCH_TOOLS),
        required=True,
        help="Tool name to launch from aiplane session metadata.",
    )
    _profile_arg(session_start)
    session_start.add_argument(
        "--model",
        help="Model alias to apply. If omitted, defaults to chat_model.",
    )
    session_start.add_argument(
        "--app",
        help="Target application name for `aiplane session start --tool ollama`.",
    )
    session_start.add_argument(
        "--transcript",
        help="Optional transcript file path. Defaults to .aiplane/sessions/<session-id>.log under workspace.",
    )
    session_start.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the session metadata without writing it or emitting an audit event.",
    )
    deploy_cmd = _command(
        subparsers,
        "deploy",
        "Plan/check/apply remote deployment targets",
        "Work with configured cloud/shared deployment targets. Apply is guarded and intentionally narrow.",
        "Examples:\n  aiplane deploy list\n  aiplane deploy workflow-plan --target azure_gpu_vm\n  aiplane deploy plan --target aks_gpu_pool\n  aiplane deploy doctor --target aks_gpu_pool\n  aiplane deploy apply --target aks_gpu_pool --yes",
    )
    deploy_sub = deploy_cmd.add_subparsers(dest="deploy_command", required=True, metavar="command")
    deploy_list = deploy_sub.add_parser(
        "list",
        help="List deployment targets",
        description="List targets from profiles/<profile>/targets.yaml.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(deploy_list)
    deploy_show = deploy_sub.add_parser(
        "show",
        help="Show one deployment target",
        description="Show one target config; uses profile default when --target is omitted.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(deploy_show)
    deploy_show.add_argument("--target", help="Target name, such as aks_gpu_pool")
    deploy_workflow = deploy_sub.add_parser(
        "workflow-plan",
        help="Classify a deployment workflow",
        description="Show whether a target is local install, local VM, remote workstation/VM, cloud VM, or Kubernetes/cloud provisioning, and which external tools own each phase.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(deploy_workflow)
    deploy_workflow.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_plan = deploy_sub.add_parser(
        "plan",
        help="Render deployment plan",
        description="Show required tools and commands for a target without applying changes.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(deploy_plan)
    deploy_plan.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_doctor = deploy_sub.add_parser(
        "doctor",
        help="Check target prerequisites",
        description="Check local tools and target prerequisites where implemented.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(deploy_doctor)
    deploy_doctor.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_apply = deploy_sub.add_parser(
        "apply",
        help="Apply guarded bootstrap steps",
        description="Run narrow, planned bootstrap steps for the selected target. Use deploy plan first to preview commands.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(deploy_apply)
    deploy_apply.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_apply.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that mutating target bootstrap commands should run",
    )

    remote_cmd = _command(
        subparsers,
        "remote",
        "Plan remote access commands",
        "Render remote access commands such as SSH local port forwards for shared/cloud endpoints.",
        "Example:\n  aiplane remote tunnel plan --target gpu_workstation_ssh",
    )
    remote_sub = remote_cmd.add_subparsers(dest="remote_command", required=True, metavar="command")
    remote_tunnel = remote_sub.add_parser(
        "tunnel",
        help="SSH tunnel planning",
        description="Work with SSH tunnel targets.",
        formatter_class=HelpFormatter,
    )
    tunnel_sub = remote_tunnel.add_subparsers(dest="tunnel_command", required=True, metavar="command")
    tunnel_plan = tunnel_sub.add_parser(
        "plan",
        help="Render ssh -L command",
        description="Render an SSH local-forward command and endpoint URL. It does not start the tunnel.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tunnel_plan)
    tunnel_plan.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")
    tunnel_status = tunnel_sub.add_parser(
        "status",
        help="Show tunnel process status",
        description="Show whether a helper-started SSH tunnel is running and which endpoint to use.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tunnel_status)
    tunnel_status.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")
    tunnel_start = tunnel_sub.add_parser(
        "start",
        help="Start an SSH tunnel",
        description="Start the configured ssh -L tunnel in the background and write PID/log files under .aiplane/remote.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tunnel_start)
    tunnel_start.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")
    tunnel_stop = tunnel_sub.add_parser(
        "stop",
        help="Stop a helper-started SSH tunnel",
        description="Stop a tunnel process previously started by this CLI.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tunnel_stop)
    tunnel_stop.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")

    providers_cmd = _command(
        subparsers,
        "providers",
        "List and inspect model catalog providers",
        "Providers are source catalogs such as Ollama library, Hugging Face, GGUF repositories, or local files. Runtimes are handled by aiplane runtimes.",
        "Examples:\n  aiplane providers list\n  aiplane providers list --status disabled\n  aiplane providers list --runtime ollama\n  aiplane providers list --runtime vllm --group-by runtime\n  aiplane providers list --group-by ownership\n  aiplane providers show ollama\n  aiplane providers models ollama",
    )
    providers_sub = providers_cmd.add_subparsers(dest="providers_command", required=True, metavar="command")
    providers_list = providers_sub.add_parser(
        "list",
        help="List model catalog providers",
        description="List model providers that supply downloadable model identifiers or artifacts. Runtimes such as vLLM, TGI, llama.cpp, and Transformers are listed under aiplane runtimes.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane providers list\n  aiplane providers list --status enabled\n  aiplane providers list --status disabled\n  aiplane providers list --runtime ollama\n  aiplane providers list --runtime vllm --group-by runtime\n  aiplane providers list --group-by ownership",
    )
    _profile_arg(providers_list)
    providers_list.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="Only show catalog providers whose models are typically served by this runtime; can be repeated",
    )
    providers_list.add_argument(
        "--status",
        choices=["enabled", "disabled", "all"],
        default="all",
        help="Filter providers by enabled state. Defaults to all providers.",
    )
    providers_list.add_argument(
        "--group-by",
        choices=["runtime", "ownership"],
        help="Group catalog providers by typical runtime or ownership",
    )
    providers_show = providers_sub.add_parser(
        "show",
        help="Show one catalog provider",
        description="Show model provider metadata and configured model aliases from that source.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_show)
    providers_show.add_argument("name", help="Provider name, such as ollama, huggingface, or huggingface_gguf")
    providers_endpoint_types = providers_sub.add_parser(
        "endpoint-types",
        help="List supported provider API families and catalog adapters",
        description="List the provider API families and catalog discovery adapters that user-added providers can declare. New API shapes require a code update before they can be used safely.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  aiplane providers endpoint-types\n"
            "  aiplane providers add my_gateway --ownership managed_service --endpoint-family custom_openai_compatible --catalog-adapter openai --auth-method bearer --api-key-env MY_GATEWAY_API_KEY"
        ),
    )
    _profile_arg(providers_endpoint_types)
    providers_models = providers_sub.add_parser(
        "models",
        help="List catalog provider models",
        description="List known model ids for a model provider. With --online, query supported catalog adapters such as Ollama, Hugging Face, OpenAI-compatible /v1/models, Azure OpenAI deployments, and ElevenLabs voices.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_models)
    providers_models.add_argument("name", help="Catalog provider name to query")
    providers_models.add_argument(
        "--online",
        action="store_true",
        help="Query the provider's online catalog API when aiplane has an adapter for it",
    )
    providers_models.add_argument("--query", help="Optional search query for online/catalog model lookup")
    providers_models.add_argument("--limit", type=int, default=500, help="Maximum model ids to return")
    providers_enable = providers_sub.add_parser(
        "enable",
        help="Enable a model provider",
        description="Enable a model provider in this profile. Disabled providers are skipped by refresh/list unless explicitly included.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_enable)
    providers_enable.add_argument("name", help="Provider name, or all")
    providers_disable = providers_sub.add_parser(
        "disable",
        help="Disable a model provider",
        description="Disable a model provider in this profile without removing model aliases.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_disable)
    providers_disable.add_argument("name", help="Provider name, or all")
    providers_remove = providers_sub.add_parser(
        "remove",
        help="Hide/remove a model provider",
        description="Mark a model provider as removed in this profile. Existing model aliases are not deleted; use models clear-cache for aliases.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_remove)
    providers_remove.add_argument("name", help="Provider name to hide/remove from provider discovery")
    providers_add = providers_sub.add_parser(
        "add",
        help="Add a profile model provider",
        description="Add a user-defined model provider to model-providers.user.yaml. This does not edit the shipped defaults file.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_add)
    providers_add.add_argument("name", help="Provider name to add")
    providers_add.add_argument("--description", default="", help="Human-readable provider description")
    providers_add.add_argument(
        "--ownership",
        choices=["self_managed", "managed_service"],
        help="Provider ownership. Defaults to managed_service when --endpoint-family is used, otherwise self_managed.",
    )
    providers_add.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="Self-managed compatible runtime; can be repeated. Do not use for managed-service providers.",
    )
    providers_add.add_argument(
        "--endpoint-family",
        choices=sorted(SUPPORTED_ENDPOINT_FAMILIES),
        help="Managed-service endpoint/API family. If the provider does not match one of these, aiplane needs a code update.",
    )
    providers_add.add_argument(
        "--catalog-adapter",
        choices=sorted(SUPPORTED_CATALOG_ADAPTERS),
        default="profile_catalog",
        help="Catalog discovery adapter/API shape to reuse. Use profile_catalog when the catalog is manually curated.",
    )
    providers_add.add_argument("--endpoint", help="Default endpoint URL for this provider, when applicable")
    providers_add.add_argument("--credential-ref", help="Default credential ref, such as openai.personal")
    providers_add.add_argument("--api-key-env", help="Environment variable that provides the API key/token")
    providers_add.add_argument(
        "--auth-method",
        choices=["none", "api_key", "bearer", "oauth2", "custom"],
        default="none",
        help="Authentication style required by the provider/catalog API",
    )
    providers_add.add_argument(
        "--requires-credentials",
        action="store_true",
        help="Mark this provider/catalog as requiring credentials even if the auth method is custom or configured elsewhere",
    )
    providers_add.add_argument("--disabled", action="store_true", help="Add the provider disabled")
    providers_init = providers_sub.add_parser(
        "init-defaults",
        help="Write built-in provider defaults",
        description="Dump aiplane's hardcoded model-provider defaults into model-providers.yaml for this profile. Use --overwrite to reinitialize an existing defaults file.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_init)
    providers_init.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing model-providers.yaml file",
    )
    providers_update = providers_sub.add_parser(
        "update-defaults",
        help="Refresh profile provider defaults from this aiplane version",
        description="Update model-providers.yaml from built-in defaults while preserving existing enabled/disabled values and leaving model-providers.user.yaml untouched.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_update)
    providers_clear = providers_sub.add_parser(
        "clear",
        help="Clear provider config files",
        description="Clear provider configuration. embedded/all writes an empty model-providers.yaml marker so hardcoded defaults do not silently reappear.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_clear)
    providers_clear.add_argument(
        "--scope",
        choices=["embedded", "user", "all"],
        default="all",
        help="Which provider config to clear. embedded clears model-providers.yaml, user clears model-providers.user.yaml, and all clears both. Bare providers clear defaults to all.",
    )
    providers_doctor = providers_sub.add_parser(
        "doctor",
        help="Check catalog-provider model readiness",
        description="Check configured model aliases from one model provider, or all aliases when omitted.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(providers_doctor)
    providers_doctor.add_argument(
        "name",
        nargs="?",
        help="Optional model provider name to filter readiness checks",
    )
    providers_test = providers_sub.add_parser(
        "test",
        help="Test a managed provider endpoint credential",
        description="Make a small provider-specific API call to verify endpoint and credential configuration. Secrets are never printed.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane providers test openai\n  aiplane providers test azure_openai --credential-ref azure_openai.personal\n  aiplane providers test elevenlabs",
    )
    _profile_arg(providers_test)
    providers_test.add_argument(
        "name",
        help="Provider name, such as openai, azure_openai, elevenlabs, or a custom OpenAI-compatible provider",
    )
    providers_test.add_argument(
        "--credential-ref",
        help="Override the provider credential_ref, such as azure_openai.personal",
    )
    providers_test.add_argument("--timeout", type=int, help="HTTP timeout in seconds")

    runtimes_cmd = _command(
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
        formatter_class=HelpFormatter,
    )
    _profile_arg(runtimes_map)
    runtimes_map.add_argument(
        "--include-gui",
        action="store_true",
        help="Include GUI-managed runtimes such as LM Studio",
    )
    runtimes_list = runtimes_sub.add_parser(
        "list",
        help="List known runtimes",
        description="List configured and known runtimes, omitting GUI-managed runtimes unless --include-gui is used.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(runtimes_list)
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
        formatter_class=HelpFormatter,
    )
    _profile_arg(runtimes_sources)
    runtimes_models = runtimes_sub.add_parser(
        "models",
        help="Group configured models by runtime",
        description="Show models grouped by runtime, or only models for one runtime.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(runtimes_models)
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
        formatter_class=HelpFormatter,
    )
    _profile_arg(runtimes_model)
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
        formatter_class=HelpFormatter,
    )
    _profile_arg(runtimes_use)
    runtimes_use.add_argument("name", help="Model alias from models.yaml")
    runtimes_use.add_argument(
        "runtime",
        help="Runtime to prefer for this model, such as ollama, vllm, llamacpp, tgi, transformers, or localai",
    )
    runtimes_doctor = runtimes_sub.add_parser(
        "doctor",
        help="Check runtime availability",
        description="Check availability for one runtime, or all non-GUI runtimes when omitted.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(runtimes_doctor)
    runtimes_doctor.add_argument("runtime", nargs="?", help="Optional runtime name")
    runtimes_prereqs = runtimes_sub.add_parser(
        "prerequisites",
        help="Check runtime installer prerequisites",
        description="Report host tools needed before helper-managed runtime install/start actions can work. Ubuntu/Debian package hints are included when known.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane runtimes prerequisites ollama\n  aiplane runtimes prerequisites vllm\n  aiplane runtimes prerequisites all",
    )
    _profile_arg(runtimes_prereqs)
    runtimes_prereqs.add_argument(
        "runtime",
        help="Runtime name, such as ollama, vllm, tgi, transformers, localai, llamacpp, lmstudio, or all",
    )
    runtimes_bundle = runtimes_sub.add_parser(
        "bundle",
        help="Render runtime bundle files",
        description="Render a Dockerfile or Conda environment plan for a selected runtime/model. This does not build images, create environments, or pull weights.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  aiplane runtimes bundle vllm --model MODEL_ALIAS --mode docker --format dockerfile\n"
            "  aiplane runtimes bundle transformers --model MODEL_ALIAS --mode conda --format conda-yaml\n"
            "  aiplane runtimes bundle ollama --model MODEL_ALIAS --format json"
        ),
    )
    _profile_arg(runtimes_bundle)
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
    ]:
        command_name = "list-runtime-models" if lifecycle_action == "runtime-list" else lifecycle_action
        lifecycle = runtimes_sub.add_parser(
            command_name,
            help=f"Run provider helper {lifecycle_action.replace('-', ' ')}",
            description="Delegate runtime lifecycle/download operations to scripts/provider_helper.sh while keeping the operation available through aiplane.",
            formatter_class=HelpFormatter,
        )
        _profile_arg(lifecycle)
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

    tools_cmd = _command(
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
        formatter_class=HelpFormatter,
    )
    _profile_arg(tools_list)
    tools_matrix = tools_sub.add_parser(
        "matrix",
        help="Show the tool task matrix",
        description="Group known external tools by workflow category and show tasks, required/optional status, installability, and starter export availability.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tools_matrix)
    tools_doctor = tools_sub.add_parser(
        "doctor",
        help="Check external toolchain health",
        description="Check whether prerequisite tools are installed and whether selected services are reachable, such as Azure login or Docker daemon status.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tools_doctor)
    tools_doctor.add_argument(
        "name",
        nargs="?",
        help="Optional tool name, such as azure-cli, opentofu, docker, kubectl, helm, openssh-client, or ansible",
    )
    tools_plan = tools_sub.add_parser(
        "plan",
        help="Plan how a tool fits a workflow",
        description="Show prerequisites, safe commands, generated artifacts, and next steps for an external tool workflow without mutating anything.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tools_plan)
    tools_plan.add_argument(
        "name",
        help="Tool name, such as vagrant, packer, opentofu, terraform, pulumi, devcontainer-cli, or ansible",
    )
    tools_export = tools_sub.add_parser(
        "export",
        help="Print a starter tool artifact",
        description="Print a starter Vagrantfile, Packer template, IaC module, Dev Container config, or Ansible playbook. Output is not written automatically.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tools_export)
    tools_export.add_argument(
        "name",
        help="Tool name, such as vagrant, packer, opentofu, terraform, pulumi, devcontainer-cli, or ansible",
    )
    tools_install = tools_sub.add_parser(
        "install",
        help="Plan or run prerequisite tool install",
        description="Render and run platform-specific install commands where supported. Use --dry-run to inspect commands without executing them.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tools_install)
    tools_install.add_argument(
        "name",
        help="Tool name, such as azure-cli, opentofu, docker, kubectl, helm, openssh-client, or ansible",
    )
    tools_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Print install commands without executing them",
    )

    credentials_cmd = _command(
        subparsers,
        "credentials",
        "Inspect ignored local credential references",
        "List or show redacted credential accounts from the ignored local credentials file. This never prints raw secrets.",
        "Examples:\n  aiplane credentials list\n  aiplane credentials show openai.personal",
    )
    credentials_sub = credentials_cmd.add_subparsers(dest="credentials_command", required=True, metavar="command")
    credentials_list = credentials_sub.add_parser(
        "list",
        help="List configured credential refs",
        description="List credential account names and metadata without secret values.",
        formatter_class=HelpFormatter,
    )
    credentials_list.add_argument(
        "--path",
        help="Optional credentials YAML path. Defaults to AIPLANE_CREDENTIALS, local config credentials_path, or .aiplane/credentials.yaml",
    )
    credentials_show = credentials_sub.add_parser(
        "show",
        help="Show one credential ref with secrets redacted",
        description="Show one credential account without printing raw secret values.",
        formatter_class=HelpFormatter,
    )
    credentials_show.add_argument("ref", help="Credential ref, such as openai.personal or openai/personal")
    credentials_show.add_argument("--path", help="Optional credentials YAML path")

    mcp_cmd = _command(
        subparsers,
        "mcp",
        "Expose MCP tools over stdio",
        "Run or inspect the MCP adapter so IDEs/agents can query aiplane configuration and use guarded write tools.",
        "Examples:\n  aiplane mcp manifest\n  aiplane mcp serve",
    )
    mcp_sub = mcp_cmd.add_subparsers(dest="mcp_command", required=True, metavar="command")
    mcp_sub.add_parser(
        "manifest",
        help="Print MCP tool manifest",
        description="Print the MCP tool surface as JSON, including guarded mutating tools.",
        formatter_class=HelpFormatter,
    )
    mcp_serve = mcp_sub.add_parser(
        "serve",
        help="Start stdio MCP server",
        description="Start the MCP server over stdio for MCP-capable IDEs or agents. Mutating tools execute through the same managers as the CLI.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(mcp_serve)

    audit = _command(
        subparsers,
        "audit",
        "Read local audit logs",
        "Inspect JSONL audit events written under the workspace .aiplane directory.",
        "Example:\n  aiplane audit tail --limit 50",
    )
    audit_sub = audit.add_subparsers(dest="audit_command", required=True, metavar="command")
    tail = audit_sub.add_parser(
        "tail",
        help="Show recent audit events",
        description="Print the last N audit events as JSON lines.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(tail)
    tail.add_argument("--limit", type=int, default=20, help="Number of events to print")

    policy = _command(
        subparsers,
        "policy",
        "Explain policy decisions",
        "Explain how the active profile treats a named action.",
        "Example:\n  aiplane policy explain --action cloud_escalation",
    )
    policy_sub = policy.add_subparsers(dest="policy_command", required=True, metavar="command")
    explain = policy_sub.add_parser(
        "explain",
        help="Explain one action",
        description="Print policy decision details for an action name.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(explain)
    explain.add_argument(
        "--action",
        required=True,
        help="Action name to explain, such as backend:cloud, provider:ollama, model:fixture-chat-small, or write_file",
    )

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    profiles_dir = Path(args.profiles_dir).expanduser().resolve() if args.profiles_dir else None
    if profiles_dir is None and args.command != "config":
        profiles_dir = _profiles_dir_from_env()
    requested_profile = getattr(args, "profile", None)

    if args.command == "config":
        if args.config_command == "templates":
            print("\n".join(list_config_templates()))
            return 0
        if args.config_command == "init":
            path = init_local_config(template=args.template, path=args.path, overwrite=args.overwrite)
            print(
                _json(
                    {"created": str(path), "template": args.template},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.config_command == "default-profile":
            if args.name:
                path = set_default_profile(args.name, path=args.path)
                print(
                    _json(
                        {"default_profile": args.name, "path": str(path)},
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            print(
                _json(
                    {
                        "default_profile": default_profile(args.path),
                        "source": "AIPLANE_PROFILE or local config or fallback",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.config_command == "get":
            print(
                _json(
                    {
                        "key": args.key,
                        "value": get_local_config_value(args.key, path=args.path),
                        "path": str(local_config_path(args.path)),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.config_command == "set":
            path = set_local_config_value(args.key, _parse_setting_value(args.value), path=args.path)
            print(
                _json(
                    {
                        "key": args.key,
                        "value": get_local_config_value(args.key, path=path),
                        "path": str(path),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.config_command == "format":
            if args.value is not None and args.clear:
                raise ValueError("use either --clear or a format value, not both")
            config_path = local_config_path(args.path)
            if args.value is not None:
                write_path = set_output_format(
                    args.value, profile=args.profile, command=args.format_command, path=config_path
                )
            elif args.clear:
                write_path = clear_output_format(profile=args.profile, command=args.format_command, path=config_path)
            else:
                write_path = config_path
            print(
                _json(
                    {
                        "path": str(write_path),
                        "format": get_output_format_override(path=write_path),
                        "profile": args.profile,
                        "command": args.format_command,
                        "profile_format": get_profile_output_format(args.profile, path=write_path)
                        if args.profile
                        else None,
                        "command_format": get_command_output_format(args.format_command, path=write_path)
                        if args.format_command
                        else None,
                        "resolved_format": resolve_output_format(
                            profile=args.profile,
                            command=args.format_command,
                            path=write_path,
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.config_command == "verbosity":
            if args.value is not None and args.clear:
                raise ValueError("use either --clear or a verbosity value, not both")
            config_path = local_config_path(args.path)
            if args.value is not None:
                write_path = set_output_verbosity(
                    args.value,
                    profile=args.profile,
                    command=args.verbosity_command,
                    path=config_path,
                )
            elif args.clear:
                write_path = clear_output_verbosity(
                    profile=args.profile,
                    command=args.verbosity_command,
                    path=config_path,
                )
            else:
                write_path = config_path
            print(
                _json(
                    {
                        "path": str(write_path),
                        "verbosity": get_output_verbosity_override(path=write_path),
                        "profile": args.profile,
                        "command": args.verbosity_command,
                        "profile_verbosity": get_profile_output_verbosity(args.profile, path=write_path)
                        if args.profile
                        else None,
                        "command_verbosity": get_command_output_verbosity(args.verbosity_command, path=write_path)
                        if args.verbosity_command
                        else None,
                        "resolved_verbosity": resolve_output_verbosity(
                            profile=args.profile,
                            command=args.verbosity_command,
                            path=write_path,
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        config_path = local_config_path(args.path)
        profile_root = profiles_root(profiles_dir, config_path=config_path)
        configured_default_profile = default_profile(config_path)
        current_profile = None
        current_profile_error = None
        available_profiles = list_profiles(profile_root)
        if requested_profile:
            current_profile = requested_profile
        elif configured_default_profile in available_profiles:
            current_profile = configured_default_profile
        elif len(available_profiles) == 1:
            current_profile = available_profiles[0]
        elif not available_profiles:
            current_profile_error = (
                "no aiplane profiles found. Create one with: aiplane profiles create local-dev --template local-dev"
            )
        else:
            current_profile_error = (
                "no valid default profile is configured. Set one with: "
                "aiplane config default-profile <name>, or pass --profile. "
                f"Available profiles: {', '.join(available_profiles)}"
            )
        profile_paths = {
            "default_root": str(default_profiles_root()),
            "active_root": str(profile_root),
            "default_profile": configured_default_profile,
            "default_profile_path": str(profile_root / configured_default_profile),
            "current_profile": current_profile,
            "current_profile_path": (str(profile_root / current_profile) if current_profile else None),
        }
        if current_profile_error:
            profile_paths["current_profile_error"] = current_profile_error
        print(
            _json(
                {
                    "path": str(config_path),
                    "exists": config_path.exists(),
                    "settings": load_local_config(config_path),
                    "paths": {
                        "config": {
                            "default": str(default_local_config_path()),
                            "active": str(config_path),
                            "exists": config_path.exists(),
                        },
                        "profiles": profile_paths,
                    },
                    "effective": {
                        "default_profile": configured_default_profile,
                        "current_profile": current_profile,
                        "profiles_dir": str(profile_root),
                        "agent_artifacts_dir": str(agent_artifacts_root(config_path=config_path)),
                        "credentials_path": str(credentials_path(config_path=config_path)),
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "profiles":
        if args.profile_command == "list":
            default = resolve_profile_name(None, profiles_dir=profiles_dir)
            rows = [name + (" *" if name == default else "") for name in list_profiles(profiles_dir)]
            print("\n".join(rows))
            return 0
        if args.profile_command == "templates":
            print("\n".join(list_profile_templates()))
            return 0
        if args.profile_command == "create":
            path = create_profile(
                args.name,
                template=args.template,
                overwrite=args.overwrite,
                profiles_dir=profiles_dir,
            )
            print(
                _json(
                    {
                        "created": args.name,
                        "template": args.template,
                        "path": str(path),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.profile_command == "repair":
            profile_name = args.name or resolve_profile_name(requested_profile, profiles_dir=profiles_dir)
            result = repair_profile(
                profile_name,
                template=args.template,
                files=args.file or None,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                profiles_dir=profiles_dir,
            )
            print(_json(result, indent=2, sort_keys=True))
            return 0
        if args.profile_command == "remove":
            result = remove_profile(
                args.name,
                yes=args.yes,
                dry_run=args.dry_run,
                profiles_dir=profiles_dir,
            )
            print(_json(result, indent=2, sort_keys=True))
            return 0
        if args.profile_command == "bootstrap-local":
            result = _bootstrap_local_profile(args, workspace, profiles_dir)
            print(_json(result, indent=2, sort_keys=True))
            validation = result.get("validation") if isinstance(result.get("validation"), dict) else None
            return 0 if validation is None or validation.get("ok", False) else 1
        effective_profile = resolve_profile_name(requested_profile, profiles_dir=profiles_dir)
        profile_name = args.name or effective_profile
        profile = load_profile(profile_name, workspace, profiles_dir=profiles_dir)
        if args.profile_command == "validate":
            result = _validate_profile(profile)
            print(_json(result, indent=2))
            return 0 if result["ok"] else 1
        payload = (
            _profile_selected(profile, effective_profile)
            if args.selected
            else _profile_summary(profile, effective_profile)
        )
        print(_json(payload, indent=2))
        return 0

    if args.command == "quickstart":
        if args.quickstart_command == "local-coding":
            result = _quickstart_local_coding(args, workspace, profiles_dir)
            output_format = resolve_output_format(
                args.format,
                profile=args.name,
                path=local_config_path(),
            )
            if output_format == "text":
                print(_quickstart_local_coding_text(result))
            else:
                print(_json(result, indent=2, sort_keys=True))
            validation = (
                result.get("bootstrap", {}).get("validation") if isinstance(result.get("bootstrap"), dict) else None
            )
            return 0 if validation is None or validation.get("ok", False) else 1

    effective_profile = resolve_profile_name(requested_profile, profiles_dir=profiles_dir)

    if args.command == "discover":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        payload = _public_discover(profile)
        output_format = resolve_output_format(
            args.format,
            profile=effective_profile,
            command="discover",
            path=local_config_path(),
            default="text",
        )
        if output_format == "json":
            print(_json(payload, indent=2, sort_keys=True))
        else:
            print(_public_discover_text(payload))
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
            print(_json(payload, indent=2, sort_keys=True))
        else:
            print(_public_recommend_text(payload))
        return 0

    if args.command == "export":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        _print_public_export(args, profile)
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
            print(_json(payload, indent=2, sort_keys=True))
        else:
            print(local_coding_doctor_text(payload))
        return _doctor_exit_code(payload)

    if args.command == "run":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        result = Router(profile, AuditLogger(profile)).route(
            args.task,
            prefer_escalation=args.escalate,
            model_name=args.model,
            dry_run=args.dry_run,
            ignore_hardware_fit=args.ignore_hardware_fit,
        )
        print(result.text)
        return 0

    if args.command == "tool":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        output = ToolExecutor(profile, AuditLogger(profile), ApprovalHandler(True)).run(args.tool_name, args.tool_args)
        print(output)
        return 0

    if args.command == "tools":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = ToolchainManager(profile)
        if args.tools_command == "list":
            print(_json(manager.list(), indent=2))
            return 0
        if args.tools_command == "doctor":
            print(_json(manager.doctor(args.name), indent=2))
            return 0
        if args.tools_command == "matrix":
            print(_json(manager.matrix(), indent=2))
            return 0
        if args.tools_command == "plan":
            print(_json(manager.plan(args.name), indent=2))
            return 0
        if args.tools_command == "export":
            exported = manager.export(args.name)
            print(exported["content"])
            if exported.get("notes"):
                print("\n# Notes")
                for note in exported["notes"]:
                    print(f"# - {note}")
            return 0
        print(
            _json(
                manager.install(args.name, dry_run=args.dry_run, yes=not args.dry_run),
                indent=2,
            )
        )
        return 0

    if args.command == "benchmarks":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = BenchmarkToolManager(profile)
        if args.benchmarks_command == "list":
            print(_json(manager.list(), indent=2))
            return 0
        if args.benchmarks_command == "doctor":
            print(_json(manager.doctor(args.name), indent=2))
            return 0
        if args.benchmarks_command == "install":
            print(_json(manager.install(args.name, dry_run=args.dry_run), indent=2))
            return 0
        print(
            _json(
                manager.plan(args.name, model=args.model, endpoint=args.endpoint, spec=args.spec),
                indent=2,
            )
        )
        return 0

    if args.command == "hardware":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = HardwareManager(profile)
        if args.hardware_command == "show":
            if args.list_types:
                print(_json(manager.show_types(), indent=2, sort_keys=True))
                return 0
            output_format = resolve_output_format(
                args.format,
                profile=effective_profile,
                command="hardware show",
                path=local_config_path(),
                default="json",
            )
            if output_format == "text":
                print(_hardware_show_text(manager.show(verbosity=int(args.verbosity))))
            else:
                print(_json(manager.show(verbosity=int(args.verbosity)), indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "templates":
            print(_json(manager.templates(), indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "schema":
            print(_json(manager.schema(), indent=2))
            return 0
        if args.hardware_command == "active":
            print(_json(manager.active_config(), indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "use":
            print(
                _json(
                    manager.use_template(args.template, _parse_settings(args.settings)),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.hardware_command == "set":
            print(
                _json(
                    manager.customize_active(_parse_settings(args.settings)),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.hardware_command == "discover":
            result = (
                manager.select_closest_discovered(dry_run=args.dry_run) if args.select_closest else manager.discover()
            )
            print(_json(result, indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "clear":
            print(
                _json(
                    manager.clear_selection(dry_run=args.dry_run),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.hardware_command == "recommend":
            print(
                _json(
                    manager.recommend(include_not_recommended=args.include_not_recommended),
                    indent=2,
                )
            )
            return 0
        if args.hardware_command == "export-machine":
            exported = MachineManager(profile).export_machine(
                args.name, origin=args.origin, include_discovery=args.include_discovery
            )
            if args.format == "json":
                print(_json(exported, indent=2))
            else:
                from .config import dump_yaml

                print(dump_yaml(exported), end="")
            return 0
        print(_json(manager.doctor(args.model), indent=2, sort_keys=True))
        return 0

    if args.command == "machines":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = MachineManager(profile)
        if args.machines_command == "list":
            print(_json(manager.list(), indent=2))
            return 0
        if args.machines_command == "show":
            print(_json(manager.show(args.name), indent=2))
            return 0
        if args.machines_command == "validate":
            result = manager.validate(args.name)
            print(_json(result, indent=2))
            return 0 if result["ok"] else 1
        if args.machines_command == "cache-list":
            print(_json(manager.cache_list(), indent=2))
            return 0
        if args.machines_command == "cache-clear":
            print(_json(manager.cache_clear(args.key), indent=2))
            return 0
        if args.machines_command == "azure-status":
            verbosity = int(getattr(args, "verbosity", 0))
            reporter = _AzCommandReporter(verbosity=verbosity)
            try:
                print(
                    _json(
                        manager.azure_status(
                            region=args.region,
                            run_sku_probe=args.sku_query,
                            verbosity=verbosity,
                            az_event_sink=reporter.report,
                        ),
                        indent=2,
                    )
                )
            finally:
                reporter.close()
            return 0
        if args.machines_command == "import":
            print(
                _json(
                    manager.import_file(
                        Path(args.path),
                        name=args.name,
                        overrides=_parse_settings(args.settings),
                    ),
                    indent=2,
                )
            )
            return 0
        if args.machines_command == "recommend":
            print(
                _json(
                    manager.recommend(
                        model=args.model,
                        runtime=args.runtime,
                        workload=args.workload,
                        limit=args.limit,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.machines_command == "discover":
            verbosity = int(getattr(args, "verbosity", 0))
            reporter = _AzCommandReporter(verbosity=verbosity)
            try:
                print(
                    _json(
                        manager.discover_azure(
                            args.region,
                            workload=args.workload,
                            model=args.model,
                            gpu_vendor=args.gpu_vendor,
                            min_cpu_cores=args.min_cpu_cores,
                            min_ram_gb=args.min_ram_gb,
                            min_vram_gb=args.min_vram_gb,
                            limit=args.limit,
                            verbosity=verbosity,
                            az_event_sink=reporter.report,
                        ),
                        indent=2,
                    )
                )
            finally:
                reporter.close()
            return 0
        if args.machines_command == "import-azure-sku":
            print(
                _json(
                    manager.import_azure_sku(
                        args.sku,
                        args.region,
                        name=args.name,
                        overrides=_parse_settings(args.settings),
                    ),
                    indent=2,
                )
            )
            return 0
        if args.machines_command == "profile-remote-plan":
            print(
                _json(
                    manager.profile_remote_plan(args.name, args.host, user=args.user, port=args.port),
                    indent=2,
                )
            )
            return 0

    if args.command == "orchestrators":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        catalog = OrchestratorCatalog(profile)
        if args.orchestrators_command == "list":
            print(
                _json(
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
            print(_json(catalog.show(args.name), indent=2))
            return 0
        if args.orchestrators_command == "setup":
            print(
                _json(
                    catalog.setup(
                        args.name,
                        runtime=args.runtime,
                        model=args.model,
                        endpoint=args.endpoint,
                        environment=args.environment,
                        approval_mode=args.approval_mode,
                        limits=_parse_settings(args.limit),
                        tools=_parse_settings(args.tool),
                        dry_run=args.dry_run,
                        yes=not args.dry_run,
                        install=args.install,
                    ),
                    indent=2,
                )
            )
            return 0
        print(_json(catalog.doctor(args.name), indent=2))
        return 0

    if args.command == "stacks":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = StackManager(profile)
        if args.stacks_command == "list":
            print(_json(manager.list(), indent=2))
            return 0
        if args.stacks_command == "show":
            print(_json(manager.show(args.name), indent=2))
            return 0
        if args.stacks_command == "setup":
            print(
                _json(
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
                        limits=_parse_settings(args.limit),
                        tools=_parse_settings(args.tool),
                        roles={key: str(value) for key, value in _parse_settings(args.role).items()},
                        approval_mode=args.approval_mode,
                        audit_label=args.audit_label,
                        dry_run=args.dry_run,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.stacks_command == "plan":
            print(_json(manager.plan(args.name), indent=2))
            return 0
        if args.stacks_command == "doctor":
            print(_json(manager.doctor(args.name), indent=2))
            return 0
        if args.stacks_command == "endpoint-plan":
            print(_json(manager.endpoint_plan(args.name), indent=2))
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
            print(_json(manager.prepare(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "start":
            print(_json(manager.start(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "stop":
            print(_json(manager.stop(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "restart":
            print(_json(manager.restart(args.name, dry_run=args.dry_run), indent=2))
            return 0
        if args.stacks_command == "status":
            print(_json(manager.status(args.name), indent=2))
            return 0
    if args.command == "environment":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = EnvironmentManager(profile)
        if args.environment_command == "show":
            print(_json(manager.show(), indent=2, sort_keys=True))
            return 0
        if args.environment_command == "list":
            print(_json(manager.list_modes(), indent=2, sort_keys=True))
            return 0
        if args.environment_command == "active":
            print(_json(manager.active(), indent=2, sort_keys=True))
            return 0
        if args.environment_command == "use":
            print(_json(manager.use(args.mode), indent=2, sort_keys=True))
            return 0
        if args.environment_command == "doctor":
            progress = _stderr_line_progress()
            payload = ToolchainManager(profile).environment_doctor(
                include_optional=not args.required_only,
                progress=progress,
            )
            progress("")
            output_format = resolve_output_format(
                args.format,
                profile=effective_profile,
                path=local_config_path(),
            )
            if output_format == "text":
                print(_environment_doctor_text(payload))
            else:
                print(_json(payload, indent=2))
            return 0
        if args.environment_command == "plan":
            command = args.env_command_args
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                raise ValueError("environment plan requires a command after plan")
            plan = manager.plan(command)
            print(
                _json(
                    {
                        "mode": plan.mode,
                        "command": plan.command,
                        "cwd": str(plan.cwd),
                        "description": plan.description,
                    },
                    indent=2,
                )
            )
            return 0

    if args.command == "models":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        output_format = None
        output_verbosity = None
        if args.models_command == "list":
            output_format = resolve_output_format(
                args.format,
                profile=effective_profile,
                command="models list",
                path=local_config_path(),
                default="json",
            )
            output_verbosity = resolve_output_verbosity(
                args.verbosity,
                profile=effective_profile,
                command="models list",
                path=local_config_path(),
                default=0,
            )
        return handle_models_command(
            args,
            profile=profile,
            json_dumps=_json,
            output_format=output_format,
            output_verbosity=output_verbosity,
        )

    if args.command == "code":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        runner = CodeTaskRunner(profile, AuditLogger(profile))
        if args.code_command == "analyze":
            result = runner.analyze(
                args.model,
                Path(args.target),
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.code_command == "complete":
            result = runner.complete(
                args.model,
                Path(args.target),
                args.line,
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
            )
        else:
            result = runner.write(
                args.model,
                args.task,
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
            )
        print(result.output)
        return 0

    if args.command == "credentials":
        store = CredentialStore(args.path)
        if args.credentials_command == "list":
            print(_json(store.list(), indent=2, sort_keys=True))
            return 0
        print(_json(store.show(args.ref), indent=2, sort_keys=True))
        return 0

    if args.command == "agents":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = AgentManager(profile)
        if args.agents_command == "templates":
            print(_json(manager.templates(), indent=2))
            return 0
        if args.agents_command == "plan":
            print(
                _json(
                    manager.plan(
                        args.name,
                        framework=args.framework,
                        model=args.model,
                        runtime=args.runtime,
                        provider=args.provider,
                        endpoint=args.endpoint,
                        api_key_env=args.api_key_env,
                        instruction=args.instruction,
                        output_dir=args.output_dir,
                    ),
                    indent=2,
                )
            )
            return 0
        exported = manager.export(
            args.name,
            framework=args.framework,
            model=args.model,
            runtime=args.runtime,
            provider=args.provider,
            endpoint=args.endpoint,
            api_key_env=args.api_key_env,
            instruction=args.instruction,
            file=args.file,
            output_dir=args.output_dir,
        )
        print(exported["content"])
        if exported.get("notes"):
            print("\n# Notes")
            for note in exported["notes"]:
                print(f"# - {note}")
        return 0

    if args.command == "integrations":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        return handle_integrations_command(args, profile, _json)

    if args.command == "chat":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = IntegrationManager(profile)
        prompt = args.prompt
        if args.stdin:
            prompt = sys.stdin.read()
        if args.native_ollama or args.dry_run or prompt is not None:
            output = manager.run_chat(
                args.model,
                prompt=prompt,
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
                native_ollama=args.native_ollama,
            )
            if output:
                print(output)
            return 0
        if not sys.stdin.isatty():
            prompt = sys.stdin.read()
            if not prompt.strip():
                raise ValueError("endpoint chat requires a prompt; pass --prompt, --stdin, or use --native-ollama")
            output = manager.run_chat(args.model, prompt=prompt, timeout_seconds=args.timeout_seconds)
            if output:
                print(output)
            return 0
        print("Endpoint chat. Type /exit to quit.")
        while True:
            try:
                prompt = input("aiplane chat> ")
            except EOFError:
                break
            if prompt.strip() in {"/exit", "/quit"}:
                break
            if not prompt.strip():
                continue
            output = manager.run_chat(args.model, prompt=prompt, timeout_seconds=args.timeout_seconds)
            if output:
                print(output)
        return 0

    if args.command == "bridge":
        if args.bridge_command == "list":
            actions = []
            for action, spec in sorted(_BRIDGE_ACTIONS.items()):
                actions.append(
                    {
                        "action": action,
                        "description": spec.get("description"),
                        "command": list(spec.get("base_command", [])),
                        "requires_model": bool(spec.get("requires_model")),
                        "supports_prompt": bool(spec.get("supports_prompt")),
                    }
                )
            print(_json({"name": "bridge_actions", "actions": actions}, indent=2))
            return 0
        if args.bridge_command == "exec":
            command = _bridge_action_command(args.action, model=args.model, prompt=args.prompt)
            payload = {
                "name": "bridge_exec",
                "action": args.action,
                "command": command,
                "dry_run": bool(args.dry_run),
            }
            if args.dry_run:
                payload["ok"] = True
                print(_json(payload, indent=2))
                return 0
            executable = command[0] if command else ""
            if executable and not shutil.which(executable):
                payload["ok"] = False
                payload["reason"] = f"required executable not found on PATH: {executable}"
                print(_json(payload, indent=2))
                return 2
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            return int(completed.returncode)
        raise ValueError(f"unknown bridge command: {args.bridge_command}")

    if args.command == "launch":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        plan = _launch_plan(profile, args.tool, model=args.model, app=args.app)
        payload = {
            "name": "launch_plan",
            "tool": args.tool,
            "profile": profile.name,
            "dry_run": bool(args.dry_run),
            **plan,
        }
        if args.dry_run:
            payload["ok"] = True
            print(_json(payload, indent=2))
            return 0
        executable = str(plan["command"][0]) if plan.get("command") else ""
        if executable and not shutil.which(executable):
            payload["ok"] = False
            payload["reason"] = f"required executable not found on PATH: {executable}"
            print(_json(payload, indent=2))
            return 2
        completed = subprocess.run(
            [str(part) for part in plan["command"]],
            cwd=workspace,
            env=plan.get("env"),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        payload["returncode"] = int(completed.returncode)
        return int(completed.returncode)

    if args.command == "session":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        launch_plan = _launch_plan(profile, args.tool, model=args.model, app=args.app)
        session_id = _new_session_id()
        transcript_path = _default_session_transcript(args.transcript, workspace, session_id)
        payload = {
            "name": "session_start",
            "session_id": session_id,
            "tool": args.tool,
            "profile": profile.name,
            "model": launch_plan["selection"]["name"],
            "dry_run": bool(args.dry_run),
            "transcript": str(transcript_path),
            "launch": launch_plan,
        }
        if args.dry_run:
            print(_json(payload, indent=2))
            return 0
        metadata_path = _session_metadata_path(workspace, session_id)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        session_record = {
            "name": "session_record",
            "session_id": session_id,
            "tool": args.tool,
            "profile": profile.name,
            "model": launch_plan["selection"]["name"],
            "command": launch_plan["command"],
            "transcript": str(transcript_path),
            "created": datetime.now(timezone.utc).isoformat(),
        }
        metadata_path.write_text(_json(session_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        launch_event = AuditEvent(
            event_type="session",
            profile=profile.name,
            action="session.start",
            decision="allowed",
            details={
                "session_id": session_id,
                "tool": args.tool,
                "model": launch_plan["selection"]["name"],
                "transcript": str(transcript_path),
                "command": launch_plan["command"],
                "selection": launch_plan["selection"],
            },
        )
        AuditLogger(profile).record(launch_event)
        payload["record"] = str(metadata_path)
        print(_json(payload, indent=2))
        return 0

    if args.command == "deploy":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = DeployManager(profile)
        if args.deploy_command == "list":
            print(_json(manager.list(), indent=2, sort_keys=True))
            return 0
        if args.deploy_command == "show":
            print(_json(manager.show(args.target), indent=2, sort_keys=True))
            return 0
        if args.deploy_command == "workflow-plan":
            print(_json(manager.workflow_plan(args.target), indent=2, sort_keys=True))
            return 0
        if args.deploy_command == "plan":
            print(_json(manager.plan(args.target), indent=2, sort_keys=True))
            return 0
        if args.deploy_command == "doctor":
            print(_json(manager.doctor(args.target), indent=2, sort_keys=True))
            return 0
        if args.deploy_command == "apply":
            print(_json(manager.apply(args.target, yes=args.yes), indent=2, sort_keys=True))
            return 0
        raise ValueError(f"unknown deploy command: {args.deploy_command}")

    if args.command == "remote":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = RemoteManager(profile)
        if args.remote_command == "tunnel":
            if args.tunnel_command == "plan":
                print(_json(manager.tunnel_plan(args.target), indent=2))
                return 0
            if args.tunnel_command == "status":
                print(_json(manager.tunnel_status(args.target), indent=2))
                return 0
            if args.tunnel_command == "start":
                print(_json(manager.tunnel_start(args.target, yes=True), indent=2))
                return 0
            if args.tunnel_command == "stop":
                print(_json(manager.tunnel_stop(args.target, yes=True), indent=2))
                return 0

    if args.command == "providers":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        registry = ProviderRegistry(profile)
        if args.providers_command == "list":
            print(
                _json(
                    registry.list(
                        runtimes=args.runtime,
                        group_by=args.group_by,
                        status=args.status,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.providers_command == "show":
            print(_json(registry.show(args.name), indent=2, sort_keys=True))
            return 0
        if args.providers_command == "endpoint-types":
            print(_json(registry.endpoint_families(), indent=2, sort_keys=True))
            return 0
        if args.providers_command == "models":
            result = registry.models(args.name, query=args.query, limit=args.limit, online=args.online)
            print(_json(result.__dict__, indent=2, sort_keys=True))
            return 0
        if args.providers_command == "enable":
            result = registry.set_all_enabled(True) if args.name == "all" else registry.set_enabled(args.name, True)
            print(_json(result, indent=2))
            return 0
        if args.providers_command == "disable":
            result = registry.set_all_enabled(False) if args.name == "all" else registry.set_enabled(args.name, False)
            print(_json(result, indent=2))
            return 0
        if args.providers_command == "remove":
            print(_json(registry.remove(args.name), indent=2))
            return 0
        if args.providers_command == "add":
            print(
                _json(
                    registry.add(
                        args.name,
                        description=args.description,
                        typical_runtimes=args.runtime,
                        catalog_adapter=args.catalog_adapter,
                        enabled=not args.disabled,
                        ownership=args.ownership,
                        endpoint_family=args.endpoint_family,
                        endpoint=args.endpoint,
                        credential_ref=args.credential_ref,
                        api_key_env=args.api_key_env,
                        auth_method=args.auth_method,
                        requires_credentials=args.requires_credentials,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.providers_command == "init-defaults":
            print(_json(registry.init_defaults(overwrite=args.overwrite), indent=2))
            return 0
        if args.providers_command == "update-defaults":
            print(_json(registry.update_defaults(), indent=2, sort_keys=True))
            return 0
        if args.providers_command == "clear":
            print(_json(registry.clear_config(args.scope), indent=2))
            return 0
        if args.providers_command == "test":
            payload = registry.test_connection(args.name, credential_ref=args.credential_ref, timeout=args.timeout)
            print(_json(payload, indent=2, sort_keys=True))
            return 0 if payload.get("ok") else 2
        print(
            _json(
                [status.__dict__ for status in registry.doctor(args.name)],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "runtimes":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        catalog = RuntimeCatalog(profile)
        if args.runtimes_command == "map":
            print(_json(catalog.map(include_gui=args.include_gui), indent=2))
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
                print(_json(rows, indent=2))
            return 0
        if args.runtimes_command == "sources":
            print(_json(catalog.sources(), indent=2))
            return 0
        if args.runtimes_command == "models":
            print(
                _json(
                    catalog.models_by_runtime(args.runtime, include_gui=args.include_gui),
                    indent=2,
                )
            )
            return 0
        if args.runtimes_command == "model":
            print(
                _json(
                    catalog.runtimes_by_model(args.name, include_gui=args.include_gui),
                    indent=2,
                )
            )
            return 0
        if args.runtimes_command == "use":
            print(_json(catalog.set_preferred_runtime(args.name, args.runtime), indent=2))
            return 0
        if args.runtimes_command == "bundle":
            plan = catalog.bundle_plan(args.runtime, model_name=args.model, mode=args.mode)
            if args.format == "dockerfile":
                print(plan["files"]["Dockerfile"], end="")
            elif args.format == "conda-yaml":
                print(plan["files"]["environment.yaml"], end="")
            else:
                print(_json(plan, indent=2))
            return 0
        if args.runtimes_command == "prerequisites":
            payload = catalog.prerequisites(args.runtime)
            print(_json(payload, indent=2))
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
        }
        if args.runtimes_command in lifecycle_actions:
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
                print(_json(payload, indent=2))
                return 2
            helper_action = "list" if args.runtimes_command == "list-runtime-models" else args.runtimes_command
            if args.runtimes_command in {"install", "update", "update-installed"} and platform.system() != "Linux":
                print(
                    _json(
                        {
                            "name": "runtime_helper_platform_unsupported",
                            "runtime": args.runtime,
                            "action": args.runtimes_command,
                            "platform": platform.system(),
                            "supported_platforms": ["Linux"],
                            "reason": "aiplane runtime install helpers are not supported on this platform",
                            "next_steps": [
                                "Install the runtime with the platform-native installer.",
                                "Use aiplane discover, doctor, recommend, and export after the runtime is installed.",
                            ],
                        },
                        indent=2,
                    )
                )
                return 2
            install_reporter: _RuntimeInstallReporter | None = None
            if args.runtimes_command == "install" and not args.dry_run:
                install_reporter = _RuntimeInstallReporter()
                install_reporter.step(
                    "checking prerequisites", command=f"internal: runtimes prerequisites {args.runtime}"
                )
                prerequisites = catalog.prerequisites(args.runtime)
                if not prerequisites.get("ok"):
                    install_reporter.complete(f"prerequisites failed: {args.runtime}")
                    print(_json(prerequisites, indent=2))
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
        print(_json([catalog.runtime_available(runtime) for runtime in runtimes], indent=2))
        return 0

    if args.command == "mcp":
        if args.mcp_command == "manifest":
            print(_json(mcp_manifest(), indent=2))
            return 0
        if args.mcp_command == "serve":
            load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
            return serve_stdio(workspace, default_profile=effective_profile, profiles_dir=profiles_dir)

    if args.command == "audit":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        for event in AuditLogger(profile).tail(args.limit):
            print(_json(event, sort_keys=True))
        return 0

    if args.command == "policy":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        decision = PolicyEngine(profile).explain(args.action)
        print(_json(decision.__dict__, indent=2, sort_keys=True))
        return 0

    return 1


def _launch_plan(
    profile,
    tool: str,
    model: str | None = None,
    app: str | None = None,
) -> dict[str, object]:
    if app and tool != "ollama":
        raise ValueError("--app is only supported with --tool ollama")
    manager = IntegrationManager(profile)
    plan_args: dict[str, object] = {}
    if tool == "continue":
        if model:
            plan_args["chat"] = model
    elif tool == "ollama":
        if model:
            plan_args["model_name"] = model
        plan_args["runtime"] = "ollama"
    else:
        if model:
            plan_args["model_name"] = model
    plan = manager.plan("openai-compatible" if tool == "ollama" else tool, **plan_args)
    selections = plan.get("selection", {})
    if not isinstance(selections, dict):
        raise ValueError("integration plan did not include a selection map")
    if tool == "continue":
        selected = selections.get("chat")
        if not isinstance(selected, dict):
            raise ValueError("integration plan is missing continue chat selection")
    else:
        selected = selections.get("primary")
        if not isinstance(selected, dict):
            raise ValueError("integration plan is missing primary selection")

    model_name = str(selected.get("name") or "")
    if not model_name:
        raise ValueError("selected model name is missing")

    decision = PolicyEngine(profile).model_decision(model_name)
    if not decision.allowed:
        raise ValueError(f"launch blocked: {decision.reason}")

    if tool == "ollama":
        model_id = str(selected.get("model") or "")
        command = ["ollama", "launch", model_id]
        if app:
            command.extend(["--app", app])
        return {
            "tool": tool,
            "selection": selected,
            "command": command,
        }

    if tool == "aider":
        api_key_env = str(selected.get("api_key_env") or "")
        model_id = str(selected.get("model") or "")
        if not model_id:
            raise ValueError("selected model has no model id")
        command = ["aider", "--model", f"openai/{model_id}"]
        launch_env: dict[str, str] = os.environ.copy()
        launch_env["OPENAI_API_BASE"] = str(selected.get("endpoint") or "")
        if api_key_env:
            if api_key_env not in launch_env:
                raise ValueError(f"required environment variable {api_key_env} for aider is not set")
            launch_env[api_key_env] = os.environ.get(api_key_env, "")
        return {
            "tool": tool,
            "selection": selected,
            "command": command,
            "env": launch_env,
        }

    if tool == "continue":
        return {
            "tool": tool,
            "selection": selected,
            "command": ["continue"],
        }

    raise ValueError(f"unsupported launch tool: {tool}")


def _new_session_id() -> str:
    return uuid.uuid4().hex


def _default_session_transcript(transcript_arg: str | Path | None, workspace: Path, session_id: str) -> Path:
    if transcript_arg:
        return Path(transcript_arg).expanduser()
    return workspace / ".aiplane" / "sessions" / f"{session_id}.log"


def _session_metadata_path(workspace: Path, session_id: str) -> Path:
    return workspace / ".aiplane" / "sessions" / f"{session_id}.json"


def _runtime_helper_substrate(profile: object, runtime: str, override: str | None = None) -> str:
    if override:
        return override
    provider = ModelCatalog(profile).providers().get(runtime, {}) if hasattr(profile, "models") else {}
    substrate = str(provider.get("substrate") or "native") if isinstance(provider, dict) else "native"
    return "docker" if substrate == "docker" else "native"


def _bridge_action_command(action: str, model: str | None = None, prompt: str | None = None) -> list[str]:
    if action not in _BRIDGE_ACTIONS:
        raise ValueError(f"unsupported bridge action: {action}")
    spec = _BRIDGE_ACTIONS[action]
    requires_model = bool(spec.get("requires_model"))
    supports_prompt = bool(spec.get("supports_prompt"))
    if requires_model and not (model or "").strip():
        raise ValueError(f"bridge action {action} requires --model")
    if not requires_model and model:
        raise ValueError(f"bridge action {action} does not accept --model")
    if not supports_prompt and prompt:
        raise ValueError(f"bridge action {action} does not accept --prompt")
    command = [str(part) for part in spec.get("base_command", [])]
    if requires_model:
        command.append(str(model).strip())
    if supports_prompt and prompt is not None:
        command.append(prompt)
    return command


def _run_provider_helper(
    runtime: str,
    action: str,
    profile: str,
    model: str,
    substrate: str = "native",
    dry_run: bool = False,
    profiles_dir: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    helper = Path(__file__).resolve().parents[2] / "scripts" / "provider_helper.sh"
    if not helper.exists():
        raise FileNotFoundError(f"provider helper not found: {helper}")
    command = _provider_helper_command(runtime, action, profile, model, substrate=substrate, dry_run=dry_run)
    env = None
    if profiles_dir is not None:
        env = os.environ.copy()
        env["AIPLANE_PROFILES_DIR"] = str(profiles_dir)
    return subprocess.run(
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
    helper = Path(__file__).resolve().parents[2] / "scripts" / "provider_helper.sh"
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


def _profile_summary(profile, default_name: str | None = None) -> dict[str, object]:
    return {
        "name": profile.name,
        "default": profile.name == default_name,
        "root": str(profile.root),
        "workspace": str(profile.workspace),
        "selected": _profile_selected(profile, default_name),
        "environment": profile.environment,
        "hardware": profile.hardware,
        "models": profile.models,
        "targets": profile.targets,
        "repository": profile.repository,
        "tools": profile.tools,
        "approvals": profile.approvals,
        "backends": profile.backends,
    }


def _profile_selected(profile, default_name: str | None = None) -> dict[str, object]:
    providers = ModelCatalog(profile).providers()
    models = profile.models.get("models", {}) if isinstance(profile.models, dict) else {}
    targets = profile.targets.get("targets", {}) if isinstance(profile.targets, dict) else {}
    hardware_selected = profile.hardware.get("selected", {}) if isinstance(profile.hardware, dict) else {}
    return {
        "name": profile.name,
        "default": profile.name == default_name,
        "root": str(profile.root),
        "environment": {
            "active": profile.environment.get("active"),
            "config": _dict_value(profile.environment.get("modes", {})).get(str(profile.environment.get("active")), {}),
        },
        "hardware": {
            "origin": hardware_selected.get("origin"),
            "custom": hardware_selected.get("custom"),
            "values": hardware_selected.get("values", {}),
        },
        "providers": [
            {"name": name, **provider}
            for name, provider in _dict_value(providers).items()
            if bool(provider.get("enabled", True))
        ],
        "model_defaults": (profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {}),
        "models": [
            {"name": name, **model} for name, model in _dict_value(models).items() if bool(model.get("enabled", True))
        ],
        "targets": {
            "default": (profile.targets.get("default") if isinstance(profile.targets, dict) else None),
            "config": (
                _dict_value(targets).get(str(profile.targets.get("default")), {})
                if isinstance(profile.targets, dict)
                else {}
            ),
        },
        "repository": profile.repository,
    }


def _validate_profile(profile) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    for filename in [
        "hardware.yaml",
        "backends.yaml",
        "repository.yaml",
        "tools.yaml",
        "approvals.yaml",
        "environment.yaml",
        "models.yaml",
        "targets.yaml",
        "orchestrators.yaml",
    ]:
        path = profile.root / filename
        checks.append({"name": f"file:{filename}", "ok": path.exists(), "detail": str(path)})

    active_env = profile.environment.get("active") if isinstance(profile.environment, dict) else None
    modes = _dict_value(profile.environment.get("modes", {})) if isinstance(profile.environment, dict) else {}
    checks.append(
        {
            "name": "environment:active_mode",
            "ok": bool(active_env in modes),
            "detail": active_env,
        }
    )

    providers = ModelCatalog(profile).providers()
    models = _dict_value(profile.models.get("models", {})) if isinstance(profile.models, dict) else {}
    defaults = _dict_value(profile.models.get("defaults", {})) if isinstance(profile.models, dict) else {}
    for role, name in defaults.items():
        model = models.get(str(name))
        checks.append(
            {
                "name": f"model_default:{role}",
                "ok": isinstance(model, dict),
                "detail": name,
            }
        )
        if isinstance(model, dict) and not bool(model.get("enabled", True)):
            checks.append(
                {
                    "name": f"model_default_enabled:{role}",
                    "ok": True,
                    "warning": True,
                    "detail": f"{name} is configured but disabled",
                }
            )
    for name, model in models.items():
        provider = str(model.get("provider", "")) if isinstance(model, dict) else ""
        checks.append(
            {
                "name": f"model_provider:{name}",
                "ok": provider in providers,
                "detail": provider,
            }
        )
        if (
            provider in providers
            and bool(model.get("enabled", True))
            and not bool(providers[provider].get("enabled", True))
        ):
            checks.append(
                {
                    "name": f"provider_enabled:{provider}",
                    "ok": True,
                    "warning": True,
                    "detail": f"{name} is catalogued, but runtime endpoint {provider} is disabled",
                }
            )

    targets = _dict_value(profile.targets.get("targets", {})) if isinstance(profile.targets, dict) else {}
    default_target = profile.targets.get("default") if isinstance(profile.targets, dict) else None
    checks.append(
        {
            "name": "target:default",
            "ok": bool(default_target in targets),
            "detail": default_target,
        }
    )

    return {
        "name": profile.name,
        "ok": all(bool(check["ok"]) for check in checks if not check.get("warning")),
        "checks": checks,
    }


_AZ_SENSITIVE_FLAGS = {
    "--subscription",
    "--tenant",
    "--tenant-id",
    "--account-name",
    "--username",
    "--password",
    "--token",
    "--access-token",
    "--api-key",
    "--client-id",
    "--client-secret",
    "--sas-token",
    "--connection-string",
}

_AZ_SENSITIVE_JSON_KEYS = {
    "id",
    "tenantid",
    "subscriptionid",
    "userid",
    "username",
    "principalid",
    "clientid",
    "objectid",
    "accesstoken",
    "refreshtoken",
    "token",
    "password",
    "secret",
    "connectionstring",
}


def _redact_command_for_stderr(command: list[str]) -> str:
    parts: list[str] = []
    redact_next = False
    for item in command:
        token = str(item)
        lowered = token.lower()
        if redact_next:
            parts.append("[redacted]")
            redact_next = False
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            key_lower = key.lower()
            if key_lower in _AZ_SENSITIVE_FLAGS or _looks_sensitive_assignment(key):
                parts.append(f"{key}=[redacted]")
                continue
            parts.append(token if value else key)
            continue
        if lowered in _AZ_SENSITIVE_FLAGS:
            parts.append(token)
            redact_next = True
            continue
        parts.append(token)
    return " ".join(parts)


def _looks_sensitive_assignment(key: str) -> bool:
    key_lower = key.lower()
    return any(marker in key_lower for marker in ("token", "secret", "password", "apikey", "api_key", "key"))


def _redact_az_output_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return value
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    redacted = _redact_json_payload(payload)
    return json.dumps(redacted, indent=2, ensure_ascii=False)


def _redact_json_payload(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in _AZ_SENSITIVE_JSON_KEYS:
                redacted[key] = "[redacted]"
                continue
            if key_lower == "user" and isinstance(item, dict):
                user_redacted = dict(item)
                if "name" in user_redacted and user_redacted["name"]:
                    user_redacted["name"] = "[redacted]"
                redacted[key] = _redact_json_payload(user_redacted)
                continue
            redacted[key] = _redact_json_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json_payload(item) for item in value]
    return value


class _AzCommandReporter:
    def __init__(self, verbosity: int):
        self.verbosity = max(int(verbosity), 0)
        self._lock = threading.Lock()
        self._has_running_line = False
        self._dot_thread: threading.Thread | None = None
        self._dot_stop: threading.Event | None = None

    def report(self, event: dict[str, object]) -> None:
        phase = str(event.get("phase") or "")
        command = event.get("command")
        command_parts = [str(part) for part in command] if isinstance(command, list) else [str(command or "")]
        command_text = _redact_command_for_stderr(command_parts)
        if phase == "start":
            self._start_command_line(command_text)
            return
        if phase == "complete":
            self._stop_dot_line(clear_line=True)
            if self.verbosity >= 1:
                returncode = event.get("returncode", "?")
                self._write(f"[az] completed (exit {returncode}): {command_text}\n")
                stdout = event.get("stdout")
                stderr = event.get("stderr")
                if isinstance(stdout, str) and stdout.strip():
                    self._write(f"[az] stdout:\n{_redact_az_output_text(stdout).rstrip()}\n")
                if isinstance(stderr, str) and stderr.strip():
                    self._write(f"[az] stderr:\n{_redact_az_output_text(stderr).rstrip()}\n")

    def close(self) -> None:
        self._stop_dot_line(clear_line=True)

    def _start_command_line(self, command_text: str) -> None:
        self._stop_dot_line(clear_line=True)
        if self.verbosity <= 0 and self._has_running_line:
            self._write("\x1b[1A\r\x1b[2K")
        self._write(f"[az] running: {command_text}\n")
        self._has_running_line = True
        self._start_dot_line()

    def _start_dot_line(self) -> None:
        stop = threading.Event()
        self._dot_stop = stop
        thread = threading.Thread(target=self._dot_worker, args=(stop,), daemon=True)
        self._dot_thread = thread
        thread.start()

    def _dot_worker(self, stop: threading.Event) -> None:
        while not stop.wait(2):
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


class _RuntimeInstallReporter:
    def __init__(self):
        self._lock = threading.Lock()
        self._has_status_line = False
        self._dot_thread: threading.Thread | None = None
        self._dot_stop: threading.Event | None = None

    def step(self, message: str, command: str | list[str] | None = None) -> None:
        self._stop_dot_line(clear_line=True)
        if self._has_status_line:
            self._write("\x1b[1A\r\x1b[2K")
        if isinstance(command, list):
            command_text = _redact_command_for_stderr([str(part) for part in command])
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
        while not stop.wait(2):
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


def _stderr_line_progress():
    longest = 0

    def progress(message: str) -> None:
        nonlocal longest
        if not message:
            if longest:
                sys.stderr.write("\r" + " " * longest + "\r")
                sys.stderr.flush()
                longest = 0
            return
        text = f"{message}..."
        longest = max(longest, len(text))
        sys.stderr.write("\r" + text.ljust(longest))
        sys.stderr.flush()

    return progress


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


def _hardware_show_text(payload: dict[str, object]) -> str:
    if not isinstance(payload, dict):
        return "hardware show\n(no data)"

    active = payload.get("active_selection", {})
    if not isinstance(active, dict):
        active = {}
    machine = payload.get("effective_machine", {})
    if not isinstance(machine, dict):
        machine = {}
    cpu = machine.get("cpu", {})
    memory = machine.get("memory", {})
    gpu = machine.get("gpu", {})
    stock = machine.get("stock", {})
    if not isinstance(cpu, dict):
        cpu = {}
    if not isinstance(memory, dict):
        memory = {}
    if not isinstance(gpu, dict):
        gpu = {}
    if not isinstance(stock, dict):
        stock = {}

    def _to_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _single_row_table(headers: dict[str, str], row: dict[str, str]) -> str:
        keys = list(headers)
        widths = {key: len(headers[key]) for key in keys}
        for key in keys:
            widths[key] = max(widths[key], len(row.get(key, "")))
        lines = [
            "".join(headers[key].ljust(widths[key] + 2) for key in keys),
            "".join(row[key].ljust(widths[key] + 2) for key in keys),
        ]
        return "\n".join(lines)

    active_row = {
        "name": _to_text(active.get("name")),
        "origin": _to_text(active.get("origin")),
        "custom": _to_text(active.get("custom")),
    }
    active_lines = _single_row_table(
        {"name": "NAME", "origin": "ORIGIN", "custom": "CUSTOM"},
        active_row,
    )

    effective_row = {
        "name": _to_text(machine.get("name")),
        "provider": _to_text(stock.get("provider")),
        "placement": _to_text(machine.get("placement")),
        "substrate": _to_text(machine.get("substrate")),
        "cpu_cores": _to_text(cpu.get("cores")),
        "cpu_threads": _to_text(cpu.get("threads")),
        "ram_gb": _to_text(memory.get("ram_gb")),
        "vram_gb": _to_text(gpu.get("vram_gb")),
        "total_vram_gb": _to_text(gpu.get("total_vram_gb")),
        "gpu_vendor": _to_text(gpu.get("vendor")),
        "gpu_model": _to_text(gpu.get("model")),
    }
    effective_lines = _single_row_table(
        {
            "name": "NAME",
            "provider": "PROVIDER",
            "placement": "PLACEMENT",
            "substrate": "SUBSTRATE",
            "cpu_cores": "CPU_CORES",
            "cpu_threads": "CPU_THREADS",
            "ram_gb": "RAM_GB",
            "vram_gb": "VRAM_GB",
            "total_vram_gb": "TOTAL_VRAM_GB",
            "gpu_vendor": "GPU_VENDOR",
            "gpu_model": "GPU_MODEL",
        },
        effective_row,
    )

    return "\n".join(
        [
            "hardware show",
            "active_selection",
            active_lines,
            "",
            "effective_machine",
            effective_lines,
        ]
    )


def _environment_doctor_text(payload: dict[str, object]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    rows: list[dict[str, str]] = []
    tool_rows: list[dict[str, str]] = []
    for section in [
        "installed",
        "missing_installable_by_aiplane",
        "missing_manual_or_platform_specific",
    ]:
        values = payload.get(section, [])
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            needed_for = item.get("needed_for", [])
            why = (
                ", ".join(str(value) for value in needed_for[:2])
                if isinstance(needed_for, list)
                else str(needed_for or "")
            )
            tool_rows.append(
                {
                    "name": str(item.get("name") or ""),
                    "kind": "tool",
                    "status": "installed" if item.get("installed") else "missing",
                    "required": str(item.get("requirement") or "optional"),
                    "why": why or str(item.get("description") or ""),
                }
            )
    rows.extend(
        sorted(
            tool_rows,
            key=lambda row: (
                0 if row["required"] == "mandatory" else 1,
                row["status"] != "installed",
                row["name"],
            ),
        )
    )
    values = payload.get("runtime_prerequisites", [])
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict):
            continue
        purpose = item.get("purpose", [])
        why = ", ".join(str(value) for value in purpose[:2]) if isinstance(purpose, list) else str(purpose or "")
        missing_required = item.get("missing_required", [])
        missing_count = len(missing_required) if isinstance(missing_required, list) else 0
        rows.append(
            {
                "name": str(item.get("runtime") or ""),
                "kind": "runtime",
                "status": (
                    "ready" if item.get("ok") else (f"missing {missing_count}" if missing_count else "needs setup")
                ),
                "required": "optional",
                "why": why,
            }
        )
    headers = {
        "name": "NAME",
        "kind": "TYPE",
        "status": "STATUS",
        "required": "REQUIRED",
        "why": "WHY",
    }
    keys = ["name", "kind", "status", "required", "why"]
    widths = {key: len(value) for key, value in headers.items()}
    for row in rows:
        for key in keys:
            limit = 52 if key == "why" else 24
            widths[key] = min(max(widths[key], len(row.get(key, ""))), limit)

    def clipped(value: str, width: int) -> str:
        return value if len(value) <= width else value[: max(0, width - 3)] + "..."

    lines = [
        f"environment doctor for profile {payload.get('profile', 'unknown')}",
        f"tools: {summary.get('tools_installed', 0)}/{summary.get('tools_checked', 0)} installed; runtime prerequisites missing: {summary.get('runtime_prerequisites_missing', 0)}",
        "",
        "  ".join(headers[key].ljust(widths[key]) for key in keys),
    ]
    for row in rows:
        lines.append("  ".join(clipped(row[key], widths[key]).ljust(widths[key]) for key in keys))
    notes = payload.get("notes", [])
    if isinstance(notes, list) and notes:
        lines.append("")
        lines.append("next steps:")
        lines.extend(f"- {note}" for note in notes[:3])
    return "\n".join(lines)


def _public_discover(profile) -> dict[str, object]:
    catalog = ModelCatalog(profile)
    models = catalog.models()
    providers = catalog.providers()
    defaults = catalog.defaults()
    hardware = HardwareManager(profile).discover()
    runtimes = RuntimeCatalog(profile).list(include_gui=True)
    integrations = IntegrationManager(profile).list()
    endpoints = [
        {
            "provider": name,
            "endpoint": provider.get("endpoint"),
            "enabled": bool(provider.get("enabled", True)),
            "api_key_env": provider.get("api_key_env"),
            "ownership": provider.get("ownership"),
        }
        for name, provider in sorted(providers.items())
        if isinstance(provider, dict) and (provider.get("endpoint") or provider.get("api_key_env"))
    ]
    local_models = [
        {
            "name": name,
            "model": model.get("model"),
            "provider": model.get("provider"),
            "enabled": bool(model.get("enabled", True)),
        }
        for name, model in sorted(models.items())
        if isinstance(model, dict) and bool(model.get("local", False))
    ]
    return {
        "name": "environment_discovery",
        "profile": profile.name,
        "read_only": True,
        "hardware": hardware,
        "runtimes": runtimes,
        "local_models": local_models,
        "endpoints": endpoints,
        "coding_tools": integrations,
        "defaults": defaults,
        "provenance": _profile_provenance(
            profile,
            hardware=hardware,
            runtimes=runtimes,
            local_models=local_models,
            endpoints=endpoints,
            integrations=integrations,
        ),
        "next_command": f"aiplane doctor --profile {profile.name}",
    }


def _public_discover_text(payload: dict[str, object]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    summary = provenance.get("summary") if isinstance(provenance.get("summary"), dict) else {}
    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    lines = [
        f"aiplane discover for profile {payload.get('profile', 'unknown')}",
        f"hardware: CPU={hardware.get('cpu_count', 'unknown')}; RAM={hardware.get('memory_gb', 'unknown')}GB; GPUs={len(hardware.get('gpus', []) or [])}",
        f"runtimes: {len(payload.get('runtimes', []) or [])}; local_models: {len(payload.get('local_models', []) or [])}; endpoints: {len(payload.get('endpoints', []) or [])}; coding_tools: {len(payload.get('coding_tools', []) or [])}",
        "configuration provenance: "
        f"detected={summary.get('detected_values', 0)}, "
        f"generated={summary.get('generated_values', 0)}, "
        f"user_supplied={summary.get('user_supplied_values', 0)}, "
        f"unresolved={summary.get('unresolved_values', 0)}",
        "",
        f"next command: {payload.get('next_command')}",
    ]
    return "\n".join(lines)


def _public_recommend_text(payload: dict[str, object]) -> str:
    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    lines = ["aiplane recommend", "recommended:"]
    recommended = models.get("recommended", []) if isinstance(models, dict) else []
    if recommended:
        for row in recommended[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {row.get('name')}: {row.get('reason')}")
    else:
        lines.append("- none")
    usable = models.get("usable", []) if isinstance(models, dict) else []
    remote = models.get("remote_or_cloud", []) if isinstance(models, dict) else []
    lines.append(f"usable: {len(usable)}; remote_or_cloud: {len(remote)}")
    lines.append("next command: aiplane export continue")
    return "\n".join(lines)


def _print_public_export(args, profile) -> None:
    manager = IntegrationManager(profile)
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


def _doctor_exit_code(payload: dict[str, object]) -> int:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("blocking", 0) or 0) > 0:
        return 2
    if int(summary.get("warnings", 0) or 0) > 0:
        return 1
    return 0


def _profile_provenance(
    profile,
    *,
    hardware: dict[str, object] | None = None,
    runtimes: list[dict[str, object]] | None = None,
    local_models: list[dict[str, object]] | None = None,
    endpoints: list[dict[str, object]] | None = None,
    integrations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    values: list[dict[str, object]] = []

    def add(state: str, source: str, name: str, value: object) -> None:
        values.append({"state": state, "source": source, "name": name, "value": value})

    hardware = hardware or {}
    if hardware.get("cpu_count") is not None:
        add("detected", "hardware.discover", "hardware.cpu_count", hardware.get("cpu_count"))
    if hardware.get("memory_gb") is not None:
        add("detected", "hardware.discover", "hardware.memory_gb", hardware.get("memory_gb"))
    for index, gpu in enumerate(hardware.get("gpus", []) or []):
        if isinstance(gpu, dict):
            add("detected", "hardware.discover", f"hardware.gpus.{index}", gpu.get("name") or gpu.get("vendor"))
    for runtime in runtimes or []:
        if isinstance(runtime, dict):
            add("generated", "runtime_catalog", f"runtime.{runtime.get('name')}", runtime.get("protocol"))
    for tool in integrations or []:
        if isinstance(tool, dict):
            add("generated", "integration_contracts", f"integration.{tool.get('name')}", tool.get("description"))
    for model in local_models or []:
        if isinstance(model, dict):
            add("user_supplied", "profile.models", f"model.{model.get('name')}", model.get("model"))
    for endpoint in endpoints or []:
        if isinstance(endpoint, dict):
            add("user_supplied", "profile.providers", f"endpoint.{endpoint.get('provider')}", endpoint.get("endpoint"))
    defaults = profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {}
    if isinstance(defaults, dict):
        for key, value in sorted(defaults.items()):
            if value:
                add("user_supplied", "profile.defaults", f"defaults.{key}", value)
            else:
                add("unresolved", "profile.defaults", f"defaults.{key}", value)
    if not local_models:
        add("unresolved", "profile.models", "local_models", "no local model aliases discovered or configured")
    summary = {
        "detected_values": sum(1 for row in values if row["state"] == "detected"),
        "generated_values": sum(1 for row in values if row["state"] == "generated"),
        "user_supplied_values": sum(1 for row in values if row["state"] == "user_supplied"),
        "unresolved_values": sum(1 for row in values if row["state"] == "unresolved"),
    }
    return {"summary": summary, "values": values}


def _bootstrap_local_profile(args, workspace: Path, profiles_dir: Path | None) -> dict[str, object]:
    root = profiles_root(profiles_dir)
    profile_path = root / args.name
    created = False
    would_create = False
    if args.dry_run:
        would_create = args.overwrite or not profile_path.exists()
    elif args.overwrite or not profile_path.exists():
        profile_path = create_profile(
            args.name,
            template=args.template,
            overwrite=args.overwrite,
            profiles_dir=profiles_dir,
        )
        created = True
    profile_exists = profile_path.exists()
    validation = None
    discovery = None
    hardware = None
    provenance = None
    if profile_exists:
        profile = load_profile(args.name, workspace, profiles_dir=profiles_dir)
        validation = _validate_profile(profile)
        verbosity = int(getattr(args, "verbosity", 0))
        if not args.no_hardware_discovery:
            manager = HardwareManager(profile)
            hardware = (
                manager.select_closest_discovered(dry_run=args.dry_run)
                if args.select_closest_hardware
                else manager.discover()
            )
        if not args.no_discovery:
            catalog = ModelCatalog(profile)
            provider_limits = _parse_provider_limits(args.provider_limit)
            progress = _refresh_progress()
            write = not args.dry_run
            try:
                if args.provider == "all":
                    refresh_all_kwargs: dict[str, object] = {
                        "write": write,
                        "enable": not args.disable_new,
                        "query": args.query,
                        "provider_limits": provider_limits,
                        "progress": progress,
                        "verbose": verbosity >= 2,
                    }
                    if args.limit is not None:
                        refresh_all_kwargs["limit"] = args.limit
                    discovery = catalog.refresh_all(**refresh_all_kwargs)
                else:
                    refresh_kwargs: dict[str, object] = {
                        "write": write,
                        "enable": not args.disable_new,
                        "query": args.query,
                        "progress": progress,
                        "verbose": verbosity >= 2,
                    }
                    provider_limit = provider_limits.get(args.provider)
                    if provider_limit is not None:
                        refresh_kwargs["limit"] = int(provider_limit)
                    elif args.limit is not None:
                        refresh_kwargs["limit"] = args.limit
                    discovery = catalog.refresh(args.provider, **refresh_kwargs)
            finally:
                if progress:
                    progress("done", "", "")
            if isinstance(discovery, dict) and "results" in discovery:
                discovery = refresh_cli_payload(discovery, verbosity=verbosity)
        provenance = _public_discover(profile)["provenance"]
    elif not args.no_discovery or not args.no_hardware_discovery:
        skipped = "profile does not exist yet; rerun without --dry-run to create it before discovery"
        if not args.no_discovery:
            discovery = {"skipped": True, "reason": skipped}
        if not args.no_hardware_discovery:
            hardware = {"skipped": True, "reason": skipped}
    return {
        "name": "profiles_bootstrap_local",
        "profile": args.name,
        "template": args.template,
        "path": str(profile_path),
        "created": created,
        "would_create": would_create,
        "overwrite": args.overwrite,
        "dry_run": args.dry_run,
        "discovery_requested": not args.no_discovery,
        "discovery": discovery,
        "hardware_discovery_requested": not args.no_hardware_discovery,
        "hardware": hardware,
        "provenance": provenance,
        "validation": validation,
        "next_steps": _profile_bootstrap_next_steps(args.name, not args.no_discovery, args.dry_run),
    }


def _quickstart_local_coding(args, workspace: Path, profiles_dir: Path | None) -> dict[str, object]:
    bootstrap = _bootstrap_local_profile(args, workspace, profiles_dir)
    doctor_payload = None
    recommendation_payload = None
    pull = None
    profile_path = Path(str(bootstrap.get("path", "")))
    profile = None
    if profile_path.exists():
        profile = load_profile(args.name, workspace, profiles_dir=profiles_dir)
        if args.pull_model:
            pull = _quickstart_pull_model(
                profile,
                args.name,
                args.pull_model,
                runtime=args.pull_runtime,
                substrate=args.pull_substrate,
                execute=not args.dry_run,
                profiles_dir=profiles_dir,
            )
        doctor_payload = local_coding_doctor(profile, include_optional=False)
        recommendation_payload = HardwareManager(profile).recommend()
    elif args.pull_model:
        pull = {
            "name": "quickstart_model_pull",
            "model": args.pull_model,
            "executed": False,
            "dry_run": True,
            "skipped": True,
            "reason": "profile does not exist yet; rerun quickstart without --dry-run before pulling models",
        }
    commands = [
        f"aiplane discover --profile {args.name}",
        f"aiplane doctor --profile {args.name}",
        f"aiplane recommend --profile {args.name}",
        f"aiplane export continue --profile {args.name}",
        f"aiplane export aider --profile {args.name}",
        "aiplane export vscode-mcp",
    ]
    if args.pull_model:
        pull_runtime = (pull.get("runtime") if isinstance(pull, dict) else None) or args.pull_runtime or "RUNTIME"
        commands.insert(
            1,
            f"aiplane runtimes pull {pull_runtime} --model {args.pull_model}" + (" --dry-run" if args.dry_run else ""),
        )
    if args.dry_run and not profile_path.exists():
        commands.insert(0, f"aiplane quickstart local-coding --name {args.name}")
    return {
        "name": "quickstart_local_coding",
        "profile": args.name,
        "dry_run": args.dry_run,
        "bootstrap": bootstrap,
        "pull": pull,
        "doctor": doctor_payload,
        "recommend": recommendation_payload,
        "commands": commands,
        "notes": [
            "This quickstart stays in the environment-doctor workflow lane: it creates or previews a local profile, runs discovery/doctor checks, optionally delegates an explicit model pull, and prints export commands.",
            "Use --dry-run with --pull-model to preview the existing runtime helper pull path without pulling model weights.",
            "It does not install runtimes, edit IDE configuration, start cloud resources, or run an agent conversation.",
        ],
    }


def _quickstart_pull_model(
    profile,
    profile_name: str,
    model_name: str,
    runtime: str | None = None,
    substrate: str | None = None,
    execute: bool = False,
    profiles_dir: Path | str | None = None,
) -> dict[str, object]:
    catalog = ModelCatalog(profile)
    model = catalog.get(model_name)
    provider = catalog.providers().get(str(model.get("provider") or ""), {})
    if str(model.get("ownership") or provider.get("ownership") or "") == "managed_service":
        return {
            "name": "quickstart_model_pull",
            "model": model_name,
            "executed": False,
            "dry_run": True,
            "ok": False,
            "reason": "managed-service model aliases are endpoint-backed and do not use local runtime model pulls",
        }
    selected_runtime = runtime or RuntimeCatalog(profile).select_runtime(model_name).get("selected")
    if not selected_runtime:
        return {
            "name": "quickstart_model_pull",
            "model": model_name,
            "executed": False,
            "dry_run": True,
            "ok": False,
            "reason": "no supported runtime is configured for this model alias",
        }
    resolved_substrate = _runtime_helper_substrate(profile, str(selected_runtime), substrate)
    completed = _run_provider_helper(
        str(selected_runtime),
        "pull",
        profile_name,
        model_name,
        substrate=resolved_substrate,
        dry_run=not execute,
        profiles_dir=profiles_dir,
    )
    return {
        "name": "quickstart_model_pull",
        "model": model_name,
        "runtime": str(selected_runtime),
        "substrate": resolved_substrate,
        "executed": execute,
        "dry_run": not execute,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _quickstart_local_coding_text(payload: dict[str, object]) -> str:
    bootstrap = payload.get("bootstrap") if isinstance(payload.get("bootstrap"), dict) else {}
    doctor = payload.get("doctor") if isinstance(payload.get("doctor"), dict) else None
    lines = [
        f"local coding quickstart for profile {payload.get('profile', 'unknown')}",
        f"profile path: {bootstrap.get('path', '')}",
        f"created: {bootstrap.get('created', False)}; dry_run: {payload.get('dry_run', False)}",
    ]
    validation = bootstrap.get("validation") if isinstance(bootstrap.get("validation"), dict) else None
    if validation is not None:
        lines.append(f"profile validation: {'ok' if validation.get('ok') else 'issues found'}")
    pull = payload.get("pull") if isinstance(payload.get("pull"), dict) else None
    if pull is not None:
        lines.append(
            f"pull: {'executed' if pull.get('executed') else 'preview'}; "
            f"model: {pull.get('model')}; runtime: {pull.get('runtime', 'n/a')}"
        )
    if doctor is not None:
        summary = doctor.get("summary") if isinstance(doctor.get("summary"), dict) else {}
        lines.append(
            f"doctor: {'ok' if doctor.get('ok') else 'issues found'}; "
            f"needs_attention: {summary.get('blocking', 0)}; further_actions: {summary.get('warnings', 0)}"
        )
        # show top blocking checks and simple suggestions
        if doctor is not None:
            blocking: list[tuple[str, str]] = []
            warnings: list[tuple[str, str]] = []
            for section in doctor.get("sections", []) or []:
                if not isinstance(section, dict):
                    continue
                section_name = str(section.get("name") or "general")
                for check in section.get("checks", []) or []:
                    if not isinstance(check, dict):
                        continue
                    reason = check.get("reason") or check.get("detail") or ""
                    # simple suggestion mapping with exact CLI snippets
                    if check.get("name") == "model_catalog":
                        suggestion = (
                            "Try: `aiplane models refresh --dry-run`; "
                            "`aiplane models list --group-by runtime`; "
                            "`aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`"
                        )
                    elif section.get("name") == "model_defaults" or str(check.get("name", "")).endswith("_model"):
                        role_arg = check.get("name") or "<role>"
                        suggestion = (
                            "Try: `aiplane models refresh --dry-run`; "
                            "`aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`; "
                            f"`aiplane models use {role_arg} ALIAS`"
                        )
                    elif section.get("name") == "environment":
                        suggestion = (
                            "Try: `aiplane environment doctor --required-only` then install missing CLIs listed above."
                        )
                    elif section.get("name") == "endpoints" or str(check.get("name", "")).startswith("endpoint:"):
                        suggestion = "Try: `aiplane runtimes status <runtime>` or `aiplane providers test <provider>`. If provider is disabled, run `aiplane providers enable <provider>`."
                    elif section.get("name") == "integrations":
                        suggestion = "Try: `aiplane integrations list`; `aiplane integrations roles <tool>`; `aiplane integrations plan <tool>`."
                    else:
                        suggestion = "See `aiplane doctor --profile <name>` for details."
                    check_name = str(check.get("name") or "check")
                    if section_name == "integrations" and check_name.startswith("integration:"):
                        check_name = check_name.split(":", 1)[1]
                    item = f"{check_name}: {reason} -> {suggestion}"
                    if not check.get("ok"):
                        blocking.append((section_name, item))
                    elif check.get("warning"):
                        warnings.append((section_name, item))

            if blocking:
                lines.append("")
                lines.append(f"recommended actions ({len(blocking)}):")
                current_root = ""
                for root, item in blocking:
                    if root != current_root:
                        lines.append(f"- {root}:")
                        current_root = root
                    lines.append(f"  - {item}")
            if warnings:
                lines.append("")
                lines.append(f"further actions/status ({len(warnings)}):")
                current_root = ""
                for root, item in warnings:
                    if root != current_root:
                        lines.append(f"- {root}:")
                        current_root = root
                    lines.append(f"  - {item}")
    lines.append("")
    lines.append("next commands:")
    commands = payload.get("commands", [])
    if isinstance(commands, list):
        lines.extend(f"- {command}" for command in commands)
    return "\n".join(lines).rstrip()


def _profile_bootstrap_next_steps(profile: str, discovery_requested: bool, dry_run: bool) -> list[str]:
    if dry_run:
        steps = [
            f"Rerun aiplane profiles bootstrap-local --name {profile} without --dry-run to create or refresh the profile."
        ]
    else:
        steps = [f"Run aiplane profiles validate {profile} after local edits."]
    if discovery_requested:
        steps.append(f"Review discovered candidates with aiplane models list --profile {profile} --group-by runtime.")
        steps.append(
            "Promote a reviewed discovered entry or add a profile-owned entry before setting defaults or exporting IDE config."
        )
    else:
        steps.append(
            f"Run aiplane models refresh --profile {profile} when you want to populate models.discovered.yaml."
        )
    return steps


def _dict_value(value: object) -> dict:
    return value if isinstance(value, dict) else {}
