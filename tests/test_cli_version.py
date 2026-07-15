from __future__ import annotations

from aiplane import __version__
from aiplane.version_info import (
    VersionInfo,
    _distribution_matches_module,
    _install_type,
    _looks_like_source_checkout,
    format_version_info,
)
from tests.cli_fixtures import run_cli


class FakeDistribution:
    version = "9.8.7"

    def __init__(self, direct_url: str | None) -> None:
        self.direct_url = direct_url

    def read_text(self, name: str) -> str | None:
        if name != "direct_url.json":
            return None
        return self.direct_url


def test_top_level_version_prints_effective_metadata_and_module_details() -> None:
    result = run_cli(["--version"])

    assert result.code == 0
    assert result.stderr == ""
    assert result.stdout.startswith("aiplane ")
    assert f"module_version: {__version__}" in result.stdout
    assert "metadata_version:" in result.stdout
    assert "install_type:" in result.stdout
    assert "module_path:" in result.stdout


def test_version_formatter_uses_metadata_version_when_available() -> None:
    text = format_version_info(
        VersionInfo(
            package="aiplane",
            version="1.2.3",
            metadata_version="1.2.3",
            module_version="1.2.3",
            install_type="wheel",
            module_path="/tmp/site-packages/aiplane/__init__.py",
        )
    )

    assert text.splitlines() == [
        "aiplane 1.2.3",
        "metadata_version: 1.2.3",
        "module_version: 1.2.3",
        "install_type: wheel",
        "module_path: /tmp/site-packages/aiplane/__init__.py",
    ]


def test_install_type_classifies_source_editable_static_and_wheel() -> None:
    assert _install_type(None) == "source"
    assert _install_type(FakeDistribution('{"dir_info": {"editable": true}, "url": "file:///repo"}')) == "editable"
    assert _install_type(FakeDistribution('{"dir_info": {}, "url": "file:///repo"}')) == "static"
    assert _install_type(FakeDistribution('{"archive_info": {}, "url": "file:///tmp/aiplane-1.0.0.whl"}')) == "wheel"
    assert _install_type(FakeDistribution(None)) == "installed"


def test_distribution_mismatch_is_not_used_as_effective_source_checkout_version(tmp_path) -> None:
    distribution = FakeDistribution('{"dir_info": {}, "url": "file:///other/repo"}')
    module_path = tmp_path / "src" / "aiplane" / "__init__.py"

    assert _looks_like_source_checkout(module_path)
    assert not _distribution_matches_module(distribution, module_path)
