from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .config import (
    create_profile,
    list_profile_templates,
    list_profiles,
    load_profile,
    remove_profile,
    repair_profile,
    resolve_profile_name,
)
from .profile_archive import archive_profile, restore_profile_archive
from .profile_compare import assess_profile_drift, check_profile_replays, compare_profile_sources
from .profile_schema import canonical_profile, load_profile_schema

CommandFactory = Callable[..., argparse.ArgumentParser]
ProfileArg = Callable[[argparse.ArgumentParser], None]
JsonDumps = Callable[..., str]


def add_profiles_parser(
    subparsers: Any,
    *,
    command_factory: CommandFactory,
    profile_arg: ProfileArg,
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    profiles = command_factory(
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
            "  aiplane profiles render local-dev\n"
            "  aiplane profiles archive local-dev --output local-dev.aiplane-profile.json --dry-run\n"
            "  aiplane profiles restore local-dev.aiplane-profile.json --as restored-local --yes\n"
            "  aiplane profiles compare local-dev restored-local\n"
            "  aiplane profiles replay-check approved.json --source archive --client-archive laptop.json --client-archive desktop.json\n"
            "  aiplane profiles drift local-dev\n"
            "  aiplane profiles schema\n"
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    profile_sub.add_parser(
        "templates",
        help="List shipped profile templates",
        description="List checked-in templates that can be copied into profiles/.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    create = profile_sub.add_parser(
        "create",
        help="Create a profile from a template",
        description="Copy a shipped profile template into profiles/<name> so it can be customized without changing the template.",
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        default=False,
        help="Replace an existing profile directory with a fresh copy of the template before discovery; existing profiles are preserved by default",
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
        formatter_class=formatter_class,
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
    profile_sub.add_parser(
        "schema",
        help="Print the canonical profile v1 JSON Schema",
        description="Print the dependency-free JSON Schema used to validate canonical profile documents.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    render = profile_sub.add_parser(
        "render",
        help="Render a canonical profile v1 document",
        description="Combine the editable profile YAML files into one deterministic JSON document for external validation or comparison. This command is read-only.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    render.add_argument(
        "name",
        nargs="?",
        help="Profile name. If omitted, uses the effective default profile",
    )
    archive = profile_sub.add_parser(
        "archive",
        help="Create a deterministic portable profile archive",
        description=(
            "Validate and package reviewed profile YAML into a deterministic JSON archive with checksums and an explicit "
            "exclusion manifest. Credentials, generated caches, runtime state, model weights, and generated exports are excluded."
        ),
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog=(
            "Examples:\n"
            "  aiplane profiles archive local-dev --output local-dev.aiplane-profile.json --dry-run\n"
            "  aiplane profiles archive local-dev --output local-dev.aiplane-profile.json\n"
            "  aiplane profiles archive local-dev --output local-dev.aiplane-profile.json --overwrite"
        ),
    )
    archive.add_argument(
        "name",
        nargs="?",
        help="Profile name. If omitted, uses the effective default profile",
    )
    archive.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="Destination JSON archive path; must be outside the source profile directory",
    )
    archive.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing archive file; never changes the source profile",
    )
    archive.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate content and show the portable manifest without writing the archive",
    )
    restore = profile_sub.add_parser(
        "restore",
        help="Preview or restore a portable profile archive",
        description=(
            "Validate a portable JSON archive and restore its reviewed YAML into a new profile directory. "
            "The default is a preview; --yes is required to write. Existing profiles are never overwritten."
        ),
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog=(
            "Examples:\n"
            "  aiplane profiles restore local-dev.aiplane-profile.json --as restored-local\n"
            "  aiplane profiles restore local-dev.aiplane-profile.json --as restored-local --yes"
        ),
    )
    restore.add_argument("archive", metavar="ARCHIVE", help="Portable profile JSON archive to validate and restore")
    restore.add_argument(
        "--as",
        dest="target_name",
        metavar="NAME",
        help="Destination profile name; defaults to the archived profile name",
    )
    restore.add_argument(
        "--yes",
        action="store_true",
        help="Create the destination profile after validation",
    )
    restore.add_argument(
        "--dry-run",
        action="store_true",
        help="Force preview mode even when --yes is present",
    )
    compare = profile_sub.add_parser(
        "compare",
        help="Compare portable profile or archive evidence",
        description=(
            "Compare two validated portable sources and classify them as exact, capability-equivalent, "
            "materially incompatible, or unresolved. The command is read-only."
        ),
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog=(
            "Examples:\n"
            "  aiplane profiles compare local-dev restored-local\n"
            "  aiplane profiles compare backup.json local-dev --left-source archive"
        ),
    )
    compare.add_argument("left", metavar="LEFT", help="Left profile name or archive path")
    compare.add_argument("right", metavar="RIGHT", help="Right profile name or archive path")
    compare.add_argument(
        "--left-source",
        choices=["profile", "archive"],
        default="profile",
        help="Interpret LEFT as a profile name or validated archive path",
    )
    compare.add_argument(
        "--right-source",
        choices=["profile", "archive"],
        default="profile",
        help="Interpret RIGHT as a profile name or validated archive path",
    )
    replay_check = profile_sub.add_parser(
        "replay-check",
        help="Verify approved profile replay across multiple clients",
        description=(
            "Compare one approved profile or archive with at least two portable archives produced by separate "
            "client installations. This command is deterministic and read-only."
        ),
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog=(
            "Examples:\n"
            "  aiplane profiles replay-check approved.json --source archive "
            "--client-archive laptop.json --client-archive desktop.json"
        ),
    )
    replay_check.add_argument("source", metavar="SOURCE", help="Approved profile name or portable archive path")
    replay_check.add_argument(
        "--source",
        dest="source_type",
        choices=["profile", "archive"],
        default="profile",
        help="Interpret SOURCE as a profile name or validated archive path",
    )
    replay_check.add_argument(
        "--client-archive",
        action="append",
        required=True,
        metavar="PATH",
        help="Portable archive produced by a replayed client profile; repeat for at least two distinct clients",
    )
    drift = profile_sub.add_parser(
        "drift",
        help="Assess profile portability against this machine",
        description=(
            "Compare explicit active profile hardware evidence with live hardware discovery and classify "
            "selected-model compatibility. The command is read-only."
        ),
        formatter_class=formatter_class,
        allow_abbrev=False,
        epilog=("Examples:\n  aiplane profiles drift local-dev\n  aiplane profiles drift backup.json --source archive"),
    )
    drift.add_argument("source", metavar="SOURCE", help="Profile name or portable archive path")
    drift.add_argument(
        "--source",
        dest="source_type",
        choices=["profile", "archive"],
        default="profile",
        help="Interpret SOURCE as a profile name or validated archive path",
    )
    validate = profile_sub.add_parser(
        "validate",
        help="Validate a profile",
        description="Check required profile files and cross-references such as defaults, providers, targets, and environment modes.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    validate.add_argument(
        "name",
        nargs="?",
        help="Profile name. If omitted, uses the effective default profile",
    )


