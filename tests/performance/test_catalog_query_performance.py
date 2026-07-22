from __future__ import annotations

import os

import pytest

from scripts.benchmark_catalog_queries import benchmark_size


pytestmark = [
    pytest.mark.performance,
    pytest.mark.skipif(
        os.environ.get("AIPLANE_RUN_PERFORMANCE") != "1",
        reason="set AIPLANE_RUN_PERFORMANCE=1 to run 1k/10k/100k catalog benchmarks",
    ),
]


@pytest.mark.parametrize("size", [1_000, 10_000, 100_000])
def test_materialized_catalog_query_benchmark(size: int) -> None:
    result = benchmark_size(size, repeats=3)
    assert result["result_count"] > 0
    assert result["query_max_ms"] < float(os.environ.get("AIPLANE_CATALOG_QUERY_MAX_MS", "2000"))
