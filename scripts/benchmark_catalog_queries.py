#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from aiplane.materialized_catalog import MaterializedCatalog, clear_materialized_memory_cache, property_matches


def synthetic_rows(size: int) -> list[dict[str, Any]]:
    providers = ("ollama", "huggingface", "vllm", "openai")
    parameters = (1, 3, 7, 14, 32, 70)
    rows = []
    for index in range(size):
        provider = providers[index % len(providers)]
        parameter_count = parameters[index % len(parameters)]
        runtime = "ollama" if index % 2 == 0 else "vllm"
        quantization = "q4" if index % 3 == 0 else "fp16"
        benchmark = {"average_score": 90 + index % 10, "passed": 1, "failed": 0} if index % 5 == 0 else None
        properties = {
            "provider": provider,
            "model": f"example/model-{parameter_count}b-{index}",
            "quantization": quantization,
            "architecture": "transformer",
            "supported_runtimes": [runtime],
        }
        rows.append(
            {
                "name": f"model-{index:06d}",
                "model": properties["model"],
                "provider": provider,
                "source": provider,
                "ownership": "managed_service" if provider == "openai" else "self_managed",
                "runtime": runtime,
                "supported_runtimes": [runtime],
                "roles": ["chat", "analysis"] if index % 2 == 0 else ["embedding"],
                "enabled": True,
                "parameter_count_b": parameter_count,
                "min_ram_gb": parameter_count * 2,
                "min_vram_gb": max(0, parameter_count // 2),
                "capability_avg_score": float(index % 6),
                "capabilities": {"score_source": "synthetic", "scores": {"analysis": index % 6}},
                "latest_benchmark": benchmark,
                "likes": index * 10,
                "downloads": index * 100,
                "gpu_vendor_requirement": "generic",
                "accelerator_api_requirements": [],
                "_properties": properties,
            }
        )
    return rows


def benchmark_size(size: int, repeats: int = 5) -> dict[str, Any]:
    rows = synthetic_rows(size)
    filters = {
        "provider": "ollama",
        "runtime": "ollama",
        "properties": {"quantization": "q4"},
        "min_parameters_b": 1,
        "max_parameters_b": 8,
        "min_benchmark_score": 90,
    }
    with tempfile.TemporaryDirectory(prefix="aiplane-catalog-benchmark-") as tmp:
        store = MaterializedCatalog(Path(tmp))
        started = perf_counter()
        store.write(rows, f"synthetic-{size}")
        build_write_ms = (perf_counter() - started) * 1000
        cache_bytes = store.path.stat().st_size
        clear_materialized_memory_cache()
        started = perf_counter()
        loaded = store.load(f"synthetic-{size}")
        cold_load_ms = (perf_counter() - started) * 1000
        if loaded is None:
            raise RuntimeError("materialized benchmark catalog could not be loaded")
        query_times = []
        result_count = 0
        for _ in range(repeats):
            started = perf_counter()
            candidates = store.candidate_rows(loaded, filters)
            result = [row for row in candidates if _matches_numeric_filters(row, filters)]
            query_times.append((perf_counter() - started) * 1000)
            result_count = len(result)
        expected = [row for row in rows if _matches_all_filters(row, filters)]
        if [row["name"] for row in result] != [row["name"] for row in expected]:
            raise AssertionError("indexed benchmark query differs from full scan")
    return {
        "records": size,
        "result_count": result_count,
        "build_write_ms": round(build_write_ms, 3),
        "cold_load_ms": round(cold_load_ms, 3),
        "query_min_ms": round(min(query_times), 3),
        "query_median_ms": round(statistics.median(query_times), 3),
        "query_max_ms": round(max(query_times), 3),
        "cache_bytes": cache_bytes,
    }


def run_benchmarks(sizes: list[int], repeats: int = 5) -> dict[str, Any]:
    return {
        "name": "materialized_catalog_query_benchmark",
        "repeats": repeats,
        "results": [benchmark_size(size, repeats=repeats) for size in sizes],
    }


def _matches_numeric_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    parameters = float(row.get("parameter_count_b") or 0)
    benchmark = row.get("latest_benchmark") if isinstance(row.get("latest_benchmark"), dict) else None
    return (
        parameters >= float(filters["min_parameters_b"])
        and parameters <= float(filters["max_parameters_b"])
        and benchmark is not None
        and float(benchmark.get("average_score", 0)) >= float(filters["min_benchmark_score"])
    )


def _matches_all_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    properties = row.get("_properties") if isinstance(row.get("_properties"), dict) else {}
    return (
        row.get("provider") == filters["provider"]
        and filters["runtime"] in row.get("supported_runtimes", [])
        and all(property_matches(properties, path, expected) for path, expected in filters["properties"].items())
        and _matches_numeric_filters(row, filters)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark generated catalog build, load, and indexed query time")
    parser.add_argument("--sizes", nargs="+", type=int, default=[1_000, 10_000, 100_000])
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if any(size <= 0 for size in args.sizes) or args.repeats <= 0:
        parser.error("sizes and repeats must be positive")
    print(json.dumps(run_benchmarks(args.sizes, repeats=args.repeats), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
