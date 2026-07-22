"""Deterministic, render-only Kubernetes artifacts for an existing stack."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from .config import dump_yaml

_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def render_kubernetes(
    stack: dict[str, Any],
    *,
    image: str,
    device_class: str,
    namespace: str = "default",
    replicas: int = 1,
) -> dict[str, Any]:
    name = _name(str(stack.get("name") or ""))
    namespace = _name(namespace)
    device_class = device_class.strip()
    if not device_class or any(character.isspace() for character in device_class):
        raise ValueError("device class must be a non-empty Kubernetes device class name")
    if not image.strip() or any(character.isspace() for character in image):
        raise ValueError("image must be a non-empty container image reference")
    if replicas < 1:
        raise ValueError("replicas must be at least 1")
    endpoint = str(stack.get("endpoint") or "")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("stack endpoint must be an absolute HTTP(S) URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    claim_name = f"{name}-accelerator"
    files = {
        "resourceclaim.yaml": (
            "apiVersion: resource.k8s.io/v1\n"
            "kind: ResourceClaim\n"
            "metadata:\n"
            f"  name: {claim_name}\n"
            f"  namespace: {namespace}\n"
            "spec:\n"
            "  devices:\n"
            "    requests:\n"
            "      - name: accelerator\n"
            f"        exactly:\n          deviceClassName: {device_class}\n"
            "          allocationMode: ExactCount\n"
            "          count: 1\n"
        ),
        "deployment.yaml": (
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            f"  name: {name}\n"
            f"  namespace: {namespace}\n"
            "spec:\n"
            f"  replicas: {replicas}\n"
            "  selector:\n"
            "    matchLabels:\n"
            f"      app.kubernetes.io/name: {name}\n"
            "  template:\n"
            "    metadata:\n"
            "      labels:\n"
            f"        app.kubernetes.io/name: {name}\n"
            "    spec:\n"
            "      resourceClaims:\n"
            "        - name: accelerator\n"
            f"          resourceClaimName: {claim_name}\n"
            "      containers:\n"
            f"        - name: {name}\n"
            f"          image: {image}\n"
            "          resources:\n"
            "            claims:\n"
            "              - name: accelerator\n"
            "          env:\n"
            "            - name: AIPLANE_MODEL_ID\n"
            f"              value: {json.dumps(str(stack.get('model') or ''))}\n"
            "          ports:\n"
            f"            - name: http\n              containerPort: {port}\n"
        ),
        "service.yaml": (
            "apiVersion: v1\n"
            "kind: Service\n"
            "metadata:\n"
            f"  name: {name}\n"
            f"  namespace: {namespace}\n"
            "spec:\n"
            "  selector:\n"
            f"    app.kubernetes.io/name: {name}\n"
            "  ports:\n"
            "    - name: http\n"
            f"      port: {port}\n"
            f"      targetPort: {port}\n"
        ),
        "values.yaml": dump_yaml(
            {
                "nameOverride": name,
                "namespace": namespace,
                "replicaCount": replicas,
                "image": {"repository": image, "pullPolicy": "IfNotPresent"},
                "model": {"alias": str(stack.get("model") or ""), "runtime": str(stack.get("runtime") or "")},
                "service": {"port": port},
                "resourceClaim": {"name": claim_name, "deviceClassName": device_class, "count": 1},
            }
        ),
    }
    return {
        "schema_version": "1.0",
        "artifact_family": "kubernetes",
        "stack": name,
        "render_only": True,
        "apply_supported": False,
        "review_required": True,
        "files": files,
        "notes": [
            "Review image entrypoint, ports, storage, probes, security context, and device class before use.",
            "Aiplane does not apply these artifacts. No kubectl or Helm command was executed.",
            "The output contains model identity and topology only; credentials must be supplied separately.",
        ],
    }


def _name(value: str) -> str:
    normalized = value.lower().replace("_", "-")
    if len(normalized) > 63 or not _DNS_LABEL.fullmatch(normalized):
        raise ValueError(f"invalid Kubernetes name: {value!r}")
    return normalized
