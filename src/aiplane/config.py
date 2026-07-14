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


OUTPUT_FORMAT_OPTIONS = {"text", "json"}
OUTPUT_FORMAT_CONFIG_KEY = "format"
OUTPUT_FORMAT_PROFILE_OVERRIDES_KEY = "profile_formats"
OUTPUT_FORMAT_COMMAND_OVERRIDES_KEY = "command_formats"

OUTPUT_VERBOSITY_OPTIONS = {0, 1, 2}
OUTPUT_VERBOSITY_CONFIG_KEY = "verbosity"
OUTPUT_VERBOSITY_PROFILE_OVERRIDES_KEY = "profile_verbosity"
OUTPUT_VERBOSITY_COMMAND_OVERRIDES_KEY = "command_verbosity"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_local_config_path() -> Path:
    return project_root() / ".aiplane" / "config.yaml"


def local_config_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.environ.get("AIPLANE_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return default_local_config_path()


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


def _validate_output_format(value: object) -> str:
    if not isinstance(value, str) or value not in OUTPUT_FORMAT_OPTIONS:
        raise ValueError(f"format must be one of: {', '.join(sorted(OUTPUT_FORMAT_OPTIONS))}")
    return value


def _validate_output_verbosity(value: object) -> int:
    try:
        verbosity = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"verbosity must be one of: {', '.join(str(v) for v in sorted(OUTPUT_VERBOSITY_OPTIONS))}")
    if verbosity not in OUTPUT_VERBOSITY_OPTIONS:
        raise ValueError(f"verbosity must be one of: {', '.join(str(v) for v in sorted(OUTPUT_VERBOSITY_OPTIONS))}")
    return verbosity


def get_output_format_override(path: Path | str | None = None, default: str = "text") -> str:
    config = load_local_config(path)
    return _validate_output_format(config.get(OUTPUT_FORMAT_CONFIG_KEY, default))


def get_profile_output_format(profile: str, path: Path | str | None = None) -> str | None:
    config = load_local_config(path)
    raw = config.get(OUTPUT_FORMAT_PROFILE_OVERRIDES_KEY, {})
    if not isinstance(raw, dict):
        return None
    value = raw.get(profile)
    if value is None:
        return None
    return _validate_output_format(value)


def get_command_output_format(command: str, path: Path | str | None = None) -> str | None:
    config = load_local_config(path)
    raw = config.get(OUTPUT_FORMAT_COMMAND_OVERRIDES_KEY, {})
    if not isinstance(raw, dict):
        return None
    value = raw.get(command)
    if value is None:
        return None
    return _validate_output_format(value)


def set_output_format(
    value: str,
    *,
    profile: str | None = None,
    command: str | None = None,
    path: Path | str | None = None,
) -> Path:
    _validate_output_format(value)
    config_path = local_config_path(path)
    config = load_local_config(config_path)
    if profile is not None and command is not None:
        raise ValueError("set_output_format accepts profile or command, but not both")
    if profile:
        _validate_profile_name(profile)
        profile_formats = config.get(OUTPUT_FORMAT_PROFILE_OVERRIDES_KEY, {})
        if not isinstance(profile_formats, dict):
            raise ValueError(f"{OUTPUT_FORMAT_PROFILE_OVERRIDES_KEY} must be a mapping")
        profile_formats[profile] = value
        config[OUTPUT_FORMAT_PROFILE_OVERRIDES_KEY] = profile_formats
    elif command:
        command_formats = config.get(OUTPUT_FORMAT_COMMAND_OVERRIDES_KEY, {})
        if not isinstance(command_formats, dict):
            raise ValueError(f"{OUTPUT_FORMAT_COMMAND_OVERRIDES_KEY} must be a mapping")
        command_formats[command] = value
        config[OUTPUT_FORMAT_COMMAND_OVERRIDES_KEY] = command_formats
    else:
        config[OUTPUT_FORMAT_CONFIG_KEY] = value
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(dump_yaml(config), encoding="utf-8")
    return config_path


def clear_output_format(
    profile: str | None = None,
    *,
    command: str | None = None,
    path: Path | str | None = None,
) -> Path:
    if profile is not None and command is not None:
        raise ValueError("clear_output_format accepts profile or command, but not both")
    config_path = local_config_path(path)
    config = load_local_config(config_path)
    if profile is None:
        if command is None:
            config.pop(OUTPUT_FORMAT_CONFIG_KEY, None)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(dump_yaml(config), encoding="utf-8")
            return config_path
        command_formats = config.get(OUTPUT_FORMAT_COMMAND_OVERRIDES_KEY, {})
        if not isinstance(command_formats, dict):
            command_formats = {}
        if command in command_formats:
            command_formats.pop(command)
        config[OUTPUT_FORMAT_COMMAND_OVERRIDES_KEY] = command_formats
    else:
        _validate_profile_name(profile)
        profile_formats = config.get(OUTPUT_FORMAT_PROFILE_OVERRIDES_KEY, {})
        if not isinstance(profile_formats, dict):
            profile_formats = {}
        if profile in profile_formats:
            profile_formats.pop(profile)
        config[OUTPUT_FORMAT_PROFILE_OVERRIDES_KEY] = profile_formats
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(dump_yaml(config), encoding="utf-8")
    return config_path


