from __future__ import annotations

import json

import pytest

from aiplane.kubernetes_artifacts import render_kubernetes


def test_artifact_family_is_deterministic_linked_and_render_only() -> None:
    stack = {
        "name": "demo_stack",
        "runtime": "docker_model_runner",
        "model": "local-chat",
        "endpoint": "http://localhost:12434",
    }
    first = render_kubernetes(stack, image="registry.example/runtime:reviewed", device_class="gpu.example.com")
    second = render_kubernetes(stack, image="registry.example/runtime:reviewed", device_class="gpu.example.com")
    assert first == second
    assert set(first["files"]) == {"resourceclaim.yaml", "deployment.yaml", "service.yaml", "values.yaml"}
    assert first["apply_supported"] is False
    assert "resource.k8s.io/v1" in first["files"]["resourceclaim.yaml"]
    assert "resourceClaimName: demo-stack-accelerator" in first["files"]["deployment.yaml"]
    assert "kind: Service" in first["files"]["service.yaml"]
    assert "secret" not in json.dumps(first).lower()


@pytest.mark.parametrize(("field", "value"), [("image", ""), ("device_class", ""), ("namespace", "Bad Namespace")])
def test_artifact_family_rejects_incomplete_inputs(field: str, value: str) -> None:
    kwargs = {"image": "example/runtime:tag", "device_class": "gpu.example.com", "namespace": "default"}
    kwargs[field] = value
    with pytest.raises(ValueError):
        render_kubernetes({"name": "demo", "model": "m", "runtime": "r", "endpoint": "http://x:8000"}, **kwargs)
