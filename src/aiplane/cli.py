from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .agents import AgentManager
from .approvals import ApprovalHandler
from .audit import AuditLogger
from .benchmarks import BenchmarkRunner
from .benchmark_tools import BenchmarkToolManager
from .code_tasks import CodeTaskRunner
from .config import (
    agent_artifacts_root,
    create_profile,
    default_local_config_path,
    default_profile,
    default_profiles_root,
    get_local_config_value,
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
    set_default_profile,
    set_local_config_value,
)
from .deploy import DeployManager
from .env import EnvironmentManager
from .hardware import HardwareManager
from .cli_integrations import add_integrations_parser, handle_integrations_command
from .integrations import IntegrationManager
from .machines import MachineManager
from .machine_model_filters import merge_machine_model_filters
from .mcp import mcp_manifest, serve_stdio
from .model_catalog import ModelCatalog
from .model_filters import ACCELERATOR_API_CHOICES, GPU_VENDOR_CHOICES, MODEL_SORT_CHOICES, model_filter_args
from .model_output import group_model_rows, group_rows
from .orchestrators import OrchestratorCatalog
from .output import json_dumps as _json
from .policy import PolicyEngine
from .providers import ProviderRegistry, SUPPORTED_CATALOG_ADAPTERS, SUPPORTED_ENDPOINT_FAMILIES
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
    )


