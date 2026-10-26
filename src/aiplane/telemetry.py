"""Explicit throughput rates; the available-source average is a display statistic."""

from __future__ import annotations

import math
from typing import Any


def _nonnegative_finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def rate_from_milliseconds(tokens: object, duration_ms: object) -> float | None:
    count = _nonnegative_finite(tokens)
    duration = _nonnegative_finite(duration_ms)
    if count is None or duration is None or duration == 0:
        return None
    rate = count / duration * 1000
    return round(rate, 3) if math.isfinite(rate) else None


def throughput_rates(server: object, client: object) -> dict[str, Any]:
    server = _nonnegative_finite(server)
    client = _nonnegative_finite(client)
    values = [value for value in (server, client) if value is not None]
    return {
        "server_tokens_per_second": server,
        "client_tokens_per_second": client,
        "average_tokens_per_second": round(sum(value / len(values) for value in values), 3) if values else None,
        "throughput_average_sources": [
            name for name, value in (("server", server), ("client", client)) if value is not None
        ],
    }
