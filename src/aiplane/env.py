from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import dump_yaml
from .models import Profile


@dataclass(frozen=True)
class ExecutionPlan:
    mode: str
    command: list[str]
    cwd: Path
    description: str


class EnvironmentManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.config = profile.environment or {}

    def active_mode(self) -> str:
        return str(self.config.get("active", "system"))

    def modes(self) -> dict[str, object]:
        return dict(self.config.get("modes", {}))

    def show(self) -> dict[str, object]:
        return {
            "active": self.active_mode(),
            "modes": self.modes(),
        }

    def list_modes(self) -> list[dict[str, object]]:
        active = self.active_mode()
        rows = []
        for name, config in self.modes().items():
            rows.append(
                {
                    "name": name,
                    "active": name == active,
                    "config": config,
                }
            )
        return sorted(rows, key=lambda row: str(row["name"]))

    def active(self) -> dict[str, object]:
        active = self.active_mode()
        modes = self.modes()
        return {
            "active": active,
            "config": modes.get(active, {}),
            "available": sorted(modes),
        }

    def use(self, mode: str) -> dict[str, object]:
        modes = self.modes()
        if mode not in modes:
            raise ValueError(f"unknown environment mode: {mode}")
        self.config["active"] = mode
        path = self.profile.root / "environment.yaml"
        path.write_text(dump_yaml(self.config), encoding="utf-8")
        return {
            "active": mode,
            "path": str(path),
            "config": modes.get(mode, {}),
        }

    def plan(self, command: list[str], mode: str | None = None) -> ExecutionPlan:
        if not command:
            raise ValueError("command cannot be empty")
        mode = mode or self.active_mode()
        modes = self.modes()
        mode_config = modes.get(mode, {})
        if mode == "system":
            return ExecutionPlan(mode, command, self.profile.workspace, "host system shell")
        if mode == "venv":
            return self._venv_plan(command, mode_config)
        if mode == "conda":
            return self._conda_plan(command, mode_config)
        if mode == "docker":
            return self._docker_plan(command, mode_config)
        raise ValueError(f"unknown environment mode: {mode}")

    def _venv_plan(self, command: list[str], config: object) -> ExecutionPlan:
        cfg = config if isinstance(config, dict) else {}
        path = Path(str(cfg.get("path", ".venv")))
        if not path.is_absolute():
            path = self.profile.workspace / path
        python_path = path / "bin" / "python"
        planned = [str(python_path), *command[1:]] if command[0] == "python" else command
        return ExecutionPlan("venv", planned, self.profile.workspace, f"venv at {path}")

    def _conda_plan(self, command: list[str], config: object) -> ExecutionPlan:
        cfg = config if isinstance(config, dict) else {}
        executable = str(cfg.get("executable", "conda"))
        name = str(cfg.get("name", "aiplane"))
        return ExecutionPlan(
            "conda",
            [executable, "run", "-n", name, *command],
            self.profile.workspace,
            f"conda env {name}",
        )

    def _docker_plan(self, command: list[str], config: object) -> ExecutionPlan:
        cfg = config if isinstance(config, dict) else {}
        image = str(cfg.get("image", "python:3.13-slim"))
        workdir = str(cfg.get("workdir", "/workspace"))
        volume = f"{self.profile.workspace}:{workdir}"
        planned = ["docker", "run", "--rm", "-v", volume, "-w", workdir]

        cpus = cfg.get("cpus")
        if cpus not in (None, "", "null"):
            planned.extend(["--cpus", str(cpus)])

        memory = cfg.get("memory")
        if memory not in (None, "", "null"):
            planned.extend(["--memory", str(memory)])

        gpus = cfg.get("gpus")
        if gpus not in (None, "", "none", "null"):
            planned.extend(["--gpus", str(gpus)])

        shm_size = cfg.get("shm_size")
        if shm_size not in (None, "", "null"):
            planned.extend(["--shm-size", str(shm_size)])

        for device in _list_value(cfg.get("devices")):
            planned.extend(["--device", str(device)])

        for env_name in _list_value(cfg.get("env")):
            planned.extend(["-e", str(env_name)])

        network = cfg.get("network")
        if network not in (None, "", "null"):
            planned.extend(["--network", str(network)])

        planned.extend([image, *command])
        return ExecutionPlan("docker", planned, self.profile.workspace, f"docker image {image}")


def _list_value(value: object) -> list[object]:
    if value in (None, "", "null"):
        return []
    if isinstance(value, list):
        return value
    return [value]
