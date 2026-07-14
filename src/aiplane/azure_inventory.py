from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.parse import quote_plus

from .boundaries import HttpTransport, UrllibHttpTransport


class AzureRetailPricing:
    """Query and normalize Azure retail VM prices behind an injectable HTTP boundary."""

    def __init__(self, transport: HttpTransport | None = None, timeout: float = 4):
        self.transport = transport or UrllibHttpTransport()
        self.timeout = timeout

    def prices(self, region: str, skus: list[str]) -> dict[str, Any]:
        unique_skus = sorted({sku for sku in skus if sku})
        if not unique_skus:
            return {"method": "skipped", "ok": False, "reason": "no SKU names available", "items": {}}
        url = self._url(region, unique_skus)
        try:
            with self.transport.open(url, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            return self._failure(unique_skus, str(exc))
        except Exception as exc:  # noqa: BLE001 - discovery degrades to unpriced candidates.
            return self._failure(unique_skus, f"{type(exc).__name__}: pricing query failed")
        values = payload.get("Items", []) if isinstance(payload, dict) else []
        if not isinstance(values, list):
            return self._failure(unique_skus, "unexpected retail prices response shape")
        items = _lowest_consumption_prices(values, unique_skus)
        return {
            "method": "azure_retail_prices_api",
            "ok": bool(items),
            "items": items,
            "missing_skus": [sku for sku in unique_skus if sku not in items],
            "failed_skus": [],
        }

    @staticmethod
    def _url(region: str, skus: list[str]) -> str:
        sku_filter = " or ".join(f"armSkuName eq {_odata_literal(sku)}" for sku in skus)
        expression = (
            "serviceName eq " + _odata_literal("Virtual Machines") + " and "
            f"armRegionName eq {_odata_literal(region)} and "
            "priceType eq " + _odata_literal("Consumption") + " and "
            f"({sku_filter})"
        )
        return "https://prices.azure.com/api/retail/prices?$filter=" + quote_plus(expression)

    @staticmethod
    def _failure(skus: list[str], reason: str) -> dict[str, Any]:
        return {
            "method": "azure_retail_prices_api",
            "ok": False,
            "reason": reason,
            "items": {},
            "failed_skus": skus,
        }


def _odata_literal(value: str) -> str:
    quote = chr(39)
    return quote + value.replace(quote, quote + quote) + quote


def _lowest_consumption_prices(values: list[Any], skus: list[str]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("armSkuName") or "")
        price = _number(item.get("unitPrice"))
        if sku not in skus or price is None or "spot" in str(item.get("meterName") or "").lower():
            continue
        existing = best.get(sku)
        if existing is None or (_number(existing.get("unitPrice")) or 0.0) > price:
            best[sku] = item
    result: dict[str, dict[str, Any]] = {}
    for sku, selected in best.items():
        unit = str(selected.get("unitOfMeasure") or "")
        result[sku] = {
            "currency": selected.get("currencyCode"),
            "unit_price": _number(selected.get("unitPrice")),
            "unit_of_measure": unit,
            "unit": _normalize_price_unit(unit),
            "meter_name": selected.get("meterName"),
            "product_name": selected.get("productName"),
            "sku_name": selected.get("skuName"),
            "source": "azure_retail_prices_api",
        }
    return result


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_price_unit(value: str) -> str:
    lowered = value.strip().lower()
    if "hour" in lowered:
        return "per_hour"
    if "month" in lowered:
        return "per_month"
    if "second" in lowered:
        return "per_second"
    return value or "unknown"