def _profile_arg(parser) -> None:
    parser.add_argument(
        "--profile",
        help="Profile name. Optional: defaults to AIPLANE_PROFILE, local config default_profile, or the only available profile",
    )


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
            "aiplane is a control-plane CLI: it manages profiles, providers, models, hardware fit,\n"
            "IDE/CLI exports, remote endpoint plans, and MCP access. It does not replace IDE agents."
        ),
        epilog=(
            "Common flows:\n"
            "  aiplane config init\n"
            "  aiplane profiles list\n"
            "  aiplane providers models ollama\n"
            "  aiplane hardware recommend\n"
            "  aiplane models benchmark MODEL_ALIAS --dry-run\n"
            "  aiplane integrations export continue --model MODEL_ALIAS\n"
            "  aiplane mcp serve\n\n"
            "Docs: docs/user/index.md"
        ),
        formatter_class=HelpFormatter,
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
    )
    config_init = config_sub.add_parser(
        "init",
        help="Create local config from template",
        description="Copy a checked-in config template to .aiplane/config.yaml or AIPLANE_CONFIG. The copied file is ignored by git.",
        formatter_class=HelpFormatter,
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
    )
    config_set.add_argument("key", help="Top-level config key, such as profiles_dir or default_profile")
    config_set.add_argument("value", help="Value to store")
    config_set.add_argument(
        "--path",
        help="Optional config path. Defaults to AIPLANE_CONFIG or .aiplane/config.yaml",
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
    )
    profile_sub.add_parser(
        "templates",
        help="List shipped profile templates",
        description="List checked-in templates that can be copied into profiles/.",
        formatter_class=HelpFormatter,
    )
    create = profile_sub.add_parser(
        "create",
        help="Create a profile from a template",
        description="Copy a shipped profile template into profiles/<name> so it can be customized without changing the template.",
        formatter_class=HelpFormatter,
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
        action="store_true",
        help="Replace an existing profile directory with a fresh copy of the template before discovery",
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
        default=25,
        help="Default maximum model ids to read per provider catalog during bootstrap discovery",
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
        "--verbose",
        action="store_true",
        help="Include per-model discovery rows in the refresh result",
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
        help="Show raw hardware profile config",
        description="Print the hardware.yaml content for the selected profile.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(hardware_show)
    hardware_templates = hardware_sub.add_parser(
        "templates",
        help="List immutable hardware templates",
        description="Show hardware templates that can be copied into the active selected config.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(hardware_templates)
    hardware_schema = hardware_sub.add_parser(
        "schema",
        help="Show machine property schema",
        description="Show the editable machine fields used for hardware-aware recommendation: stock tag/SKU, CPU, RAM, GPU, VRAM, accelerator APIs, OS, placement, and substrate.",
        formatter_class=HelpFormatter,
        epilog="Example:\n  aiplane hardware schema",
    )
    _profile_arg(hardware_schema)
    hardware_active = hardware_sub.add_parser(
        "active",
        help="Show selected hardware config",
        description="Show the active copied/customized hardware config and template origin.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(hardware_active)
    hardware_use = hardware_sub.add_parser(
        "use",
        help="Copy a template into active hardware config",
        description="Select a hardware template by copying it into the mutable active config. Overrides do not modify the template.",
        formatter_class=HelpFormatter,
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
    )
    _profile_arg(hardware_clear)
    hardware_clear.add_argument(
        "--dry-run", action="store_true", help="Preview the reset without writing hardware.yaml"
    )
    hardware_doctor = hardware_sub.add_parser(
        "doctor",
        help="Check hardware/model fit",
        description="Check whether configured local models fit the discovered or selected hardware.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(hardware_doctor)
    hardware_doctor.add_argument(
        "--model",
        help="Optional model alias to check, such as a discovered or promoted alias",
    )
    hardware_recommend = hardware_sub.add_parser(
        "recommend",
        help="Recommend models for active/discovered hardware",
        description="Return hardware-aware model recommendations, sorted by capability score within recommendation groups.",
        formatter_class=HelpFormatter,
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
        "Examples:\n  aiplane machines import gpu_box_01.machine.yaml\n  aiplane machines list\n  aiplane machines recommend --model MODEL_ALIAS --runtime vllm\n  aiplane machines discover azure --region uksouth --workload inference_large",
    )
    machines_sub = machines_cmd.add_subparsers(dest="machines_command", required=True, metavar="command")
    machines_list = machines_sub.add_parser(
        "list",
        help="List imported machines",
        description="List self-managed machines registered in the profile hardware inventory.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(machines_list)
    machines_show = machines_sub.add_parser(
        "show",
        help="Show one imported machine",
        description="Show one machine profile from the self-managed inventory.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(machines_show)
    machines_show.add_argument("name", help="Machine name")
    machines_validate = machines_sub.add_parser(
        "validate",
        help="Validate imported machine profiles",
        description="Validate required machine profile fields for one machine or all imported machines.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(machines_validate)
    machines_validate.add_argument("name", nargs="?", help="Optional machine name")
    machines_cache_list = machines_sub.add_parser(
        "cache-list",
        help="List machine discovery cache entries",
        description="Inspect cached discovery results, including whether each entry came from live provider data or offline hints.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(machines_cache_list)
    machines_cache_clear = machines_sub.add_parser(
        "cache-clear",
        help="Clear machine discovery cache",
        description="Clear all cached machine discovery results, or one cache key.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(machines_cache_clear)
    machines_cache_clear.add_argument("--key", help="Specific cache key to clear")
    machines_azure_status = machines_sub.add_parser(
        "azure-status",
        help="Check Azure CLI login/query status",
        description="Report whether az is installed, az account show works, and optionally whether VM SKU query works for a region.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(machines_azure_status)
    machines_azure_status.add_argument("--region", help="Region for optional SKU query probe, such as uksouth")
    machines_azure_status.add_argument(
        "--sku-query",
        action="store_true",
        help="Also run az vm list-skus as a live query probe",
    )
    machines_import = machines_sub.add_parser(
        "import",
        help="Import exported machine profile",
        description="Import a machine profile created by aiplane hardware export-machine. Overrides are applied to the imported copy only.",
        formatter_class=HelpFormatter,
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
    )
    _profile_arg(machines_discover)
    machines_discover.add_argument("provider", choices=["azure"], help="Machine provider to discover")
    machines_discover.add_argument("--region", required=True, help="Provider region, such as uksouth")
    machines_discover.add_argument("--workload", help="Workload class filter")
    machines_discover.add_argument("--model", help="Configured model alias filter")
    machines_discover.add_argument("--runtime", help="Runtime name filter")
    machines_discover.add_argument("--limit", type=int, default=20, help="Maximum candidates to return")
    machines_import_azure = machines_sub.add_parser(
        "import-azure-sku",
        help="Import an Azure SKU as a machine",
        description="Create a self-managed machine entry from an Azure VM SKU hint. Verify exact quota/availability before provisioning.",
        formatter_class=HelpFormatter,
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
    )
    _profile_arg(stacks_list)
    stacks_show = stacks_sub.add_parser(
        "show",
        help="Show one stack",
        description="Show one stack definition.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(stacks_show)
    stacks_show.add_argument("name", help="Stack name")
    stacks_setup = stacks_sub.add_parser(
        "setup",
        help="Write or preview a stack",
        description="Persist an orchestrator + runtime + model + machine + access binding in hardware.yaml. Use --dry-run to preview without writing.",
        formatter_class=HelpFormatter,
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
        "--access",
        default="ssh_tunnel",
        help="Access mode, such as same_host, ssh_tunnel, lan_http, or gateway",
    )
    stacks_setup.add_argument(
        "--endpoint-policy",
        default="private",
        help="Endpoint policy label, such as private, vpn, or gateway",
    )
    stacks_setup.add_argument("--endpoint", help="Endpoint URL override")
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
        "--dry-run",
        action="store_true",
        help="Preview the stack without writing hardware.yaml",
    )
    stacks_plan = stacks_sub.add_parser(
        "plan",
        help="Plan a stack",
        description="Render the checks and actions needed to run a stack.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(stacks_plan)
    stacks_plan.add_argument("name", help="Stack name")
    stacks_doctor = stacks_sub.add_parser(
        "doctor",
        help="Check a stack",
        description="Check machine fit and runtime availability for a stack.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(stacks_doctor)
    stacks_doctor.add_argument("name", help="Stack name")
    stacks_export = stacks_sub.add_parser(
        "export",
        help="Export stack artifacts",
        description="Export IDE config or packaging artifacts for a stack endpoint.",
        formatter_class=HelpFormatter,
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
    )
    _profile_arg(env_show)
    env_list = env_sub.add_parser(
        "list",
        help="List available environment modes",
        description="List configured environment modes and mark the active one.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(env_list)
    env_active = env_sub.add_parser(
        "active",
        help="Show active environment mode",
        description="Show only the active environment mode, its config, and available modes.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(env_active)
    env_use = env_sub.add_parser(
        "use",
        help="Set active environment mode",
        description="Persist a new active environment mode in the profile environment.yaml file.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane environment use system\n  aiplane environment use venv\n  aiplane environment use conda\n  aiplane environment use docker",
    )
    _profile_arg(env_use)
    env_use.add_argument("mode", help="Configured mode name, such as system, venv, conda, or docker")
    env_plan = env_sub.add_parser(
        "plan",
        help="Render command execution plan",
        description="Show the command aiplane would run under the active environment mode.",
        formatter_class=HelpFormatter,
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
        default="text",
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
    )
    _profile_arg(benchmarks_list)
    benchmarks_doctor = benchmarks_sub.add_parser(
        "doctor",
        help="Check benchmark framework availability",
        description="Check which benchmark frameworks are available and which need install/manual setup.",
        formatter_class=HelpFormatter,
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

    models_cmd = _command(
        subparsers,
        "models",
        "List, inspect, test, pull, and benchmark approved models",
        "Work with the approved model catalog in the selected profile.",
        "Examples:\n  aiplane models list\n  aiplane models show MODEL_ALIAS\n  aiplane models test --dry-run MODEL_ALIAS\n  aiplane models benchmark --task all MODEL_ALIAS\n  aiplane models defaults\n  aiplane models use self_managed_model MODEL_ALIAS",
    )
    models_sub = models_cmd.add_subparsers(dest="models_command", required=True, metavar="command")
    models_defaults = models_sub.add_parser(
        "defaults",
        help="Show configured default model aliases",
        description="Show profile-level model defaults used by run and future routing commands.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(models_defaults)
    models_defaults.add_argument(
        "--group-by",
        choices=["none", "provider"],
        default="provider",
        help="Group defaults by provider; use none for a flat defaults list",
    )
    models_use = models_sub.add_parser(
        "use",
        help="Set a default model alias",
        description="Persist a model alias as a named default, such as chat_model, autocomplete_model, embedding_model, code_model, self_managed_model, completion_model, or reasoning_model.",
        formatter_class=HelpFormatter,
        epilog="Example:\n  aiplane models use self_managed_model MODEL_ALIAS",
    )
    _profile_arg(models_use)
    models_use.add_argument(
        "role",
        help="Default role name, such as chat_model, autocomplete_model, embedding_model, code_model, self_managed_model, completion_model, or reasoning_model",
    )
    models_use.add_argument("name", help="Existing model alias to set as the default for ROLE")
    models_add = models_sub.add_parser(
        "add",
        help="Add a model as a profile-owned entry in models.yaml",
        description="Create a profile-owned model entry. Most providers require a reviewed entry from models.discovered.yaml, resolved by --alias or by --provider/--model. The local_file provider is the exception: --provider local_file --model PATH writes a direct local artifact entry because there is no online discovery catalog.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  aiplane models add local_chat --alias ollama-llama3-2-3b --role chat --role analysis\n"
            "  aiplane models add local_chat --provider ollama --model llama3.2:3b --role chat --runtime ollama\n"
            "  aiplane models add local_gguf --provider local_file --model /models/mistral.Q4_K_M.gguf --runtime llamacpp --role chat\n"
            "  aiplane models add azure_chat --alias azure-openai-gpt-4o-prod --role chat --disable --dry-run"
        ),
    )
    _profile_arg(models_add)
    models_add.add_argument("name", help="Profile model entry name to write to models.yaml, such as local_chat")
    models_add.add_argument(
        "--alias",
        dest="discovered_name",
        help="Discovered model alias from models.discovered.yaml to use as the source",
    )
    models_add.add_argument(
        "--provider", help="Model source/provider name, such as ollama, huggingface, or azure_openai"
    )
    models_add.add_argument(
        "--model", dest="model_id", help="Provider/source-native model id or managed deployment name"
    )
    models_add.add_argument("--role", action="append", default=[], help="Usage role; can be repeated")
    models_add.add_argument(
        "--runtime",
        action="append",
        default=[],
        dest="supported_runtimes",
        help="Supported runtime for this entry; can be repeated",
    )
    models_add.add_argument(
        "--preferred-runtime", help="Preferred runtime when more than one runtime can serve the model"
    )
    models_add.add_argument("--notes", help="Human notes to store with the model entry")
    models_add.add_argument(
        "--set",
        dest="settings",
        action="append",
        default=[],
        help="Extra model metadata as key=value, such as min_ram_gb=16 or min_vram_gb=0; can be repeated",
    )
    models_add.add_argument("--disable", action="store_true", help="Create the entry disabled")
    models_add.add_argument(
        "--overwrite", action="store_true", help="Overwrite an existing profile-owned entry after review"
    )
    models_add.add_argument("--dry-run", action="store_true", help="Preview the entry without writing models.yaml")
    models_clone = models_sub.add_parser(
        "clone",
        help="Clone a model entry under a new profile name",
        description="Create a second profile-owned model entry from an existing discovered or profile-owned entry, optionally overriding roles, runtime metadata, notes, and other fields.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane models clone local_chat local_fast_draft --role completion --notes 'Fast draft model for local coding tasks'\n  aiplane models clone DISCOVERED_ENTRY_NAME local_chat --role chat --runtime ollama --dry-run",
    )
    _profile_arg(models_clone)
    models_clone.add_argument("source", help="Existing discovered or profile-owned model entry name")
    models_clone.add_argument("target", help="New profile model entry name")
    models_clone.add_argument("--role", action="append", default=None, help="Replacement usage role; can be repeated")
    models_clone.add_argument(
        "--runtime",
        action="append",
        default=None,
        dest="supported_runtimes",
        help="Replacement supported runtime; can be repeated",
    )
    models_clone.add_argument("--preferred-runtime", help="Replacement preferred runtime")
    models_clone.add_argument("--notes", help="Replacement human notes")
    models_clone.add_argument(
        "--set",
        dest="settings",
        action="append",
        default=[],
        help="Extra model metadata override as key=value; can be repeated",
    )
    clone_enabled = models_clone.add_mutually_exclusive_group()
    clone_enabled.add_argument("--enable", action="store_true", help="Mark the cloned entry enabled")
    clone_enabled.add_argument("--disable", action="store_true", help="Mark the cloned entry disabled")
    models_clone.add_argument(
        "--overwrite", action="store_true", help="Overwrite an existing profile-owned entry after review"
    )
    models_clone.add_argument("--dry-run", action="store_true", help="Preview the clone without writing models.yaml")
    models_remove = models_sub.add_parser(
        "remove",
        help="Remove a profile-owned model alias by name",
        description="Remove one profile-owned model alias from models.yaml. This does not remove discovered cache entries, provider caches, or model files from disk.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane models remove local_chat\n  aiplane models remove local_chat --dry-run\n  aiplane models clear-cache --provider local_file",
    )
    _profile_arg(models_remove)
    models_remove.add_argument("name", help="Profile-owned model alias to remove")
    models_remove.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    models_enable = models_sub.add_parser(
        "enable",
        help="Enable one model alias",
        description="Mark a model alias enabled in models.yaml so automatic selection/recommendation can use it.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(models_enable)
    models_enable.add_argument("name", help="Model alias to enable")
    models_disable = models_sub.add_parser(
        "disable",
        help="Disable one model alias",
        description="Mark a model alias disabled in models.yaml so automatic selection/recommendation skips it unless explicitly shown.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(models_disable)
    models_disable.add_argument("name", help="Model alias to disable")
    models_list = models_sub.add_parser(
        "list",
        help="List approved model aliases",
        description="List catalog entries with model provider, supported runtimes, configured runtime endpoints, roles, enabled state, and capability scores.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(models_list)
    models_list.add_argument(
        "--name-only",
        action="store_true",
        help="Print only model aliases (one per line) instead of full JSON",
    )
    models_list.add_argument(
        "--group-by",
        choices=[
            "none",
            "provider",
            "provider-kind",
            "source",
            "runtime",
            "model",
            "ownership",
        ],
        default="none",
        help="Group output by model provider, provider ownership/provider, model source/catalog, supported runtime, or provider-native model id",
    )
    models_list.add_argument(
        "--provider",
        help="Filter by model provider, such as ollama, huggingface, or huggingface_gguf",
    )
    models_list.add_argument(
        "--runtime",
        help="Filter by supported runtime, such as ollama, vllm, tgi, transformers",
    )
    models_list.add_argument(
        "--source",
        help="Filter by model source/catalog, such as ollama, huggingface, huggingface_gguf",
    )
    models_list.add_argument(
        "--role",
        action="append",
        default=[],
        help="Filter by usage role, such as chat, autocomplete, embedding, analysis, completion, generation, refactor; can be repeated",
    )
    models_list.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Require a capability threshold, e.g. code_generation>=4 or debugging>=3; can be repeated",
    )
    models_list.add_argument(
        "--min-capability-avg-score",
        type=float,
        help="Require a minimum average catalog capability score on the 0-5 scale",
    )
    models_list.add_argument(
        "--score-source",
        help="Filter by capability score source, such as configured or catalog_heuristic",
    )
    models_list.add_argument(
        "--min-benchmark-score",
        type=float,
        help="Require a latest saved aiplane benchmark average score on the 0-100 scale",
    )
    models_list.add_argument(
        "--require-benchmark",
        action="store_true",
        help="Show only models with at least one saved aiplane benchmark result",
    )
    models_list.add_argument(
        "--min-likes",
        type=float,
        help="Require a minimum provider catalog likes count when source metadata includes likes",
    )
    models_list.add_argument(
        "--min-downloads",
        type=float,
        help="Require a minimum provider catalog downloads count when source metadata includes downloads",
    )
    models_list.add_argument("--enabled-only", action="store_true", help="Show only enabled profile models")
    models_list.add_argument(
        "--self-managed-only",
        action="store_true",
        help="Show only self-managed models/runtimes",
    )
    models_list.add_argument(
        "--managed-service-only",
        action="store_true",
        help="Show only managed-service models if the profile defines any",
    )
    models_list.add_argument(
        "--fits-hardware",
        action="store_true",
        help="Filter to models whose minimum RAM/VRAM/vendor/API requirements fit the active hardware profile",
    )
    machine_filter_group = models_list.add_mutually_exclusive_group()
    machine_filter_group.add_argument(
        "--machine",
        help="Named machine profile from `aiplane machines list`; derives RAM, VRAM, GPU vendor, and accelerator filters",
    )
    machine_filter_group.add_argument(
        "--machine-file",
        type=Path,
        help="Portable machine JSON/YAML file from `aiplane hardware export-machine`; derives hardware fit filters without importing it",
    )
    machine_filter_group.add_argument(
        "--current-machine",
        action="store_true",
        help="Discover this machine now and derive RAM, VRAM, GPU vendor, and accelerator filters",
    )
    models_list.add_argument(
        "--ram-gb",
        type=float,
        metavar="GB",
        help="Available RAM in GB; filters out models whose configured/estimated minimum RAM exceeds this",
    )
    models_list.add_argument(
        "--vram-gb",
        type=float,
        metavar="GB",
        help="Available VRAM in GB; filters out models whose configured/estimated minimum VRAM exceeds this",
    )
    models_list.add_argument(
        "--min-parameters-b",
        type=float,
        metavar="B",
        help="Minimum model parameter count in billions, inferred from model ids such as 7b or 40B",
    )
    models_list.add_argument(
        "--max-parameters-b",
        type=float,
        metavar="B",
        help="Maximum model parameter count in billions, inferred from model ids such as 7b or 40B",
    )
    models_list.add_argument(
        "--gpu-vendor",
        choices=GPU_VENDOR_CHOICES,
        help="Available GPU vendor; filters out models with explicit incompatible vendor requirements",
    )
    models_list.add_argument(
        "--accelerator-api",
        choices=ACCELERATOR_API_CHOICES,
        help="Available accelerator API; filters out models with explicit incompatible API requirements",
    )
    models_list.add_argument(
        "--sort-by",
        choices=MODEL_SORT_CHOICES,
        default="name",
        help="Sort rows by entry name, capability score, role score, benchmark score, provider likes, provider downloads, combined provider popularity, or inferred parameter count",
    )
    models_list.add_argument(
        "--limit",
        type=int,
        help="Maximum number of rows to print after filtering and sorting",
    )
    models_show = models_sub.add_parser(
        "show",
        help="Show one model alias",
        description="Show one model entry, provider config, and capability metadata.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(models_show)
    models_show.add_argument("name", help="Model alias from models.yaml, for example MODEL_ALIAS")
    models_doctor = models_sub.add_parser(
        "doctor",
        help="Check model/provider readiness",
        description="Check whether enabled models are usable now: provider reachable, model pulled/listed, keys present.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(models_doctor)
    models_pull = models_sub.add_parser(
        "pull",
        help="Plan or run model download",
        description="Plan a source/catalog-oriented model download. Ollama aliases can be pulled directly; Hugging Face downloads are rendered and can be delegated to runtime helpers.",
        formatter_class=HelpFormatter,
    )
    _profile_arg(models_pull)
    models_pull.add_argument(
        "name",
        nargs="?",
        help="Configured model alias, for example MODEL_ALIAS or MODEL_ALIAS",
    )
    models_pull.add_argument(
        "--source",
        help="Model source/catalog, such as ollama, huggingface, huggingface_gguf, local_file",
    )
    models_pull.add_argument(
        "--model-id",
        help="Source-native model id when NAME is omitted, such as provider/native-model-id",
    )
    models_pull.add_argument(
        "--for-runtime",
        help="Runtime compatibility intent, such as vllm, tgi, transformers, or llamacpp",
    )
    models_pull.add_argument("--file", help="Optional file inside a source repo, useful for GGUF downloads")
    models_pull.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved pull/download command without executing it",
    )
    models_refresh = models_sub.add_parser(
        "refresh",
        help="Refresh model-provider model catalog entries",
        description="Refresh the editable profile catalog from model providers. Providers are model catalogs or artifact sources such as Ollama Library, Hugging Face Hub, GGUF sources, Azure Speech voices, or local files. Runtimes such as vLLM, TGI, llama.cpp, Transformers, and LM Studio are execution engines and are managed under aiplane runtimes. Refresh is online-first where a source adapter exists, then falls back to the profile catalog for sources without an online adapter or temporarily unavailable APIs.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane models refresh --dry-run\n  aiplane models refresh --provider huggingface --query text-generation --limit 500 --dry-run\n  aiplane models refresh --provider huggingface --reset-cache --dry-run\n  aiplane models refresh --limit 100 --provider-limit huggingface=500 --provider-limit ollama=500 --dry-run\n  aiplane models refresh --provider huggingface --limit 10 --dry-run --verbose\n  aiplane models refresh --disable-new",
    )
    _profile_arg(models_refresh)
    models_refresh.add_argument(
        "--provider",
        default="all",
        help="Model provider to refresh, or all to refresh all known model providers",
    )
    models_refresh.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which models would be added without writing models.yaml",
    )
    models_refresh.add_argument(
        "--disable-new",
        action="store_true",
        help="Write newly imported model entries as disabled; by default they are enabled",
    )
    models_refresh.add_argument(
        "--reset-cache",
        action="store_true",
        help="Clear existing refresh/import entries for the refreshed provider(s) before pulling a fresh catalog",
    )
    models_refresh.add_argument(
        "--include-empty-providers",
        action="store_true",
        help="Ignored legacy flag; refresh uses configured model providers even when the model cache is empty",
    )
    models_refresh.add_argument(
        "--query",
        help="Optional search query passed to online provider catalog adapters",
    )
    models_refresh.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Default maximum model ids to read per provider catalog",
    )
    models_refresh.add_argument(
        "--provider-limit",
        action="append",
        default=[],
        metavar="PROVIDER=COUNT",
        help="Override --limit for one model provider; can be repeated, for example --provider-limit huggingface=25 --provider-limit ollama=500",
    )
    models_refresh.add_argument(
        "--verbose",
        action="store_true",
        help="Include per-model change rows. By default refresh prints provider-level counts only.",
    )
    models_clear_cache = models_sub.add_parser(
        "clear-cache",
        help="Remove model catalog refresh/import aliases",
        description=(
            "Remove discovery refresh/import entries from models.discovered.yaml plus matching profile-owned review "
            "entries from models.yaml by default. Use --keep-curated to remove only discovered/imported entries. "
            "Use --dry-run first to preview."
        ),
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  aiplane models clear-cache --dry-run\n"
            "  aiplane models clear-cache --provider huggingface --dry-run\n"
            "  aiplane models clear-cache --provider huggingface --keep-curated --dry-run\n"
            "  aiplane models clear-cache"
        ),
    )
    _profile_arg(models_clear_cache)
    models_clear_cache.add_argument(
        "--provider",
        help="Only clear aliases from this model provider, such as huggingface or huggingface_gguf",
    )
    curated_clear = models_clear_cache.add_mutually_exclusive_group()
    curated_clear.add_argument(
        "--include-curated",
        action="store_true",
        default=True,
        help="Remove profile-owned review entries from models.yaml too. This is the default and is kept for explicit confirmation.",
    )
    curated_clear.add_argument(
        "--keep-curated",
        action="store_true",
        help="Keep profile-owned entries in models.yaml; remove only discovered/imported entries.",
    )
    models_clear_cache.add_argument(
        "--dry-run",
        action="store_true",
        help="Show entry counts that would be removed without writing models.yaml",
    )
    models_promote = models_sub.add_parser(
        "promote",
        help="Promote a discovered model entry into models.yaml",
        description="Copy a reviewed discovered/imported entry from models.discovered.yaml into profile-owned models.yaml. The discovered copy is kept by default and the profile-owned entry records discovered_entry for traceability.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --dry-run\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat --keep-discovered\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat --overwrite"
        ),
    )
    _profile_arg(models_promote)
    models_promote.add_argument("name", help="Discovered model entry from models.discovered.yaml")
    models_promote.add_argument(
        "--as",
        dest="new_name",
        help="Promote under a cleaner profile-owned entry name instead of reusing the discovered entry name",
    )
    models_promote.add_argument(
        "--keep-discovered",
        dest="keep_discovered",
        action="store_true",
        default=True,
        help="Keep the discovered entry after writing the profile-owned copy. This is the default and is kept for explicit scripts.",
    )
    models_promote.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing profile-owned target entry after review. Without this, promotion refuses profile-owned entry collisions.",
    )
    models_promote.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the promotion without editing files",
    )
    models_test = models_sub.add_parser(
        "test",
        help="Run a small prompt against one model",
        description="Send a simple analysis/completion/write prompt to a model, or preview the prompt with --dry-run.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane models test --dry-run MODEL_ALIAS\n  aiplane models test --task analysis --target src/aiplane/model_catalog.py MODEL_ALIAS",
    )
    _profile_arg(models_test)
    models_test.add_argument(
        "--task",
        choices=["analysis", "completion", "write"],
        default="analysis",
        help="Smoke prompt type to run",
    )
    models_test.add_argument(
        "--target",
        help="Optional file path used as prompt context for analysis/completion",
    )
    models_test.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling the provider",
    )
    models_test.add_argument("name", help="Model alias to test")
    models_benchmark = models_sub.add_parser(
        "benchmark",
        help="Run smoke benchmark tasks",
        description="Run small analysis/completion/generation/reasoning tasks and save a benchmark JSON unless --no-save is used.",
        formatter_class=HelpFormatter,
        epilog="Examples:\n  aiplane models benchmark MODEL_ALIAS\n  aiplane models benchmark --task completion --no-save MODEL_ALIAS\n  aiplane models benchmark --dry-run MODEL_ALIAS",
    )
    _profile_arg(models_benchmark)
    models_benchmark.add_argument(
        "--task",
        default="all",
        help="Benchmark task name to run, or all. Built-in tasks: analysis, completion, generation, reasoning",
    )
    models_benchmark.add_argument(
        "--spec",
        help="Optional JSON/YAML benchmark spec with custom tasks and evaluators",
    )
    models_benchmark.add_argument(
        "--environment",
        choices=["system", "venv", "conda", "docker"],
        help="Environment mode used for custom evaluator commands; defaults to the active profile environment",
    )
    models_benchmark.add_argument("--timeout-seconds", type=int, help="Timeout for each custom evaluator command")
    models_benchmark.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview benchmark prompts and evaluator commands without calling the provider",
    )
    models_benchmark.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write benchmark JSON under .aiplane/benchmarks",
    )
    models_benchmark.add_argument(
        "--model",
        dest="model_name",
        help="Model alias; alternative to the positional name",
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
        "--timeout-seconds", type=int, help="Override provider request timeout for this code task"
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
        "--timeout-seconds", type=int, help="Override provider request timeout for this code task"
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
    code_write.add_argument("--timeout-seconds", type=int, help="Override provider request timeout for this code task")

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
        "Launch provider-native chat for a model",
        "Resolve a model alias and delegate to the provider-native chat CLI. Currently supports local Ollama models.",
        "Examples:\n  aiplane chat --model MODEL_ALIAS --dry-run\n  aiplane chat --model MODEL_ALIAS",
    )
    _profile_arg(chat_cmd)
    chat_cmd.add_argument(
        "--model",
        help="Model alias to launch. If omitted, uses the profile chat_model default",
    )
    chat_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the provider-native command without running it",
    )

    deploy_cmd = _command(
        subparsers,
        "deploy",
        "Plan/check/apply remote deployment targets",
        "Work with configured cloud/shared deployment targets. Apply is guarded and intentionally narrow.",
        "Examples:\n  aiplane deploy list\n  aiplane deploy plan --target aks_gpu_pool\n  aiplane deploy doctor --target aks_gpu_pool\n  aiplane deploy apply --target aks_gpu_pool",
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
            "  aiplane providers add my_gateway --ownership managed_service --endpoint-family custom_openai_compatible --catalog-adapter profile_catalog --auth-method bearer --api-key-env MY_GATEWAY_API_KEY"
        ),
    )
    _profile_arg(providers_endpoint_types)
    providers_models = providers_sub.add_parser(
        "models",
        help="List catalog provider models",
        description="List known model ids for a model provider. Online source discovery will be added provider by provider; currently this reports configured aiplane catalog entries.",
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
        help="Action name to explain, such as cloud_escalation or write_file",
    )

    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    profiles_dir = Path(args.profiles_dir).expanduser().resolve() if args.profiles_dir else None
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
            "current_profile_path": str(profile_root / current_profile) if current_profile else None,
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
            if profile_exists:
                profile = load_profile(args.name, workspace, profiles_dir=profiles_dir)
                validation = _validate_profile(profile)
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
                            discovery = catalog.refresh_all(
                                write=write,
                                enable=not args.disable_new,
                                query=args.query,
                                limit=args.limit,
                                provider_limits=provider_limits,
                                progress=progress,
                                verbose=args.verbose,
                            )
                        else:
                            provider_limit = int(provider_limits.get(args.provider, args.limit))
                            discovery = catalog.refresh(
                                args.provider,
                                write=write,
                                enable=not args.disable_new,
                                query=args.query,
                                limit=provider_limit,
                                progress=progress,
                                verbose=args.verbose,
                            )
                    finally:
                        if progress:
                            progress("done", "", "")
            elif not args.no_discovery or not args.no_hardware_discovery:
                skipped = "profile does not exist yet; rerun without --dry-run to create it before discovery"
                if not args.no_discovery:
                    discovery = {"skipped": True, "reason": skipped}
                if not args.no_hardware_discovery:
                    hardware = {"skipped": True, "reason": skipped}
            print(
                _json(
                    {
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
                        "validation": validation,
                        "next_steps": _profile_bootstrap_next_steps(args.name, not args.no_discovery, args.dry_run),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
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

    effective_profile = resolve_profile_name(requested_profile, profiles_dir=profiles_dir)

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
            print(_json(manager.show(), indent=2, sort_keys=True))
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
            print(_json(manager.clear_selection(dry_run=args.dry_run), indent=2, sort_keys=True))
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
            print(
                _json(
                    manager.azure_status(region=args.region, run_sku_probe=args.sku_query),
                    indent=2,
                )
            )
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
            print(
                _json(
                    manager.discover_azure(
                        args.region,
                        workload=args.workload,
                        model=args.model,
                        runtime=args.runtime,
                        limit=args.limit,
                    ),
                    indent=2,
                )
            )
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
                        endpoint_policy=args.endpoint_policy,
                        endpoint=args.endpoint,
                        limits=_parse_settings(args.limit),
                        tools=_parse_settings(args.tool),
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
            if args.format == "text":
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
        catalog = ModelCatalog(profile)
        if args.models_command == "defaults":
            summary = catalog.default_summary()
            if args.group_by != "none":
                summary = {
                    "group_by": args.group_by,
                    "defaults": group_rows(summary["defaults"], args.group_by),
                }
            print(_json(summary, indent=2))
            return 0
        if args.models_command == "use":
            print(_json(catalog.set_default(args.role, args.name), indent=2))
            return 0
        if args.models_command == "add":
            print(
                _json(
                    catalog.add_model(
                        args.name,
                        provider=args.provider,
                        model_id=args.model_id,
                        discovered_name=args.discovered_name,
                        roles=args.role,
                        supported_runtimes=args.supported_runtimes,
                        preferred_runtime=args.preferred_runtime,
                        enabled=not args.disable,
                        notes=args.notes,
                        settings=_parse_settings(args.settings),
                        write=not args.dry_run,
                        overwrite=args.overwrite,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.models_command == "clone":
            enabled = True if args.enable else False if args.disable else None
            print(
                _json(
                    catalog.clone_model(
                        args.source,
                        args.target,
                        roles=args.role,
                        supported_runtimes=args.supported_runtimes,
                        preferred_runtime=args.preferred_runtime,
                        enabled=enabled,
                        notes=args.notes,
                        settings=_parse_settings(args.settings),
                        write=not args.dry_run,
                        overwrite=args.overwrite,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.models_command == "remove":
            print(_json(catalog.remove_model(args.name, write=not args.dry_run), indent=2))
            return 0
        if args.models_command == "enable":
            print(_json(catalog.set_enabled(args.name, True), indent=2))
            return 0
        if args.models_command == "disable":
            print(_json(catalog.set_enabled(args.name, False), indent=2))
            return 0
        if args.models_command == "list":
            filters = model_filter_args(args)
            if args.fits_hardware:
                filters.update(_active_hardware_model_filters(profile))
            filters = merge_machine_model_filters(
                profile,
                filters,
                machine=args.machine,
                machine_file=args.machine_file,
                current_machine=args.current_machine,
            )
            rows = catalog.sort_rows(
                catalog.filter(filters),
                sort_by=args.sort_by,
                roles=filters.get("roles", []),
            )
            if args.limit is not None:
                rows = rows[: args.limit]
            if args.name_only:
                if args.group_by != "none":
                    raise ValueError("--name-only cannot be combined with --group-by")
                print("\n".join([str(row.get("name") or "") for row in rows]))
            elif args.group_by == "none":
                print(_json(rows, indent=2))
            else:
                print(_json(group_model_rows(profile, rows, args.group_by), indent=2))
            return 0
        if args.models_command == "show":
            print(_json(catalog.show(args.name), indent=2, sort_keys=True))
            return 0
        if args.models_command == "doctor":
            print(
                _json(
                    [status.__dict__ for status in catalog.doctor()],
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.models_command == "pull":
            if args.source or args.model_id or args.dry_run or args.for_runtime or args.file:
                plan = catalog.pull_plan(
                    args.name,
                    source=args.source,
                    model_id=args.model_id,
                    for_runtime=args.for_runtime,
                    file=args.file,
                )
                if args.dry_run:
                    print(_json(plan, indent=2))
                    return 0
                if plan["source"] == "ollama" and args.name:
                    print(catalog.pull(args.name))
                    return 0
                raise ValueError(
                    "non-Ollama source downloads are planned in this command; use --dry-run or aiplane runtimes pull to execute through a runtime helper"
                )
            print(catalog.pull(args.name))
            return 0
        if args.models_command == "refresh":
            write = not args.dry_run
            provider_limits = _parse_provider_limits(args.provider_limit)
            reset_cache_result = None
            if args.reset_cache:
                if args.provider == "all":
                    reset_results = {}
                    skipped = []
                    for provider_row in ProviderRegistry(profile).list(include_empty=True):
                        provider_name = str(provider_row.get("name", ""))
                        if provider_name == "local_file":
                            skipped.append(
                                {"name": provider_name, "reason": "local_file has no remote catalog to repopulate"}
                            )
                            continue
                        if provider_row.get("enabled") is False:
                            skipped.append({"name": provider_name, "reason": "model provider is disabled"})
                            continue
                        reset_results[provider_name] = catalog.clear_imported(
                            provider_name=provider_name,
                            write=write,
                            include_curated=True,
                        )
                    reset_cache_result = {
                        "name": "model_catalog_refresh_reset_cache",
                        "write": write,
                        "provider": "all",
                        "include_curated": True,
                        "results": reset_results,
                        "skipped": skipped,
                    }
                elif args.provider == "local_file":
                    reset_cache_result = {
                        "name": "model_catalog_refresh_reset_cache",
                        "write": write,
                        "provider": "local_file",
                        "include_curated": True,
                        "skipped": [{"name": "local_file", "reason": "local_file has no remote catalog to repopulate"}],
                    }
                else:
                    reset_cache_result = catalog.clear_imported(
                        provider_name=args.provider,
                        write=write,
                        include_curated=True,
                    )
            progress = _refresh_progress()
            try:
                if args.provider == "all":
                    result = catalog.refresh_all(
                        write=write,
                        enable=not args.disable_new,
                        include_empty_providers=args.include_empty_providers,
                        query=args.query,
                        limit=args.limit,
                        provider_limits=provider_limits,
                        progress=progress,
                        verbose=args.verbose,
                    )
                else:
                    provider_limit = int(provider_limits.get(args.provider, args.limit))
                    result = catalog.refresh(
                        args.provider,
                        write=write,
                        enable=not args.disable_new,
                        query=args.query,
                        limit=provider_limit,
                        progress=progress,
                        verbose=args.verbose,
                    )
            finally:
                if progress:
                    progress("done", "", "")
            if reset_cache_result is not None:
                result["reset_cache"] = reset_cache_result
            print(_json(_refresh_cli_payload(result, verbose=args.verbose), indent=2))
            return 0
        if args.models_command == "clear-cache":
            print(
                _json(
                    catalog.clear_imported(
                        provider_name=args.provider,
                        write=not args.dry_run,
                        include_curated=not args.keep_curated,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.models_command == "promote":
            print(
                _json(
                    catalog.promote_generated(
                        args.name,
                        new_name=args.new_name,
                        write=not args.dry_run,
                        keep_discovered=args.keep_discovered,
                        overwrite=args.overwrite,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.models_command == "benchmark":
            model_name = args.model_name or args.name
            if not model_name:
                raise ValueError("benchmark requires a model name or --model")
            spec_path = Path(args.spec).resolve() if args.spec else None
            result = BenchmarkRunner(profile).run(
                model_name,
                task=args.task,
                dry_run=args.dry_run,
                save=not args.no_save,
                spec_path=spec_path,
                environment_mode=args.environment,
                timeout_seconds=args.timeout_seconds,
            )
            print(_json(result, indent=2))
            return 0
        target = Path(args.target).resolve() if args.target else None
        if target is not None and not PolicyEngine(profile).path_decision(target).allowed:
            raise PermissionError("target escapes workspace boundary")
        result = catalog.test_prompt(args.name, args.task, target, dry_run=args.dry_run)
        print(result.text)
        return 0

    if args.command == "code":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        runner = CodeTaskRunner(profile, AuditLogger(profile))
        if args.code_command == "analyze":
            result = runner.analyze(
                args.model, Path(args.target), dry_run=args.dry_run, timeout_seconds=args.timeout_seconds
            )
        elif args.code_command == "complete":
            result = runner.complete(
                args.model, Path(args.target), args.line, dry_run=args.dry_run, timeout_seconds=args.timeout_seconds
            )
        else:
            result = runner.write(args.model, args.task, dry_run=args.dry_run, timeout_seconds=args.timeout_seconds)
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
        output = IntegrationManager(profile).run_chat(args.model, dry_run=args.dry_run)
        if output:
            print(output)
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
        if args.deploy_command == "plan":
            print(_json(manager.plan(args.target), indent=2, sort_keys=True))
            return 0
        if args.deploy_command == "doctor":
            print(_json(manager.doctor(args.target), indent=2, sort_keys=True))
            return 0
        print(_json(manager.apply(args.target, yes=True), indent=2, sort_keys=True))
        return 0

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
            print(_json(catalog.list(include_gui=args.include_gui), indent=2))
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
            if args.runtimes_command == "install" and not args.dry_run:
                prerequisites = catalog.prerequisites(args.runtime)
                if not prerequisites.get("ok"):
                    print(_json(prerequisites, indent=2))
                    return 2
            substrate = _runtime_helper_substrate(profile, args.runtime, args.substrate)
            completed = _run_provider_helper(
                args.runtime,
                helper_action,
                effective_profile,
                args.model,
                substrate=substrate,
                dry_run=args.dry_run,
            )
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
) -> subprocess.CompletedProcess[str]:
    helper = Path(__file__).resolve().parents[2] / "scripts" / "provider_helper.sh"
    if not helper.exists():
        raise FileNotFoundError(f"provider helper not found: {helper}")
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
    return subprocess.run(command, cwd=helper.parents[1], text=True, capture_output=True, check=False)


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
        "model_defaults": profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {},
        "models": [
            {"name": name, **model} for name, model in _dict_value(models).items() if bool(model.get("enabled", True))
        ],
        "targets": {
            "default": profile.targets.get("default") if isinstance(profile.targets, dict) else None,
            "config": _dict_value(targets).get(str(profile.targets.get("default")), {})
            if isinstance(profile.targets, dict)
            else {},
        },
        "repository": profile.repository,
    }


def _refresh_cli_payload(result: dict[str, object], verbose: bool) -> dict[str, object]:
    if verbose or not isinstance(result.get("results"), dict):
        return result
    payload = dict(result)
    results = result.get("results", {})
    provider_summary = []
    if isinstance(results, dict):
        for provider, row in sorted(results.items()):
            if not isinstance(row, dict):
                continue
            provider_summary.append(
                {
                    "provider": str(provider),
                    "status": row.get("status"),
                    "ownership": row.get("ownership"),
                    "source_contacted": row.get("source_contacted"),
                    "source_models_returned": row.get("source_models_returned"),
                    "source_models_already_profiled": row.get("source_models_already_profiled"),
                    "source_models_to_import": row.get("source_models_to_import"),
                    "source_models_to_update": row.get("source_models_to_update"),
                    "model_changes_count": row.get("model_changes_count"),
                    "changes": row.get("changes", {}),
                    "error": row.get("error"),
                }
            )
    payload.pop("results", None)
    payload["provider_summary"] = provider_summary
    return payload


def _active_hardware_model_filters(profile) -> dict[str, object]:
    machine = HardwareManager(profile).machine()
    memory = machine.get("memory", {}) if isinstance(machine.get("memory"), dict) else {}
    gpu = machine.get("gpu", {}) if isinstance(machine.get("gpu"), dict) else {}
    filters: dict[str, object] = {}
    ram = memory.get("ram_gb") or memory.get("unified_memory_gb")
    if ram is not None:
        filters["max_min_ram_gb"] = ram
    vram = gpu.get("vram_gb") or memory.get("unified_memory_gb")
    if vram is not None:
        filters["max_min_vram_gb"] = vram
    vendor = gpu.get("vendor")
    if vendor:
        filters["gpu_vendor"] = str(vendor)
    accelerator_apis = machine.get("accelerator_apis")
    if isinstance(accelerator_apis, list) and accelerator_apis:
        filters["accelerator_api"] = str(accelerator_apis[0])
    return filters


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
            key=lambda row: (0 if row["required"] == "mandatory" else 1, row["status"] != "installed", row["name"]),
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
                "status": "ready"
                if item.get("ok")
                else (f"missing {missing_count}" if missing_count else "needs setup"),
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


def _refresh_progress():
    if not sys.stderr.isatty():
        return None

    def report(event: str, provider: str, detail: str) -> None:
        if event == "done":
            print("\r" + " " * 100 + "\r", file=sys.stderr, end="", flush=True)
            return
        label = {
            "connecting": "connecting",
            "succeeded": "succeeded",
            "failed": "failed",
        }.get(event, event)
        message = f"refresh: {label} {provider}"
        if detail:
            message += f" - {detail}"
        print("\r" + message[:100].ljust(100), file=sys.stderr, end="", flush=True)

    return report


def _parse_provider_limits(values: list[str]) -> dict[str, int]:
    limits: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("provider limit must use PROVIDER=COUNT, for example huggingface=25")
        provider, raw_count = value.split("=", 1)
        provider = provider.strip()
        if not provider:
            raise ValueError("provider limit is missing provider name")
        try:
            count = int(raw_count.strip())
        except ValueError as exc:
            raise ValueError(f"provider limit for {provider} must be an integer") from exc
        if count < 1:
            raise ValueError(f"provider limit for {provider} must be at least 1")
        limits[provider] = count
    return limits


def _parse_settings(settings: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for setting in settings:
        if "=" not in setting:
            raise ValueError(f"invalid setting {setting!r}; expected key=value")
        key, value = setting.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid setting {setting!r}; key is empty")
        parsed[key] = _parse_setting_value(value.strip())
    return parsed


def _parse_setting_value(value: str) -> object:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
