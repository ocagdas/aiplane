from __future__ import annotations

from pathlib import Path
import os
import shutil
from typing import Any

from .models import Profile


CONFIG_FILES = {
    "hardware": "hardware.yaml",
    "backends": "backends.yaml",
    "repository": "repository.yaml",
    "tools": "tools.yaml",
    "approvals": "approvals.yaml",
    "environment": "environment.yaml",
    "models": "models.yaml",
    "targets": "targets.yaml",
    "orchestrators": "orchestrators.yaml",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def local_config_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.environ.get("AIPLANE_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return project_root() / ".aiplane" / "config.yaml"


def config_templates_root() -> Path:
    return project_root() / "config-templates"


def list_config_templates() -> list[str]:
    root = config_templates_root()
    if not root.exists():
        return []
    return sorted(path.stem for path in root.iterdir() if path.is_file() and path.suffix in {".yaml", ".yml"})


def load_local_config(path: Path | str | None = None) -> dict[str, Any]:
    config_path = local_config_path(path)
    if not config_path.exists():
        return {}
    return parse_yaml(config_path.read_text(encoding="utf-8"))


def init_local_config(template: str = "local", path: Path | str | None = None, overwrite: bool = False) -> Path:
    if not template or "/" in template or "\\" in template:
        raise ValueError("config template name must be a simple name")
    source = config_templates_root() / f"{template}.yaml"
    if not source.exists():
        raise ValueError(f"unknown config template: {template}")
    destination = local_config_path(path)
    if destination.exists() and not overwrite:
        raise ValueError(f"local config already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination



def default_profile() -> str:
    env_value = os.environ.get("AIPLANE_PROFILE")
    if env_value:
        return env_value
    configured = load_local_config().get("default_profile")
    return str(configured or "local-dev")


def set_default_profile(name: str, path: Path | str | None = None) -> Path:
    if not name or "/" in name or "\\" in name:
        raise ValueError("profile name must be a simple directory name")
    return set_local_config_value("default_profile", name, path=path)


def get_local_config_value(key: str, path: Path | str | None = None) -> Any:
    if not key or "." in key:
        raise ValueError("config get currently supports one top-level key")
    config = load_local_config(path)
    return config.get(key)


def set_local_config_value(key: str, value: Any, path: Path | str | None = None) -> Path:
    if not key or "." in key:
        raise ValueError("config set currently supports one top-level key")
    config_path = local_config_path(path)
    config = load_local_config(config_path)
    config[key] = value
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(dump_yaml(config), encoding="utf-8")
    return config_path


def profiles_root(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.environ.get("AIPLANE_PROFILES_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    config_path = local_config_path()
    if config_path.exists():
        configured = load_local_config(config_path).get("profiles_dir")
        if configured:
            return Path(str(configured)).expanduser().resolve()
    return project_root() / "profiles"


def profile_templates_root() -> Path:
    return project_root() / "profile-templates"


def list_profile_templates() -> list[str]:
    root = profile_templates_root()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def create_profile(name: str, template: str = "local-dev", overwrite: bool = False, profiles_dir: Path | str | None = None) -> Path:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError("profile name must be a simple directory name")
    source = profile_templates_root() / template
    if not source.is_dir():
        raise ValueError(f"unknown profile template: {template}")
    missing = [filename for filename in CONFIG_FILES.values() if not (source / filename).exists()]
    if missing:
        raise ValueError(f"profile template {template!r} is missing: {', '.join(missing)}")
    destination = profiles_root(profiles_dir) / name
    if destination.exists():
        if not overwrite:
            raise ValueError(f"profile already exists: {name}")
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def list_profiles(profiles_dir: Path | str | None = None) -> list[str]:
    root = profiles_root(profiles_dir)
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def resolve_profile_name(name: str | None = None, profiles_dir: Path | str | None = None) -> str:
    if name:
        return name
    profiles = list_profiles(profiles_dir)
    configured = default_profile()
    if configured in profiles:
        return configured
    if len(profiles) == 1:
        return profiles[0]
    if not profiles:
        raise ValueError(
            "no aiplane profiles found. Create one with: aiplane profiles create local-dev --template local-dev"
        )
    raise ValueError(
        "no valid default profile is configured. Set one with: "
        "aiplane config default-profile <name>, or pass --profile. "
        f"Available profiles: {', '.join(profiles)}"
    )


def load_profile(name: str, workspace: Path | None = None, profiles_dir: Path | str | None = None) -> Profile:
    root = profiles_root(profiles_dir) / name
    if not root.is_dir():
        raise ValueError(f"unknown profile: {name}")

    data = {}
    for key, filename in CONFIG_FILES.items():
        path = root / filename
        if not path.exists():
            raise ValueError(f"profile {name!r} is missing {filename}")
        data[key] = parse_yaml(path.read_text(encoding="utf-8"))

    return Profile(
        name=name,
        root=root,
        workspace=(workspace or Path.cwd()).resolve(),
        hardware=data["hardware"],
        backends=data["backends"],
        repository=data["repository"],
        tools=data["tools"],
        approvals=data["approvals"],
        environment=data["environment"],
        models=data["models"],
        targets=data["targets"],
        orchestrators=data["orchestrators"],
    )


def parse_yaml(text: str) -> dict[str, Any]:
    """Small YAML subset parser for the shipped profile files.

    It supports nested mappings, scalar values, and simple list values.
    PyYAML can replace this later; keeping v1 dependency-free makes the CLI
    runnable immediately in a clean Python environment.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        raw = lines[index]
        index += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if ":" not in stripped:
            raise ValueError(f"invalid YAML line: {raw}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            continue

        if value == "[]":
            parent[key] = []
        elif value.startswith("[") and value.endswith("]"):
            parent[key] = [_parse_scalar(item.strip()) for item in value[1:-1].split(",") if item.strip()]
        else:
            parent[key] = _parse_scalar(value)

    return root


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def dump_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    _dump_mapping(data, lines, 0)
    return "\n".join(lines) + "\n"


def _dump_mapping(data: dict[str, Any], lines: list[str], indent: int) -> None:
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            _dump_mapping(value, lines, indent + 2)
        else:
            lines.append(f"{prefix}{key}: {_format_scalar(value)}")


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, list):
        return "[" + ", ".join(_format_scalar(item) for item in value) + "]"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or text.strip() != text or text in {"null", "true", "false", "None", "True", "False"} or ":" in text or "#" in text:
        return repr(text)
    return text
