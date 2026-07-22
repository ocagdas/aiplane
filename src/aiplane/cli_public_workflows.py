from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Callable

from .cli_models import refresh_cli_payload
from .cli_profile_support import _validate_profile
from .cli_runtimes import _run_provider_helper, _runtime_helper_substrate
from .cli_support import parse_provider_limits as _parse_provider_limits, refresh_progress as _refresh_progress
from .config import create_profile, load_profile, profiles_root
from .evidence import evidence_provenance, evidence_source
from .hardware import HardwareManager
from .integrations import IntegrationManager
from .local_doctor import local_coding_doctor
from .model_catalog import ModelCatalog
from .runtime_catalog import RuntimeCatalog


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
            output_format=args.integration_format,
            api_type=args.api_type,
            offline=args.offline,
        )
    print(exported.content)
    if exported.notes:
        destination = sys.stderr if exported.content_format == "json" else sys.stdout
        print("\n# Notes", file=destination)
        for note in exported.notes:
            print(f"# - {note}", file=destination)


def _doctor_exit_code(payload: dict[str, object]) -> int:
    if isinstance(payload.get("exit_code"), int):
        return int(payload["exit_code"])
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
    sources: list[dict[str, object]] = []

    def add(state: str, source: str | None, name: str, value: object = None) -> None:
        sources.append(evidence_source(name, state, source, value=value))

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
            discovered = model.get("origin") == "discovered_cache"
            add(
                "discovered" if discovered else "configured",
                "models.discovered.yaml" if discovered else "profile.models",
                f"model.{model.get('name')}",
                model.get("model"),
            )
    for endpoint in endpoints or []:
        if isinstance(endpoint, dict):
            configured = endpoint.get("origin") == "profile"
            add(
                "configured" if configured else "generated",
                "profile.providers" if configured else "provider_defaults",
                f"endpoint.{endpoint.get('provider')}",
                endpoint.get("endpoint"),
            )
    defaults = profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {}
    if isinstance(defaults, dict):
        for key, value in sorted(defaults.items()):
            add("configured" if value else "unresolved", "profile.defaults", f"defaults.{key}", value)
    uncertainty: list[str] = []
    if not local_models:
        add("unresolved", "profile.models", "local_models", "no local model aliases discovered or configured")
        uncertainty.append("no local model aliases were discovered or configured")
    return evidence_provenance(sources, uncertainty=uncertainty, method="environment_inventory")


