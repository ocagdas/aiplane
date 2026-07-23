from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from aiplane import config as agent_config
from aiplane.config import load_profile
from aiplane.models import Profile


_REAL_LOAD_PROFILE = load_profile


def _test_model_fixture() -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / "local-model-cache.yaml"
    return agent_config.parse_yaml(fixture_path.read_text(encoding="utf-8"))


def _materialize_test_models(profile_root: Path) -> None:
    models_path = profile_root / "models.yaml"
    models_config = agent_config.parse_yaml(models_path.read_text(encoding="utf-8"))
    fixture = _test_model_fixture()
    models_config.setdefault("defaults", {}).update(fixture.get("defaults", {}))
    models = models_config.setdefault("models", {})
    for name, model in (fixture.get("models", {}) or {}).items():
        models.setdefault(name, model)

    from aiplane.runtime_catalog import PROVIDER_ENDPOINT_DEFAULTS

    providers = models_config.setdefault("providers", {})
    for provider_name, provider in PROVIDER_ENDPOINT_DEFAULTS.items():
        providers.setdefault(provider_name, dict(provider))
    models_path.write_text(agent_config.dump_yaml(models_config), encoding="utf-8")


def _ensure_repo_test_profile(name: str, profiles_dir: Path | str | None = None) -> None:
    if profiles_dir is not None:
        return
    destination = Path.cwd() / "profiles" / name
    source = Path.cwd() / "profile-templates" / name
    if not source.is_dir():
        return
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        _materialize_test_models(destination)
        return
    for source_file in source.iterdir():
        if not source_file.is_file():
            continue
        destination_file = destination / source_file.name
        if source_file.name == "model-providers.yaml" or not destination_file.exists():
            shutil.copy2(source_file, destination_file)
    _materialize_test_models(destination)


@contextmanager
def _isolated_profiles_dir(name: str = "local-dev"):
    with tempfile.TemporaryDirectory() as tmp:
        profiles_dir = Path(tmp) / "profiles"
        template_source = Path.cwd() / "profile-templates" / name
        prepared_root = os.environ.get("AIPLANE_PROFILES_DIR")
        prepared_source = Path(prepared_root) / name if prepared_root else None
        source = prepared_source if prepared_source is not None and prepared_source.is_dir() else template_source
        destination = profiles_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        if source == template_source:
            _materialize_test_models(destination)
        yield profiles_dir


@contextmanager
def _isolated_test_profile(name: str = "local-dev", workspace: Path | None = None):
    with _isolated_profiles_dir(name) as profiles_dir:
        yield _load_profile_with_test_models(name, workspace or Path.cwd(), profiles_dir=profiles_dir)


def _load_profile_with_test_models(
    name: str, workspace: Path | None = None, profiles_dir: Path | str | None = None
) -> Profile:
    if profiles_dir is None:
        env_profiles_dir = os.environ.get("AIPLANE_PROFILES_DIR")
        if env_profiles_dir:
            profiles_dir = Path(env_profiles_dir)
    _ensure_repo_test_profile(name, profiles_dir=profiles_dir)
    return _REAL_LOAD_PROFILE(name, workspace, profiles_dir=profiles_dir)


load_profile = _load_profile_with_test_models

__all__ = [
    "_REAL_LOAD_PROFILE",
    "_ensure_repo_test_profile",
    "_isolated_profiles_dir",
    "_isolated_test_profile",
    "_load_profile_with_test_models",
    "_materialize_test_models",
    "_test_model_fixture",
    "load_profile",
]
