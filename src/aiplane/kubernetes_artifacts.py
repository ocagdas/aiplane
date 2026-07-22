"""Deterministic, render-only Kubernetes artifacts for an existing stack."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from .config import dump_yaml

_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_QUANTITY = re.compile(r"^(?:\d+(?:\.\d+)?|\.\d+)(?:[EPTGMK]i?|[numkMGTPE]|e[+-]?\d+)?$")


def render_kubernetes(
    stack: dict[str, Any],
    *,
    image: str,
    device_class: str,
    namespace: str = "default",
    replicas: int = 1,
    claim_count: int = 1,
    cpu: str = "1",
    memory: str = "4Gi",
    cache_size: str = "20Gi",
    image_pull_policy: str = "IfNotPresent",
    service_type: str = "ClusterIP",
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
    if claim_count < 1:
        raise ValueError("claim count must be at least 1")
    if image_pull_policy not in {"Always", "IfNotPresent", "Never"}:
        raise ValueError("image pull policy must be Always, IfNotPresent, or Never")
    if service_type not in {"ClusterIP", "NodePort", "LoadBalancer"}:
        raise ValueError("service type must be ClusterIP, NodePort, or LoadBalancer")
    for label, value in {"cpu": cpu, "memory": memory, "cache size": cache_size}.items():
        if not _QUANTITY.fullmatch(value):
            raise ValueError(f"{label} must be a non-negative Kubernetes quantity")
    endpoint = str(stack.get("endpoint") or "")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("stack endpoint must be an absolute HTTP(S) URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    evidence = stack.get("runtime_evidence") if isinstance(stack.get("runtime_evidence"), dict) else {}
    launch_manifest = evidence.get("launch_manifest") if isinstance(evidence.get("launch_manifest"), dict) else {}
    launch = launch_manifest.get("launch") if isinstance(launch_manifest.get("launch"), dict) else {}
    endpoint_evidence = launch_manifest.get("endpoint") if isinstance(launch_manifest.get("endpoint"), dict) else {}
    command = [str(value) for value in launch.get("command", [])] if isinstance(launch.get("command"), list) else []
    health_path = str(endpoint_evidence.get("health_path") or "/v1/models")
    if not health_path.startswith("/"):
        raise ValueError("launch health path must be absolute")
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
            f"          count: {claim_count}\n"
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
            f"          imagePullPolicy: {image_pull_policy}\n"
            + (f"          command: {json.dumps(command)}\n" if command else "")
            + "          securityContext:\n"
            "            allowPrivilegeEscalation: false\n"
            "            capabilities:\n"
            '              drop: ["ALL"]\n'
            "            runAsNonRoot: true\n"
            "          resources:\n"
            "            requests:\n"
            f"              cpu: {cpu}\n"
            f"              memory: {memory}\n"
            "            limits:\n"
            f"              memory: {memory}\n"
            "            claims:\n"
            "              - name: accelerator\n"
            "          env:\n"
            "            - name: AIPLANE_MODEL_ID\n"
            f"              value: {json.dumps(str(stack.get('model') or ''))}\n"
            "          ports:\n"
            f"            - name: http\n              containerPort: {port}\n"
            "          readinessProbe:\n"
            f"            httpGet:\n              path: {health_path}\n              port: http\n"
            "            initialDelaySeconds: 5\n"
            "            periodSeconds: 10\n"
            "          livenessProbe:\n"
            f"            httpGet:\n              path: {health_path}\n              port: http\n"
            "            initialDelaySeconds: 30\n"
            "            periodSeconds: 20\n"
            "          volumeMounts:\n"
            "            - name: model-cache\n"
            "              mountPath: /var/lib/aiplane/models\n"
            "      volumes:\n"
            "        - name: model-cache\n"
            f"          emptyDir:\n            sizeLimit: {cache_size}\n"
        ),
        "service.yaml": (
            "apiVersion: v1\n"
            "kind: Service\n"
            "metadata:\n"
            f"  name: {name}\n"
            f"  namespace: {namespace}\n"
            "spec:\n"
            f"  type: {service_type}\n"
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
                "image": {"repository": image, "pullPolicy": image_pull_policy},
                "model": {"alias": str(stack.get("model") or ""), "runtime": str(stack.get("runtime") or "")},
                "service": {"type": service_type, "port": port},
                "resources": {"cpu": cpu, "memory": memory, "cacheSize": cache_size},
                "health": {"path": health_path},
                "launch": {"command": command},
                "resourceClaim": {"name": claim_name, "deviceClassName": device_class, "count": claim_count},
            }
        ),
    }
    return {
        "$schema": "schemas/aiplane-kubernetes-artifacts-v1.schema.json",
        "schema_version": "1.0",
        "artifact_family": "kubernetes",
        "stack": name,
        "render_only": True,
        "apply_supported": False,
        "review_required": True,
        "files": files,
        "notes": [
            "Review the rendered command, image entrypoint, resource quantities, cache persistence, probes, security context, and device class before use.",
            "Aiplane does not apply these artifacts. No kubectl or Helm command was executed.",
            "The output contains model identity and topology only; credentials must be supplied separately.",
        ],
    }


def _name(value: str) -> str:
    normalized = value.lower().replace("_", "-")
    if len(normalized) > 63 or not _DNS_LABEL.fullmatch(normalized):
        raise ValueError(f"invalid Kubernetes name: {value!r}")
    return normalized
