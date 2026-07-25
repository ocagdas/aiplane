from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .audit import AuditLogger
from .boundaries import CommandRunner
from .config import load_profile
from .patches import PatchManager


def add_patch_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    patches = command_factory(
        subparsers,
        "patches",
        "Inspect and explicitly apply reviewed Git patches",
        "Validate user-supplied Git patches against the current workspace. Application is explicit, policy-gated, audited, and never stages or commits changes.",
        "Examples:\n  aiplane patches inspect changes.patch\n  aiplane patches apply changes.patch --yes",
    )
    patch_sub = patches.add_subparsers(dest="patches_command", required=True, metavar="command")
    for name, help_text in (
        ("inspect", "Inspect a patch without changing files"),
        ("apply", "Apply a validated patch with explicit confirmation"),
    ):
        parser = patch_sub.add_parser(name, help=help_text, formatter_class=formatter_class)
        profile_arg(parser)
        parser.add_argument("path", help="Patch file inside the selected workspace")
        if name == "apply":
            parser.add_argument("--yes", action="store_true", help="Confirm application after validation")


def handle_patch_command(
    args: Any,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
    command_runner: CommandRunner,
) -> int | None:
    if args.command != "patches":
        return None
    profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
    manager = PatchManager(profile, AuditLogger(profile), command_runner=command_runner)
    if args.patches_command == "inspect":
        payload = manager.inspect(args.path)
    else:
        payload = manager.apply(args.path, yes=bool(args.yes))
    print(json_dumps(payload, indent=2))
    return 0
