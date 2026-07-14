from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from aiplane.azure_cli import command_status, run_az
from aiplane.azure_inventory import AzureRetailPricing
from aiplane.model_store import ModelCatalogStore


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class PricingTransport:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.urls: list[str] = []

    def open(self, url: str, timeout: float = 10):
        self.urls.append(url)
        return Response(json.dumps(self.payload).encode())


class TimeoutRunner:
    def run(self, command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 0))


def test_model_store_owns_generated_cache_banner_and_invalidation(tmp_path: Path) -> None:
    store = ModelCatalogStore(tmp_path, "models.discovered.yaml", "# generated\n")
    store.write_curated({"models": {"curated": {"enabled": True}}})
    store.write_generated({"models": {"first": {"enabled": True}}})
    assert store.curated_path.read_text().startswith("models:")
    assert store.generated_path.read_text().startswith("# generated\n")
    assert "first" in store.load_generated()["models"]

    store.write_generated({"models": {"second": {"enabled": False}}})
    assert "second" in store.load_generated()["models"]
    assert "first" not in store.load_generated()["models"]


def test_azure_pricing_selects_lowest_non_spot_consumption_price() -> None:
    transport = PricingTransport(
        {
            "Items": [
                {"armSkuName": "Standard_X", "unitPrice": 5, "meterName": "Linux VM", "unitOfMeasure": "1 Hour"},
                {"armSkuName": "Standard_X", "unitPrice": 1, "meterName": "Spot VM", "unitOfMeasure": "1 Hour"},
                {"armSkuName": "Standard_X", "unitPrice": 3, "meterName": "Linux VM", "unitOfMeasure": "1 Hour"},
            ]
        }
    )
    result = AzureRetailPricing(transport).prices("uksouth", ["Standard_X"])
    assert result["ok"]
    assert result["items"]["Standard_X"]["unit_price"] == 3
    assert result["items"]["Standard_X"]["unit"] == "per_hour"
    assert "prices.azure.com" in transport.urls[0]


def test_azure_pricing_escapes_odata_literals() -> None:
    transport = PricingTransport({"Items": []})
    AzureRetailPricing(transport).prices("uk south", ["SKU quote" + chr(39) + " value"])
    decoded_url = transport.urls[0]
    assert "%27" in decoded_url
    assert "%27%27" in decoded_url


def test_azure_cli_timeout_is_data_and_emits_balanced_progress_events() -> None:
    events: list[dict[str, object]] = []
    result = run_az(["az", "account", "show"], event_sink=events.append, runner=TimeoutRunner())
    assert result.returncode == 124
    assert command_status(result)["ok"] is False
    assert [event["phase"] for event in events] == ["start", "complete"]


def test_architecture_boundaries_prevent_domain_module_regression() -> None:
    catalog = Path("src/aiplane/model_catalog.py").read_text()
    refresh = Path("src/aiplane/model_refresh.py").read_text()
    machines = Path("src/aiplane/machines.py").read_text()
    assert "atomic_write_text" not in catalog
    assert "atomic_write_text" not in refresh
    assert "AzureRetailPricing" in machines
    assert "URLError" not in machines
    assert "TimeoutExpired" not in machines
    assert len(catalog.splitlines()) < 1850
    assert len(machines.splitlines()) < 1000
