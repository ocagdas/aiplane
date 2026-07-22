from __future__ import annotations

import json

from aiplane.cli import main
from aiplane.integration_contracts import ALL_INTEGRATION_TOOLS
from aiplane.runtime_definitions import RUNTIME_DEFINITIONS, SOURCE_DEFINITIONS
from aiplane.support_catalog import support_catalog, support_record, support_records


def test_support_catalog_covers_public_surfaces() -> None:
    catalog = support_catalog()
    assert set(catalog["runtimes"]) == set(RUNTIME_DEFINITIONS)
    assert set(catalog["providers"]) == set(SOURCE_DEFINITIONS)
    assert set(catalog["clients"]) == set(ALL_INTEGRATION_TOOLS)
    assert support_record("runtime", "docker_model_runner")["support_tier"] == "tier_1"
    assert all(row["upstream_versions"] == [] for row in support_records())


def test_support_cli_is_profile_independent(capsys) -> None:
    assert main(["support", "show", "client", "continue"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "continue"
