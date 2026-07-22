from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .benchmarks import BenchmarkRunner
from .cli_support import parse_provider_limits, parse_settings, refresh_progress
from .hardware import HardwareManager
from .machine_model_filters import merge_machine_model_filters
from .model_catalog import ModelCatalog
from .model_filters import (
    ACCELERATOR_API_CHOICES,
    GPU_VENDOR_CHOICES,
    MODEL_SORT_CHOICES,
    model_filter_args,
)
from .model_output import group_model_rows, group_rows
from .models import Profile
from .policy import PolicyEngine
from .providers import ProviderRegistry

JsonDumps = Callable[..., str]
ProfileArg = Callable[[argparse.ArgumentParser], None]


def add_models_parser(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: ProfileArg,
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    models_cmd = command_factory(
        subparsers,
        "models",
        "List, inspect, test, pull, and benchmark approved models",
        "Work with the approved model catalog in the selected profile.",
        "Examples:\n  aiplane models list\n  aiplane models show MODEL_ALIAS\n  aiplane models test --dry-run MODEL_ALIAS\n  aiplane models benchmark --task all MODEL_ALIAS\n  aiplane models defaults\n  aiplane models use self_managed_model MODEL_ALIAS\n  aiplane models clear-cache --dry-run",
    )
    models_sub = models_cmd.add_subparsers(dest="models_command", required=True, metavar="command")
    models_defaults = models_sub.add_parser(
        "defaults",
        help="Show configured default model aliases",
        description="Show profile-level model defaults used by run and future routing commands.",
        formatter_class=formatter_class,
    )
    profile_arg(models_defaults)
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
        formatter_class=formatter_class,
        epilog="Example:\n  aiplane models use self_managed_model MODEL_ALIAS",
    )
    profile_arg(models_use)
    models_use.add_argument(
        "role",
        help="Default role name, such as chat_model, autocomplete_model, embedding_model, code_model, self_managed_model, completion_model, or reasoning_model",
    )
    models_use.add_argument("name", help="Existing model alias to set as the default for ROLE")
    models_add = models_sub.add_parser(
        "add",
        help="Add a model as a profile-owned entry in models.yaml",
        description="Create a profile-owned model entry. Most providers require a reviewed entry from models.discovered.yaml, resolved by --alias or by --provider/--model. The local_file provider is the exception: --provider local_file --model PATH writes a direct local artifact entry because there is no online discovery catalog.",
        formatter_class=formatter_class,
        epilog=(
            "Examples:\n"
            "  aiplane models add local_chat --alias ollama-llama3-2-3b --role chat --role analysis\n"
            "  aiplane models add local_chat --provider ollama --model llama3.2:3b --role chat --runtime ollama\n"
            "  aiplane models add local_gguf --provider local_file --model /models/mistral.Q4_K_M.gguf --runtime llamacpp --role chat\n"
            "  aiplane models add azure_chat --alias azure-openai-gpt-4o-prod --role chat --disable --dry-run"
        ),
    )
    profile_arg(models_add)
    models_add.add_argument(
        "name",
        help="Profile model entry name to write to models.yaml, such as local_chat",
    )
    models_add.add_argument(
        "--alias",
        dest="discovered_name",
        help="Discovered model alias from models.discovered.yaml to use as the source",
    )
    models_add.add_argument(
        "--provider",
        help="Model source/provider name, such as ollama, huggingface, or azure_openai",
    )
    models_add.add_argument(
        "--model",
        dest="model_id",
        help="Provider/source-native model id or managed deployment name",
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
        "--preferred-runtime",
        help="Preferred runtime when more than one runtime can serve the model",
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
        "--overwrite",
        action="store_true",
        help="Overwrite an existing profile-owned entry after review",
    )
    models_add.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the entry without writing models.yaml",
    )
    models_clone = models_sub.add_parser(
        "clone",
        help="Clone a model entry under a new profile name",
        description="Create a second profile-owned model entry from an existing discovered or profile-owned entry, optionally overriding roles, runtime metadata, notes, and other fields.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane models clone local_chat local_fast_draft --role completion --notes 'Fast draft model for local coding tasks'\n  aiplane models clone DISCOVERED_ENTRY_NAME local_chat --role chat --runtime ollama --dry-run",
    )
    profile_arg(models_clone)
    models_clone.add_argument("source", help="Existing discovered or profile-owned model entry name")
    models_clone.add_argument("target", help="New profile model entry name")
    models_clone.add_argument(
        "--role",
        action="append",
        default=None,
        help="Replacement usage role; can be repeated",
    )
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
        "--overwrite",
        action="store_true",
        help="Overwrite an existing profile-owned entry after review",
    )
    models_clone.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the clone without writing models.yaml",
    )
    models_remove = models_sub.add_parser(
        "remove",
        help="Remove a profile-owned model alias by name",
        description="Remove one profile-owned model alias from models.yaml. This does not remove discovered cache entries, provider caches, or model files from disk.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane models remove local_chat\n  aiplane models remove local_chat --dry-run\n  aiplane models clear-cache --provider local_file",
    )
    profile_arg(models_remove)
    models_remove.add_argument("name", help="Profile-owned model alias to remove")
    models_remove.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    models_enable = models_sub.add_parser(
        "enable",
        help="Enable one model alias",
        description="Mark a model alias enabled in models.yaml so automatic selection/recommendation can use it.",
        formatter_class=formatter_class,
    )
    profile_arg(models_enable)
    models_enable.add_argument("name", help="Model alias to enable")
    models_disable = models_sub.add_parser(
        "disable",
        help="Disable one model alias",
        description="Mark a model alias disabled in models.yaml so automatic selection/recommendation skips it unless explicitly shown.",
        formatter_class=formatter_class,
    )
    profile_arg(models_disable)
    models_disable.add_argument("name", help="Model alias to disable")
    models_list = models_sub.add_parser(
        "list",
        help="List approved model aliases",
        description="List catalog entries with model provider, supported runtimes, configured runtime endpoints, roles, enabled state, and capability scores.",
        formatter_class=formatter_class,
    )
    profile_arg(models_list)
    models_list.add_argument(
        "--identity",
        choices=["both", "alias", "model"],
        default="both",
        help=(
            "Choose model identity output: both shows aliases and provider-native model ids; "
            "alias or model prints one selected identity per line"
        ),
    )
    models_list.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. JSON is full payload; text is compact table view.",
    )
    models_list.add_argument(
        "--verbosity",
        type=int,
        choices=[0, 1, 2],
        default=None,
        help="Output detail level for text mode: 0=table, 1+ full payload.",
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
    models_list.add_argument("--alias", help="Filter by exact profile/discovered model alias")
    models_list.add_argument("--model-id", help="Filter by exact provider-native model id")
    models_list.add_argument(
        "--provider",
        help="Filter by model provider, such as ollama, huggingface, or huggingface_gguf",
    )
    models_list.add_argument(
        "--runtime",
        "--runner",
        dest="runtime",
        help="Filter by supported runtime/runner, such as ollama, vllm, tgi, transformers",
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
        "--property",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="Filter by an exact raw model property; supports dotted paths and can be repeated, e.g. quantization=q4 or source_metadata.pipeline_tag=text-generation",
    )
    models_list.add_argument(
        "--catalog-cache",
        choices=["auto", "off", "rebuild"],
        default="auto",
        help="Use the generated enriched catalog, bypass it, or rebuild it before querying",
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
        "--fits-machine",
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
    models_catalog_cache = models_sub.add_parser(
        "catalog-cache",
        help="Inspect, rebuild, or clear the generated enriched model catalog",
        description="Manage the disposable query-ready catalog generated from models.yaml, models.discovered.yaml, runtime metadata, and benchmark summaries.",
        formatter_class=formatter_class,
    )
    profile_arg(models_catalog_cache)
    models_catalog_cache.add_argument("action", choices=["status", "rebuild", "clear"])
    models_show = models_sub.add_parser(
        "show",
        help="Show one model alias",
        description="Show one model entry, provider config, and capability metadata.",
        formatter_class=formatter_class,
    )
    profile_arg(models_show)
    models_show.add_argument("name", help="Model alias from models.yaml, for example MODEL_ALIAS")
    models_doctor = models_sub.add_parser(
        "doctor",
        help="Check model/provider readiness",
        description="Check whether enabled models are usable now: provider reachable, model pulled/listed, keys present.",
        formatter_class=formatter_class,
    )
    profile_arg(models_doctor)
    models_pull = models_sub.add_parser(
        "pull",
        help="Plan or run model download",
        description="Plan a source/catalog-oriented model download. Ollama aliases can be pulled directly; Hugging Face downloads are rendered and can be delegated to runtime helpers.",
        formatter_class=formatter_class,
    )
    profile_arg(models_pull)
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
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane models refresh --dry-run\n  aiplane models refresh --provider huggingface --query text-generation --limit 500 --dry-run\n  aiplane models refresh --provider huggingface --reset-cache --dry-run\n  aiplane models refresh --limit 100 --provider-limit huggingface=500 --provider-limit ollama=500 --dry-run\n  aiplane models refresh --provider huggingface --limit 10 --dry-run --verbosity 1\n  aiplane models refresh --provider huggingface --limit 10 --dry-run --verbosity 2\n  aiplane models refresh --disable-new",
    )
    profile_arg(models_refresh)
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
        "--verbosity",
        type=int,
        choices=[0, 1, 2],
        default=0,
        help="Output detail: 0=top-level summary, 1=add provider_summary, 2=full provider results including per-model change rows",
    )
    models_clear_cache = models_sub.add_parser(
        "clear-cache",
        help="Remove model catalog refresh/import aliases",
        description=(
            "Remove discovery refresh/import entries from models.discovered.yaml plus matching profile-owned review "
            "entries from models.yaml by default. Use --keep-curated to remove only discovered/imported entries. "
            "Use --dry-run first to preview."
        ),
        formatter_class=formatter_class,
        epilog=(
            "Examples:\n"
            "  aiplane models clear-cache --dry-run\n"
            "  aiplane models clear-cache --provider huggingface --dry-run\n"
            "  aiplane models clear-cache --provider huggingface --keep-curated --dry-run\n"
            "  aiplane models clear-cache"
        ),
    )
    profile_arg(models_clear_cache)
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
        formatter_class=formatter_class,
        epilog=(
            "Examples:\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --dry-run\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat --keep-discovered\n"
            "  aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat --overwrite"
        ),
    )
    profile_arg(models_promote)
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
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane models test --dry-run MODEL_ALIAS\n  aiplane models test --task analysis --target src/aiplane/model_catalog.py MODEL_ALIAS",
    )
    profile_arg(models_test)
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
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane models benchmark MODEL_ALIAS\n  aiplane models benchmark --task completion --no-save MODEL_ALIAS\n  aiplane models benchmark --dry-run MODEL_ALIAS",
    )
    profile_arg(models_benchmark)
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
    models_benchmark.add_argument("name", help="Model alias to benchmark")


