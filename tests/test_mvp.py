from __future__ import annotations

import json
import os
import subprocess
import shutil
import tempfile
import threading
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO, StringIO
import unittest
from unittest.mock import patch
from pathlib import Path

from aiplane.approvals import ApprovalHandler
from aiplane.audit import AuditLogger
from aiplane.benchmarks import BenchmarkRunner
from aiplane.cli import main as cli_main
import aiplane.cli as cli_module
import aiplane.mcp as mcp_module
from aiplane.code_tasks import CodeTaskRunner
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
from aiplane.orchestrators import OrchestratorCatalog
from aiplane.models import Profile
from aiplane.policy import PolicyEngine
from aiplane.providers import ProviderModelsResult, ProviderRegistry
from aiplane.remote import RemoteManager
from aiplane.router import Router
from aiplane.runtime_catalog import RuntimeCatalog
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
    if destination.exists():
        return
    source = Path.cwd() / "profile-templates" / name
    if source.is_dir():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)


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


class MvpTests(unittest.TestCase):
    def test_profile_loads(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        self.assertEqual(profile.name, "local-dev")
        self.assertEqual(profile.tools["mode"], "full_automation")

    def test_shipped_profile_template_does_not_hardcode_model_entries(self) -> None:
        data = agent_config.parse_yaml(
            (Path.cwd() / "profile-templates/local-dev/models.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(data.get("defaults"), {})
        self.assertEqual(data.get("models"), {})
        self.assertNotIn("providers", data)

    def test_profile_templates_are_listed(self) -> None:
        self.assertIn("local-dev", list_profile_templates())

    def test_create_profile_copies_template_without_modifying_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            templates = root / "profile-templates" / "base"
            templates.mkdir(parents=True)
            for filename in agent_config.CONFIG_FILES.values():
                (templates / filename).write_text("value: original\n", encoding="utf-8")
            profiles = root / "profiles"
            profiles.mkdir()
            original_project_root = agent_config.project_root
            agent_config.project_root = lambda: root
            try:
                created = create_profile("custom", template="base")
            finally:
                agent_config.project_root = original_project_root
            self.assertEqual(created, profiles / "custom")
            (created / "models.yaml").write_text("value: changed\n", encoding="utf-8")
            self.assertEqual(
                (templates / "models.yaml").read_text(encoding="utf-8"),
                "value: original\n",
            )

    def test_create_profile_supports_custom_profiles_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            templates = root / "profile-templates" / "base"
            templates.mkdir(parents=True)
            for filename in agent_config.CONFIG_FILES.values():
                (templates / filename).write_text("value: original\n", encoding="utf-8")
            custom_profiles = root / "custom-profiles"
            original_project_root = agent_config.project_root
            agent_config.project_root = lambda: root
            try:
                created = create_profile("custom", template="base", profiles_dir=custom_profiles)
                self.assertEqual(agent_config.list_profiles(custom_profiles), ["custom"])
            finally:
                agent_config.project_root = original_project_root
            self.assertEqual(created, custom_profiles / "custom")

    def test_repair_profile_restores_missing_models_yaml_from_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            models_path = profiles_dir / "local-dev" / "models.yaml"
            models_path.unlink()

            result = repair_profile("local-dev", files=["models.yaml"], profiles_dir=profiles_dir)

            self.assertEqual(result["copied"], ["models.yaml"])
            self.assertTrue(models_path.exists())
            restored = agent_config.parse_yaml(models_path.read_text(encoding="utf-8"))
            self.assertEqual(restored.get("defaults"), {})
            self.assertEqual(restored.get("models"), {})
            self.assertNotIn("providers", restored)
            profile = _REAL_LOAD_PROFILE("local-dev", Path.cwd(), profiles_dir=profiles_dir)
            self.assertTrue(cli_module._validate_profile(profile)["ok"])

    def test_profiles_repair_cli_restores_selected_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            models_path = profiles_dir / "local-dev" / "models.yaml"
            models_path.unlink()
            stdout = StringIO()

            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "repair",
                        "local-dev",
                        "--file",
                        "models.yaml",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["copied"], ["models.yaml"])
            self.assertEqual(payload["skipped_existing"], [])
            self.assertTrue(models_path.exists())

    def test_profiles_repair_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            models_path = profiles_dir / "local-dev" / "models.yaml"
            models_path.unlink()
            stdout = StringIO()

            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "repair",
                        "local-dev",
                        "--file",
                        "models.yaml",
                        "--dry-run",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["would_copy"], ["models.yaml"])
            self.assertFalse(models_path.exists())

    def test_profiles_bootstrap_local_creates_template_profile_without_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "bootstrap-local",
                        "--no-discovery",
                    ]
                )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(code, 0)
            self.assertTrue(payload["created"])
            self.assertFalse(payload["discovery_requested"])
            self.assertTrue(payload["validation"]["ok"])
            models_path = profiles_dir / "local-dev" / "models.yaml"
            self.assertTrue(models_path.exists())
            self.assertFalse((profiles_dir / "local-dev" / "models.discovered.yaml").exists())
            models_config = agent_config.parse_yaml(models_path.read_text(encoding="utf-8"))
            self.assertEqual(models_config.get("defaults"), {})
            self.assertEqual(models_config.get("models"), {})
            self.assertNotIn("providers", models_config)

            profile = _REAL_LOAD_PROFILE("local-dev", Path.cwd(), profiles_dir=profiles_dir)
            runtimes = RuntimeCatalog(profile).list(include_gui=True)
            ollama = next(row for row in runtimes if row["name"] == "ollama")
            self.assertFalse(ollama["configured"])
            self.assertTrue(ollama["enabled"])
            self.assertEqual(ollama["endpoint"], "http://localhost:11434")
            self.assertEqual(ModelCatalog(profile).providers()["ollama"]["origin"], "default_runtime_catalog")

    def test_profiles_root_uses_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("AIPLANE_PROFILES_DIR")
            os.environ["AIPLANE_PROFILES_DIR"] = tmp
            try:
                self.assertEqual(agent_config.profiles_root(), Path(tmp).resolve())
            finally:
                if old is None:
                    os.environ.pop("AIPLANE_PROFILES_DIR", None)
                else:
                    os.environ["AIPLANE_PROFILES_DIR"] = old

    def test_local_config_template_is_listed(self) -> None:
        self.assertIn("local", list_config_templates())

    def test_local_config_can_set_profiles_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            profiles_dir = root / "external-profiles"
            config_path.write_text(f"profiles_dir: {profiles_dir}\n", encoding="utf-8")
            old_config = os.environ.get("AIPLANE_CONFIG")
            old_profiles = os.environ.get("AIPLANE_PROFILES_DIR")
            os.environ["AIPLANE_CONFIG"] = str(config_path)
            os.environ.pop("AIPLANE_PROFILES_DIR", None)
            try:
                self.assertEqual(agent_config.profiles_root(), profiles_dir.resolve())
            finally:
                if old_config is None:
                    os.environ.pop("AIPLANE_CONFIG", None)
                else:
                    os.environ["AIPLANE_CONFIG"] = old_config
                if old_profiles is not None:
                    os.environ["AIPLANE_PROFILES_DIR"] = old_profiles

    def test_init_local_config_copies_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            created = init_local_config(path=path)
            self.assertEqual(created, path)
            loaded = load_local_config(path)
            self.assertIn("profiles_dir", loaded)
            self.assertEqual(loaded["default_profile"], "local-dev")

    def test_default_profile_comes_from_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            old_config = os.environ.get("AIPLANE_CONFIG")
            old_profile = os.environ.get("AIPLANE_PROFILE")
            os.environ["AIPLANE_CONFIG"] = str(config_path)
            os.environ.pop("AIPLANE_PROFILE", None)
            try:
                set_default_profile("custom", path=config_path)
                self.assertEqual(default_profile(), "custom")
            finally:
                if old_config is None:
                    os.environ.pop("AIPLANE_CONFIG", None)
                else:
                    os.environ["AIPLANE_CONFIG"] = old_config
                if old_profile is not None:
                    os.environ["AIPLANE_PROFILE"] = old_profile

    def test_resolve_profile_uses_single_available_profile_and_errors_without_profiles(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            profiles_root = Path(tmp) / "profiles"
            only = profiles_root / "only-one"
            only.mkdir(parents=True)
            for filename, data in agent_config.CONFIG_FILES.items():
                (only / data).write_text(agent_config.dump_yaml(getattr(source, filename)), encoding="utf-8")
            self.assertEqual(resolve_profile_name(None, profiles_dir=profiles_root), "only-one")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "profiles create local-dev"):
                resolve_profile_name(None, profiles_dir=Path(tmp) / "empty")

    def test_config_default_profile_cli_sets_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "default-profile",
                        "local-dev",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(load_local_config(config_path)["default_profile"], "local-dev")

    def test_config_get_set_cli_updates_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "set",
                        "profiles_dir",
                        str(Path(tmp) / "profiles"),
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertIn("profiles_dir", load_local_config(config_path))
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "get", "profiles_dir", "--path", str(config_path)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["key"], "profiles_dir")

    def test_config_show_includes_default_and_active_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            shutil.copytree(
                Path.cwd() / "profile-templates" / "local-dev",
                profiles_dir / "local-dev",
            )
            config_path = root / "config.yaml"
            config_path.write_text(
                f"default_profile: local-dev\nprofiles_dir: {profiles_dir}\ncredentials_path: {root / 'credentials.yaml'}\nagent_artifacts_dir: {root / 'agents'}\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "show", "--path", str(config_path)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["path"], str(config_path.resolve()))
            self.assertEqual(payload["paths"]["config"]["active"], str(config_path.resolve()))
            self.assertTrue(payload["paths"]["config"]["default"].endswith(".aiplane/config.yaml"))
            self.assertEqual(payload["paths"]["profiles"]["active_root"], str(profiles_dir.resolve()))
            self.assertTrue(payload["paths"]["profiles"]["default_root"].endswith("profiles"))
            self.assertEqual(
                payload["paths"]["profiles"]["default_profile_path"],
                str((profiles_dir / "local-dev").resolve()),
            )
            self.assertEqual(
                payload["paths"]["profiles"]["current_profile_path"],
                str((profiles_dir / "local-dev").resolve()),
            )
            self.assertEqual(
                payload["effective"]["credentials_path"],
                str((root / "credentials.yaml").resolve()),
            )
            self.assertEqual(
                payload["effective"]["agent_artifacts_dir"],
                str((root / "agents").resolve()),
            )

    def test_profiles_show_defaults_to_effective_profile(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["profiles", "show", "--selected"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "local-dev")
        self.assertIn("environment", payload)
        self.assertIn("models", payload)

    def test_profiles_show_full_starts_with_name_and_selected(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["profiles", "show", "local-dev"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            list(payload.keys())[:5],
            ["name", "default", "root", "workspace", "selected"],
        )
        self.assertIn("environment", payload["selected"])

    def test_profiles_selected_entries_put_name_first(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        selected = __import__("aiplane.cli", fromlist=["_profile_selected"])._profile_selected(profile, "local-dev")
        self.assertTrue(selected["models"])
        self.assertEqual(next(iter(selected["models"][0].keys())), "name")
        self.assertTrue(selected["providers"])
        self.assertEqual(next(iter(selected["providers"][0].keys())), "name")

    def test_profiles_validate_accepts_default_profile(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["profiles", "validate", "local-dev"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["name"], "local-dev")

    def test_top_level_help_has_examples_and_command_descriptions(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli_main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("Common flows", output)
        self.assertIn("Configure, check, and connect", output)
        self.assertIn("hardware", output)

    def test_command_help_mentions_argument_purpose(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli_main(["integrations", "export", "--help"])
        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("Print configuration", output)
        self.assertIn("Override provider endpoint", output)
        self.assertIn("Endpoint examples", output)

    def test_tool_command_accepts_passthrough_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(
                Path.cwd() / "profile-templates" / "local-dev",
                profiles_dir / "local-dev",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--workspace",
                        str(workspace),
                        "--profiles-dir",
                        str(profiles_dir),
                        "tool",
                        "--profile",
                        "local-dev",
                        "run_tests",
                        "python",
                        "-c",
                        "print('ok')",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertIn("ok", stdout.getvalue())

    def test_policy_allows_read_and_requires_write_approval(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        policy = PolicyEngine(profile)
        self.assertFalse(policy.tool_decision("read_file").requires_approval)
        self.assertTrue(policy.tool_decision("write_file").requires_approval)

    def test_workspace_boundary_blocks_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            decision = PolicyEngine(profile).path_decision(Path(tmp).parent / "outside.txt")
            self.assertFalse(decision.allowed)

    def test_secret_detection_and_redaction(self) -> None:
        text = "api_key = 'abcdefghijklmnop'"
        self.assertTrue(contains_secret(text))
        self.assertEqual(redact(text), "[REDACTED_SECRET]")

    def test_credentials_cli_lists_and_redacts_local_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.yaml"
            path.write_text(
                "providers:\n"
                "  openai:\n"
                "    accounts:\n"
                "      personal:\n"
                "        api_key: dummy-api-key-value-123456\n"
                "        endpoint: https://api.openai.com/v1\n"
                "      business_a:\n"
                "        api_key_env: OPENAI_BUSINESS_A_API_KEY\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["credentials", "list", "--path", str(path)])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            refs = {row["ref"] for row in payload["credentials"]}
            self.assertIn("openai.personal", refs)
            self.assertIn("openai.business_a", refs)

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["credentials", "show", "openai.personal", "--path", str(path)])
            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertIn("[REDACTED_SECRET]", output)
            self.assertNotIn("dummy-api-key-value-123456", output)

    def test_credentials_cli_missing_file_lists_empty_without_path_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing-credentials.yaml"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["credentials", "list", "--path", str(path)])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload, {"name": "credentials", "credentials": []})
        self.assertNotIn("missing-credentials.yaml", stdout.getvalue())

    def test_router_blocks_secret_cloud_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            router = Router(profile, AuditLogger(profile))
            with self.assertRaises(PermissionError):
                router.route("token=abcdefghijklmnop", prefer_escalation=True)

    def test_router_run_dry_run_selects_enabled_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            result = Router(profile, AuditLogger(profile)).route("explain setup", dry_run=True)
            self.assertEqual(result.backend, "dry_run")
            self.assertFalse(result.escalated)
            self.assertIn("local-analysis-small", result.text)
            self.assertIn("provider-text-small:0.5b", result.text)

    def test_router_uses_profile_self_managed_model_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            profile.models["defaults"]["self_managed_model"] = "local-code-small"
            result = Router(profile, AuditLogger(profile)).route("explain setup", dry_run=True)
            self.assertIn("local-code-small", result.text)

    def test_router_run_dry_run_can_use_explicit_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            result = Router(profile, AuditLogger(profile)).route(
                "explain setup", model_name="local-code-small", dry_run=True
            )
            self.assertIn("local-code-small", result.text)
            self.assertIn("provider-code-small:1.5b", result.text)

    def test_router_run_blocks_managed_service_model_when_policy_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            profile.repository["allow_cloud"] = False
            profile.models.setdefault("providers", {})["openai"] = {
                "ownership": "managed_service",
                "runtime": "openai_api",
                "protocol": "openai_compatible",
                "endpoint": "https://api.openai.com/v1",
                "enabled": True,
                "api_key_env": "OPENAI_API_KEY",
            }
            profile.models.setdefault("models", {})["openai-main"] = {
                "provider": "openai",
                "model": "gpt-4.1",
                "roles": ["analysis"],
                "local": False,
                "enabled": True,
            }
            with self.assertRaises(PermissionError):
                Router(profile, AuditLogger(profile)).route("explain setup", model_name="openai-main", dry_run=True)

    def test_tool_read_and_write_with_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = load_profile("local-dev", workspace)
            executor = ToolExecutor(profile, AuditLogger(profile), ApprovalHandler(assume_yes=True))
            executor.run("write_file", ["note.txt", "hello"])
            self.assertEqual(executor.run("read_file", ["note.txt"]), "hello")

    def test_environment_system_plan(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.environment["active"] = "system"
        plan = EnvironmentManager(profile).plan(["python", "-m", "unittest"])
        self.assertEqual(plan.mode, "system")
        self.assertEqual(plan.command, ["python", "-m", "unittest"])

    def test_environment_lists_and_switches_active_mode(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "environment.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=json.loads(json.dumps(source.environment)),
                models=source.models,
                targets=source.targets,
            )
            manager = EnvironmentManager(profile)
            rows = manager.list_modes()
            self.assertIn("system", {row["name"] for row in rows})
            result = manager.use("venv")
            self.assertEqual(result["active"], "venv")
            self.assertIn("active: venv", (root / "environment.yaml").read_text(encoding="utf-8"))
            self.assertEqual(manager.active_mode(), "venv")

    def test_environment_use_rejects_unknown_mode(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with self.assertRaises(ValueError):
            EnvironmentManager(profile).use("missing")

    def test_environment_docker_resource_plan(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.environment["active"] = "docker"
        profile.environment["modes"]["docker"]["cpus"] = 4
        profile.environment["modes"]["docker"]["memory"] = "8g"
        profile.environment["modes"]["docker"]["gpus"] = "all"
        profile.environment["modes"]["docker"]["devices"] = ["/dev/dri"]
        plan = EnvironmentManager(profile).plan(["python", "-V"])
        self.assertIn("--cpus", plan.command)
        self.assertIn("--memory", plan.command)
        self.assertIn("--gpus", plan.command)
        self.assertIn("--device", plan.command)
        self.assertIn("/dev/dri", plan.command)

    def test_deploy_plan_uses_az_first_for_aks_target(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = DeployManager(profile).plan("aks_gpu_pool")
        self.assertEqual(plan["first_control_tool"], "az")
        self.assertIn("az", plan["required_tools"])
        self.assertEqual(plan["config"]["cluster"], "ai-coding-aks")
        first_command = plan["steps"][0]["command"]
        self.assertEqual(first_command[:2], ["az", "account"])

    def test_deploy_plan_supports_azure_vm_target(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = DeployManager(profile).plan("azure_gpu_vm")
        self.assertEqual(plan["type"], "azure_vm")
        self.assertEqual(plan["first_control_tool"], "az")
        self.assertIn("ssh", plan["required_tools"])
        self.assertIn("training_finetune", plan["resource_classes"])
        commands = [step["command"] for step in plan["steps"]]
        self.assertTrue(any(command[:3] == ["az", "vm", "create"] for command in commands))

    def test_deploy_apply_supports_guarded_azure_vm_steps(self) -> None:
        profile = load_profile("local-dev", Path.cwd())

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        with patch("aiplane.deploy.subprocess.run", return_value=Completed()) as run:
            result = DeployManager(profile).apply("azure_gpu_vm", yes=True)
        self.assertEqual(result["target"], "azure_gpu_vm")
        self.assertTrue(result["results"])
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any(command[:3] == ["az", "vm", "create"] for command in commands))

    def test_deploy_apply_requires_yes(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with self.assertRaises(PermissionError):
            DeployManager(profile).apply("aks_gpu_pool")

    def test_remote_tunnel_plan_uses_ssh_local_forwarding(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")
        self.assertEqual(plan["type"], "ssh_tunnel")
        self.assertIn("-L", plan["command"])
        self.assertEqual(plan["endpoint"], "http://localhost:11434/v1")
        self.assertEqual(plan["connection"]["ide_endpoint"], "http://localhost:11434/v1")
        self.assertIn("remote_service", plan["connection"])

    def test_remote_tunnel_lifecycle_is_guarded_and_status_uses_pid_file(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = Profile(
                name="tmp",
                root=source.root,
                workspace=workspace,
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = RemoteManager(profile)
            with self.assertRaises(PermissionError):
                manager.tunnel_start("gpu_workstation_ssh")

            class Process:
                pid = 12345

            with (
                patch("aiplane.remote.shutil.which", return_value="/usr/bin/ssh"),
                patch("aiplane.remote.subprocess.Popen", return_value=Process()),
            ):
                started = manager.tunnel_start("gpu_workstation_ssh", yes=True)
            self.assertEqual(started["status"], "started")
            self.assertTrue((workspace / ".aiplane" / "remote" / "gpu_workstation_ssh.pid").exists())
            with patch("aiplane.remote.os.kill") as kill:
                status = manager.tunnel_status("gpu_workstation_ssh")
            self.assertTrue(status["running"])
            kill.assert_called_with(12345, 0)
            with patch("aiplane.remote.os.kill") as kill:
                stopped = manager.tunnel_stop("gpu_workstation_ssh", yes=True)
            self.assertEqual(stopped["status"], "stopped")
            kill.assert_called_with(12345, 15)

    def test_mcp_manifest_exposes_guarded_write_tools(self) -> None:
        manifest = mcp_manifest()
        self.assertEqual(manifest["status"], "guarded_write_stdio_available")
        self.assertEqual(manifest["transport"], "stdio")
        self.assertTrue(manifest["tools"])
        names = {tool["name"] for tool in manifest["tools"]}
        self.assertIn("aiplane.models.defaults", names)
        self.assertIn("aiplane.models.list", names)
        self.assertIn("aiplane.models.refresh", names)
        self.assertIn("aiplane.models.use", names)
        self.assertIn("aiplane.runtimes.status", names)
        self.assertTrue(any(tool["mutates"] for tool in manifest["tools"]))
        self.assertTrue(
            all(tool["mutates"] for tool in manifest["write_tools"] if tool["name"] != "aiplane.remote.tunnel.status")
        )

    def test_mcp_server_lists_tools(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertIsNotNone(response)
        tools = response["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertIn("aiplane.models.list", names)
        self.assertIn("inputSchema", tools[0])

    def test_mcp_server_calls_read_only_tool(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "aiplane.profiles.list", "arguments": {}},
            }
        )
        self.assertIsNotNone(response)
        result = response["result"]
        self.assertIn("local-dev", result["structuredContent"]["profiles"])
        self.assertEqual(result["content"][0]["type"], "text")

    def test_mcp_provider_list_supports_status_and_ownership_grouping(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 25,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.providers.list",
                    "arguments": {"status": "all", "group_by": "ownership"},
                },
            }
        )
        self.assertIsNotNone(response)
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["group_by"], "ownership")
        self.assertEqual(list(payload["groups"])[:2], ["self_managed", "managed_service"])
        self.assertIn("self_managed", payload["groups"])
        self.assertIn("managed_service", payload["groups"])
        self.assertTrue(any(row["name"] == "nvidia" for row in payload["groups"]["self_managed"]))
        self.assertTrue(any(row["name"] == "openai" for row in payload["groups"]["managed_service"]))

    def test_mcp_server_can_list_ranked_models(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 24,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.models.list",
                    "arguments": {
                        "capabilities": {"code_generation": 3, "debugging_refactor": 2},
                        "ownership": "self_managed",
                        "vram_gb": 96,
                        "sort_by": "avg",
                        "limit": 3,
                    },
                },
            }
        )
        self.assertIsNotNone(response)
        result = response["result"]["structuredContent"]
        self.assertLessEqual(len(result["models"]), 3)
        self.assertTrue(all(row["ownership"] == "self_managed" for row in result["models"]))

    def test_mcp_server_can_show_model_and_provider_models(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        model_response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.models.show",
                    "arguments": {"model": "local-analysis-small"},
                },
            }
        )
        self.assertIsNotNone(model_response)
        self.assertEqual(
            model_response["result"]["structuredContent"]["model"],
            "provider-text-small:0.5b",
        )
        provider_response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 23,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.providers.models",
                    "arguments": {"provider": "huggingface"},
                },
            }
        )
        self.assertIsNotNone(provider_response)
        self.assertEqual(provider_response["result"]["structuredContent"]["provider"], "huggingface")

    def test_mcp_write_tools_can_update_model_default(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(
                agent_config.dump_yaml(json.loads(json.dumps(source.models))),
                encoding="utf-8",
            )
            profile = Profile(
                name="tmp",
                root=root,
                workspace=root,
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(source.models)),
                targets=source.targets,
            )
            with patch("aiplane.mcp.load_profile", return_value=profile):
                server = AiplaneMcpServer(Path.cwd())
                allowed = server.handle_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 31,
                        "method": "tools/call",
                        "params": {
                            "name": "aiplane.models.use",
                            "arguments": {
                                "role": "code_model",
                                "model": "local-code-small",
                            },
                        },
                    }
                )
            self.assertIsNotNone(allowed)
            self.assertEqual(allowed["result"]["structuredContent"]["name"], "local-code-small")
            self.assertIn(
                "code_model: local-code-small",
                (root / "models.yaml").read_text(encoding="utf-8"),
            )
            events = AuditLogger(profile).tail(1)
            self.assertEqual(events[0]["event_type"], "mcp")
            self.assertEqual(events[0]["action"], "aiplane.models.use")
            self.assertEqual(events[0]["decision"], "allowed")

    def test_mcp_mutating_failures_are_audited(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(
                agent_config.dump_yaml(json.loads(json.dumps(source.models))),
                encoding="utf-8",
            )
            profile = Profile(
                name="tmp",
                root=root,
                workspace=root,
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(source.models)),
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            with patch("aiplane.mcp.load_profile", return_value=profile):
                response = AiplaneMcpServer(root).handle_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 32,
                        "method": "tools/call",
                        "params": {
                            "name": "aiplane.models.use",
                            "arguments": {
                                "role": "code_model",
                                "model": "missing-model",
                            },
                        },
                    }
                )
            self.assertIsNotNone(response)
            self.assertIn("error", response)
            events = AuditLogger(profile).tail(1)
            self.assertEqual(events[0]["event_type"], "mcp")
            self.assertEqual(events[0]["action"], "aiplane.models.use")
            self.assertEqual(events[0]["decision"], "failed")

    def test_mcp_can_export_non_continue_integrations(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.integrations.export",
                    "arguments": {"tool": "cline", "model": "local-analysis-small"},
                },
            }
        )
        self.assertIsNotNone(response)
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["tool"], "cline")
        self.assertIn("openai-compatible", payload["content"])

    def test_mcp_can_preview_refresh_and_runtime_status(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config.setdefault("models", {})["local-chat-small"] = {
            "provider": "ollama",
            "model": "provider-chat-small:8b",
            "enabled": True,
        }
        discovered = ProviderModelsResult(
            "ollama",
            "provider_api",
            ["provider-chat-small:8b", "fresh-model:1b"],
            "test discovery",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
            )
            with (
                patch("aiplane.mcp.load_profile", return_value=profile),
                patch.object(ProviderRegistry, "models", return_value=discovered),
            ):
                server = AiplaneMcpServer(Path.cwd())
                response = server.handle_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 33,
                        "method": "tools/call",
                        "params": {
                            "name": "aiplane.models.refresh",
                            "arguments": {"provider": "ollama", "dry_run": True},
                        },
                    }
                )
        self.assertIsNotNone(response)
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["write"])
        self.assertEqual(payload["changes"]["would_import"], 1)
        self.assertEqual(payload["changes"]["would_remove"], 0)
        self.assertEqual(payload["results"]["ollama"]["source_models_returned"], 2)
        self.assertEqual(payload["results"]["ollama"]["source_models_already_profiled"], 1)
        self.assertTrue(payload["results"]["ollama"]["source_contacted"])
        self.assertTrue(payload["results"]["ollama"]["prune_enabled"])
        self.assertNotIn("catalog", payload)
        self.assertIn("ollama", payload["results"])

        response = AiplaneMcpServer(Path.cwd()).handle_message(
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.runtimes.status",
                    "arguments": {"runtime": "ollama"},
                },
            }
        )
        self.assertIsNotNone(response)
        self.assertEqual(response["result"]["structuredContent"][0]["name"], "ollama")

    def test_mcp_stdio_message_framing_round_trips(self) -> None:
        stream = BytesIO()
        message = {"jsonrpc": "2.0", "id": 3, "result": {"ok": True}}
        _write_message(stream, message)
        stream.seek(0)
        self.assertEqual(_read_message(stream), message)

    def test_hardware_show_includes_named_profiles(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        config = HardwareManager(profile).show()
        self.assertIn("hardware_profiles", config)
        self.assertIn("nvidia_dgx_spark_style", config["hardware_profiles"])
        self.assertIn("amd_ryzen_ai_max_halo_style", config["hardware_profiles"])

    def test_hardware_discover_has_cpu_memory_and_template_matches(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        discovered = HardwareManager(profile).discover()
        self.assertIn("cpu_count", discovered)
        self.assertIn("memory_gb", discovered)
        self.assertIn("gpus", discovered)
        self.assertIn("closest_profiles", discovered)
        self.assertLessEqual(len(discovered["closest_profiles"]), 3)
        self.assertTrue(all("name" in row for row in discovered["closest_profiles"]))

    def test_hardware_closest_profiles_excludes_zero_score_gpu_templates(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = HardwareManager(profile)
        discovered = {"gpus": [], "memory_gb": 64}
        closest = manager._closest_profiles(discovered)
        names = {row["name"] for row in closest}
        self.assertIn("cpu_laptop", names)
        self.assertNotIn("nvidia_consumer_gpu", names)
        self.assertNotIn("nvidia_workstation_gpu", names)
        self.assertTrue(all(row["score"] > 0 for row in closest))

    def test_hardware_doctor_checks_model_fit(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        fits = HardwareManager(profile).doctor("local-analysis-small")
        self.assertEqual(len(fits["needs_fit_check"]), 1)
        self.assertIn("provider-text-small:0.5b", fits["needs_fit_check"][0]["model"])

    def test_hardware_doctor_groups_remote_models_after_local_fit_checks(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"] = {
            "ownership": "managed_service",
            "runtime": "openai_api",
            "protocol": "openai_compatible",
            "endpoint": "https://api.openai.com/v1",
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
        }
        profile.models.setdefault("models", {})["openai-main"] = {
            "provider": "openai",
            "model": "gpt-4.1",
            "roles": ["analysis"],
            "local": False,
            "enabled": True,
        }
        grouped = HardwareManager(profile).doctor()
        self.assertIn("needs_fit_check", grouped)
        self.assertIn("no_local_fit_check_required", grouped)
        self.assertTrue(grouped["needs_fit_check"])
        remote_models = {row["model"] for row in grouped["no_local_fit_check_required"]}
        self.assertIn("gpt-4.1", remote_models)

    def test_hardware_recommend_hides_not_recommended_by_default(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = HardwareManager(profile).recommend()
        self.assertIn("criteria", result)
        self.assertEqual(list(result["models"].keys()), ["recommended", "usable", "remote_or_cloud"])
        self.assertNotIn("not_recommended", result["models"])
        self.assertGreaterEqual(result["hidden"]["not_recommended_count"], 1)
        first_group = result["models"]["recommended"] or result["models"]["usable"]
        self.assertIn("capabilities", first_group[0])
        self.assertIn("capability_avg_score", first_group[0])
        self.assertEqual(
            list(first_group[0].keys())[:10],
            [
                "name",
                "model",
                "provider",
                "capability_avg_score",
                "level",
                "enabled",
                "min_ram_gb",
                "recommended_ram_gb",
                "min_vram_gb",
                "recommended_vram_gb",
            ],
        )
        scores = [row["capability_avg_score"] for row in result["models"]["recommended"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_hardware_recommend_can_include_not_recommended(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = HardwareManager(profile).recommend(include_not_recommended=True)
        self.assertEqual(
            list(result["models"].keys()),
            ["recommended", "usable", "remote_or_cloud", "not_recommended"],
        )
        names = {row["name"] for rows in result["models"].values() for row in rows}
        self.assertIn("local-reasoning-large", names)
        self.assertIn("local-code-large", names)

    def test_hardware_recommend_includes_latest_benchmark_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / ".aiplane" / "benchmarks"
            root.mkdir(parents=True)
            benchmark = {
                "created_at": "2026-06-19T00:00:00+00:00",
                "model_name": "local-analysis-small",
                "summary": {"average_score": 88, "average_elapsed_ms": 1234},
            }
            (root / "20260619T000000Z-local-analysis-small.json").write_text(json.dumps(benchmark), encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = HardwareManager(profile).recommend()
            rows = [row for group in result["models"].values() for row in group]
            model_row = next(row for row in rows if row["name"] == "local-analysis-small")
            self.assertEqual(model_row["latest_benchmark"]["summary"]["average_score"], 88)

    def test_hardware_schema_and_active_machine_are_available(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = HardwareManager(profile)
        schema = manager.schema()
        self.assertEqual(schema["name"], "machine_schema")
        self.assertIn("memory_gb", schema["fields"])
        active = manager.active_config()
        self.assertIn("machine", active)
        self.assertIn("cpu", active["machine"])
        self.assertIn("memory", active["machine"])

    def test_hardware_recommend_uses_custom_active_machine(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = HardwareManager(profile)
            manager.use_template(
                "cloud_gpu_vm",
                {
                    "machine_tag": "azure_h100_test",
                    "provider": "azure",
                    "stock_sku": "Standard_NC40ads_H100_v5",
                    "memory_gb": 320,
                    "gpu_vendor": "nvidia",
                    "gpu_model": "H100 NVL",
                    "gpu_count": 1,
                    "vram_gb": 94,
                },
            )
            result = manager.recommend()
            self.assertEqual(result["machine"]["stock"]["machine_tag"], "azure_h100_test")
            self.assertEqual(result["machine"]["gpu"]["vram_gb"], 94)
            recommended_names = {row["name"] for row in result["models"]["recommended"]}
            self.assertIn("local-code-large", recommended_names)

    def test_machine_export_import_recommend_and_remote_plan(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = MachineManager(profile)
            exported = manager.export_machine("this_pc")
            export_path = root / "this_pc.machine.json"
            export_path.write_text(json.dumps(exported), encoding="utf-8")
            imported = manager.import_file(export_path, overrides={"memory_gb": 128, "vram_gb": 48})
            self.assertEqual(imported["name"], "this_pc")
            rows = manager.list()
            self.assertEqual(rows[0]["name"], "this_pc")
            recommendation = manager.recommend(model="local-code-large", runtime="vllm")
            self.assertEqual(recommendation["machines"][0]["level"], "recommended")
            remote = manager.profile_remote_plan("gpu_box_01", "gpu.example.com", user="dev")
            self.assertEqual(remote["mode"], "ssh_remote_profile")
            self.assertIn("ssh", remote["steps"][1]["command"][0])

    def test_machine_azure_discovery_includes_quota_and_restrictions(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            calls = []

            class Completed:
                def __init__(self, stdout, returncode=0):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = ""

            def fake_run(command, **kwargs):
                calls.append(command)
                if command[:3] == ["az", "account", "show"]:
                    return Completed(
                        json.dumps(
                            {
                                "environmentName": "AzureCloud",
                                "state": "Enabled",
                                "isDefault": True,
                                "name": "sub",
                                "id": "sub-id",
                                "tenantId": "tenant",
                                "user": {"name": "u", "type": "user"},
                            }
                        )
                    )
                if command[:3] == ["az", "vm", "list-skus"]:
                    return Completed(
                        json.dumps(
                            [
                                {
                                    "name": "Standard_NC40ads_H100_v5",
                                    "restrictions": [
                                        {
                                            "type": "Location",
                                            "reasonCode": "NotAvailableForSubscription",
                                            "values": ["uksouth"],
                                        }
                                    ],
                                }
                            ]
                        )
                    )
                if command[:3] == ["az", "vm", "list-usage"]:
                    return Completed(
                        json.dumps(
                            [
                                {
                                    "name": {
                                        "value": "cores",
                                        "localizedValue": "Total Regional vCPUs",
                                    },
                                    "currentValue": 4,
                                    "limit": 100,
                                    "unit": "Count",
                                }
                            ]
                        )
                    )
                return Completed("", returncode=1)

            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", side_effect=fake_run),
            ):
                result = MachineManager(profile).discover_azure("uksouth", workload="inference_large", limit=1)
            self.assertEqual(result["discovery"]["method"], "live")
            self.assertTrue(result["quota"]["ok"])
            self.assertEqual(result["quota"]["items"][0]["remaining"], 96)
            self.assertEqual(
                result["candidates"][0]["restrictions"][0]["reason_code"],
                "NotAvailableForSubscription",
            )

    def test_machine_azure_discovery_records_method_and_live_overrides_offline_cache(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = MachineManager(profile)
            with patch("aiplane.machines.shutil.which", return_value=None):
                offline = manager.discover_azure("uksouth", workload="inference_large", limit=2)
            self.assertEqual(offline["discovery"]["method"], "offline")
            self.assertTrue(offline["discovery"]["cache"]["written"])
            self.assertEqual(offline["discovery"]["cache"]["action"], "created")

            class Completed:
                returncode = 0
                stdout = json.dumps([{"name": "Standard_NC40ads_H100_v5"}])
                stderr = ""

            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", return_value=Completed()),
            ):
                live = manager.discover_azure("uksouth", workload="inference_large", limit=2)
            self.assertEqual(live["discovery"]["method"], "live")
            self.assertEqual(live["discovery"]["cache"]["previous_method"], "offline")
            self.assertEqual(live["discovery"]["cache"]["action"], "overrode_previous")
            cache = json.loads((root / "machine-discovery-cache.json").read_text(encoding="utf-8"))
            only_entry = next(iter(cache.values()))
            self.assertEqual(only_entry["discovery"]["method"], "live")
            self.assertEqual(
                only_entry["candidates"][0]["machine"]["stock"]["stock_sku"],
                "Standard_NC40ads_H100_v5",
            )

    def test_machine_cache_validate_and_azure_status_cli(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = MachineManager(profile)
            manager.import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            self.assertTrue(manager.validate("azure_h100_test")["ok"])
            with patch("aiplane.machines.shutil.which", return_value=None):
                status = manager.azure_status(region="uksouth", run_sku_probe=True)
            self.assertFalse(status["cli_available"])

            class AccountCompleted:
                returncode = 0
                stdout = json.dumps(
                    {
                        "environmentName": "AzureCloud",
                        "state": "Enabled",
                        "isDefault": True,
                        "name": "Test Subscription",
                        "id": "sub-123",
                        "tenantId": "tenant-456",
                        "user": {"name": "user@example.com", "type": "user"},
                    }
                )
                stderr = ""

            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", return_value=AccountCompleted()),
            ):
                logged_in = manager.azure_status()
            self.assertEqual(logged_in["account"]["user_name"], "[redacted]")
            self.assertEqual(logged_in["account"]["user_name_hint"], "[redacted]")
            self.assertEqual(logged_in["account"]["subscription_id"], "[redacted]")
            self.assertEqual(logged_in["account"]["subscription_id_hint"], "...-123")
            self.assertEqual(logged_in["account"]["tenant_id"], "[redacted]")
            self.assertEqual(logged_in["account"]["tenant_id_hint"], "...-456")
            self.assertTrue(logged_in["account"]["redacted"])
            with patch("aiplane.machines.shutil.which", return_value=None):
                manager.discover_azure("uksouth", workload="inference_large", limit=1)
            listed = manager.cache_list()
            self.assertEqual(len(listed["entries"]), 1)
            cleared = manager.cache_clear()
            self.assertEqual(cleared["remaining"], 0)

    def test_machine_azure_discovery_and_import_sku(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = MachineManager(profile)
            with patch("aiplane.machines.shutil.which", return_value=None):
                discovered = manager.discover_azure("uksouth", workload="inference_large", limit=2)
            self.assertEqual(discovered["provider"], "azure")
            self.assertEqual(discovered["discovery"]["method"], "offline")
            self.assertTrue(discovered["candidates"])
            imported = manager.import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            self.assertEqual(imported["machine"]["stock"]["stock_sku"], "Standard_NC40ads_H100_v5")
            self.assertIn("azure_h100_test", {row["name"] for row in manager.list()})

    def test_stack_deploy_same_host_executes_mutating_steps(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.create(
                "local_chat_stack",
                "local-analysis-small",
                "ollama",
                "local_box",
                access="same_host",
            )

            class Completed:
                returncode = 0
                stdout = "ok"
                stderr = ""

            with patch("aiplane.stacks.subprocess.run", return_value=Completed()) as run:
                result = stacks.deploy("local_chat_stack", yes=True)
            self.assertEqual(result["status"], "executed_same_host_steps")
            self.assertEqual(run.call_count, 3)

    def test_stack_create_plan_doctor_and_export(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            MachineManager(profile).import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            stacks = StackManager(profile)
            created = stacks.create(
                "code_on_gpu",
                "local-code-large",
                "vllm",
                "azure_h100_test",
                endpoint="http://localhost:8000/v1",
            )
            self.assertEqual(created["stack"]["runtime"], "vllm")
            plan = stacks.plan("code_on_gpu")
            self.assertEqual(plan["machine"], "azure_h100_test")
            self.assertEqual(plan["model"], "local-code-large")
            self.assertIn("preflight", plan)
            self.assertTrue(any(check["name"] == "runtime_prerequisites" for check in plan["preflight"]["checks"]))
            self.assertTrue(any(check["name"].startswith("port_available:") for check in plan["preflight"]["checks"]))
            doctor = stacks.doctor("code_on_gpu")
            self.assertTrue(any(check["name"] == "machine_fit" for check in doctor["checks"]))
            self.assertTrue(any(check["name"] == "runtime_prerequisites" for check in doctor["checks"]))
            exported = stacks.export("openai-compatible", "code_on_gpu")
            self.assertEqual(exported["endpoint"], "http://localhost:8000/v1")

    def test_hardware_use_template_copies_selected_values(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = HardwareManager(profile)
            active = manager.use_template("nvidia_consumer_gpu", {"vram_gb": 16})
            self.assertEqual(active["origin"], "nvidia_consumer_gpu")
            self.assertTrue(active["custom"])
            self.assertEqual(active["values"]["vram_gb"], 16)
            self.assertEqual(
                source.hardware["hardware_profiles"]["nvidia_consumer_gpu"]["vram_gb"],
                "8-24",
            )

    def test_model_catalog_lists_default_models(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        rows = ModelCatalog(profile).list()
        names = {row["name"] for row in rows}
        self.assertIn("local-analysis-small", names)
        self.assertNotIn("openai-main", names)
        self.assertIn("local-reasoning-xl", names)
        self.assertIn("codelocal-chat-large", names)
        analysis_model = next(row for row in rows if row["name"] == "local-analysis-small")
        self.assertIn("capabilities", analysis_model)
        self.assertEqual(analysis_model["capabilities"]["score_scale"], "0-5")
        self.assertIn("code_generation", analysis_model["capabilities"]["scores"])

    def test_continue_visible_ollama_models_have_catalog_roles(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        catalog = ModelCatalog(profile)

        llama = catalog.show("local-chat-small")
        self.assertEqual(llama["model"], "provider-chat-small:8b")
        self.assertIn("chat", llama["roles"])

        code_base = catalog.show("local-code-base")
        self.assertEqual(code_base["model"], "provider-code-base:1.5b")
        self.assertIn("autocomplete", code_base["roles"])
        self.assertGreaterEqual(code_base["capabilities"]["scores"]["code_completion"], 3)

        embedding_row = catalog.show("local-embedding-small")
        self.assertEqual(embedding_row["model"], "local-embedding-small:latest")
        self.assertIn("embedding", embedding_row["roles"])
        self.assertEqual(embedding_row["capabilities"]["scores"]["embedding"], 5)

        autocomplete_rows = catalog.filter({"role": "autocomplete"})
        self.assertIn("local-code-base", {row["name"] for row in autocomplete_rows})
        embedding_rows = catalog.filter({"role": "embedding"})
        self.assertIn("local-embedding-small", {row["name"] for row in embedding_rows})

    def test_model_catalog_refresh_imports_provider_discovered_models(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config.setdefault("models", {})["local-chat-small"] = {
            "provider": "ollama",
            "model": "provider-chat-small:8b",
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
            )
            discovered = ProviderModelsResult(
                provider="ollama",
                source="provider_api",
                models=[
                    "provider-chat-small:8b",
                    "new-embed-model:latest",
                    "new-coder:1b-base",
                ],
                reason="test discovery",
            )
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                preview = ModelCatalog(profile).refresh("ollama", write=False, verbose=True)
                self.assertEqual(preview["changes"]["would_import"], 2)
                self.assertEqual(preview["results"]["ollama"]["source_models_returned"], 3)
                self.assertEqual(preview["results"]["ollama"]["source_models_already_profiled"], 1)
                self.assertEqual(preview["results"]["ollama"]["source_models_to_import"], 2)
                self.assertEqual(preview["changes"]["would_remove"], 0)
                self.assertNotIn("catalog", preview)
                rows = preview["results"]["ollama"]["model_changes"]
                imported_preview = {row["name"]: row for row in rows if row["refresh_status"] == "would_import"}
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["suitable_runtimes"],
                    ["ollama"],
                )
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["preferred_runtime"],
                    "ollama",
                )
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["ownership"],
                    "self_managed",
                )
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["local_presence"],
                    "pulled",
                )
                self.assertFalse((root / "models.yaml").exists())

                written = ModelCatalog(profile).refresh("ollama", write=True, verbose=True)

            self.assertEqual(written["changes"]["imported"], 2)
            self.assertEqual(written["changes"]["removed"], 0)
            self.assertTrue((root / "models.discovered.yaml").exists())
            if (root / "models.yaml").exists():
                self.assertIn(
                    "local-chat-small:",
                    (root / "models.yaml").read_text(encoding="utf-8"),
                )
            rows = written["results"]["ollama"]["model_changes"]
            names = {row["name"] for row in rows}
            self.assertIn("ollama-new-embed-model-latest", names)
            self.assertIn("ollama-new-coder-1b-base", names)
            discovered_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
            self.assertIn("This file is generated by aiplane model discovery", discovered_text)
            self.assertIn("Do not edit it manually", discovered_text)
            self.assertIn("enabled: true", discovered_text)

    def test_models_refresh_default_omits_per_model_changes_until_verbose(self) -> None:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:1b"], "test discovery")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "ollama",
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["changes"]["would_import"], 1)
        self.assertNotIn("results", payload)
        self.assertEqual(payload["provider_summary"][0]["provider"], "ollama")
        self.assertGreaterEqual(payload["provider_summary"][0]["model_changes_count"], 1)
        self.assertEqual(payload["provider_summary"][0]["changes"]["would_import"], 1)

    def test_models_refresh_cli_previews_with_mocked_provider(self) -> None:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:1b"], "test discovery")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "ollama",
                        "--dry-run",
                        "--verbose",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["changes"]["would_import"], 1)
        self.assertNotIn("catalog", payload)
        rows = payload["results"]["ollama"]["model_changes"]
        imported = [row for row in rows if row["refresh_status"] == "would_import"]
        self.assertEqual(imported[0]["suitable_runtimes"], ["ollama"])
        self.assertEqual(imported[0]["ownership"], "self_managed")
        self.assertFalse(payload["write"])

    def test_models_refresh_cli_can_disable_new_imports_and_groups_provider_results(
        self,
    ) -> None:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:1b"], "test discovery")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "ollama",
                        "--disable-new",
                        "--dry-run",
                        "--verbose",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["write"])
        self.assertFalse(payload["new_entries_enabled"])
        imported = [
            row for row in payload["results"]["ollama"]["model_changes"] if row["refresh_status"] == "would_import"
        ]
        self.assertEqual(imported[0]["enabled"], False)

    def test_models_refresh_all_reports_mocked_provider_success_and_failure(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            name: model
            for name, model in models_config["models"].items()
            if name in {"local-analysis-small", "provider-code-large-vllm"}
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )

            def fake_models(provider: str, **kwargs) -> ProviderModelsResult:
                if provider == "ollama":
                    return ProviderModelsResult("ollama", "provider_api", ["fresh:1b"], "mock ok")
                if provider == "huggingface":
                    raise RuntimeError("mock failure")
                return ProviderModelsResult(provider, "profile_catalog", [], "empty")

            with patch.object(ProviderRegistry, "models", side_effect=fake_models):
                result = ModelCatalog(profile).refresh_all(write=False)
        self.assertGreaterEqual(result["providers_total"], 2)
        self.assertEqual(result["providers_failed"], 1)
        self.assertEqual(result["results"]["ollama"]["ownership"], "self_managed")
        self.assertEqual(result["results"]["ollama"]["status"], "would_update")
        self.assertEqual(result["results"]["huggingface"]["ownership"], "self_managed")
        self.assertEqual(result["results"]["huggingface"]["status"], "failed")
        self.assertNotIn("catalog", result)

    def test_models_refresh_all_still_uses_model_providers_after_catalog_clear(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {"curated": {"provider": "ollama", "model": "curated:1b", "enabled": True}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(source.root, root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            profile.models["models"] = models_config["models"]
            catalog = ModelCatalog(profile)
            catalog.clear_imported(write=False, include_curated=True)
            discovered = ProviderModelsResult("ollama", "source_api", ["fresh:1b"], "mock ok")

            def fake_models(provider: str, **kwargs) -> ProviderModelsResult:
                if provider == "ollama":
                    return discovered
                return ProviderModelsResult(provider, "profile_catalog", [], "empty")

            with patch.object(ProviderRegistry, "models", side_effect=fake_models):
                result = catalog.refresh_all(write=False)
        self.assertIn("ollama", result["results"])
        self.assertEqual(result["results"]["ollama"]["source_discovery_method"], "source_api")
        self.assertEqual(result["results"]["ollama"]["source_models_to_import"], 1)

    def test_models_enable_disable_rejects_discovered_cache_entry(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"models": {}}
            generated_config = {
                "models": {
                    "discovered_local": {
                        "provider": "ollama",
                        "source": "ollama",
                        "model": "llama3.2:3b",
                        "enabled": True,
                        "imported_by": "aiplane_refresh",
                    }
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            with self.assertRaisesRegex(ValueError, "discovered model entry is cache state"):
                ModelCatalog(profile).set_enabled("discovered_local", False)
            discovered_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
        self.assertIn("enabled: true", discovered_text)

    def test_models_refresh_reset_cache_previews_clear_before_refresh(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            shutil.copytree(source.root, profiles_dir / "local-dev")
            profile_root = profiles_dir / "local-dev"
            discovered_config = {
                "models": {
                    "ollama-old-model-latest": {
                        "provider": "ollama",
                        "source": "ollama",
                        "model": "old-model:latest",
                        "enabled": True,
                        "imported_by": "aiplane_refresh",
                    }
                }
            }
            (profile_root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(discovered_config),
                encoding="utf-8",
            )
            discovered = ProviderModelsResult("ollama", "provider_api", ["fresh:1b"], "mock ok")
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                stdout = StringIO()
                with redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "models",
                            "refresh",
                            "--profile",
                            "local-dev",
                            "--provider",
                            "ollama",
                            "--reset-cache",
                            "--dry-run",
                            "--verbose",
                        ]
                    )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["reset_cache"]["name"], "model_catalog_clear_cache")
        self.assertEqual(payload["reset_cache"]["provider"], "ollama")
        self.assertGreaterEqual(payload["reset_cache"]["would_remove"], 1)
        self.assertIn(
            {"name": "ollama", "count": payload["reset_cache"]["would_remove"]},
            payload["reset_cache"]["provider_counts"],
        )
        self.assertEqual(payload["changes"]["would_import"], 1)

    def test_model_catalog_clear_cache_removes_only_refresh_imports(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {"curated": {"provider": "ollama", "model": "curated:1b", "enabled": True}}
        for index in range(55):
            models_config["models"][f"imported-{index:02d}"] = {
                "provider": "vllm",
                "source": "huggingface",
                "model": f"org/model-{index:02d}",
                "enabled": True,
                "imported_by": "aiplane_refresh",
            }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            preview = ModelCatalog(profile).clear_imported(write=False)
            self.assertEqual(preview["would_remove"], 56)
            self.assertEqual(
                preview["provider_counts"],
                [{"name": "huggingface", "count": 55}, {"name": "ollama", "count": 1}],
            )
            self.assertEqual(preview["curated_provider_counts"], [{"name": "ollama", "count": 1}])
            self.assertTrue(preview["include_curated"])
            self.assertNotIn("model_changes", preview)

            keep_curated = ModelCatalog(profile).clear_imported(write=False, include_curated=False)
            self.assertEqual(keep_curated["would_remove"], 55)
            self.assertEqual(keep_curated["provider_counts"], [{"name": "huggingface", "count": 55}])
            self.assertEqual(keep_curated["curated_provider_counts"], [])
            self.assertFalse(keep_curated["include_curated"])

            written = ModelCatalog(profile).clear_imported(write=True, include_curated=False)
            self.assertEqual(written["removed"], 55)
            self.assertEqual(written["provider_counts"], [{"name": "huggingface", "count": 55}])
            self.assertEqual(written["curated_provider_counts"], [])
            written_text = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("curated:", written_text)
            self.assertNotIn("imported-00:", written_text)

    def test_discovered_huggingface_image_classifier_does_not_default_to_chat_roles(
        self,
    ) -> None:
        entry = _discovered_model_entry(
            "huggingface",
            "AdamCodd/vit-base-nsfw-detector",
            enable=True,
            source_metadata={"pipeline_tag": "image-classification"},
        )
        self.assertEqual(entry["roles"], ["image_classification"])
        self.assertNotIn("chat", entry["roles"])
        self.assertEqual(entry["preferred_runtime"], "vllm")

    def test_discovered_huggingface_media_pipeline_tags_map_to_media_roles(
        self,
    ) -> None:
        cases = [
            ({"pipeline_tag": "text-to-speech"}, "text_to_speech", "transformers", 0),
            ({"pipeline_tag": "text-to-image"}, "image_generation", "diffusers", 12),
            ({"pipeline_tag": "text-to-video"}, "video_generation", "diffusers", 8),
        ]
        for metadata, role, runtime, min_vram in cases:
            with self.subTest(role=role):
                entry = _discovered_model_entry("huggingface", f"org/{role}", enable=False, source_metadata=metadata)
                self.assertEqual(entry["roles"], [role])
                self.assertEqual(entry["source"], "huggingface")
                self.assertEqual(entry["provider"], runtime)
                self.assertEqual(entry["preferred_runtime"], runtime)
                if role == "image_generation" or role == "video_generation":
                    self.assertEqual(entry["supported_runtimes"], ["diffusers", "comfyui"])
                if role == "text_to_speech":
                    self.assertEqual(entry["supported_runtimes"], ["transformers"])
                self.assertEqual(entry["min_vram_gb"], min_vram)
                self.assertGreater(entry["capability_scores"][role], 0)
                self.assertFalse(entry["enabled"])

    def test_models_promote_generated_moves_alias_to_curated_catalog(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {},
            }
            generated_config = {
                "models": {
                    "generated-provider-chat": {
                        "provider": "ollama",
                        "model": "provider-text-small:0.5b",
                        "source": "ollama",
                        "roles": ["chat"],
                        "enabled": True,
                        "imported_by": "aiplane_refresh",
                    }
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )

            preview = ModelCatalog(profile).promote_generated(
                "generated-provider-chat",
                new_name="reviewed-provider-chat",
                write=False,
            )
            self.assertEqual(preview["would_promote"], 1)
            self.assertIn("next_steps", preview)
            self.assertIn("without --dry-run", preview["next_steps"][0])
            self.assertIn(
                "generated-provider-chat",
                (root / "models.discovered.yaml").read_text(encoding="utf-8"),
            )

            written = ModelCatalog(profile).promote_generated(
                "generated-provider-chat", new_name="reviewed-provider-chat", write=True
            )
            self.assertEqual(written["promoted"], 1)
            self.assertIn("next_steps", written)
            self.assertIn("models.yaml", written["next_steps"][0])
            curated_text = (root / "models.yaml").read_text(encoding="utf-8")
            generated_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
            self.assertIn("reviewed-provider-chat:", curated_text)
            self.assertIn("promoted_from: generated-provider-chat", curated_text)
            self.assertIn("discovered_entry: generated-provider-chat", curated_text)
            self.assertNotIn("imported_by", curated_text)
            self.assertIn("generated-provider-chat:", generated_text)

    def test_models_promote_refuses_curated_alias_collision_without_overwrite(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {
                    "generated-provider-chat": {
                        "provider": "ollama",
                        "model": "existing",
                        "source": "ollama",
                        "enabled": True,
                    }
                },
            }
            generated_config = {
                "models": {
                    "generated-provider-chat": {
                        "provider": "ollama",
                        "model": "provider-text-small:0.5b",
                        "source": "ollama",
                        "enabled": True,
                    }
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )

            with self.assertRaises(ValueError):
                ModelCatalog(profile).promote_generated("generated-provider-chat", write=False)

            preview = ModelCatalog(profile).promote_generated("generated-provider-chat", write=False, overwrite=True)
            self.assertTrue(preview["target_exists"])
            self.assertTrue(preview["overwrite"])

    def test_models_add_writes_curated_profile_entry(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"providers": {"ollama": {"runtime": "ollama"}}, "models": {}}
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "ollama-llama3-2-3b": {
                                "provider": "ollama",
                                "model": "llama3.2:3b",
                                "roles": ["chat", "analysis"],
                                "supported_runtimes": ["ollama"],
                                "capability_scores": {"general_chat": 4, "code_generation": 3},
                                "capability_score_source": "catalog_heuristic",
                                "imported_by": "aiplane_refresh",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )

            result = ModelCatalog(profile).add_model(
                "local_chat",
                provider="ollama",
                model_id="llama3.2:3b",
                roles=["chat"],
                supported_runtimes=["ollama"],
                preferred_runtime="ollama",
                notes="Local chat model",
                settings={"min_ram_gb": 8, "min_vram_gb": 0},
                write=True,
            )

            self.assertEqual(result["added"], 1)
            self.assertEqual(result["discovered_entry"], "ollama-llama3-2-3b")
            self.assertEqual(result["model"]["model"], "llama3.2:3b")
            self.assertEqual(result["model"]["discovered_entry"], "ollama-llama3-2-3b")
            self.assertEqual(result["model"]["capability_scores"]["general_chat"], 4)
            self.assertEqual(result["model"]["capability_score_source"], "catalog_heuristic")
            written = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("local_chat:", written)
            self.assertIn("discovered_entry: ollama-llama3-2-3b", written)
            self.assertIn("roles: [chat]", written)
            self.assertIn("min_ram_gb: 8", written)

    def test_models_add_can_create_direct_local_file_entry(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"providers": {}, "models": {}}
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )
            result = ModelCatalog(profile).add_model(
                "local_gguf",
                provider="local_file",
                model_id="/models/mistral.Q4_K_M.gguf",
                roles=["chat", "analysis"],
                supported_runtimes=["llamacpp"],
                notes="Local GGUF on this machine",
                write=True,
            )
            written = (root / "models.yaml").read_text(encoding="utf-8")
        self.assertEqual(result["added"], 1)
        self.assertIsNone(result["discovered_entry"])
        self.assertEqual(result["model"]["provider"], "local_file")
        self.assertEqual(result["model"]["source"], "local_file")
        self.assertEqual(result["model"]["model"], "/models/mistral.Q4_K_M.gguf")
        self.assertEqual(result["model"]["preferred_runtime"], "llamacpp")
        self.assertIn("local_gguf:", written)
        self.assertNotIn("discovered_entry", written)

    def test_models_add_can_use_discovered_entry_name_and_rejects_missing_discovery(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"providers": {"ollama": {"runtime": "ollama"}}, "models": {}}
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "ollama-llama3-2-3b": {
                                "provider": "ollama",
                                "model": "llama3.2:3b",
                                "roles": ["chat", "analysis"],
                                "supported_runtimes": ["ollama"],
                                "imported_by": "aiplane_refresh",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )

            result = ModelCatalog(profile).add_model(
                "local_chat",
                discovered_name="ollama-llama3-2-3b",
                roles=["chat"],
                write=False,
            )
            self.assertEqual(result["model"]["model"], "llama3.2:3b")
            self.assertEqual(result["model"]["discovered_entry"], "ollama-llama3-2-3b")

            with self.assertRaisesRegex(ValueError, "discovered model entry not found"):
                ModelCatalog(profile).add_model("missing", provider="ollama", model_id="missing:1b", write=False)
            with self.assertRaisesRegex(ValueError, "discovered model entry not found"):
                ModelCatalog(profile).add_model("missing", discovered_name="ollama-missing", write=False)

    def test_models_remove_deletes_profile_owned_alias_by_name(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "defaults": {"chat_model": "curated_local"},
                "models": {
                    "curated_local": {"provider": "local_file", "model": "/models/a.gguf", "enabled": True}
                },
            }
            generated_config = {
                "models": {
                    "discovered_local": {
                        "provider": "local_file",
                        "source": "local_file",
                        "model": "/models/b.gguf",
                        "imported_by": "aiplane_refresh",
                    }
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )
            preview = ModelCatalog(profile).remove_model("curated_local", write=False)
            self.assertTrue(preview["would_remove_curated"])
            self.assertEqual(preview["would_remove_defaults"], ["chat_model"])
            removed = ModelCatalog(profile).remove_model("curated_local", write=True)
            self.assertTrue(removed["removed_curated"])
            self.assertEqual(removed["removed_defaults"], ["chat_model"])
            curated_text = (root / "models.yaml").read_text(encoding="utf-8")
            discovered_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
        self.assertNotIn("curated_local:", curated_text)
        self.assertNotIn("chat_model:", curated_text)
        self.assertIn("discovered_local:", discovered_text)

    def test_models_remove_cli_dry_run_reports_profile_owned_alias(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "defaults": {"local_file_model": "local_gguf"},
                        "models": {
                            "local_gguf": {
                                "provider": "local_file",
                                "source": "local_file",
                                "model": "/models/mistral.Q4_K_M.gguf",
                                "enabled": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "remove",
                        "--profile",
                        "tmp",
                        "local_gguf",
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "model_catalog_remove")
        self.assertTrue(payload["would_remove_curated"])
        self.assertEqual(payload["would_remove_defaults"], ["local_file_model"])

    def test_models_add_cli_accepts_local_file_without_discovery(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(agent_config.dump_yaml({"defaults": {}, "models": {}}), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "add",
                        "--profile",
                        "tmp",
                        "local_gguf",
                        "--provider",
                        "local_file",
                        "--model",
                        "/models/mistral.Q4_K_M.gguf",
                        "--runtime",
                        "llamacpp",
                        "--role",
                        "chat",
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["would_add"], 1)
        self.assertIsNone(payload["discovered_entry"])
        self.assertEqual(payload["model"]["provider"], "local_file")
        self.assertEqual(payload["model"]["preferred_runtime"], "llamacpp")

    def test_models_clone_creates_second_entry_with_overrides(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {
                    "local_chat": {
                        "provider": "ollama",
                        "model": "llama3.2:3b",
                        "roles": ["chat"],
                        "enabled": True,
                    }
                },
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )

            result = ModelCatalog(profile).clone_model(
                "local_chat",
                "local_fast_draft",
                roles=["completion"],
                notes="Fast draft model for local coding tasks.",
                write=True,
            )

            self.assertEqual(result["cloned"], 1)
            self.assertEqual(result["model"]["model"], "llama3.2:3b")
            self.assertEqual(result["model"]["roles"], ["completion"])
            written = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("local_fast_draft:", written)
            self.assertIn("cloned_from: local_chat", written)
            self.assertIn("Fast draft model", written)

    def test_models_add_cli_dry_run_does_not_write(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(
                agent_config.dump_yaml({"providers": {"ollama": {"runtime": "ollama"}}, "models": {}}),
                encoding="utf-8",
            )
            (profile_root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "ollama-llama3-2-3b": {
                                "provider": "ollama",
                                "model": "llama3.2:3b",
                                "source": "ollama",
                                "roles": ["chat", "analysis"],
                                "supported_runtimes": ["ollama"],
                                "imported_by": "aiplane_refresh",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "add",
                        "--profile",
                        "tmp",
                        "local_chat",
                        "--provider",
                        "ollama",
                        "--model",
                        "llama3.2:3b",
                        "--role",
                        "chat",
                        "--runtime",
                        "ollama",
                        "--set",
                        "min_ram_gb=8",
                        "--dry-run",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["would_add"], 1)
            self.assertEqual(payload["discovered_entry"], "ollama-llama3-2-3b")
            self.assertEqual(payload["model"]["discovered_entry"], "ollama-llama3-2-3b")
            self.assertNotIn("capability_scores", payload["model"])
            self.assertIn("without --dry-run", payload["next_steps"][0])
            self.assertNotIn("local_chat:", (profile_root / "models.yaml").read_text(encoding="utf-8"))

    def test_models_promote_cli_dry_run(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(
                agent_config.dump_yaml({"providers": {"ollama": {"runtime": "ollama"}}, "models": {}}),
                encoding="utf-8",
            )
            (profile_root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "generated-provider-chat": {
                                "provider": "ollama",
                                "model": "provider-text-small:0.5b",
                                "source": "ollama",
                                "enabled": True,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "promote",
                        "--profile",
                        "tmp",
                        "generated-provider-chat",
                        "--as",
                        "reviewed-provider-chat",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["name"], "model_catalog_promote")
            self.assertEqual(payload["target"], "reviewed-provider-chat")
            self.assertEqual(payload["would_promote"], 1)
            self.assertIn("next_steps", payload)
            self.assertTrue(payload["keep_discovered"])
            self.assertIn("without --dry-run", payload["next_steps"][0])

    def test_refresh_verbose_rows_use_model_source_and_runtime_endpoint_names(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            "speech": {
                "provider": "transformers",
                "source": "huggingface",
                "model": "Provider/speech-to-text-large",
                "enabled": True,
                "preferred_runtime": "faster_whisper",
            }
        }
        profile = Profile(
            name="tmp",
            root=Path.cwd(),
            workspace=Path.cwd(),
            hardware=source.hardware,
            backends=source.backends,
            repository=source.repository,
            tools=source.tools,
            approvals=source.approvals,
            environment=source.environment,
            models=models_config,
            targets=source.targets,
            orchestrators=source.orchestrators,
        )
        discovered = ProviderModelsResult(
            "huggingface",
            "source_api",
            ["Provider/speech-to-text-large"],
            "live source",
            {"Provider/speech-to-text-large": {"downloads": 3}},
        )
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            result = ModelCatalog(profile).refresh("huggingface", write=False, verbose=True)
        row = result["results"]["huggingface"]["model_changes"][0]
        self.assertNotIn("provider", row)
        self.assertEqual(
            row["model"],
            {"id": "Provider/speech-to-text-large", "source": "huggingface"},
        )
        self.assertEqual(row["runtime_endpoint"], "transformers")
        self.assertEqual(row["preferred_runtime"], "faster_whisper")
        self.assertIn("faster_whisper", row["suitable_runtimes"])

    def test_model_catalog_refresh_updates_source_metadata_and_preserves_curated_fields(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            "curated-provider-chat": {
                "provider": "vllm",
                "source": "huggingface",
                "model": "Provider/Code-Large-Instruct",
                "enabled": True,
                "roles": ["manual_role"],
                "notes": "keep this note",
                "preferred_runtime": "transformers",
                "capability_scores": {"code_generation": 5, "debugging_refactor": 4},
                "capability_score_source": "manual",
                "source_metadata": {"downloads": 1},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            discovered = ProviderModelsResult(
                "huggingface",
                "source_api",
                ["Provider/Code-Large-Instruct"],
                "live source",
                {
                    "Provider/Code-Large-Instruct": {
                        "downloads": 99,
                        "pipeline_tag": "text-generation",
                    }
                },
            )
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                preview = ModelCatalog(profile).refresh("huggingface", write=False, verbose=True)
                self.assertEqual(preview["changes"]["would_update"], 1)
                self.assertIn("next_steps", preview)
                self.assertIn(
                    "aiplane models refresh --provider huggingface",
                    preview["next_steps"][0],
                )
                self.assertEqual(preview["results"]["huggingface"]["source_models_to_update"], 1)
                self.assertEqual(
                    preview["results"]["huggingface"]["profile_curated_models_before_refresh"],
                    1,
                )
                self.assertEqual(
                    preview["results"]["huggingface"]["profile_refresh_imported_models_before_refresh"],
                    0,
                )
                written = ModelCatalog(profile).refresh("huggingface", write=True, verbose=True)

            self.assertEqual(written["changes"]["updated"], 1)
            model = profile.models["models"]["curated-provider-chat"]
            self.assertEqual(
                model["source_metadata"],
                {"downloads": 99, "pipeline_tag": "text-generation"},
            )
            self.assertEqual(model["roles"], ["manual_role"])
            self.assertEqual(model["notes"], "keep this note")
            self.assertEqual(model["preferred_runtime"], "transformers")
            self.assertEqual(model["capability_score_source"], "manual")
            self.assertEqual(model["capability_scores"]["code_generation"], 5)

    def test_model_catalog_refresh_updates_refresh_imported_fields_from_source(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            "hf-old": {
                "provider": "vllm",
                "source": "huggingface",
                "model": "org/old-embed",
                "enabled": True,
                "roles": ["chat"],
                "imported_by": "aiplane_refresh",
                "source_metadata": {"downloads": 1},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            discovered = ProviderModelsResult(
                "huggingface",
                "source_api",
                ["org/old-embed"],
                "live source",
                {"org/old-embed": {"downloads": 2}},
            )
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                written = ModelCatalog(profile).refresh("huggingface", write=True, verbose=True)
            self.assertEqual(written["changes"]["updated"], 1)
            generated_models = ModelCatalog(profile).generated_config["models"]
            self.assertEqual(generated_models["hf-old"]["roles"], ["embedding"])
            self.assertEqual(generated_models["hf-old"]["source_metadata"], {"downloads": 2})

    def test_model_catalog_refresh_prunes_live_discovery_but_not_fallback(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config.setdefault("models", {})["local-chat-small"] = {
            "provider": "ollama",
            "model": "provider-chat-small:8b",
            "enabled": True,
        }
        models_config.setdefault("models", {})["local-analysis-small"] = {
            "provider": "ollama",
            "model": "provider-text-small:0.5b",
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            live = ProviderModelsResult(
                "ollama",
                "provider_api",
                ["provider-chat-small:8b"],
                "live runtime inventory",
            )
            with patch.object(ProviderRegistry, "models", return_value=live):
                preview = ModelCatalog(profile).refresh("ollama", write=False, verbose=True)
                self.assertEqual(preview["changes"]["would_remove"], 0)
                self.assertTrue(preview["results"]["ollama"]["prune_enabled"])
                self.assertIn(
                    "local-analysis-small:",
                    (root / "models.yaml").read_text(encoding="utf-8"),
                )

                written = ModelCatalog(profile).refresh("ollama", write=True, verbose=True)

            self.assertEqual(written["changes"]["removed"], 0)
            written_text = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("local-analysis-small:", written_text)
            self.assertIn("local-chat-small:", written_text)

            fallback_profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(models_config)),
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            fallback = ProviderModelsResult(
                "ollama",
                "profile_catalog",
                ["provider-chat-small:8b"],
                "offline fallback",
            )
            with patch.object(ProviderRegistry, "models", return_value=fallback):
                fallback_result = ModelCatalog(fallback_profile).refresh("ollama", write=True)
            self.assertFalse(fallback_result["results"]["ollama"]["prune_enabled"])
            self.assertEqual(fallback_result["changes"]["removed"], 0)

    def test_model_defaults_can_be_shown_and_changed(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(source.models)),
                targets=source.targets,
            )
            catalog = ModelCatalog(profile)
            self.assertEqual(
                catalog.default_model("self_managed_model")["name"],
                "local-analysis-small",
            )
            changed = catalog.set_default("self_managed_model", "local-code-small")
            self.assertEqual(changed["name"], "local-code-small")
            self.assertIn(
                "self_managed_model: local-code-small",
                (root / "models.yaml").read_text(encoding="utf-8"),
            )

    def test_models_list_and_defaults_support_grouping(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["models", "list", "--profile", "local-dev", "--group-by", "provider"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "provider")
        self.assertIn("ollama", payload["groups"])
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["models", "list", "--profile", "local-dev", "--group-by", "runtime"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("vllm", payload["groups"])
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["models", "list", "--profile", "local-dev", "--group-by", "ownership"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "ownership")
        self.assertIn("self_managed", payload["groups"])
        self.assertIn("managed_service", payload["groups"])
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--group-by",
                    "provider-kind",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "provider-kind")
        self.assertIn("self_managed", payload["groups"])
        self.assertIn("ollama", payload["groups"]["self_managed"])
        self.assertIn("managed_service", payload["groups"])
        self.assertIn("openai", payload["groups"]["managed_service"])
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "defaults",
                    "--profile",
                    "local-dev",
                    "--group-by",
                    "provider",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "provider")
        self.assertIn("ollama", payload["defaults"])

    def test_models_list_filters_sorts_and_limits_cli(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--capability",
                    "code_generation>=3",
                    "--capability",
                    "debugging>=2",
                    "--self-managed-only",
                ]
            )
        self.assertEqual(code, 0)
        rows = json.loads(stdout.getvalue())
        self.assertTrue(rows)
        self.assertTrue(all(row["ownership"] == "self_managed" for row in rows))
        self.assertIn("top_capabilities", rows[0])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--capability",
                    "coding>=3",
                    "--vram-gb",
                    "96",
                    "--self-managed-only",
                    "--sort-by",
                    "avg",
                    "--limit",
                    "3",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertLessEqual(len(payload), 3)

    def test_models_list_name_only_supports_cli_alias_selection(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--runtime",
                    "ollama",
                    "--role",
                    "chat",
                    "--name-only",
                    "--limit",
                    "2",
                ]
            )
        self.assertEqual(code, 0)
        names = [line.strip() for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertGreaterEqual(len(names), 1)
        self.assertTrue(all(line and "{" not in line and "}" not in line for line in names))

    def test_models_list_name_only_cannot_use_group_by(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--name-only",
                    "--group-by",
                    "runtime",
                    "--limit",
                    "2",
                ]
            )
        self.assertEqual(code, 1)

    def test_models_list_filters_and_sorts_by_provider_popularity(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"providers": {"huggingface": {"runtime": "vllm"}}, "models": {}}
            discovered_config = {
                "models": {
                    "hf-low": {
                        "provider": "vllm",
                        "model": "org/low",
                        "source": "huggingface",
                        "roles": ["chat"],
                        "enabled": True,
                        "source_metadata": {"likes": 5, "downloads": 1000},
                    },
                    "hf-high": {
                        "provider": "vllm",
                        "model": "org/high",
                        "source": "huggingface",
                        "roles": ["chat"],
                        "enabled": True,
                        "source_metadata": {"likes": 50, "downloads": 500},
                    },
                    "hf-downloads": {
                        "provider": "vllm",
                        "model": "org/downloads",
                        "source": "huggingface",
                        "roles": ["embedding"],
                        "enabled": True,
                        "source_metadata": {"likes": 10, "downloads": "2,500"},
                    },
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(discovered_config), encoding="utf-8")
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )

            catalog = ModelCatalog(profile)
            rows = catalog.sort_rows(catalog.filter({"roles": ["chat"], "min_likes": 10}), sort_by="likes")
            self.assertEqual([row["name"] for row in rows], ["hf-high"])
            self.assertEqual(rows[0]["likes"], 50)

            rows = catalog.sort_rows(catalog.filter({"source": "huggingface"}), sort_by="downloads")
            self.assertEqual(rows[0]["name"], "hf-downloads")
            self.assertEqual(rows[0]["downloads"], 2500)

    def test_models_pull_can_plan_huggingface_download(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "pull",
                    "--profile",
                    "local-dev",
                    "--source",
                    "huggingface",
                    "--model-id",
                    "Provider/Code-Large-Instruct",
                    "--for-runtime",
                    "vllm",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["source"], "huggingface")
        self.assertEqual(payload["runtime"], "vllm")
        self.assertIn("snapshot_download", " ".join(payload["command"]))

    def test_model_catalog_dry_run_analysis_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "sample.py"
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = ModelCatalog(profile).test_prompt("local-analysis-small", "analysis", target, dry_run=True)
            self.assertEqual(result.backend, "dry_run")
            self.assertIn("Explain what this code does", result.text)
            self.assertIn("def add", result.text)

    def test_model_benchmark_dry_run_reports_tasks_without_saving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            result = BenchmarkRunner(profile).run("local-analysis-small", task="all", dry_run=True, save=False)
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["summary"]["previewed"], 4)
            self.assertEqual(result["summary"]["average_score"], 0)
            self.assertTrue(all(row["passed"] is None for row in result["results"]))
            self.assertEqual(
                {row["task"] for row in result["results"]},
                {"analysis", "completion", "generation", "reasoning"},
            )
            self.assertNotIn("saved_to", result)

    def test_model_catalog_cloud_doctor_checks_env_var(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"] = {
            "ownership": "managed_service",
            "runtime": "openai_api",
            "protocol": "openai_compatible",
            "endpoint": "https://api.openai.com/v1",
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
        }
        profile.models.setdefault("models", {})["openai-main"] = {
            "provider": "openai",
            "model": "managed-chat-model",
            "roles": ["analysis"],
            "local": False,
            "enabled": True,
        }
        statuses = {status.name: status for status in ModelCatalog(profile).doctor()}
        self.assertIn("OPENAI_API_KEY", statuses["openai-main"].reason)

    def test_managed_service_models_do_not_mix_into_runtime_groups(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["models"]["managed-chat-small"]["preferred_runtime"] = "ollama"
        profile.models["models"]["managed-chat-small"]["supported_runtimes"] = ["ollama"]
        catalog = ModelCatalog(profile)
        managed = catalog.show("managed-chat-small")
        self.assertEqual(managed["provider"], "openai")
        self.assertEqual(managed["ownership"], "managed_service")
        self.assertIsNone(managed["runtime"])
        self.assertIsNone(managed["runtime_endpoint"])
        self.assertEqual(managed["supported_runtimes"], [])
        self.assertFalse(catalog.filter({"runtime": "openai"}))
        ollama_matches = {row["name"] for row in catalog.filter({"runtime": "ollama"})}
        self.assertNotIn("managed-chat-small", ollama_matches)

        stdout = StringIO()
        with (
            patch("aiplane.cli.load_profile", return_value=profile),
            redirect_stdout(stdout),
        ):
            code = cli_main(["models", "list", "--profile", "local-dev", "--group-by", "runtime"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("no_runtime", payload["groups"])
        self.assertTrue(any(row["name"] == "managed-chat-small" for row in payload["groups"]["no_runtime"]))
        self.assertFalse(any(row["name"] == "managed-chat-small" for row in payload["groups"].get("ollama", [])))

        with self.assertRaisesRegex(ValueError, "managed-service model"):
            RuntimeCatalog(profile).set_preferred_runtime("managed-chat-small", "ollama")
        with self.assertRaisesRegex(ValueError, "cannot be bundled"):
            RuntimeCatalog(profile).bundle_plan("ollama", "managed-chat-small")
        with self.assertRaisesRegex(ValueError, "cannot define local runtime fields"):
            catalog.complete("managed-chat-small", "hello")

    def test_model_show_includes_provider_config(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        model = ModelCatalog(profile).show("local-analysis-small")
        self.assertEqual(model["provider"], "ollama")
        self.assertIn("endpoint", model["provider_config"])
        self.assertIn("capabilities", model)
        self.assertIn("benchmark_refs", model["capabilities"])

    def test_code_analyze_dry_run_includes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "sample.py"
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = CodeTaskRunner(profile, AuditLogger(profile)).analyze("local-analysis-small", target, dry_run=True)
            self.assertTrue(result.dry_run)
            self.assertIn("Analyze this code file", result.output)
            self.assertIn("def add", result.output)

    def test_code_complete_dry_run_uses_line_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "sample.py"
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = CodeTaskRunner(profile, AuditLogger(profile)).complete(
                "local-analysis-small", target, 2, dry_run=True
            )
            self.assertIn("Before cursor", result.output)
            self.assertIn("After cursor", result.output)

    def test_code_write_dry_run_builds_prompt(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = CodeTaskRunner(profile, AuditLogger(profile)).write(
            "local-analysis-small", "add email validation", dry_run=True
        )
        self.assertIn("add email validation", result.output)

    def test_code_runner_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            outside = Path(tmp) / "outside.py"
            outside.write_text("print('x')", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            with self.assertRaises(PermissionError):
                CodeTaskRunner(profile, AuditLogger(profile)).analyze("local-analysis-small", outside, dry_run=True)

    def test_integrations_continue_export_uses_profile_defaults_bundle(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        exported = IntegrationManager(profile).export("continue")
        self.assertEqual(exported.tool, "continue")
        self.assertIn("apiBase: http://localhost:11434/v1", exported.content)
        self.assertIn("model: provider-chat-small:8b", exported.content)
        self.assertIn("tabAutocompleteModel:", exported.content)
        self.assertIn("model: provider-code-base:1.5b", exported.content)
        self.assertIn("embeddingsProvider:", exported.content)
        self.assertIn("model: local-embedding-small:latest", exported.content)

    def test_integrations_plan_selects_defaults_best_and_manual_overrides(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = IntegrationManager(profile)

        default_plan = manager.plan("continue")
        self.assertEqual(default_plan["selection"]["chat"]["name"], "local-chat-small")
        self.assertIn("tool_use", default_plan["selection"]["chat"]["role_capabilities"])
        self.assertEqual(default_plan["selection"]["autocomplete"]["name"], "local-code-base")
        self.assertEqual(default_plan["selection"]["embedding"]["name"], "local-embedding-small")

        best_plan = manager.plan("continue", runtime="ollama", select_best=True)
        self.assertEqual(best_plan["constraints"]["runtime"], "ollama")
        self.assertTrue(all(row["runtime"] == "ollama" for row in best_plan["selection"].values()))

        manual = manager.plan(
            "continue",
            chat="local-code-small",
            autocomplete="local-code-base",
            embedding="local-embedding-small",
        )
        self.assertEqual(manual["selection"]["chat"]["name"], "local-code-small")
        self.assertEqual(manual["overrides"]["chat"], "local-code-small")

    def test_integrations_setup_dry_run_plans_runtime_actions(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = IntegrationManager(profile).setup("continue", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["plan"]["tool"], "continue")
        self.assertTrue(result["actions"])
        self.assertTrue(all(action["status"] in {"planned", "ok"} for action in result["actions"]))

    def test_integrations_setup_dry_run_installs_missing_ollama_before_start_and_pull(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with (
            patch("aiplane.integrations.shutil.which", return_value=None),
            patch(
                "aiplane.integrations.RuntimeCatalog.runtime_available",
                return_value={"available": False, "reason": "endpoint down"},
            ),
            patch.object(
                IntegrationManager,
                "_model_presence",
                return_value={"available": False, "reason": "model is not pulled", "provider": "ollama"},
            ),
        ):
            result = IntegrationManager(profile).setup(
                "continue",
                chat="local-chat-small",
                autocomplete="local-chat-small",
                embedding="local-chat-small",
                dry_run=True,
            )
        actions = [action["action"] for action in result["actions"]]
        self.assertEqual(actions.count("install"), 1)
        self.assertEqual(actions.count("start"), 1)
        self.assertEqual(actions.count("pull"), 1)
        self.assertLess(actions.index("install"), actions.index("start"))
        self.assertLess(actions.index("start"), actions.index("pull"))

    def test_integrations_setup_requires_yes_when_not_dry_run(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with self.assertRaises(PermissionError):
            IntegrationManager(profile).setup("continue", dry_run=False, yes=False)

    def test_integrations_setup_success_omits_captured_output(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        completed = subprocess.CompletedProcess(
            ["scripts/provider_helper.sh"],
            0,
            "+ ollama pull command-r7b\n",
            "\x1b[?25lpulling manifest\rsuccess\n",
        )
        with patch.object(IntegrationManager, "_run_with_progress", return_value=completed):
            action = IntegrationManager(profile)._setup_action(
                "ollama",
                "pull",
                "local-chat-small",
                dry_run=False,
                execute=True,
                reason="test pull",
            )
        self.assertEqual(action["status"], "succeeded")
        self.assertEqual(action["returncode"], 0)
        self.assertNotIn("stdout", action)
        self.assertNotIn("stderr", action)
        self.assertNotIn("stdout_tail", action)
        self.assertNotIn("stderr_tail", action)

    def test_integrations_setup_failure_includes_sanitized_output_tail(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        completed = subprocess.CompletedProcess(
            ["scripts/provider_helper.sh"],
            1,
            "+ ollama pull missing-model\n",
            "\x1b[?25lpulling manifest\r\x1b[31merror: not found\x1b[0m\n",
        )
        with patch.object(IntegrationManager, "_run_with_progress", return_value=completed):
            action = IntegrationManager(profile)._setup_action(
                "ollama",
                "pull",
                "local-chat-small",
                dry_run=False,
                execute=True,
                reason="test pull",
            )
        self.assertEqual(action["status"], "failed")
        self.assertEqual(action["returncode"], 1)
        self.assertNotIn("stdout", action)
        self.assertNotIn("stderr", action)
        self.assertEqual(action["stdout_tail"], ["+ ollama pull missing-model"])
        self.assertEqual(action["stderr_tail"], ["pulling manifest", "error: not found"])

    def test_integrations_plan_and_setup_cli(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "integrations",
                    "plan",
                    "continue",
                    "--runtime",
                    "ollama",
                    "--select-best",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "continue")
        self.assertEqual(payload["constraints"]["runtime"], "ollama")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["integrations", "setup", "continue", "--dry-run"])
        self.assertEqual(code, 0)
        setup = json.loads(stdout.getvalue())
        self.assertTrue(setup["dry_run"])
        self.assertIn("actions", setup)

    def test_integrations_export_continue_uses_planner_constraints(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(profile.models))
        models_config["models"] = {
            name: model
            for name, model in models_config.get("models", {}).items()
            if model.get("imported_by") != "aiplane_refresh"
        }
        profile = Profile(
            name=profile.name,
            root=profile.root,
            workspace=profile.workspace,
            hardware=profile.hardware,
            backends=profile.backends,
            repository=profile.repository,
            tools=profile.tools,
            approvals=profile.approvals,
            environment=profile.environment,
            models=models_config,
            targets=profile.targets,
            orchestrators=profile.orchestrators,
        )
        manager = IntegrationManager(profile)
        exported = manager.export("continue", runtime="ollama", select_best=True)
        planned = manager.plan("continue", runtime="ollama", select_best=True)
        self.assertIn(f"model: {planned['selection']['chat']['model']}", exported.content)
        self.assertIn(f"model: {planned['selection']['autocomplete']['model']}", exported.content)
        self.assertIn(f"model: {planned['selection']['embedding']['model']}", exported.content)
        self.assertIn("apiBase: http://localhost:11434/v1", exported.content)

    def test_demo_flow_can_export_continue_from_generated_aliases(self) -> None:
        source = _REAL_LOAD_PROFILE("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": json.loads(json.dumps(source.models.get("providers", {}))),
                "models": {},
                "defaults": {},
            }
            generated_config = {
                "models": {
                    "generated-chat": {
                        "provider": "ollama",
                        "model": "provider-chat-demo",
                        "source": "ollama",
                        "roles": ["chat", "analysis", "generation"],
                        "enabled": True,
                    },
                    "generated-code": {
                        "provider": "ollama",
                        "model": "provider-code-demo",
                        "source": "ollama",
                        "roles": ["autocomplete", "completion"],
                        "enabled": True,
                    },
                    "generated-embed": {
                        "provider": "ollama",
                        "model": "provider-embed-demo",
                        "source": "ollama",
                        "roles": ["embedding"],
                        "enabled": True,
                    },
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                "demo",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )
            manager = IntegrationManager(profile)

            plan = manager.plan(
                "continue",
                chat="generated-chat",
                autocomplete="generated-code",
                embedding="generated-embed",
            )
            exported = manager.export(
                "continue",
                chat="generated-chat",
                autocomplete="generated-code",
                embedding="generated-embed",
            )

            self.assertEqual(plan["selection"]["chat"]["name"], "generated-chat")
            self.assertIn("model: provider-chat-demo", exported.content)
            self.assertIn("model: provider-code-demo", exported.content)
            self.assertIn("model: provider-embed-demo", exported.content)
            self.assertIn("apiBase: http://localhost:11434/v1", exported.content)

    def test_integrations_continue_single_model_export_still_works(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        exported = IntegrationManager(profile).export("continue", "local-analysis-small")
        self.assertEqual(exported.tool, "continue")
        self.assertIn("apiBase: http://localhost:11434/v1", exported.content)
        self.assertIn("model: provider-text-small:0.5b", exported.content)

    def test_integrations_export_continue_supports_role_flags_and_saved_plan(
        self,
    ) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "integrations",
                    "export",
                    "continue",
                    "--chat",
                    "managed-chat-small",
                    "--autocomplete",
                    "local-code-base",
                    "--embedding",
                    "local-embedding-small",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("model: managed-chat-model", output)
        self.assertIn("model: provider-code-base:1.5b", output)
        self.assertIn("model: local-embedding-small:latest", output)

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "integrations",
                        "plan",
                        "continue",
                        "--chat",
                        "managed-chat-small",
                        "--autocomplete",
                        "local-code-base",
                        "--embedding",
                        "local-embedding-small",
                    ]
                )
            self.assertEqual(code, 0)
            plan_path.write_text(stdout.getvalue(), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "integrations",
                        "export",
                        "continue",
                        "--from-plan",
                        str(plan_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertIn("model: managed-chat-model", stdout.getvalue())

    def test_agents_plan_and_export_cli_print_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "agents",
                        "plan",
                        "repo-helper",
                        "--framework",
                        "langgraph",
                        "--model",
                        "local-analysis-small",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["name"], "agent_plan")
            self.assertEqual(payload["selection"]["model_alias"], "local-analysis-small")
            self.assertIn("agent.py", payload["files"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "agents",
                        "export",
                        "repo-helper",
                        "--framework",
                        "simple-openai",
                        "--model",
                        "local-analysis-small",
                        "--file",
                        "agent.py",
                    ]
                )
            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertIn("from openai import OpenAI", output)
            self.assertIn("provider-text-small:0.5b", output)

    def test_agent_artifacts_root_uses_env_config_and_cli_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            config_path = Path(tmp) / "config.yaml"
            configured = Path(tmp) / "agents-config"
            config_path.write_text(f"agent_artifacts_dir: {configured}\n", encoding="utf-8")
            old_config = os.environ.get("AIPLANE_CONFIG")
            old_agents = os.environ.get("AIPLANE_AGENT_ARTIFACTS_DIR")
            os.environ["AIPLANE_CONFIG"] = str(config_path)
            try:
                stdout = StringIO()
                with redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "agents",
                            "plan",
                            "demo",
                            "--model",
                            "local-analysis-small",
                        ]
                    )
                self.assertEqual(code, 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["artifact_root"], str(configured.resolve()))

                env_root = Path(tmp) / "agents-env"
                os.environ["AIPLANE_AGENT_ARTIFACTS_DIR"] = str(env_root)
                stdout = StringIO()
                with redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "agents",
                            "plan",
                            "demo",
                            "--model",
                            "local-analysis-small",
                        ]
                    )
                self.assertEqual(code, 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["artifact_root"], str(env_root.resolve()))

                override = Path(tmp) / "agents-cli"
                stdout = StringIO()
                with redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "agents",
                            "plan",
                            "demo",
                            "--model",
                            "local-analysis-small",
                            "--output-dir",
                            str(override),
                        ]
                    )
                self.assertEqual(code, 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["artifact_root"], str(override.resolve()))
            finally:
                if old_config is None:
                    os.environ.pop("AIPLANE_CONFIG", None)
                else:
                    os.environ["AIPLANE_CONFIG"] = old_config
                if old_agents is None:
                    os.environ.pop("AIPLANE_AGENT_ARTIFACTS_DIR", None)
                else:
                    os.environ["AIPLANE_AGENT_ARTIFACTS_DIR"] = old_agents

    def test_integrations_export_uses_named_credential_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cred_path = Path(tmp) / "credentials.yaml"
            cred_path.write_text(
                "providers:\n"
                "  openai:\n"
                "    accounts:\n"
                "      personal:\n"
                "        api_key_env: OPENAI_PERSONAL_KEY\n"
                "        endpoint: https://api.openai.com/v1\n",
                encoding="utf-8",
            )
            old = os.environ.get("AIPLANE_CREDENTIALS")
            os.environ["AIPLANE_CREDENTIALS"] = str(cred_path)
            try:
                profile = load_profile("local-dev", Path.cwd())
                profile.models["providers"]["openai"]["credential_ref"] = "openai.personal"
                profile.models["models"]["managed-chat-small"]["enabled"] = True
                exported = IntegrationManager(profile).export("continue", "managed-chat-small")
                self.assertIn("apiKey: ${OPENAI_PERSONAL_KEY}", exported.content)
            finally:
                if old is None:
                    os.environ.pop("AIPLANE_CREDENTIALS", None)
                else:
                    os.environ["AIPLANE_CREDENTIALS"] = old

    def test_provider_models_can_query_azure_openai_with_named_credential(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cred_path = Path(tmp) / "credentials.yaml"
            cred_path.write_text(
                "providers:\n"
                "  azure_openai:\n"
                "    accounts:\n"
                "      business_a:\n"
                "        api_key: dummy-azure-key-value-123456\n",
                encoding="utf-8",
            )
            old = os.environ.get("AIPLANE_CREDENTIALS")
            os.environ["AIPLANE_CREDENTIALS"] = str(cred_path)
            profile = load_profile("local-dev", Path.cwd())
            profile.models["providers"]["azure_openai"]["endpoint"] = "https://example.openai.azure.com"
            profile.models["providers"]["azure_openai"]["credential_ref"] = "azure_openai.business_a"
            payload = {"data": [{"id": "news-deployment", "model": "managed-chat-model"}]}

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(payload).encode("utf-8")

            try:
                with patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened:
                    result = ProviderRegistry(profile).models("azure_openai", online=True, limit=5)
                self.assertEqual(result.models, ["news-deployment"])
                self.assertEqual(
                    opened.call_args.args[0].headers.get("Api-key"),
                    "dummy-azure-key-value-123456",
                )
            finally:
                if old is None:
                    os.environ.pop("AIPLANE_CREDENTIALS", None)
                else:
                    os.environ["AIPLANE_CREDENTIALS"] = old

    def test_integrations_export_allows_remote_endpoint_override(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        exported = IntegrationManager(profile).export(
            "openai-compatible",
            "local-analysis-small",
            endpoint="https://llm.example.com/v1",
        )
        self.assertIn("https://llm.example.com/v1", exported.content)

    def test_models_list_can_rank_and_limit_by_repeated_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "list",
                        "--runtime",
                        "ollama",
                        "--role",
                        "chat",
                        "--role",
                        "autocomplete",
                        "--enabled-only",
                        "--sort-by",
                        "role",
                        "--limit",
                        "2",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(len(payload), 2)
        self.assertIn("role_score", payload[0])
        self.assertGreaterEqual(payload[0]["role_score"], payload[1]["role_score"])

    def test_models_enable_disable_cli_updates_profile_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "disable",
                        "local-analysis-small",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["enabled"])
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=profiles_dir)
            self.assertFalse(ModelCatalog(profile).show("local-analysis-small")["enabled"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "enable",
                        "local-analysis-small",
                    ]
                )
            self.assertEqual(code, 0)
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=profiles_dir)
            self.assertTrue(ModelCatalog(profile).show("local-analysis-small")["enabled"])

    def test_integrations_roles_cli_shows_required_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "integrations",
                        "roles",
                        "continue",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "continue")
        self.assertEqual(
            [role["name"] for role in payload["roles"]],
            ["chat", "autocomplete", "embedding"],
        )

    def test_integrations_roles_cli_groups_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "integrations",
                        "roles",
                        "continue",
                        "--groups",
                    ]
                )
            self.assertEqual(code, 0)
            lines = [line.strip() for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0], 'required: ["chat"]')
            self.assertEqual(lines[1], 'optional: ["autocomplete", "embedding"]')

    def test_integrations_plan_supports_single_model_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "integrations",
                        "plan",
                        "cline",
                        "--model",
                        "local-analysis-small",
                        "--endpoint",
                        "http://localhost:11434/v1",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "cline")
        self.assertEqual(payload["selection"]["primary"]["name"], "local-analysis-small")
        self.assertEqual(payload["selection"]["primary"]["endpoint"], "http://localhost:11434/v1")

    def test_integrations_export_non_continue_can_select_best(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "integrations",
                        "export",
                        "aider",
                        "--select-best",
                        "--runtime",
                        "ollama",
                        "--capability",
                        "code_generation>=1",
                    ]
                )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("aider --model openai/", output)
        self.assertIn("OPENAI_API_BASE", output)

    def test_integrations_export_cline_zed_and_aider(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        cline = IntegrationManager(profile).export("cline", "local-analysis-small")
        zed = IntegrationManager(profile).export("zed", "local-analysis-small")
        aider = IntegrationManager(profile).export("aider", "local-analysis-small")
        self.assertEqual(cline.tool, "cline")
        self.assertIn("baseUrl", cline.content)
        self.assertEqual(zed.tool, "zed")
        self.assertIn("assistant", zed.content)
        self.assertEqual(aider.tool, "aider")
        self.assertIn("aider --model openai/provider-text-small:0.5b", aider.content)

    def test_integrations_export_mcp_client_configs(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        vscode = IntegrationManager(profile).export("vscode-mcp", "local-analysis-small")
        continue_mcp = IntegrationManager(profile).export("continue-mcp", "local-analysis-small")
        generic = IntegrationManager(profile).export("generic-mcp", "local-analysis-small")
        self.assertEqual(vscode.tool, "vscode-mcp")
        self.assertIn('"servers"', vscode.content)
        self.assertIn('"aiplane"', vscode.content)
        self.assertIn("mcpServers:", continue_mcp.content)
        self.assertNotIn("--profile", continue_mcp.content)
        self.assertIn('"mcpServers"', generic.content)

    def test_chat_wrapper_dry_run_resolves_ollama_model(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        command = IntegrationManager(profile).run_chat(None, dry_run=True)
        self.assertEqual(command, "ollama run provider-chat-small:8b")
        override = IntegrationManager(profile).run_chat("local-analysis-small", dry_run=True)
        self.assertEqual(override, "ollama run provider-text-small:0.5b")

    def test_disabled_general_candidate_is_configured(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        general_row = ModelCatalog(profile).show("local-general-small")
        self.assertEqual(general_row["model"], "provider-general-small:3b")
        self.assertFalse(general_row["enabled"])

    def test_provider_registry_lists_providers(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        rows = ProviderRegistry(profile).list()
        names = {row["name"] for row in rows}
        self.assertIn("ollama", names)
        for managed in ["openai", "anthropic", "azure_openai", "ollama_cloud"]:
            self.assertIn(managed, names)
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["azure_openai"]["catalog_adapter"], "azure_openai")
        self.assertEqual(by_name["azure_openai"]["ownership"], "managed_service")
        self.assertEqual(by_name["openai"]["catalog_adapter"], "profile_catalog")
        self.assertEqual(by_name["openai"]["endpoint_family"], "openai")
        self.assertEqual(by_name["openai"]["typical_runtimes"], [])
        self.assertEqual(by_name["openai"]["auth"], {"required": True, "method": "bearer"})
        self.assertEqual(by_name["nvidia"]["ownership"], "self_managed")
        ollama = by_name["ollama"]
        self.assertIn("ollama", ollama["typical_runtimes"])

        enabled_names = {row["name"] for row in ProviderRegistry(profile).list(status="enabled")}
        disabled_names = {row["name"] for row in ProviderRegistry(profile).list(status="disabled")}
        self.assertIn("ollama", enabled_names)
        self.assertNotIn("local_file", enabled_names)
        self.assertIn("local_file", disabled_names)
        self.assertIn("azure_speech", disabled_names)

    def test_provider_list_cli_groups_by_ownership(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "list", "--group-by", "ownership"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "ownership")
        self.assertEqual(list(payload["groups"])[:2], ["self_managed", "managed_service"])
        self.assertIn("self_managed", payload["groups"])
        self.assertIn("managed_service", payload["groups"])
        self.assertTrue(any(row["name"] == "nvidia" for row in payload["groups"]["self_managed"]))
        self.assertTrue(any(row["name"] == "openai" for row in payload["groups"]["managed_service"]))

    def test_provider_list_cli_filters_by_status(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "list", "--status", "disabled"])
        self.assertEqual(code, 0)
        rows = json.loads(stdout.getvalue())
        names = {row["name"] for row in rows}
        self.assertIn("local_file", names)
        self.assertTrue(all(not row["enabled"] for row in rows))
        self.assertTrue(all(row["ownership"] in {"self_managed", "managed_service"} for row in rows))

    def test_provider_endpoint_types_cli_lists_supported_api_shapes(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "endpoint-types"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "provider_types")
        families = {row["name"] for row in payload["endpoint_families"]}
        adapters = {row["name"] for row in payload["catalog_adapters"]}
        self.assertIn("custom_openai_compatible", families)
        self.assertIn("azure_openai", families)
        self.assertIn("profile_catalog", adapters)
        self.assertIn("huggingface", adapters)

    def test_provider_add_cli_rejects_unsupported_api_family(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            cli_main(["providers", "add", "bad_gateway", "--endpoint-family", "not_real_api"] )
        self.assertIn("invalid choice", stderr.getvalue())

    def test_provider_enable_disable_cli_updates_user_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profiles" / "local-dev", root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            disabled = ProviderRegistry(profile).set_enabled("ollama", False)
            self.assertFalse(disabled["enabled"])
            user_config = profile.root / "model-providers.user.yaml"
            self.assertTrue(user_config.exists())
            self.assertFalse(ProviderRegistry(profile).model_providers(include_removed=True)["ollama"]["enabled"])
            enabled = ProviderRegistry(profile).set_all_enabled(True)
            self.assertIn("ollama", enabled["providers"])
            self.assertTrue(ProviderRegistry(profile).model_providers()["ollama"]["enabled"])

    def test_provider_defaults_can_be_initialized_and_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_root = root / "local-dev"
            profile_root.mkdir()
            profile = Profile("local-dev", profile_root, root, {}, {}, {}, {}, {}, {}, {}, {}, {})
            registry = ProviderRegistry(profile)
            initialized = registry.init_defaults()
            self.assertIn("ollama", initialized["providers"])
            with self.assertRaises(ValueError):
                registry.init_defaults()
            cleared = registry.clear_config("all")
            self.assertTrue(cleared["suppresses_hardcoded_fallback"])
            self.assertEqual(ProviderRegistry(profile).list(status="all"), [])
            reinitialized = registry.init_defaults(overwrite=True)
            self.assertIn("huggingface", reinitialized["providers"])
            self.assertIn("nvidia", reinitialized["providers"])
            nvidia = registry.model_providers()["nvidia"]
            self.assertEqual(nvidia["catalog_adapter"], "huggingface")
            self.assertEqual(nvidia["huggingface_author"], "nvidia")
            self.assertEqual(nvidia["typical_runtimes"], ["vllm", "tgi", "transformers"])

    def test_provider_update_defaults_preserves_enabled_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_root = root / "local-dev"
            profile_root.mkdir()
            (profile_root / "model-providers.yaml").write_text(
                "ollama:\n"
                "  description: stale ollama description\n"
                "  typical_runtimes: [old_runtime]\n"
                "  catalog_adapter: profile_catalog\n"
                "  enabled: false\n"
                "huggingface:\n"
                "  description: stale huggingface description\n"
                "  typical_runtimes: [vllm]\n"
                "  catalog_adapter: huggingface\n"
                "  enabled: true\n",
                encoding="utf-8",
            )
            profile = Profile("local-dev", profile_root, root, {}, {}, {}, {}, {}, {}, {}, {}, {})
            result = ProviderRegistry(profile).update_defaults()
            providers = ProviderRegistry(profile).model_providers(include_removed=True)
        self.assertEqual(result["name"], "model_provider_defaults_update")
        self.assertIn("nvidia", result["added"])
        self.assertIn("ollama", result["preserved_enabled"])
        self.assertFalse(providers["ollama"]["enabled"])
        self.assertEqual(providers["ollama"]["typical_runtimes"], ["ollama"])
        self.assertEqual(providers["ollama"]["description"], "Ollama model library and local pull store")
        self.assertTrue(providers["huggingface"]["enabled"])
        self.assertIn("nvidia", providers)

    def test_provider_update_defaults_leaves_user_disabled_override_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profile-templates" / "local-dev", root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            registry = ProviderRegistry(profile)
            registry.set_enabled("nvidia", False)
            result = registry.update_defaults()
            providers = ProviderRegistry(profile).model_providers(include_removed=True)
            user_config = parse_yaml((profile.root / "model-providers.user.yaml").read_text(encoding="utf-8"))
        self.assertIn("nvidia", result["updated"])
        self.assertFalse(providers["nvidia"]["enabled"])
        self.assertFalse(user_config["nvidia"]["enabled"])

    def test_provider_update_defaults_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profile-templates" / "local-dev", root / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(root),
                        "providers",
                        "update-defaults",
                        "--profile",
                        "local-dev",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "model_provider_defaults_update")
        self.assertIn("nvidia", payload["providers"])
        self.assertIn("nvidia", payload["preserved_enabled"])

    def test_provider_registry_reads_legacy_source_provider_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_root = root / "local-dev"
            profile_root.mkdir()
            (profile_root / "source-providers.yaml").write_text(
                "legacyhub:\n"
                "  description: Legacy provider\n"
                "  typical_runtimes: [vllm]\n"
                "  catalog_adapter: profile_catalog\n"
                "  enabled: true\n",
                encoding="utf-8",
            )
            profile = Profile(
                "local-dev",
                profile_root,
                root,
                {},
                {},
                {},
                {},
                {},
                {},
                {"models": {}},
                {},
                {},
            )
            rows = ProviderRegistry(profile).list(status="all")
            self.assertEqual([row["name"] for row in rows], ["legacyhub"])

    def test_provider_doctor_filters_by_model_provider(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        statuses = ProviderRegistry(profile).doctor("ollama")
        names = {status.name for status in statuses}
        self.assertIn("local-analysis-small", names)
        self.assertNotIn("provider-code-large-vllm", names)

    def test_provider_doctor_cli_runs_without_provider_argument(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "doctor", "--profile", "local-dev"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload)
        self.assertEqual(next(iter(payload[0].keys())), "name")

    def test_provider_clear_cli_defaults_to_all_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profiles" / "local-dev", root / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(root),
                        "providers",
                        "clear",
                        "--profile",
                        "local-dev",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["scope"], "all")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            self.assertEqual(ProviderRegistry(profile).list(status="all"), [])

    def test_provider_add_and_remove_use_user_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profiles" / "local-dev", root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            registry = ProviderRegistry(profile)
            added = registry.add(
                "myhub",
                description="Private hub",
                typical_runtimes=["vllm"],
                catalog_adapter="huggingface",
            )
            self.assertEqual(added["catalog_adapter"], "huggingface")
            self.assertEqual(added["ownership"], "self_managed")
            managed = registry.add(
                "my_gateway",
                description="Managed gateway",
                ownership="managed_service",
                endpoint_family="custom_openai_compatible",
                catalog_adapter="profile_catalog",
                endpoint="https://gateway.example.com/v1",
                api_key_env="MY_GATEWAY_API_KEY",
                auth_method="bearer",
            )
            self.assertEqual(managed["endpoint_family"], "custom_openai_compatible")
            self.assertEqual(managed["auth"], {"required": True, "method": "bearer"})
            self.assertEqual(managed["typical_runtimes"], [])
            self.assertIn("myhub", registry.model_providers())
            removed = registry.remove("myhub")
            self.assertTrue(removed["removed"])
            self.assertNotIn("myhub", registry.model_providers())
            self.assertIn("myhub", registry.model_providers(include_removed=True))

    def test_provider_show_includes_configured_models(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        provider = ProviderRegistry(profile).show("ollama")
        model_names = {row["name"] for row in provider["profile_models"]}
        self.assertIn("local-analysis-small", model_names)

    def test_provider_models_lists_source_catalog_entries(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = ProviderRegistry(profile).models("huggingface")
        self.assertEqual(result.source, "profile_catalog")
        self.assertIn("Provider/Code-Large-Instruct", result.models)

    def test_provider_models_can_query_ollama_online_adapter_with_mocked_http(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        html = '<a href="/library/provider-chat">provider-chat</a><a href="/library/provider-code">provider-code</a>'

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return html.encode("utf-8")

        with patch("aiplane.providers.urlopen", return_value=FakeResponse()):
            result = ProviderRegistry(profile).models("ollama", online=True, query="code", limit=5)
        self.assertEqual(result.source, "source_api")
        self.assertEqual(result.models, ["provider-code"])

    def test_provider_models_can_query_online_adapter_with_mocked_http(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = [{"modelId": "Provider/Test-Coder"}]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch("aiplane.providers.urlopen", return_value=FakeResponse()):
            result = ProviderRegistry(profile).models("huggingface", online=True, query="code", limit=1)
        self.assertEqual(result.source, "source_api")
        self.assertEqual(result.models, ["Provider/Test-Coder"])

    def test_provider_models_can_query_nvidia_huggingface_scope_with_mocked_http(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = [{"modelId": "nvidia/Nemotron-Test", "author": "nvidia"}]
        requested_urls: list[str] = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        def fake_urlopen(request, timeout=20):
            requested_urls.append(str(request.full_url))
            return FakeResponse()

        with patch("aiplane.providers.urlopen", side_effect=fake_urlopen):
            result = ProviderRegistry(profile).models("nvidia", online=True, query="Nemotron", limit=1)
        self.assertEqual(result.provider, "nvidia")
        self.assertEqual(result.source, "source_api")
        self.assertEqual(result.models, ["nvidia/Nemotron-Test"])
        self.assertIn("author=nvidia", requested_urls[0])
        self.assertIn("search=Nemotron", requested_urls[0])

    def test_provider_models_can_query_azure_openai_deployments_with_mocked_http(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["azure_openai"]["endpoint"] = "https://example.openai.azure.com"
        payload = {"data": [{"id": "coding-chat", "model": "managed-chat-model"}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}),
            patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).models("azure_openai", online=True, query="coding", limit=5)
        self.assertEqual(result.source, "provider_api")
        self.assertEqual(result.models, ["coding-chat"])
        request = opened.call_args.args[0]
        self.assertIn("/openai/deployments", request.full_url)
        self.assertEqual(request.headers.get("Api-key"), "test-key")

    def test_provider_models_can_query_elevenlabs_voices_with_mocked_http(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["elevenlabs"]["enabled"] = True
        profile.models.setdefault("models", {})
        payload = {"voices": [{"voice_id": "voice-alpha", "name": "Demo Voice", "category": "premade"}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key"}),
            patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).models("elevenlabs", online=True, query="demo", limit=5)
        self.assertEqual(result.source, "provider_api")
        self.assertEqual(result.models, ["voice-alpha"])
        self.assertEqual(result.model_metadata["voice-alpha"]["pipeline_tag"], "text-to-speech")
        request = opened.call_args.args[0]
        self.assertIn("/voices", request.full_url)
        self.assertEqual(request.headers.get("Xi-api-key"), "test-key")

    def test_provider_test_command_checks_openai_compatible_credential(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"] = {
            "ownership": "managed_service",
            "runtime": "openai_api",
            "protocol": "openai_compatible",
            "endpoint": "https://api.example.test/v1",
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
        }
        payload = {"data": [{"id": "managed-chat"}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).test_connection("openai")
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "openai_compatible_models")
        self.assertEqual(result["items_seen"], 1)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/v1/models")
        self.assertEqual(request.headers.get("Authorization"), "Bearer test-key")
        self.assertNotIn("test-key", json.dumps(result))

    def test_provider_test_cli_uses_named_credential_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cred_path = Path(tmp) / "credentials.yaml"
            cred_path.write_text(
                "providers:\n"
                "  openai:\n"
                "    accounts:\n"
                "      personal:\n"
                "        api_key: dummy-api-key-value-123456\n"
                "        endpoint: https://api.example.test/v1\n",
                encoding="utf-8",
            )
            payload = {"data": [{"id": "managed-chat"}]}

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(payload).encode("utf-8")

            stdout = StringIO()
            with (
                patch.dict(os.environ, {"AIPLANE_CREDENTIALS": str(cred_path)}),
                patch("aiplane.providers.urlopen", return_value=FakeResponse()),
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "providers",
                        "test",
                        "--profile",
                        "local-dev",
                        "openai",
                        "--credential-ref",
                        "openai.personal",
                    ]
                )
            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["ok"])
            self.assertEqual(result["credential_ref"], "openai.personal")
            self.assertEqual(result["endpoint"], "https://api.example.test/v1")
            self.assertNotIn("dummy-api-key-value", stdout.getvalue())

    def test_elevenlabs_refresh_imports_managed_tts_voice(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["elevenlabs"]["enabled"] = True
        discovered = ProviderModelsResult(
            "elevenlabs",
            "provider_api",
            ["voice-alpha"],
            "mocked",
            {"voice-alpha": {"pipeline_tag": "text-to-speech", "name": "Demo Voice"}},
        )
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            result = ModelCatalog(profile).refresh("elevenlabs", write=False, enable=True, online=True, verbose=True)
        rows = result["results"]["elevenlabs"]["model_changes"]
        entry = next(row for row in rows if row["name"] == "elevenlabs-voice-alpha")
        self.assertEqual(entry["model"]["source"], "elevenlabs")
        self.assertEqual(entry["ownership"], "managed_service")
        self.assertEqual(entry["preferred_runtime"], "elevenlabs")
        self.assertEqual(entry["suitable_runtimes"], [])
        self.assertFalse(entry["local"])
        self.assertIn("text_to_speech", entry["roles"])
        direct_entry = {
            "provider": "elevenlabs",
            "model": "voice-alpha",
            "source": "elevenlabs",
            "roles": ["text_to_speech"],
            "local": False,
        }
        self.assertEqual(RuntimeCatalog(profile).compatible_runtimes_for_entry(direct_entry), [])

    def test_runtime_catalog_maps_sources_and_models(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        catalog = RuntimeCatalog(profile)
        mapped = catalog.map()
        self.assertIn("Hugging Face Hub", mapped["diagram"])
        runtimes = {row["name"] for row in catalog.list()}
        self.assertIn("vllm", runtimes)
        self.assertIn("llamacpp", runtimes)
        self.assertNotIn("lmstudio", runtimes)
        grouped = catalog.models_by_runtime("vllm")
        names = {row["name"] for row in grouped["models"]["vllm"]}
        self.assertIn("provider-code-large-vllm", names)
        nvidia_entry = {"provider": "nvidia", "model": "nvidia/Nemotron-Test", "source": "nvidia"}
        self.assertEqual(
            catalog.compatible_runtimes_for_entry(nvidia_entry),
            ["vllm", "tgi", "transformers"],
        )

    def test_runtime_catalog_shows_model_runtimes_and_preference(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        info = RuntimeCatalog(profile).runtimes_by_model("provider-code-large-vllm")
        runtime_names = {row["name"] for row in info["runtimes"]}
        self.assertIn("vllm", runtime_names)
        self.assertIn("tgi", runtime_names)
        self.assertEqual(info["preferred_runtime"], "vllm")

    def test_runtime_bundle_plan_renders_dockerfile_and_conda_yaml(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = RuntimeCatalog(profile).bundle_plan("vllm", model_name="provider-code-large-vllm", mode="docker")
        self.assertEqual(plan["name"], "vllm-provider-code-large-vllm-docker")
        self.assertEqual(plan["selected_file"], "Dockerfile")
        self.assertIn("FROM python:3.13-slim", plan["files"]["Dockerfile"])
        self.assertIn("Provider/Code-Large-Instruct", plan["files"]["Dockerfile"])
        self.assertIn("name: aiplane-vllm", plan["files"]["environment.yaml"])

    def test_runtime_preference_can_be_changed(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(source.models)),
                targets=source.targets,
            )
            changed = RuntimeCatalog(profile).set_preferred_runtime("provider-code-large-vllm", "tgi")
            self.assertEqual(changed["preferred_runtime"], "tgi")
            self.assertIn(
                "preferred_runtime: tgi",
                (root / "models.yaml").read_text(encoding="utf-8"),
            )

    def test_ollama_helper_status_is_human_readable(self) -> None:
        root = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            (bindir / "ollama").write_text(
                '#!/usr/bin/env bash\nif [[ "$1" == "--version" ]]; then echo \'ollama version is 1.2.3\'; elif [[ "$1" == "list" ]]; then echo \'NAME ID SIZE MODIFIED\'; fi\n',
                encoding="utf-8",
            )
            (bindir / "curl").write_text(
                '#!/usr/bin/env bash\nprintf \'%s\' \'{"models":[{"name":"provider-text-small:0.5b","model":"provider-text-small:0.5b","size":397821516,"details":{"parameter_size":"494.03M","quantization_level":"Q4_K_M"},"capabilities":["completion","tools"]}]}\'\n',
                encoding="utf-8",
            )
            for path in bindir.iterdir():
                path.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
            completed = subprocess.run(
                [
                    "scripts/provider_helper.sh",
                    "--provider",
                    "ollama",
                    "--action",
                    "status",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Ollama status", completed.stdout)
        self.assertIn("api_running: yes", completed.stdout)
        self.assertIn("models: 1", completed.stdout)
        self.assertIn("provider-text-small:0.5b", completed.stdout)
        self.assertNotIn("+ curl", completed.stdout)
        self.assertNotIn('"models"', completed.stdout)

    def test_setup_env_can_be_sourced_without_ending_shell(self) -> None:
        root = Path.cwd()
        completed = subprocess.run(
            [
                "bash",
                "-lc",
                (
                    "set +e +u +o pipefail; "
                    "source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable --dry-run; "
                    "status=$?; "
                    "case $- in *e*) errexit=on ;; *) errexit=off ;; esac; "
                    "case $- in *u*) nounset=on ;; *) nounset=off ;; esac; "
                    "if set -o | grep -q '^pipefail[[:space:]]*on'; then pipefail=on; else pipefail=off; fi; "
                    "printf 'after-source status=%s errexit=%s nounset=%s pipefail=%s\\n' "
                    "\"$status\" \"$errexit\" \"$nounset\" \"$pipefail\"; "
                    "exit $status"
                ),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("after-source status=0", completed.stdout)
        self.assertIn("errexit=off", completed.stdout)
        self.assertIn("nounset=off", completed.stdout)
        self.assertIn("pipefail=off", completed.stdout)

    def test_setup_env_install_bootstraps_profile_before_doctor(self) -> None:
        root = Path.cwd()
        syntax = subprocess.run(
            ["bash", "-n", "scripts/setup_env.sh"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        completed = subprocess.run(
            [
                "scripts/setup_env.sh",
                "--mode",
                "local",
                "--action",
                "install",
                "--editable",
                "--python",
                "python",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        bootstrap = 'python -m aiplane profiles bootstrap-local --no-discovery'
        doctor = 'python -m aiplane profiles list'
        self.assertIn(bootstrap, completed.stdout)
        self.assertIn(doctor, completed.stdout)
        self.assertLess(completed.stdout.index(bootstrap), completed.stdout.index(doctor))

    def test_setup_env_conda_install_repairs_existing_env_without_python(self) -> None:
        root = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            fakebin = Path(tmp) / "bin"
            fakebin.mkdir()
            log_path = Path(tmp) / "conda.log"
            state_path = Path(tmp) / "python-installed"
            conda = fakebin / "conda"
            conda.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$CONDALOG"
if [[ "$1 $2" == "env list" ]]; then
  printf 'aiplane /tmp/aiplane\n'
  exit 0
fi
if [[ "$1" == "run" ]]; then
  if [[ "${4:-}" == "python" && "${5:-}" == "--version" && ! -f "$CONDA_PYTHON_INSTALLED" ]]; then
    printf 'python: command not found\n' >&2
    exit 127
  fi
  if [[ "${4:-}" == "python" && ! -f "$CONDA_PYTHON_INSTALLED" ]]; then
    exit 127
  fi
  exit 0
fi
if [[ "$1" == "install" ]]; then
  touch "$CONDA_PYTHON_INSTALLED"
  exit 0
fi
exit 0
""",
                encoding="utf-8",
            )
            conda.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH', '')}"
            env["CONDALOG"] = str(log_path)
            env["CONDA_PYTHON_INSTALLED"] = str(state_path)
            completed = subprocess.run(
                [
                    "scripts/setup_env.sh",
                    "--mode",
                    "conda",
                    "--conda-env",
                    "aiplane",
                    "--action",
                    "install",
                    "--editable",
                    "--activate",
                    "0",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            conda_log = log_path.read_text(encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Conda environment exists but does not contain Python: aiplane", completed.stderr)
        self.assertIn("+ conda install -n aiplane python=3.13 -y", completed.stdout)
        self.assertIn("install -n aiplane python=3.13 -y", conda_log)

    def test_provider_helper_runtime_dry_runs(self) -> None:
        root = Path.cwd()
        syntax = subprocess.run(
            ["bash", "-n", "scripts/provider_helper.sh"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        install = subprocess.run(
            [
                "scripts/provider_helper.sh",
                "--provider",
                "vllm",
                "--action",
                "install",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertIn("pip install vllm", install.stdout)
        start = subprocess.run(
            [
                "scripts/provider_helper.sh",
                "--provider",
                "tgi",
                "--action",
                "start",
                "--model",
                "Provider/Code-Large-Instruct",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(start.returncode, 0, start.stderr)
        self.assertIn("text-generation-inference", start.stdout)
        ollama_docker = subprocess.run(
            [
                "scripts/provider_helper.sh",
                "--provider",
                "ollama",
                "--action",
                "start",
                "--substrate",
                "docker",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ollama_docker.returncode, 0, ollama_docker.stderr)
        self.assertIn("docker run", ollama_docker.stdout)
        self.assertIn("ollama/ollama:latest", ollama_docker.stdout)

    def test_runtime_lifecycle_reports_unavailable_helper_for_planned_runtime(
        self,
    ) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["runtimes", "install", "diffusers", "--dry-run"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "runtime_helper_unavailable")
        self.assertFalse(payload["supported_by_aiplane_helper"])
        self.assertIn("install_hint", payload)

    def test_runtime_prerequisites_reports_missing_ubuntu_tools(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with patch("aiplane.runtime_catalog.shutil.which", return_value=None):
            payload = RuntimeCatalog(profile).prerequisites("vllm")
        self.assertEqual(payload["name"], "runtime_prerequisites")
        self.assertEqual(payload["runtime"], "vllm")
        self.assertFalse(payload["ok"])
        missing = {row["name"] for row in payload["missing_required"]}
        self.assertIn("python", missing)
        self.assertIn("pip", missing)
        self.assertIn("apt-get install", payload["ubuntu_install_hint"])

    def test_runtime_install_preflight_blocks_when_required_tools_missing(self) -> None:
        stdout = StringIO()
        with (
            patch("aiplane.runtime_catalog.shutil.which", return_value=None),
            redirect_stdout(stdout),
        ):
            code = cli_main(["runtimes", "install", "--profile", "local-dev", "vllm"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["runtime"], "vllm")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["missing_required"])

    def test_aiplane_runtime_lifecycle_delegates_to_provider_helper(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "start",
                    "--profile",
                    "local-dev",
                    "vllm",
                    "--model",
                    "Provider/Code-Large-Instruct",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("vllm.entrypoints.openai.api_server", output)
        self.assertIn("Provider/Code-Large-Instruct", output)

    def test_aiplane_runtime_update_installed_and_repull_dry_runs(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "update-installed",
                    "--profile",
                    "local-dev",
                    "all",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Updating helper-managed runtimes", output)
        self.assertIn("pip install --upgrade vllm", output)
        self.assertIn("docker pull ghcr.io/huggingface/text-generation-inference", output)

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "repull",
                    "--profile",
                    "local-dev",
                    "ollama",
                    "--model",
                    "all",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("ollama list", stdout.getvalue())

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "start",
                    "--profile",
                    "local-dev",
                    "ollama",
                    "--substrate",
                    "docker",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("docker run", stdout.getvalue())
        self.assertIn("ollama/ollama:latest", stdout.getvalue())

        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["ollama"]["substrate"] = "docker"
        stdout = StringIO()
        with (
            patch("aiplane.cli.load_profile", return_value=profile),
            redirect_stdout(stdout),
        ):
            code = cli_main(["runtimes", "start", "--profile", "local-dev", "ollama", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("docker run", stdout.getvalue())

    def test_aiplane_runtime_bundle_cli_prints_selected_file(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "bundle",
                    "--profile",
                    "local-dev",
                    "vllm",
                    "--model",
                    "provider-code-large-vllm",
                    "--format",
                    "dockerfile",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("FROM python:3.13-slim", output)
        self.assertIn("Provider/Code-Large-Instruct", output)

    def test_model_catalog_executes_openai_compatible_runtime(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with TestHttpServer() as endpoint:
            profile.models["providers"]["vllm"]["enabled"] = True
            profile.models["providers"]["vllm"]["endpoint"] = endpoint
            profile.models["models"]["provider-code-large-vllm"]["enabled"] = True
            profile.models["models"]["provider-code-large-vllm"]["model"] = "test-model"
            result = ModelCatalog(profile).complete("provider-code-large-vllm", "hello")
        self.assertEqual(result.backend, "openai_compatible")
        self.assertEqual(result.text, "handled test-model")

    def test_audit_log_is_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            audit = AuditLogger(profile)
            ToolExecutor(profile, audit, ApprovalHandler(assume_yes=True)).run("write_file", ["audit.txt", "ok"])
            events = audit.tail(1)
            self.assertEqual(events[0]["event_type"], "tool")
            json.dumps(events[0])

    def test_tools_doctor_and_install_dry_run_cli(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "doctor", "openssh-client"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "tools_doctor")
        self.assertEqual(payload["tools"][0]["name"], "openssh-client")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "install", "openssh-client", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "openssh-client")
        self.assertTrue(payload["dry_run"])
        self.assertIn("commands", payload)

    def test_tools_doctor_includes_vm_and_provider_agnostic_iac_tools(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "doctor"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        tools = {row["name"]: row for row in payload["tools"]}
        for name in [
            "opentofu",
            "terraform",
            "pulumi",
            "vagrant",
            "packer",
            "devcontainer-cli",
            "ruff",
            "black",
        ]:
            self.assertIn(name, tools)
            self.assertEqual(tools[name]["requirement"], "optional")
        self.assertEqual(tools["opentofu"]["category"], "iac")
        self.assertEqual(tools["pulumi"]["category"], "iac")
        self.assertEqual(tools["vagrant"]["category"], "vm")
        self.assertEqual(tools["packer"]["category"], "image-build")
        self.assertEqual(tools["devcontainer-cli"]["category"], "container")
        self.assertEqual(tools["ruff"]["category"], "quality")
        self.assertEqual(tools["black"]["category"], "quality")

    def test_tools_matrix_cli_groups_tasks_and_capabilities(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "matrix"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "tools_matrix")
        self.assertIn("summary", payload)
        self.assertGreaterEqual(payload["summary"]["mandatory"], 2)
        self.assertIn("workflows", payload)
        self.assertIn("workflows", payload["summary"])
        self.assertIn("workflows_complete", payload["summary"])
        self.assertIn("workflows_partial", payload["summary"])
        self.assertIn("workflows_needing_setup", payload["summary"])
        categories = {category["name"]: category for category in payload["categories"]}
        workflows = {workflow["name"]: workflow for workflow in payload["workflows"]}
        self.assertIn("iac", categories)
        self.assertIn("quality", categories)
        self.assertIn("iac", workflows)
        self.assertIn("quality", workflows)
        self.assertEqual(workflows["iac"]["tools"], len(categories["iac"]["tools"]))
        quality_tools = {tool["name"]: tool for tool in categories["quality"]["tools"]}
        self.assertIn("ruff", quality_tools)
        self.assertIn("black", quality_tools)
        self.assertIn(workflows["iac"]["readiness"], {"complete", "partial", "needs_setup"})
        self.assertIn(
            "provider-agnostic infrastructure provisioning",
            workflows["iac"]["primary_tasks"],
        )
        self.assertIn("missing_tools", workflows["iac"])
        iac_tools = {tool["name"]: tool for tool in categories["iac"]["tools"]}
        self.assertTrue(iac_tools["opentofu"]["plan_available"])
        self.assertTrue(iac_tools["opentofu"]["export_available"])
        self.assertEqual(iac_tools["opentofu"]["requirement"], "optional")
        remote_tools = {tool["name"]: tool for tool in categories["remote"]["tools"]}
        self.assertEqual(remote_tools["openssh-client"]["requirement"], "mandatory")
        self.assertIn("SSH tunnels", remote_tools["openssh-client"]["needed_for"])
        self.assertEqual(workflows["remote"]["mandatory"], 1)

    def test_tools_plan_and_export_cli_are_non_mutating_starters(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "plan", "vagrant"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "tools_plan")
        self.assertEqual(payload["tool"], "vagrant")
        self.assertIn("Vagrantfile", payload["artifacts"])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "export", "opentofu"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("terraform {", output)
        self.assertIn("tofu plan", output)

    def test_managed_provider_alias_exports_continue_config(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["integrations", "export", "continue", "--model", "managed-chat-small"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("provider: openai", output)
        self.assertIn("model: managed-chat-model", output)
        self.assertIn("apiKey: ${OPENAI_API_KEY}", output)

    def test_environment_doctor_cli_groups_installable_tools(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["environment", "doctor", "--required-only", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("checking tool", stderr.getvalue())
        self.assertIn("\r", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "environment_doctor")
        self.assertIn("summary", payload)
        self.assertIn("active_environment", payload)
        self.assertIn("missing_installable_by_aiplane", payload)
        self.assertIn("runtime_prerequisites", payload)
        self.assertIn("runtime_prerequisites_checked", payload["summary"])
        runtimes = {row["runtime"]: row for row in payload["runtime_prerequisites"]}
        self.assertIn("ollama", runtimes)
        self.assertIn("vllm", runtimes)
        self.assertIn("purpose", runtimes["ollama"])
        self.assertIn(
            "aiplane runtimes prerequisites ollama",
            runtimes["ollama"]["setup_commands"],
        )

    def test_environment_plan_cli_outputs_execution_plan(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["environment", "plan", "python", "--version"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("mode", payload)
        self.assertIn("command", payload)
        self.assertIn("cwd", payload)
        self.assertIn("description", payload)
        self.assertNotIn("notes", payload)

    def test_environment_doctor_text_format_outputs_human_table(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["environment", "doctor", "--required-only"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("environment doctor for profile", output)
        self.assertIn("NAME", output)
        self.assertIn("TYPE", output)
        self.assertIn("STATUS", output)
        self.assertIn("REQUIRED", output)
        self.assertIn("WHY", output)
        self.assertIn("mandatory", output)
        self.assertIn("runtime", output)
        tool_lines = [line for line in output.splitlines() if "  tool" in line]
        mandatory_indexes = [index for index, line in enumerate(tool_lines) if " mandatory" in line]
        optional_indexes = [index for index, line in enumerate(tool_lines) if " optional" in line]
        if mandatory_indexes and optional_indexes:
            self.assertLess(max(mandatory_indexes), min(optional_indexes))
        for indexes in [mandatory_indexes, optional_indexes]:
            installed_indexes = [index for index in indexes if " installed" in tool_lines[index]]
            missing_indexes = [index for index in indexes if " missing" in tool_lines[index]]
            if installed_indexes and missing_indexes:
                self.assertLess(max(installed_indexes), min(missing_indexes))

    def test_benchmark_framework_cli_plans_and_install_dry_run(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["benchmarks", "doctor", "aiplane-smoke"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "benchmark_tools_doctor")
        self.assertTrue(payload["frameworks"][0]["available"])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["benchmarks", "install", "lm-evaluation-harness", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "lm-evaluation-harness")
        self.assertTrue(payload["dry_run"])
        self.assertIn("lm_eval", payload["commands"][0])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "benchmarks",
                    "plan",
                    "vllm-serving",
                    "--model",
                    "local-code-large",
                    "--endpoint",
                    "http://localhost:8000/v1",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "vllm-serving")
        self.assertEqual(payload["commands"][1]["command"][0:3], ["vllm", "bench", "serve"])

    def test_custom_benchmark_spec_dry_run_plans_evaluator_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "bench.json"
            spec.write_text(
                json.dumps(
                    {
                        "name": "custom-code",
                        "tasks": {
                            "unit": {
                                "prompt": "Write a Python function.",
                                "expected_terms": ["def"],
                                "evaluator": {
                                    "command": [
                                        "python",
                                        "-c",
                                        'print(\'{\\"score\\": 77, \\"passed\\": true}\')',
                                    ]
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            profile = load_profile("local-dev", Path.cwd())
            result = BenchmarkRunner(profile).run(
                "local-analysis-small",
                task="unit",
                dry_run=True,
                save=False,
                spec_path=spec,
                environment_mode="system",
            )
        self.assertEqual(result["name"], "custom-code")
        self.assertEqual(result["environment_mode"], "system")
        self.assertEqual(result["results"][0]["evaluation"]["type"], "command")
        self.assertIn("command", result["results"][0]["evaluation"])

    def test_models_list_rows_include_resource_requirements(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "models": {
                    "gpu_model": {
                        "provider": "vllm",
                        "source": "huggingface",
                        "model": "org/model-7b",
                        "enabled": True,
                        "min_ram_gb": 16,
                        "recommended_ram_gb": 32,
                        "min_vram_gb": 8,
                        "recommended_vram_gb": 16,
                        "resource_estimate_source": "configured",
                        "required_gpu_vendor": "nvidia",
                        "required_accelerator_apis": ["cuda"],
                    }
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            rows = ModelCatalog(profile).filter({"gpu_vendor": "nvidia", "accelerator_api": "cuda"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["min_ram_gb"], 16.0)
        self.assertEqual(rows[0]["recommended_ram_gb"], 32.0)
        self.assertEqual(rows[0]["min_vram_gb"], 8.0)
        self.assertEqual(rows[0]["recommended_vram_gb"], 16.0)
        self.assertEqual(rows[0]["resource_estimate_source"], "configured")
        self.assertEqual(rows[0]["gpu_vendor_requirement"], "nvidia")
        self.assertEqual(rows[0]["accelerator_api_requirements"], ["cuda"])
        self.assertEqual(ModelCatalog(profile).filter({"gpu_vendor": "amd"}), [])

    def test_discovered_model_resource_requirements_are_marked_as_heuristic(self) -> None:
        entry = _discovered_model_entry("ollama", "example-model:7b", enable=True)
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"models": {}}
            generated_config = {"models": {"ollama-example-model-7b": entry}}
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            rows = ModelCatalog(profile).filter({"max_min_ram_gb": 64, "max_min_vram_gb": 64})
        self.assertEqual(rows[0]["resource_estimate_source"], "catalog_heuristic:parameter_size_and_role")
        self.assertEqual(rows[0]["min_ram_gb"], entry["min_ram_gb"])
        self.assertEqual(rows[0]["min_vram_gb"], entry["min_vram_gb"])
        self.assertEqual(rows[0]["gpu_vendor_requirement"], "generic")

    def test_models_filter_can_require_saved_benchmark_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / ".aiplane" / "benchmarks"
            root.mkdir(parents=True)
            (root / "20260101T000000Z-local-analysis-small.json").write_text(
                json.dumps({"summary": {"average_score": 91, "passed": 1, "failed": 0}}),
                encoding="utf-8",
            )
            profile = load_profile("local-dev", workspace)
            rows = ModelCatalog(profile).filter({"min_benchmark_score": 90})
        names = {row["name"] for row in rows}
        self.assertIn("local-analysis-small", names)

    def test_orchestrators_are_catalog_only_in_cli(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["orchestrators", "list"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload[0]["name"], "langgraph")
        self.assertIn("ollama", payload[0]["supported_providers"])
        self.assertIn("vllm", payload[0]["supported_runtimes"])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "orchestrators",
                    "list",
                    "--provider",
                    "ollama",
                    "--group-by",
                    "provider",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "provider")
        self.assertEqual(set(payload["groups"]), {"ollama"})
        self.assertEqual(payload["groups"]["ollama"][0]["name"], "langgraph")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "orchestrators",
                    "list",
                    "--runtime",
                    "vllm",
                    "--runtime",
                    "tgi",
                    "--group-by",
                    "runtime",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(set(payload["groups"]), {"vllm", "tgi"})

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["orchestrators", "doctor", "langgraph"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "langgraph")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(
                Path.cwd() / "profile-templates" / "local-dev",
                profiles_dir / "local-dev",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--workspace",
                        str(workspace),
                        "--profiles-dir",
                        str(profiles_dir),
                        "orchestrators",
                        "setup",
                        "langgraph",
                        "--runtime",
                        "ollama",
                        "--model",
                        "local-analysis-small",
                        "--limit",
                        "timeout=30m",
                        "--tool",
                        "shell=guarded",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["dry_run"])
            text = (profiles_dir / "local-dev" / "orchestrators.yaml").read_text(encoding="utf-8")
            self.assertIn("langgraph:", text)
            self.assertIn("timeout: 30m", text)

    def test_orchestrator_setup_writes_orchestrators_yaml(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("hardware_profiles:\n", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware={"hardware_profiles": {}},
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
                orchestrators={"orchestrators": {}},
            )
            result = OrchestratorCatalog(profile).setup(
                "langgraph",
                runtime="ollama",
                model="local-analysis-small",
                dry_run=False,
                yes=True,
            )
            orchestrators_text = (root / "orchestrators.yaml").read_text(encoding="utf-8")
            hardware_text = (root / "hardware.yaml").read_text(encoding="utf-8")
        self.assertEqual(result["results"][-1]["path"], str(root / "orchestrators.yaml"))
        self.assertIn("langgraph:", orchestrators_text)
        self.assertNotIn("langgraph", hardware_text)

    def test_stack_setup_lifecycle_and_artifact_exports(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            created = stacks.setup(
                "coding_agents",
                orchestrator="langgraph",
                runtime="ollama",
                model="local-analysis-small",
                machine="local_box",
                limits={"timeout": "30m", "max_parallel_agents": 3},
                tools={"shell": "guarded"},
            )
            self.assertFalse(created["dry_run"])
            shown = stacks.show("coding_agents")["stack"]
            self.assertEqual(shown["orchestrator"], "langgraph")
            self.assertEqual(shown["limits"]["timeout"], "30m")
            self.assertEqual(shown["tools"]["shell"], "guarded")
            prepared = stacks.prepare("coding_agents", dry_run=True)
            self.assertEqual(prepared["action"], "prepare")
            self.assertTrue(prepared["dry_run"])
            self.assertTrue(any(item["name"] == "install orchestrator packages" for item in prepared["commands"]))
            dockerfile = stacks.export("dockerfile", "coding_agents")
            self.assertIn("langgraph", dockerfile["content"])
            self.assertIn("AIPLANE_LIMITS_JSON", dockerfile["content"])
            self.assertEqual(dockerfile["metadata"]["limits"]["timeout"], "30m")
            compose = stacks.export("compose", "coding_agents")
            self.assertIn("AIPLANE_TOOLS_JSON", compose["content"])
            self.assertIn("11434:11434", compose["content"])
            status = stacks.status("coding_agents")
            self.assertEqual(status["orchestrator"], "langgraph")
            self.assertEqual(status["limits"]["max_parallel_agents"], 3)

    def test_stack_setup_cli_accepts_limits_and_tool_policies(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for key, filename in agent_config.CONFIG_FILES.items():
                (profile_root / filename).write_text(agent_config.dump_yaml(getattr(source, key)), encoding="utf-8")
            profile = load_profile("tmp", Path.cwd(), profiles_dir=profiles_dir)
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "stacks",
                        "setup",
                        "coding_agents",
                        "--orchestrator",
                        "langgraph",
                        "--runtime",
                        "ollama",
                        "--model",
                        "local-analysis-small",
                        "--machine",
                        "local_box",
                        "--limit",
                        "timeout=30m",
                        "--tool",
                        "shell=guarded",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["stack"]["limits"]["timeout"], "30m")
            self.assertEqual(payload["stack"]["tools"]["shell"], "guarded")

    def test_stack_lifecycle_uses_provider_helper_directly(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "local_stack",
                orchestrator=None,
                runtime="ollama",
                model="local-analysis-small",
                machine="local_box",
                access="same_host",
            )
            plan = stacks.prepare("local_stack", dry_run=True)
        commands = [item["command"] for item in plan["commands"]]
        self.assertTrue(commands)
        self.assertIn("provider_helper.sh", commands[0][0])
        self.assertNotEqual(commands[0][0], "aiplane")
        self.assertIn("--provider", commands[0])
        self.assertIn("ollama", commands[0])

    def test_stack_lifecycle_reports_outcome_and_runtime_snapshot(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "local_stack",
                orchestrator=None,
                runtime="ollama",
                model="local-analysis-small",
                machine="local_box",
                access="same_host",
            )

            class Completed:
                returncode = 0
                stdout = "ok"
                stderr = ""

            with patch("aiplane.stacks.subprocess.run", return_value=Completed()):
                result = stacks.start("local_stack")
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["steps_total"], 1)
        self.assertEqual(result["steps_executed"], 1)
        self.assertIsNone(result["failed_step"])
        self.assertIn("runtime_status_after", result)
        self.assertIn("available", result["runtime_status_after"])

    def test_stack_lifecycle_reports_failed_step(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "local_stack",
                orchestrator=None,
                runtime="ollama",
                model="local-analysis-small",
                machine="local_box",
                access="same_host",
            )

            class Failed:
                returncode = 7
                stdout = ""
                stderr = "failed"

            with patch("aiplane.stacks.subprocess.run", return_value=Failed()):
                result = stacks.prepare("local_stack")
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["steps_total"], 2)
        self.assertEqual(result["steps_executed"], 1)
        self.assertEqual(result["failed_step"]["returncode"], 7)

    def test_stack_lifecycle_does_not_execute_remote_stack(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            MachineManager(profile).import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            stacks = StackManager(profile)
            stacks.setup(
                "remote_stack",
                orchestrator=None,
                runtime="vllm",
                model="local-code-large",
                machine="azure_h100_test",
                access="ssh_tunnel",
            )
            with patch("aiplane.stacks.subprocess.run") as run:
                result = stacks.start("remote_stack")
        self.assertEqual(result["status"], "planned_not_executed")
        self.assertIn("same-host/local", result["reason"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