def resolve_output_format(
    explicit: str | None = None,
    *,
    profile: str | None = None,
    command: str | None = None,
    default: str = "text",
    path: Path | str | None = None,
) -> str:
    if explicit is not None:
        return _validate_output_format(explicit)
    if command:
        command_fmt = get_command_output_format(command, path=path)
        if command_fmt is not None:
            return command_fmt
    if profile:
        profile_fmt = get_profile_output_format(profile, path=path)
        if profile_fmt is not None:
            return profile_fmt
    return get_output_format_override(path=path, default=default)


def get_output_verbosity_override(path: Path | str | None = None) -> int:
    return _validate_output_verbosity(load_local_config(path).get(OUTPUT_VERBOSITY_CONFIG_KEY, 0))


def get_profile_output_verbosity(profile: str, path: Path | str | None = None) -> int | None:
    config = load_local_config(path)
    raw = config.get(OUTPUT_VERBOSITY_PROFILE_OVERRIDES_KEY, {})
    if not isinstance(raw, dict):
        return None
    value = raw.get(profile)
    if value is None:
        return None
    return _validate_output_verbosity(value)


def get_command_output_verbosity(command: str, path: Path | str | None = None) -> int | None:
    config = load_local_config(path)
    raw = config.get(OUTPUT_VERBOSITY_COMMAND_OVERRIDES_KEY, {})
    if not isinstance(raw, dict):
        return None
    value = raw.get(command)
    if value is None:
        return None
    return _validate_output_verbosity(value)


def set_output_verbosity(
    value: int,
    *,
    profile: str | None = None,
    command: str | None = None,
    path: Path | str | None = None,
) -> Path:
    verbosity = _validate_output_verbosity(value)
    config_path = local_config_path(path)
    config = load_local_config(config_path)
    if profile is not None and command is not None:
        raise ValueError("set_output_verbosity accepts profile or command, but not both")
    if profile:
        _validate_profile_name(profile)
        profile_verbosity = config.get(OUTPUT_VERBOSITY_PROFILE_OVERRIDES_KEY, {})
        if not isinstance(profile_verbosity, dict):
            raise ValueError(f"{OUTPUT_VERBOSITY_PROFILE_OVERRIDES_KEY} must be a mapping")
        profile_verbosity[profile] = verbosity
        config[OUTPUT_VERBOSITY_PROFILE_OVERRIDES_KEY] = profile_verbosity
    elif command:
        command_verbosity = config.get(OUTPUT_VERBOSITY_COMMAND_OVERRIDES_KEY, {})
        if not isinstance(command_verbosity, dict):
            raise ValueError(f"{OUTPUT_VERBOSITY_COMMAND_OVERRIDES_KEY} must be a mapping")
        command_verbosity[command] = verbosity
        config[OUTPUT_VERBOSITY_COMMAND_OVERRIDES_KEY] = command_verbosity
    else:
        config[OUTPUT_VERBOSITY_CONFIG_KEY] = verbosity
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(dump_yaml(config), encoding="utf-8")
    return config_path


def clear_output_verbosity(
    profile: str | None = None,
    *,
    command: str | None = None,
    path: Path | str | None = None,
) -> Path:
    if profile is not None and command is not None:
        raise ValueError("clear_output_verbosity accepts profile or command, but not both")
    config_path = local_config_path(path)
    config = load_local_config(config_path)
    if profile is None:
        if command is None:
            config.pop(OUTPUT_VERBOSITY_CONFIG_KEY, None)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(dump_yaml(config), encoding="utf-8")
            return config_path
        command_verbosity = config.get(OUTPUT_VERBOSITY_COMMAND_OVERRIDES_KEY, {})
        if not isinstance(command_verbosity, dict):
            command_verbosity = {}
        if command in command_verbosity:
            command_verbosity.pop(command)
        config[OUTPUT_VERBOSITY_COMMAND_OVERRIDES_KEY] = command_verbosity
    else:
        _validate_profile_name(profile)
        profile_verbosity = config.get(OUTPUT_VERBOSITY_PROFILE_OVERRIDES_KEY, {})
        if not isinstance(profile_verbosity, dict):
            profile_verbosity = {}
        if profile in profile_verbosity:
            profile_verbosity.pop(profile)
        config[OUTPUT_VERBOSITY_PROFILE_OVERRIDES_KEY] = profile_verbosity

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(dump_yaml(config), encoding="utf-8")
    return config_path


