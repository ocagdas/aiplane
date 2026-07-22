from __future__ import annotations

import argparse
from typing import Any, Callable

from .support_catalog import support_catalog, support_record, support_records


def add_support_parser(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    command = command_factory(
        subparsers,
        "support",
        "Inspect versioned support commitments",
        "List provider, runtime, and client support tiers without implying unverified upstream-version compatibility.",
    )
    children = command.add_subparsers(dest="support_command", required=True, metavar="command")
    listing = children.add_parser("list", formatter_class=formatter_class, allow_abbrev=False)
    listing.add_argument("--kind", choices=["runtime", "provider", "client"])
    listing.add_argument("--full", action="store_true", help="Include tier definitions and maintenance policy")
    show = children.add_parser("show", formatter_class=formatter_class, allow_abbrev=False)
    show.add_argument("kind", choices=["runtime", "provider", "client"])
    show.add_argument("name")


def handle_support_command(args: argparse.Namespace, json_dumps: Callable[..., str]) -> int | None:
    if args.command != "support":
        return None
    if args.support_command == "list":
        payload = support_catalog() if args.full else support_records(args.kind)
    else:
        payload = support_record(args.kind, args.name)
    print(json_dumps(payload, indent=2, sort_keys=True))
    return 0