def _bootstrap_local_profile(
    args,
    workspace: Path,
    profiles_dir: Path | None,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    if progress:
        progress("Preparing the editable profile preview" if args.dry_run else "Preparing the editable profile")
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
        if progress:
            progress("Loading and validating the profile")
        profile = load_profile(args.name, workspace, profiles_dir=profiles_dir)
        validation = _validate_profile(profile)
        verbosity = int(getattr(args, "verbosity", 0))
        if not args.no_hardware_discovery:
            if progress:
                progress("Discovering local hardware capabilities")
            manager = HardwareManager(profile)
            hardware = (
                manager.select_closest_discovered(dry_run=args.dry_run)
                if args.select_closest_hardware
                else manager.discover()
            )
        if not args.no_discovery:
            if progress:
                progress("Contacting configured provider catalogs")
            catalog = ModelCatalog(profile)
            provider_limits = _parse_provider_limits(args.provider_limit)
            catalog_progress = _refresh_progress()
            write = not args.dry_run
            try:
                if args.provider == "all":
                    refresh_all_kwargs: dict[str, object] = {
                        "write": write,
                        "enable": not args.disable_new,
                        "query": args.query,
                        "provider_limits": provider_limits,
                        "progress": catalog_progress,
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
                        "progress": catalog_progress,
                        "verbose": verbosity >= 2,
                    }
                    provider_limit = provider_limits.get(args.provider)
                    if provider_limit is not None:
                        refresh_kwargs["limit"] = int(provider_limit)
                    elif args.limit is not None:
                        refresh_kwargs["limit"] = args.limit
                    discovery = catalog.refresh(args.provider, **refresh_kwargs)
            finally:
                if catalog_progress:
                    catalog_progress("done", "", "")
            if isinstance(discovery, dict) and "results" in discovery:
                discovery = refresh_cli_payload(discovery, verbosity=verbosity)
        if progress:
            progress("Summarizing configuration provenance")
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


def _quickstart_local_coding(
    args,
    workspace: Path,
    profiles_dir: Path | None,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    if progress:
        progress("Starting a read-only quickstart preview" if args.dry_run else "Starting quickstart")
    args.no_discovery = not args.discovery
    bootstrap = _bootstrap_local_profile(args, workspace, profiles_dir, progress=progress)
    doctor_payload = None
    recommendation_payload = None
    pull = None
    profile_path = Path(str(bootstrap.get("path", "")))
    profile = None
    if profile_path.exists():
        profile = load_profile(args.name, workspace, profiles_dir=profiles_dir)
        if args.pull_model:
            if progress:
                progress("Planning the requested model pull" if args.dry_run else "Running the requested model pull")
            pull = _quickstart_pull_model(
                profile,
                args.name,
                args.pull_model,
                runtime=args.pull_runtime,
                substrate=args.pull_substrate,
                execute=not args.dry_run,
                profiles_dir=profiles_dir,
            )
        if progress:
            progress("Diagnosing environment and model readiness")
        doctor_payload = local_coding_doctor(profile, include_optional=False)
        if progress:
            progress("Matching configured models to available hardware")
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
    if progress:
        progress("Selecting one safe next action")
    readiness = _quickstart_readiness(profile, args.name)
    commands = [str(readiness["next_action"]["command"])]
    if args.pull_model:
        pull_runtime = (pull.get("runtime") if isinstance(pull, dict) else None) or args.pull_runtime or "RUNTIME"
        commands.insert(
            1,
            f"aiplane runtimes pull {pull_runtime} --model {args.pull_model}" + (" --dry-run" if args.dry_run else ""),
        )
    if progress:
        progress("Quickstart preview complete" if args.dry_run else "Quickstart complete")
    return {
        "name": "quickstart_local_coding",
        "profile": args.name,
        "dry_run": args.dry_run,
        "bootstrap": bootstrap,
        "pull": pull,
        "doctor": doctor_payload,
        "recommend": recommendation_payload,
        "readiness": readiness,
        "commands": commands,
        "notes": [
            "This quickstart creates or previews a local profile, diagnoses readiness, matches configured models to available hardware, optionally delegates an explicit model pull, and prints one next action.",
            "Use --dry-run with --pull-model to preview the existing runtime helper pull path without pulling model weights.",
            "It does not install runtimes, edit IDE configuration, start cloud resources, or run an agent conversation.",
        ],
    }


def _quickstart_readiness(profile, profile_name: str) -> dict[str, object]:
    """Return one next action and no more than two bounded setup choices."""
    export_command = f"aiplane export continue --profile {profile_name}"
    if profile is None:
        return {
            "status": "profile_required",
            "ready_to_export": False,
            "reason": "the dry-run preview did not create a profile",
            "next_action": {
                "kind": "create_profile",
                "command": f"aiplane quickstart local-coding --name {profile_name}",
                "verifies": "creates the profile while preserving it on later runs",
            },
            "export_action": {"command": export_command, "ready": False},
            "setup_choices": [],
        }

    models = ModelCatalog(profile).models()
    enabled_models = sorted(name for name, row in models.items() if bool(row.get("enabled", True)))
    if enabled_models:
        return {
            "status": "ready_to_export",
            "ready_to_export": True,
            "reason": f"{len(enabled_models)} enabled profile model alias(es) are available",
            "next_action": {
                "kind": "export_and_verify",
                "command": export_command,
                "verifies": "prints a Continue configuration without editing Continue files",
            },
            "export_action": {"command": export_command, "ready": True},
            "setup_choices": [],
        }

    ollama_available = shutil.which("ollama") is not None
    local_first = (
        f"aiplane models refresh ollama --profile {profile_name} --limit 20"
        if ollama_available
        else f"aiplane runtimes install ollama --profile {profile_name} --dry-run"
    )
    return {
        "status": "model_required",
        "ready_to_export": False,
        "reason": "the profile has no enabled model alias; no manual YAML editing is required",
        "next_action": {
            "kind": "prepare_local_model",
            "command": local_first,
            "verifies": (
                "discovers local Ollama model aliases"
                if ollama_available
                else "prints the supported local-runtime installation plan without changing the host"
            ),
        },
        "export_action": {"command": export_command, "ready": False},
        "setup_choices": [
            {
                "name": "local",
                "when": "use an Ollama-served model on this machine",
                "command": local_first,
                "then": f"aiplane models add local-chat --alias DISCOVERED_ALIAS --role chat --profile {profile_name}",
            },
            {
                "name": "existing-endpoint",
                "when": "use an OpenAI-compatible endpoint you already operate",
                "command": (f"aiplane models refresh openai --profile {profile_name} --limit 20"),
                "then": f"aiplane models add endpoint-chat --alias DISCOVERED_ALIAS --role chat --profile {profile_name}",
            },
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
