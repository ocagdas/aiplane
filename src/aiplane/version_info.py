from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse
import json

from . import __version__ as MODULE_VERSION
import aiplane as _aiplane_package


@dataclass(frozen=True)
class VersionInfo:
    package: str
    version: str
    metadata_version: str | None
    module_version: str
    install_type: str
    module_path: str


def _distribution() -> metadata.Distribution | None:
    try:
        return metadata.distribution("aiplane")
    except metadata.PackageNotFoundError:
        return None


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _file_url_path(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path)).resolve()


def _looks_like_source_checkout(module_path: Path) -> bool:
    return (
        module_path.name == "__init__.py"
        and module_path.parent.name == "aiplane"
        and module_path.parent.parent.name == "src"
    )


def _distribution_matches_module(distribution: metadata.Distribution, module_path: Path) -> bool:
    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text:
        try:
            direct_url = json.loads(direct_url_text)
        except json.JSONDecodeError:
            direct_url = {}
        source_path = _file_url_path(str(direct_url.get("url", "")))
        if source_path is not None and (
            _path_contains(source_path, module_path) or _path_contains(source_path / "src", module_path)
        ):
            return True

    try:
        distribution_root = Path(str(distribution.locate_file(""))).resolve()
    except (AttributeError, TypeError):
        return False
    return _path_contains(distribution_root, module_path)


def _install_type(distribution: metadata.Distribution | None) -> str:
    if distribution is None:
        return "source"

    direct_url_text = distribution.read_text("direct_url.json")
    if not direct_url_text:
        return "installed"

    try:
        direct_url = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return "installed"

    if direct_url.get("dir_info", {}).get("editable") is True:
        return "editable"
    if "archive_info" in direct_url or str(direct_url.get("url", "")).endswith(".whl"):
        return "wheel"
    if "dir_info" in direct_url:
        return "static"
    return "installed"


def current_version_info() -> VersionInfo:
    module_path = Path(_aiplane_package.__file__).resolve()
    distribution = _distribution()
    if _looks_like_source_checkout(module_path):
        distribution = None
    elif distribution is not None and not _distribution_matches_module(distribution, module_path):
        distribution = None
    metadata_version = distribution.version if distribution is not None else None
    module_version = MODULE_VERSION
    version = metadata_version or module_version or "unknown"
    return VersionInfo(
        package="aiplane",
        version=version,
        metadata_version=metadata_version,
        module_version=module_version,
        install_type=_install_type(distribution),
        module_path=str(module_path),
    )


def format_version_info(info: VersionInfo | None = None) -> str:
    resolved = current_version_info() if info is None else info
    metadata_version = resolved.metadata_version or "unavailable"
    return "\n".join(
        [
            f"aiplane {resolved.version}",
            f"metadata_version: {metadata_version}",
            f"module_version: {resolved.module_version}",
            f"install_type: {resolved.install_type}",
            f"module_path: {resolved.module_path}",
        ]
    )
