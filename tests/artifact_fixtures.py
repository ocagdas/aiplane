from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from typing import Any

from aiplane.models import Profile


def copy_profile_targets(source: Profile) -> dict[str, Any]:
    return copy.deepcopy(source.targets)


def profile_with_targets(source: Profile, targets: dict[str, Any]) -> Profile:
    return replace(source, name="tmp", targets=copy.deepcopy(targets))


def profile_with_target_iac(source: Profile, target_name: str, iac: str) -> Profile:
    targets = copy_profile_targets(source)
    targets["targets"][target_name]["iac"] = iac
    return profile_with_targets(source, targets)


def profile_with_local_vm_target(
    source: Profile,
    provider: str,
    *,
    target_name: str = "local_dev_vm",
) -> Profile:
    targets = copy_profile_targets(source)
    targets.setdefault("targets", {})[target_name] = {
        "type": "local_vm",
        "provider": provider,
        "box": "bento/ubuntu-24.04",
        "cpus": 4,
        "memory_mb": 8192,
    }
    return profile_with_targets(source, targets)


def materialize_artifact_files(payload: dict[str, Any], destination: Path) -> dict[str, Path]:
    rendered: dict[str, Path] = {}
    for name, content in payload["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"artifact file name escapes destination: {name!r}")
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")
        rendered[name] = path
    return rendered