def resolve_output_verbosity(
    explicit: int | None = None,
    *,
    profile: str | None = None,
    command: str | None = None,
    default: int = 0,
    path: Path | str | None = None,
) -> int:
    if explicit is not None:
        return _validate_output_verbosity(explicit)
    if command:
        command_verbosity = get_command_output_verbosity(command, path=path)
        if command_verbosity is not None:
            return command_verbosity
    if profile:
        profile_verbosity = get_profile_output_verbosity(profile, path=path)
        if profile_verbosity is not None:
            return profile_verbosity
    return get_output_verbosity_override(path=path)


def default_profile(path: Path | str | None = None) -> str:
    env_value = os.environ.get("AIPLANE_PROFILE")
    if env_value:
        return env_value
    configured = load_local_config(path).get("default_profile")
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


def agent_artifacts_root(path: Path | str | None = None, config_path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.environ.get("AIPLANE_AGENT_ARTIFACTS_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    resolved_config_path = local_config_path(config_path)
    if resolved_config_path.exists():
        configured = load_local_config(resolved_config_path).get("agent_artifacts_dir")
        if configured:
            return Path(str(configured)).expanduser().resolve()
    return project_root() / ".aiplane" / "agents"


def default_profiles_root() -> Path:
    return project_root() / "profiles"


def profiles_root(path: Path | str | None = None, config_path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.environ.get("AIPLANE_PROFILES_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    resolved_config_path = local_config_path(config_path)
    if resolved_config_path.exists():
        configured = load_local_config(resolved_config_path).get("profiles_dir")
        if configured:
            return Path(str(configured)).expanduser().resolve()
    return default_profiles_root()


def profile_templates_root() -> Path:
    return project_root() / "profile-templates"


def list_profile_templates() -> list[str]:
    root = profile_templates_root()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def create_profile(
    name: str,
    template: str = "local-dev",
    overwrite: bool = False,
    profiles_dir: Path | str | None = None,
) -> Path:
    _validate_profile_name(name)
    source = _profile_template_path(template)
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


def remove_profile(
    name: str,
    *,
    yes: bool = False,
    dry_run: bool = False,
    profiles_dir: Path | str | None = None,
) -> dict[str, Any]:
    _validate_profile_name(name)
    destination = profiles_root(profiles_dir) / name
    if not destination.is_dir():
        raise ValueError(f"unknown profile: {name}")
    preview = dry_run or not yes
    if not preview:
        shutil.rmtree(destination)
    return {
        "profile": name,
        "path": str(destination),
        "removed": not preview,
        "would_remove": preview,
        "requires_yes": not yes,
    }


def repair_profile(
    name: str,
    template: str = "local-dev",
    files: list[str] | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    profiles_dir: Path | str | None = None,
) -> dict[str, Any]:
    _validate_profile_name(name)
    source = _profile_template_path(template)
    destination = profiles_root(profiles_dir) / name
    if not destination.is_dir():
        raise ValueError(f"unknown profile: {name}")
    requested = files or list(CONFIG_FILES.values())
    allowed = set(CONFIG_FILES.values())
    invalid = [filename for filename in requested if filename not in allowed]
    if invalid:
        raise ValueError(f"unknown profile file: {', '.join(invalid)}")

    copied: list[str] = []
    would_copy: list[str] = []
    skipped_existing: list[str] = []
    for filename in requested:
        source_file = source / filename
        if not source_file.exists():
            raise ValueError(f"profile template {template!r} is missing: {filename}")
        destination_file = destination / filename
        should_copy = overwrite or not destination_file.exists()
        if not should_copy:
            skipped_existing.append(filename)
            continue
        if dry_run:
            would_copy.append(filename)
            continue
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)
        copied.append(filename)
    return {
        "profile": name,
        "template": template,
        "path": str(destination),
        "overwrite": overwrite,
        "dry_run": dry_run,
        "copied": copied,
        "would_copy": would_copy,
        "skipped_existing": skipped_existing,
    }


def _validate_profile_name(name: str) -> None:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError("profile name must be a simple directory name")


def _profile_template_path(template: str) -> Path:
    if not template or template in {".", ".."} or "/" in template or "\\" in template:
        raise ValueError("profile template name must be a simple directory name")
    source = profile_templates_root() / template
    if not source.is_dir():
        raise ValueError(f"unknown profile template: {template}")
    return source


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
    if (
        text == ""
        or text.strip() != text
        or text in {"null", "true", "false", "None", "True", "False"}
        or ":" in text
        or "#" in text
    ):
        return repr(text)
    return text
