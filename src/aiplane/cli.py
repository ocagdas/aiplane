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
from .boundaries import CommandRunner, SubprocessCommandRunner
from .models import AuditEvent
from .code_tasks import CodeTaskRunner
from .config import (
    create_profile,
    local_config_path,
    load_profile,
    profiles_root,
    provider_helper_path,
    resolve_profile_name,
    resolve_output_format,
    resolve_output_verbosity,
)
from .hardware import HardwareManager
from .cli_config import add_config_parser, handle_config_command
from .cli_deploy_remote import add_deploy_remote_parsers, handle_deploy_remote_command
from .cli_hardware import add_hardware_machine_parsers, handle_hardware_machine_command
from .cli_governance import add_governance_parsers, handle_governance_command
from .cli_integrations import add_integrations_parser, handle_integrations_command
from .cli_stacks import add_stack_parsers, handle_stack_command
from .cli_setup import add_setup_parsers, handle_setup_command
from .cli_profiles import add_profiles_parser, handle_profiles_command
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
from .model_catalog import ModelCatalog
from .output import json_dumps as _json
from .policy import PolicyEngine
from .providers import (
    ProviderRegistry,
    SUPPORTED_CATALOG_ADAPTERS,
    SUPPORTED_ENDPOINT_FAMILIES,
)
from .router import Router
from .runtime_catalog import RuntimeCatalog
from .tools import ToolExecutor


_COMMAND_RUNNER: CommandRunner = SubprocessCommandRunner()


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

    add_config_parser(
        subparsers,
        command_factory=_command,
        formatter_class=HelpFormatter,
    )

    add_profiles_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
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

    add_hardware_machine_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
    add_stack_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
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
    add_deploy_remote_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )

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

    add_setup_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
    add_governance_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    profiles_dir = Path(args.profiles_dir).expanduser().resolve() if args.profiles_dir else None
    if profiles_dir is None and args.command != "config":
        profiles_dir = _profiles_dir_from_env()
    requested_profile = getattr(args, "profile", None)

    config_result = handle_config_command(
        args,
        profiles_dir=profiles_dir,
        requested_profile=requested_profile,
        json_dumps=_json,
        parse_setting_value=_parse_setting_value,
    )
    if config_result is not None:
        return config_result

    profile_result = handle_profiles_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        requested_profile=requested_profile,
        json_dumps=_json,
        bootstrap_profile=_bootstrap_local_profile,
        validate_profile=_validate_profile,
        profile_selected=_profile_selected,
        profile_summary=_profile_summary,
    )
    if profile_result is not None:
        return profile_result

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

    setup_result = handle_setup_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
        progress_factory=_stderr_line_progress,
        resolve_format=resolve_output_format,
        config_path=local_config_path(),
        environment_doctor_text=_environment_doctor_text,
    )
    if setup_result is not None:
        return setup_result

    hardware_result = handle_hardware_machine_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
        parse_settings=_parse_settings,
        reporter_factory=_AzCommandReporter,
        resolve_format=resolve_output_format,
        config_path=local_config_path(),
        hardware_show_text=_hardware_show_text,
    )
    if hardware_result is not None:
        return hardware_result
    stack_result = handle_stack_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
        parse_settings=_parse_settings,
    )
    if stack_result is not None:
        return stack_result
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

    governance_result = handle_governance_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
    )
    if governance_result is not None:
        return governance_result

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
            completed = _COMMAND_RUNNER.run(command, text=True, capture_output=True, check=False)
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
        completed = _COMMAND_RUNNER.run(
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

    deploy_remote_result = handle_deploy_remote_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
    )
    if deploy_remote_result is not None:
        return deploy_remote_result

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
            if args.runtimes_command in {"remove", "clear"} and not args.dry_run and not args.yes:
                print(
                    _json(
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
            "origin": provider.get("origin", "built_in"),
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
            "origin": "discovered_cache" if name in catalog.generated_config.get("models", {}) else "profile",
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
        "configuration sources (counted records): "
        f"detected={summary.get('detected_values', 0)}, "
        f"built_in={summary.get('generated_values', 0)}, "
        f"discovered_cache={summary.get('discovered_values', 0)}, "
        f"profile_configured={summary.get('user_supplied_values', 0)}, "
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
            if model.get("origin") == "discovered_cache":
                add("discovered", "models.discovered.yaml", f"model.{model.get('name')}", model.get("model"))
            else:
                add("user_supplied", "profile.models", f"model.{model.get('name')}", model.get("model"))
    for endpoint in endpoints or []:
        if isinstance(endpoint, dict):
            state = "user_supplied" if endpoint.get("origin") == "profile" else "generated"
            source = "profile.providers" if state == "user_supplied" else "provider_defaults"
            add(state, source, f"endpoint.{endpoint.get('provider')}", endpoint.get("endpoint"))
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
        "discovered_values": sum(1 for row in values if row["state"] == "discovered"),
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
