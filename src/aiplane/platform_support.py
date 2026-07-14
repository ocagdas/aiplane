from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HostPlatform:
    system: str
    distribution: str | None
    distribution_like: tuple[str, ...]
    machine: str
    wsl: bool = False

    @property
    def normalized_system(self) -> str:
        return self.system.strip().lower()

    @property
    def linux(self) -> bool:
        return self.normalized_system == "linux"

    @property
    def debian_family(self) -> bool:
        ids = {self.distribution or "", *self.distribution_like}
        return bool(ids & {"ubuntu", "debian"})

    @property
    def runtime_helper_supported(self) -> bool:
        return self.linux and self.debian_family and not self.wsl

    @property
    def linux_hardware_probes_supported(self) -> bool:
        return self.linux

    def summary(self) -> dict[str, object]:
        return {
            "system": self.system,
            "distribution": self.distribution,
            "distribution_like": list(self.distribution_like),
            "machine": self.machine,
            "wsl": self.wsl,
        }

    def unsupported(self, operation: str, supported_platforms: list[str], reason: str) -> dict[str, object]:
        return {
            "name": "unsupported_platform",
            "operation": operation,
            "platform": self.summary(),
            "supported_platforms": supported_platforms,
            "reason": reason,
        }


def detect_host_platform(
    *,
    system: str | None = None,
    machine: str | None = None,
    os_release_text: str | None = None,
    proc_version_text: str | None = None,
) -> HostPlatform:
    resolved_system = system or platform.system()
    resolved_machine = machine or platform.machine()
    if os_release_text is None and resolved_system.lower() == "linux":
        try:
            os_release_text = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
        except OSError:
            os_release_text = ""
    release = _parse_os_release(os_release_text or "")
    if proc_version_text is None and resolved_system.lower() == "linux":
        try:
            proc_version_text = Path("/proc/version").read_text(encoding="utf-8", errors="replace")
        except OSError:
            proc_version_text = ""
    markers = " ".join(
        [
            proc_version_text or "",
            release.get("WSL_DISTRO_NAME", ""),
            platform.release() if resolved_system.lower() == "linux" else "",
        ]
    ).lower()
    distribution = release.get("ID", "").lower() or None
    distribution_like = tuple(part.lower() for part in release.get("ID_LIKE", "").split() if part)
    return HostPlatform(
        system=resolved_system,
        distribution=distribution,
        distribution_like=distribution_like,
        machine=resolved_machine,
        wsl="microsoft" in markers or "wsl" in markers,
    )


def _parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip()
    return values
