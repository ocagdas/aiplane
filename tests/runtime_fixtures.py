from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from aiplane.runtime_catalog import RuntimeCatalog

from .profile_fixtures import load_profile

PRIMARY_RUNTIME_FIXTURES: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "primary-runtime-contracts.json").read_text(encoding="utf-8")
)


def catalog_for_runtime_fixture(runtime: str) -> tuple[RuntimeCatalog, str, dict[str, Any]]:
    fixture = copy.deepcopy(PRIMARY_RUNTIME_FIXTURES[runtime])
    profile = load_profile("local-dev", Path.cwd())
    alias = str(fixture["alias"])
    profile.models["models"][alias] = {
        "provider": runtime,
        "ownership": "self_managed",
        "source": fixture["source"],
        "model": fixture["model"],
        "format": fixture["format"],
        "supported_runtimes": [runtime],
        "preferred_runtime": runtime,
        "context_window_tokens": 32768,
        "enabled": True,
    }
    return RuntimeCatalog(profile), alias, fixture
