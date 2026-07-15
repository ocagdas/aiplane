from __future__ import annotations

from .version_info import format_version_info


def add_version_argument(parser) -> None:
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show installed package and module version details",
    )


def handle_version_argument(args) -> int | None:
    if not getattr(args, "version", False):
        return None
    print(format_version_info())
    return 0
