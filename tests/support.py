# ruff: noqa: F401
from __future__ import annotations

import json
import os
import subprocess
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO, StringIO
import unittest
from unittest.mock import patch
from pathlib import Path

from aiplane.approvals import ApprovalHandler
from aiplane.audit import AuditLogger
from aiplane.benchmarks import BenchmarkRunner
from aiplane.backends import BackendResult, OllamaBackend
from aiplane.cli import main as cli_main
import aiplane.cli as cli_module
import aiplane.mcp as mcp_module
from aiplane.code_tasks import CodeTaskResult, CodeTaskRunner
from aiplane import config as agent_config
from aiplane.config import (
    create_profile,
    default_profile,
    repair_profile,
    init_local_config,
    list_config_templates,
    list_profile_templates,
    parse_yaml,
    load_local_config,
    load_profile,
    remove_profile,
    resolve_profile_name,
    set_default_profile,
)
from aiplane.deploy import DeployManager
from aiplane.env import EnvironmentManager
from aiplane.hardware import HardwareManager
from aiplane.integrations import IntegrationManager
from aiplane.machines import MachineManager
from aiplane.mcp import AiplaneMcpServer, _read_message, _write_message, mcp_manifest
from aiplane.model_catalog import ModelCatalog, _discovered_model_entry
from aiplane.model_filters import (
    ACCELERATOR_API_CHOICES,
    GPU_VENDOR_CHOICES,
    MODEL_FILTER_SCHEMA_PROPERTIES,
    MODEL_SORT_CHOICES,
)
from aiplane.model_output import group_model_rows
from aiplane.orchestrators import OrchestratorCatalog
from aiplane.models import Profile
from aiplane.policy import PolicyEngine
from aiplane.providers import ProviderModelsResult, ProviderRegistry
from aiplane.remote import RemoteManager
from aiplane.router import Router
from aiplane.runtime_catalog import RuntimeCatalog
from aiplane.runtime_pull import ollama_model_id, runtime_pull_support
from aiplane.stacks import StackManager
from aiplane.secrets import contains_secret, redact
from aiplane.tools import ToolExecutor


class OpenAICompatibleTestHandler(BaseHTTPRequestHandler):
    model_id = "test-model"

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._json({"data": [{"id": self.model_id}]})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            self._json({"choices": [{"message": {"content": f"handled {body['model']}"}}]})
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestHttpServer:
    def __enter__(self) -> str:
        self.server = HTTPServer(("127.0.0.1", 0), OpenAICompatibleTestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


_REAL_LOAD_PROFILE = load_profile


def _test_model_fixture() -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / "local-model-cache.yaml"
    return agent_config.parse_yaml(fixture_path.read_text(encoding="utf-8"))


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
        yield _load_profile_with_test_models(name, workspace or Path.cwd(), profiles_dir=profiles_dir)


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

__all__ = [name for name in globals() if not name.startswith("__")]
