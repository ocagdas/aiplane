from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .config import (
    agent_artifacts_root,
    clear_output_format,
    clear_output_verbosity,
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
    list_profiles,
    load_local_config,
    local_config_path,
    profiles_root,
    resolve_output_format,
    resolve_output_verbosity,
    set_default_profile,
    set_local_config_value,
    set_output_format,
    set_output_verbosity,
)
from .secrets import credentials_path


def add_config_parser(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    config_cmd = command_factory(
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
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    config_init = config_sub.add_parser(
        "init",
        help="Create local config from template",
        description="Copy a checked-in config template to .aiplane/config.yaml or AIPLANE_CONFIG. The copied file is ignored by git.",
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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
        formatter_class=formatter_class,
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


def handle_config_command(
    args: argparse.Namespace,
    *,
    profiles_dir: Path | None,
    requested_profile: str | None,
    json_dumps: Callable[..., str],
    parse_setting_value: Callable[[str], object],
) -> int | None:
    if args.command != "config":
        return None
    if args.config_command == "templates":
        print("\n".join(list_config_templates()))
        return 0
    if args.config_command == "init":
        path = init_local_config(template=args.template, path=args.path, overwrite=args.overwrite)
        print(
            json_dumps(
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
                json_dumps(
                    {"default_profile": args.name, "path": str(path)},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        print(
            json_dumps(
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
            json_dumps(
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
        path = set_local_config_value(args.key, parse_setting_value(args.value), path=args.path)
        print(
            json_dumps(
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
            json_dumps(
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
            json_dumps(
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
        json_dumps(
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
