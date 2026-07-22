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
    assert "type: ClusterIP" in first["files"]["service.yaml"]
    assert "secret" not in json.dumps(first).lower()


@pytest.mark.parametrize(("field", "value"), [("image", ""), ("device_class", ""), ("namespace", "Bad Namespace")])
def test_artifact_family_rejects_incomplete_inputs(field: str, value: str) -> None:
    kwargs = {"image": "example/runtime:tag", "device_class": "gpu.example.com", "namespace": "default"}
    kwargs[field] = value
    with pytest.raises(ValueError):
        render_kubernetes({"name": "demo", "model": "m", "runtime": "r", "endpoint": "http://x:8000"}, **kwargs)


def test_artifact_family_consumes_launch_evidence_and_renders_operations_controls() -> None:
    stack = {
        "name": "evidence_stack",
        "runtime": "vllm",
        "model": "local-code",
        "endpoint": "http://localhost:8000/v1",
        "runtime_evidence": {
            "launch_manifest": {
                "launch": {"command": ["vllm", "serve", "org/model"]},
                "endpoint": {"health_path": "/health"},
            }
        },
    }
    payload = render_kubernetes(
        stack,
        image="registry.example/vllm@sha256:reviewed",
        device_class="gpu.example.com",
        claim_count=2,
        cpu="4",
        memory="32Gi",
        cache_size="100Gi",
        image_pull_policy="Never",
    )
    deployment = payload["files"]["deployment.yaml"]
    assert 'command: ["vllm", "serve", "org/model"]' in deployment
    assert "path: /health" in deployment
    assert "allowPrivilegeEscalation: false" in deployment
    assert "runAsNonRoot: true" in deployment
    assert "sizeLimit: 100Gi" in deployment
    assert "count: 2" in payload["files"]["resourceclaim.yaml"]
    assert payload["$schema"].endswith("aiplane-kubernetes-artifacts-v1.schema.json")


@pytest.mark.parametrize("kwargs", [{"memory": "lots"}, {"cpu": "-1"}, {"cache_size": "20 Gi"}])
def test_artifact_family_rejects_invalid_resource_quantities(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="Kubernetes quantity"):
        render_kubernetes(
            {"name": "demo", "model": "m", "runtime": "r", "endpoint": "http://x:8000"},
            image="example/runtime:tag",
            device_class="gpu.example.com",
            **kwargs,
        )