def handle_profiles_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    requested_profile: str | None,
    json_dumps: JsonDumps,
    bootstrap_profile: Callable[..., dict[str, object]],
    validate_profile: Callable[..., dict[str, object]],
    profile_selected: Callable[..., dict[str, object]],
    profile_summary: Callable[..., dict[str, object]],
) -> int | None:
    if args.command != "profiles":
        return None
    if args.profile_command == "list":
        default = resolve_profile_name(None, profiles_dir=profiles_dir)
        rows = [name + (" *" if name == default else "") for name in list_profiles(profiles_dir)]
        print("\n".join(rows))
        return 0
    if args.profile_command == "templates":
        print("\n".join(list_profile_templates()))
        return 0
    if args.profile_command == "schema":
        print(json_dumps(load_profile_schema(), indent=2, sort_keys=True))
        return 0
    if args.profile_command == "create":
        path = create_profile(
            args.name,
            template=args.template,
            overwrite=args.overwrite,
            profiles_dir=profiles_dir,
        )
        print(
            json_dumps({"created": args.name, "template": args.template, "path": str(path)}, indent=2, sort_keys=True)
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
        print(json_dumps(result, indent=2, sort_keys=True))
        return 0
    if args.profile_command == "remove":
        result = remove_profile(args.name, yes=args.yes, dry_run=args.dry_run, profiles_dir=profiles_dir)
        print(json_dumps(result, indent=2, sort_keys=True))
        return 0
    if args.profile_command == "archive":
        profile_name = args.name or resolve_profile_name(requested_profile, profiles_dir=profiles_dir)
        result = archive_profile(
            profile_name,
            args.output,
            profiles_dir=profiles_dir,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
        print(json_dumps(result, indent=2, sort_keys=True))
        return 0 if not result["conflicts"] else 1
    if args.profile_command == "restore":
        result = restore_profile_archive(
            args.archive,
            name=args.target_name,
            profiles_dir=profiles_dir,
            dry_run=args.dry_run,
            yes=args.yes,
        )
        print(json_dumps(result, indent=2, sort_keys=True))
        return 0 if not result["conflicts"] else 1
    if args.profile_command == "compare":
        result = compare_profile_sources(
            args.left,
            args.right,
            left_source=args.left_source,
            right_source=args.right_source,
            profiles_dir=profiles_dir,
        )
        print(json_dumps(result, indent=2, sort_keys=True))
        return 0
    if args.profile_command == "replay-check":
        result = check_profile_replays(
            args.source,
            args.client_archive,
            source_type=args.source_type,
            profiles_dir=profiles_dir,
        )
        print(json_dumps(result, indent=2, sort_keys=True))
        return 0 if result["replay_ready"] else 1
    if args.profile_command == "drift":
        result = assess_profile_drift(
            args.source,
            source_type=args.source_type,
            profiles_dir=profiles_dir,
        )
        print(json_dumps(result, indent=2, sort_keys=True))
        return 0
    if args.profile_command == "bootstrap-local":
        result = bootstrap_profile(args, workspace, profiles_dir)
        print(json_dumps(result, indent=2, sort_keys=True))
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else None
        return 0 if validation is None or validation.get("ok", False) else 1

    if args.profile_command in {"render", "validate"}:
        profile_name = args.name or resolve_profile_name(requested_profile, profiles_dir=profiles_dir)
        profile = load_profile(profile_name, workspace, profiles_dir=profiles_dir)
        if args.profile_command == "render":
            print(json_dumps(canonical_profile(profile), indent=2, sort_keys=True))
            return 0
        result = validate_profile(profile)
        print(json_dumps(result, indent=2))
        return 0 if result["ok"] else 1

    effective_profile = resolve_profile_name(requested_profile, profiles_dir=profiles_dir)
    profile_name = args.name or effective_profile
    profile = load_profile(profile_name, workspace, profiles_dir=profiles_dir)
    payload = (
        profile_selected(profile, effective_profile) if args.selected else profile_summary(profile, effective_profile)
    )
    print(json_dumps(payload, indent=2))
    return 0