def handle_models_command(
    args: argparse.Namespace,
    *,
    profile: Profile,
    json_dumps: JsonDumps,
    output_format: str | None = None,
    output_verbosity: int | None = None,
) -> int:
    catalog = ModelCatalog(profile)
    if args.models_command == "defaults":
        summary = catalog.default_summary()
        if args.group_by != "none":
            summary = {
                "group_by": args.group_by,
                "defaults": group_rows(summary["defaults"], args.group_by),
            }
        print(json_dumps(summary, indent=2))
        return 0
    if args.models_command == "use":
        print(json_dumps(catalog.set_default(args.role, args.name), indent=2))
        return 0
    if args.models_command == "add":
        print(
            json_dumps(
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
                    settings=parse_settings(args.settings),
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
            json_dumps(
                catalog.clone_model(
                    args.source,
                    args.target,
                    roles=args.role,
                    supported_runtimes=args.supported_runtimes,
                    preferred_runtime=args.preferred_runtime,
                    enabled=enabled,
                    notes=args.notes,
                    settings=parse_settings(args.settings),
                    write=not args.dry_run,
                    overwrite=args.overwrite,
                ),
                indent=2,
            )
        )
        return 0
    if args.models_command == "remove":
        print(json_dumps(catalog.remove_model(args.name, write=not args.dry_run), indent=2))
        return 0
    if args.models_command == "enable":
        print(json_dumps(catalog.set_enabled(args.name, True), indent=2))
        return 0
    if args.models_command == "disable":
        print(json_dumps(catalog.set_enabled(args.name, False), indent=2))
        return 0
    if args.models_command == "catalog-cache":
        if args.action == "status":
            payload = catalog.materialized_status()
        elif args.action == "rebuild":
            payload = catalog.rebuild_materialized()
        else:
            payload = catalog.clear_materialized()
        print(json_dumps(payload, indent=2))
        return 0
    if args.models_command == "list":
        filters = model_filter_args(args)
        if args.fits_hardware:
            filters.update(active_hardware_model_filters(profile))
        filters = merge_machine_model_filters(
            profile,
            filters,
            machine=args.machine,
            machine_file=args.machine_file,
            current_machine=args.current_machine,
        )
        rows = catalog.sort_rows(
            catalog.filter(
                filters,
                use_materialized=args.catalog_cache != "off",
                force_rebuild=args.catalog_cache == "rebuild",
            ),
            sort_by=args.sort_by,
            roles=filters.get("roles", []),
        )
        if args.limit is not None:
            rows = rows[: args.limit]
        if args.identity != "both":
            if args.group_by != "none":
                raise ValueError("--identity alias/model cannot be combined with --group-by")
            identity_key = "name" if args.identity == "alias" else "model"
            print("\n".join([str(row.get(identity_key) or "") for row in rows]))
            return 0

        resolved_verbosity = output_verbosity if output_verbosity is not None else 0
        if output_format == "text":
            if resolved_verbosity >= 1 or args.group_by != "none":
                print("Warning: models list --format text with verbosity 1+ uses JSON payload.")
                payload = rows if args.group_by == "none" else group_model_rows(profile, rows, args.group_by)
                print(json_dumps(payload, indent=2))
            else:
                print(_models_list_text(rows))
            return 0

        if args.group_by == "none":
            print(json_dumps(rows, indent=2))
        else:
            print(json_dumps(group_model_rows(profile, rows, args.group_by), indent=2))
        return 0
    if args.models_command == "show":
        print(json_dumps(catalog.show(args.name), indent=2, sort_keys=True))
        return 0
    if args.models_command == "doctor":
        print(
            json_dumps(
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
                print(json_dumps(plan, indent=2))
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
        verbosity = int(args.verbosity)
        provider_limits = parse_provider_limits(args.provider_limit)
        reset_cache_result = None
        if args.reset_cache:
            if args.provider == "all":
                reset_results = {}
                skipped = []
                for provider_row in ProviderRegistry(profile).list(include_empty=True):
                    provider_name = str(provider_row.get("name", ""))
                    if provider_name == "local_file":
                        skipped.append(
                            {
                                "name": provider_name,
                                "reason": "local_file has no remote catalog to repopulate",
                            }
                        )
                        continue
                    if provider_row.get("enabled") is False:
                        skipped.append(
                            {
                                "name": provider_name,
                                "reason": "model provider is disabled",
                            }
                        )
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
                    "skipped": [
                        {
                            "name": "local_file",
                            "reason": "local_file has no remote catalog to repopulate",
                        }
                    ],
                }
            else:
                reset_cache_result = catalog.clear_imported(
                    provider_name=args.provider,
                    write=write,
                    include_curated=True,
                )
        progress = refresh_progress()
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
                    verbose=verbosity >= 2,
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
                    verbose=verbosity >= 2,
                )
        finally:
            if progress:
                progress("done", "", "")
        if reset_cache_result is not None:
            result["reset_cache"] = reset_cache_result
        print(json_dumps(refresh_cli_payload(result, verbosity=verbosity), indent=2))
        return 0
    if args.models_command == "clear-cache":
        print(
            json_dumps(
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
            json_dumps(
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
        model_name = args.name
        if not model_name:
            raise ValueError("benchmark requires a model name")
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
        print(json_dumps(result, indent=2))
        return 0
    target = Path(args.target).resolve() if args.target else None
    if target is not None and not PolicyEngine(profile).path_decision(target).allowed:
        raise PermissionError("target escapes workspace boundary")
    result = catalog.test_prompt(args.name, args.task, target, dry_run=args.dry_run)
    print(result.text)
    return 0


def _models_list_text(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "models: none"

    headers = {
        "name": "ALIAS",
        "model": "MODEL",
        "provider": "PROVIDER",
        "runtime": "RUNTIME",
        "enabled": "ENABLED",
    }
    keys = list(headers)
    widths = {key: len(value) for key, value in headers.items()}
    normalized: list[dict[str, str]] = []
    for row in rows:
        supported_runtimes = row.get("supported_runtimes")
        runtime = row.get("preferred_runtime")
        if runtime is None and isinstance(supported_runtimes, list):
            runtime = ", ".join(str(value) for value in supported_runtimes)
        normalized.append(
            {
                "name": str(row.get("name") or ""),
                "provider": str(row.get("provider") or ""),
                "model": str(row.get("model") or ""),
                "runtime": str(runtime or ""),
                "enabled": "yes" if bool(row.get("enabled", True)) else "no",
            }
        )

    for row in normalized:
        for key in keys:
            widths[key] = max(widths[key], len(row.get(key, "")))

    lines = [
        "models",
        "".join(headers[key].ljust(widths[key] + 2) for key in keys),
    ]
    for row in normalized:
        lines.append("".join(row[key].ljust(widths[key] + 2) for key in keys))
    return "\n".join(lines)


def refresh_cli_payload(result: dict[str, object], verbosity: int) -> dict[str, object]:
    if not isinstance(result.get("results"), dict):
        return result
    payload = dict(result)
    payload.pop("verbose", None)
    payload["verbosity"] = verbosity
    results = result.get("results", {})
    if verbosity <= 0:
        payload.pop("results", None)
        return payload
    if verbosity >= 2:
        return payload
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


def active_hardware_model_filters(profile: Profile) -> dict[str, object]:
    machine = HardwareManager(profile).machine()
    memory = machine.get("memory", {}) if isinstance(machine.get("memory"), dict) else {}
    gpu = machine.get("gpu", {}) if isinstance(machine.get("gpu"), dict) else {}
    filters: dict[str, object] = {}
    vendor = str(gpu.get("vendor") or "").strip().lower()
    ram = _number_or_none(memory.get("ram_gb"))
    if ram is None:
        ram = _number_or_none(memory.get("unified_memory_gb"))
    if ram is not None:
        filters["max_min_ram_gb"] = ram
    vram = _number_or_none(gpu.get("vram_gb"))
    # Treat unified memory as GPU budget only for unified-memory platforms.
    if vram is None and vendor == "apple":
        vram = _number_or_none(memory.get("unified_memory_gb"))
    if vram is not None:
        filters["max_min_vram_gb"] = vram
    if vendor:
        filters["gpu_vendor"] = vendor
    accelerator_apis = machine.get("accelerator_apis")
    if isinstance(accelerator_apis, list) and accelerator_apis:
        filters["accelerator_api"] = str(accelerator_apis[0])
    return filters


def _number_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
