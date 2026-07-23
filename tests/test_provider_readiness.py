from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from aiplane.providers import ProviderRegistry
from tests.profile_fixtures import _isolated_test_profile


class FailingTransport:
    def open(self, request, timeout):
        raise AssertionError("network must not be contacted when readiness fails")


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RecordingTransport:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return JsonResponse(self.payload)


def test_missing_managed_credential_blocks_before_network(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        with patch.dict("os.environ", {}, clear=True):
            registry = ProviderRegistry(profile, http_transport=FailingTransport())
            result = registry.models("openai", online=True)
            diagnostic = registry.diagnose("openai")["providers"][0]

    assert result.source == "configuration_error"
    assert result.diagnostics["failure_codes"] == ["credential_missing"]
    assert diagnostic["network_contacted"] is False
    assert diagnostic["ready"] is False
    assert diagnostic["checks"][-1]["remediation"] == "Configure credential_ref or set OPENAI_API_KEY."


def test_named_azure_adapter_uses_its_own_endpoint_and_credentials(tmp_path: Path) -> None:
    transport = RecordingTransport({"data": [{"id": "team-chat", "model": "provider-chat"}]})
    with _isolated_test_profile(workspace=tmp_path) as profile:
        registry = ProviderRegistry(profile, http_transport=transport)
        registry.add(
            "team_azure",
            ownership="managed_service",
            endpoint_family="azure_openai",
            catalog_adapter="azure_openai",
            endpoint="https://team.openai.azure.com",
            api_key_env="TEAM_AZURE_KEY",
            auth_method="api_key",
            requires_credentials=True,
        )
        with patch.dict("os.environ", {"TEAM_AZURE_KEY": "synthetic-test-key"}, clear=True):
            result = registry.models("team_azure", online=True)

    assert result.provider == "team_azure"
    assert result.models == ["team-chat"]
    request, timeout = transport.requests[0]
    assert request.full_url.startswith("https://team.openai.azure.com/openai/deployments?")
    assert request.headers["Api-key"] == "synthetic-test-key"
    assert timeout == 20
