from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import aiplane.cli as cli_module
import aiplane.mcp as mcp_module
from aiplane import config as agent_config
from aiplane.config import load_profile
from aiplane.models import Profile


_REAL_LOAD_PROFILE = load_profile


def _test_model_fixture() -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / "local-model-cache.yaml"
    return agent_config.parse_yaml(fixture_path.read_text(encoding="utf-8"))


def _ensure_repo_test_profile(
    name: str, profiles_dir: Path | str | None = None
) -> None:
    if profiles_dir is not None:
        return
    destination = Path.cwd() / "profiles" / name
    source = Path.cwd() / "profile-templates" / name
    if not source.is_dir():
        return
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        return
    for source_file in source.iterdir():
        if not source_file.is_file():
            continue
        destination_file = destination / source_file.name
        if source_file.name == "model-providers.yaml" or not destination_file.exists():
            shutil.copy2(source_file, destination_file)


@contextmanager
def _isolated_profiles_dir(name: str = "local-dev"):
    with tempfile.TemporaryDirectory() as tmp:
        profiles_dir = Path(tmp) / "profiles"
        source = Path.cwd() / "profile-templates" / name
        destination = profiles_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        yield profiles_dir


@contextmanager
def _isolated_test_profile(name: str = "local-dev", workspace: Path | None = None):
    with _isolated_profiles_dir(name) as profiles_dir:
        yield _load_profile_with_test_models(
            name, workspace or Path.cwd(), profiles_dir=profiles_dir
        )


def _load_profile_with_test_models(
    name: str, workspace: Path | None = None, profiles_dir: Path | str | None = None
) -> Profile:
    _ensure_repo_test_profile(name, profiles_dir=profiles_dir)
    profile = _REAL_LOAD_PROFILE(name, workspace, profiles_dir=profiles_dir)
    models = profile.models.get("models") if isinstance(profile.models, dict) else None
    fixture = _test_model_fixture()
    profile.models.setdefault("defaults", {}).update(fixture.get("defaults", {}))
    if not isinstance(models, dict):
        profile.models["models"] = {}
        models = profile.models["models"]
    for name, model in (fixture.get("models", {}) or {}).items():
        models.setdefault(name, model)
    from aiplane.runtime_catalog import PROVIDER_ENDPOINT_DEFAULTS

    providers = profile.models.setdefault("providers", {})
    if isinstance(providers, dict):
        for provider_name, provider in PROVIDER_ENDPOINT_DEFAULTS.items():
            providers.setdefault(provider_name, dict(provider))
    return profile


load_profile = _load_profile_with_test_models
agent_config.load_profile = _load_profile_with_test_models
cli_module.load_profile = _load_profile_with_test_models
mcp_module.load_profile = _load_profile_with_test_models

__all__ = [
    "_REAL_LOAD_PROFILE",
    "_ensure_repo_test_profile",
    "_isolated_profiles_dir",
    "_isolated_test_profile",
    "_load_profile_with_test_models",
    "_test_model_fixture",
    "load_profile",
]
