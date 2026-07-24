from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .config import load_profile
from .hardware import HardwareManager
from .machines import MachineManager


def add_hardware_machine_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    hardware_cmd = command_factory(
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_show)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_templates)
    hardware_schema = hardware_sub.add_parser(
        "schema",
        help="Show machine property schema",
        description="Show the editable machine fields used for hardware-aware recommendation: stock tag/SKU, CPU, RAM, GPU, VRAM, accelerator APIs, OS, placement, and substrate.",
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware schema",
    )
    profile_arg(hardware_schema)
    hardware_active = hardware_sub.add_parser(
        "active",
        help="Show selected hardware config",
        description="Show the active copied/customized hardware config and template origin.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_active)
    hardware_use = hardware_sub.add_parser(
        "use",
        help="Copy a template into active hardware config",
        description="Select a hardware template by copying it into the mutable active config. Overrides do not modify the template.",
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware use nvidia_consumer_gpu --set vram_gb=16 --set memory_gb=64",
    )
    profile_arg(hardware_use)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware set memory_gb=64 vram_gb=24",
    )
    profile_arg(hardware_set)
    hardware_set.add_argument(
        "settings",
        nargs="+",
        help="One or more key=value updates, such as memory_gb=64 vram_gb=24",
    )
    hardware_discover = hardware_sub.add_parser(
        "discover",
        help="Probe local CPU/RAM/GPU resources",
        description="Discover local hardware and show closest matching hardware templates. Optionally select the closest template.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_discover)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_clear)
    hardware_clear.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the reset without writing hardware.yaml",
    )
    hardware_doctor = hardware_sub.add_parser(
        "doctor",
        help="Check hardware/model fit",
        description="Check whether configured local models fit the discovered or selected hardware.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_doctor)
    hardware_doctor.add_argument(
        "--model",
        help="Optional model alias to check, such as a discovered or promoted alias",
    )
    hardware_recommend = hardware_sub.add_parser(
        "recommend",
        help="Recommend models for active/discovered hardware",
        description="Return hardware- and policy-aware model recommendations using hardware fit, runtime compatibility, and ranking rationale.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_recommend)
    hardware_recommend.add_argument(
        "--include-not-recommended",
        action="store_true",
        help="Also show models below minimum local RAM/VRAM targets",
    )
    hardware_recommend.add_argument("--runtime", help="Evaluate placement for one runtime")
    hardware_recommend.add_argument("--context-tokens", type=int, help="Requested inference context")
    hardware_recommend.add_argument("--score-profile", help="Named placement-scoring profile")
    hardware_recommend.add_argument(
        "--role", action="append", default=[], help="Limit recommendations to one or more model roles"
    )
    hardware_assess = hardware_sub.add_parser(
        "assess",
        help="Explain placement and scoring for one model",
        description="Estimate weights, KV cache, runtime placement modes, blockers, and the versioned placement-readiness score.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_assess)
    hardware_assess.add_argument("model", help="Model alias from the active profile")
    hardware_assess.add_argument("--runtime", help="Evaluate placement for one runtime")
    hardware_assess.add_argument("--context-tokens", type=int, help="Requested inference context")
    hardware_assess.add_argument("--score-profile", help="Named placement-scoring profile")
    hardware_scoring = hardware_sub.add_parser(
        "scoring",
        help="Show scoring profiles and extension contract",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(hardware_scoring)
    hardware_export = hardware_sub.add_parser(
        "export-machine",
        help="Export this machine profile",
        description="Probe this machine and print a normalized machine profile that can be imported on another control PC.",
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog="Example:\n  aiplane hardware export-machine --name gpu_box_01 > gpu_box_01.machine.yaml",
    )
    profile_arg(hardware_export)
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

    machines_cmd = command_factory(
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_list)
    machines_show = machines_sub.add_parser(
        "show",
        help="Show one imported machine",
        description="Show one machine profile from the self-managed inventory.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_show)
    machines_show.add_argument("name", help="Machine name")
    machines_validate = machines_sub.add_parser(
        "validate",
        help="Validate imported machine profiles",
        description="Validate required machine profile fields for one machine or all imported machines.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_validate)
    machines_validate.add_argument("name", nargs="?", help="Optional machine name")
    machines_cache_list = machines_sub.add_parser(
        "cache-list",
        help="List machine discovery cache entries",
        description="Inspect cached discovery results, including whether each entry came from live provider data or offline hints.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_cache_list)
    machines_cache_clear = machines_sub.add_parser(
        "cache-clear",
        help="Clear machine discovery cache",
        description="Clear all cached machine discovery results, or one cache key.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_cache_clear)
    machines_cache_clear.add_argument("--key", help="Specific cache key to clear")
    machines_azure_status = machines_sub.add_parser(
        "azure-status",
        help="Check Azure CLI login/query status",
        description="Report whether az is installed, az account show works, and optionally whether VM SKU query works for a region.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_azure_status)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_import)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_recommend)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_discover)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_import_azure)
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_arg(machines_profile_remote)
    machines_profile_remote.add_argument("--name", required=True, help="Machine name to assign to the remote export")
    machines_profile_remote.add_argument(
        "--host", required=True, help="Remote DNS hostname or IPv4/IPv6 address; option-like values are rejected"
    )
    machines_profile_remote.add_argument(
        "--user", help="SSH username (letters, digits, underscore, dot, and hyphen; cannot start with hyphen)"
    )
    machines_profile_remote.add_argument("--port", type=int, default=22, help="SSH port (1-65535)")


def handle_hardware_machine_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
    parse_settings: Callable[[list[str]], dict[str, object]],
    reporter_factory: Callable[..., Any],
    resolve_format: Callable[..., str],
    config_path: Path,
    hardware_show_text: Callable[[dict[str, object]], str],
) -> int | None:
    if args.command == "hardware":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = HardwareManager(profile)
        if args.hardware_command == "show":
            if args.list_types:
                print(json_dumps(manager.show_types(), indent=2, sort_keys=True))
                return 0
            output_format = resolve_format(
                args.format,
                profile=effective_profile,
                command="hardware show",
                path=config_path,
                default="json",
            )
            if output_format == "text":
                print(hardware_show_text(manager.show(verbosity=int(args.verbosity))))
            else:
                print(json_dumps(manager.show(verbosity=int(args.verbosity)), indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "templates":
            print(json_dumps(manager.templates(), indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "schema":
            print(json_dumps(manager.schema(), indent=2))
            return 0
        if args.hardware_command == "active":
            print(json_dumps(manager.active_config(), indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "use":
            print(
                json_dumps(
                    manager.use_template(args.template, parse_settings(args.settings)),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.hardware_command == "set":
            print(
                json_dumps(
                    manager.customize_active(parse_settings(args.settings)),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.hardware_command == "discover":
            result = (
                manager.select_closest_discovered(dry_run=args.dry_run) if args.select_closest else manager.discover()
            )
            print(json_dumps(result, indent=2, sort_keys=True))
            return 0
        if args.hardware_command == "clear":
            print(
                json_dumps(
                    manager.clear_selection(dry_run=args.dry_run),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.hardware_command == "recommend":
            print(
                json_dumps(
                    manager.recommend(
                        include_not_recommended=args.include_not_recommended,
                        runtime=args.runtime,
                        context_tokens=args.context_tokens,
                        score_profile=args.score_profile,
                        roles=args.role,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.hardware_command == "assess":
            print(
                json_dumps(
                    manager.assess(
                        args.model,
                        runtime=args.runtime,
                        context_tokens=args.context_tokens,
                        score_profile=args.score_profile,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.hardware_command == "scoring":
            print(json_dumps(manager.scoring(), indent=2))
            return 0
        if args.hardware_command == "export-machine":
            exported = MachineManager(profile).export_machine(
                args.name, origin=args.origin, include_discovery=args.include_discovery
            )
            if args.format == "json":
                print(json_dumps(exported, indent=2))
            else:
                from .config import dump_yaml

                print(dump_yaml(exported), end="")
            return 0
        print(json_dumps(manager.doctor(args.model), indent=2, sort_keys=True))
        return 0

    if args.command == "machines":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = MachineManager(profile)
        if args.machines_command == "list":
            print(json_dumps(manager.list(), indent=2))
            return 0
        if args.machines_command == "show":
            print(json_dumps(manager.show(args.name), indent=2))
            return 0
        if args.machines_command == "validate":
            result = manager.validate(args.name)
            print(json_dumps(result, indent=2))
            return 0 if result["ok"] else 1
        if args.machines_command == "cache-list":
            print(json_dumps(manager.cache_list(), indent=2))
            return 0
        if args.machines_command == "cache-clear":
            print(json_dumps(manager.cache_clear(args.key), indent=2))
            return 0
        if args.machines_command == "azure-status":
            verbosity = int(getattr(args, "verbosity", 0))
            reporter = reporter_factory(verbosity=verbosity)
            try:
                print(
                    json_dumps(
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
                json_dumps(
                    manager.import_file(
                        Path(args.path),
                        name=args.name,
                        overrides=parse_settings(args.settings),
                    ),
                    indent=2,
                )
            )
            return 0
        if args.machines_command == "recommend":
            print(
                json_dumps(
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
            reporter = reporter_factory(verbosity=verbosity)
            try:
                print(
                    json_dumps(
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
                json_dumps(
                    manager.import_azure_sku(
                        args.sku,
                        args.region,
                        name=args.name,
                        overrides=parse_settings(args.settings),
                    ),
                    indent=2,
                )
            )
            return 0
        if args.machines_command == "profile-remote-plan":
            print(
                json_dumps(
                    manager.profile_remote_plan(args.name, args.host, user=args.user, port=args.port),
                    indent=2,
                )
            )
            return 0

        return None
