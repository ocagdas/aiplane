from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiplane.offline_catalog import load_offline_catalog


def test_loads_json_catalog_without_mutating_source(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    source = {
        "contract_version": "1.0",
        "record_type": "offline_model_catalog",
        "models": {"small": {"provider": "ollama", "model": "small:latest"}},
    }
    path.write_text(json.dumps(source), encoding="utf-8")

    catalog = load_offline_catalog(path)

    assert catalog["models"]["small"]["origin"] == "offline_catalog"
    assert catalog["metadata"]["source"] == str(path)
    assert json.loads(path.read_text(encoding="utf-8")) == source


@pytest.mark.parametrize(
    "catalog",
    [
        'contract_version: "1.0"\nrecord_type: wrong\nmodels: {}\n',
        'contract_version: "1.0"\nrecord_type: offline_model_catalog\nmodels:\n  small:\n    provider: ollama\n    model: small:latest\n    api_key: harmless\n',
    ],
)
def test_rejects_invalid_or_secret_bearing_catalog(tmp_path: Path, catalog: str) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text(catalog, encoding="utf-8")

    with pytest.raises(ValueError):
        load_offline_catalog(path)
