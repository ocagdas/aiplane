from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiplane.adapter_protocol import (
    AdapterModel,
    AdapterRequest,
    AdapterResult,
    run_adapter,
    validate_result,
    validate_result_file,
)


def test_adapter_fixture_protocol_and_secret_rejection() -> None:
    fixture_path = Path("tests/fixtures/adapter-v1.json")
    result = validate_result_file(fixture_path)
    assert result.models[0].id == "example/model-7b"

    class ExampleAdapter:
        name = "example_adapter"

        def discover(self, request: AdapterRequest) -> AdapterResult:
            return AdapterResult(
                "1.0", self.name, True, (AdapterModel("model-a", request.provider),), {"source": "test"}
            )

    assert run_adapter(ExampleAdapter(), AdapterRequest("example")).models[0].provider == "example"
    fixture = json.loads(fixture_path.read_text())
    fixture["api_key"] = "forbidden"
    with pytest.raises(ValueError, match="secret-bearing"):
        validate_result(fixture)
