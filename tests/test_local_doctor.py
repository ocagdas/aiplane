from __future__ import annotations

from .support import (
    IntegrationManager,
    Path,
    StringIO,
    TestHttpServer,
    _isolated_test_profile,
    cli_main,
    json,
    load_profile,
    redirect_stdout,
    unittest,
)
from aiplane.local_doctor import local_coding_doctor, local_coding_doctor_text


class LocalDoctorTests(unittest.TestCase):
    def test_local_coding_doctor_reports_wedge_sections(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = local_coding_doctor(profile)
        self.assertEqual(payload["name"], "local_coding_doctor")
        self.assertEqual(payload["profile"], "local-dev")
        section_names = {section["name"] for section in payload["sections"]}
        self.assertEqual(
            section_names,
            {"profile", "environment", "model_defaults", "endpoints", "hardware", "providers", "integrations", "mcp"},
        )
        defaults = next(section for section in payload["sections"] if section["name"] == "model_defaults")
        default_names = {check["name"] for check in defaults["checks"]}
        self.assertIn("chat_model", default_names)
        self.assertIn("autocomplete_model", default_names)
        self.assertIn("embedding_model", default_names)
        self.assertIn("code_model", default_names)
        mcp = next(section for section in payload["sections"] if section["name"] == "mcp")
        mcp_checks = {check["name"]: check for check in mcp["checks"]}
        self.assertIn("mcp_manifest", mcp_checks)
        self.assertIn("mcp_local_coding_read_surface", mcp_checks)
        self.assertIn("mcp_guarded_write_surface", mcp_checks)
        self.assertTrue(mcp_checks["mcp_local_coding_read_surface"]["ok"])
        self.assertEqual(mcp_checks["mcp_local_coding_read_surface"]["missing_tools"], [])
        required_tools = set(mcp_checks["mcp_local_coding_read_surface"]["required_tools"])
        self.assertIn("aiplane.models.list", required_tools)
        self.assertIn("aiplane.integrations.export", required_tools)
        self.assertIn("aiplane.runtimes.status", required_tools)
        self.assertIn("aiplane.models.use", mcp_checks["mcp_guarded_write_surface"]["tools"])
        self.assertTrue(any("mcp manifest" in step.lower() for step in payload["next_steps"]))

    def test_local_coding_doctor_text_is_human_readable(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        output = local_coding_doctor_text(local_coding_doctor(profile))
        self.assertIn("aiplane doctor for profile local-dev", output)
        self.assertIn("model_defaults", output)
        self.assertIn("integrations", output)
        self.assertIn("next steps:", output)

    def test_doctor_cli_outputs_text_and_json(self) -> None:
        text_stdout = StringIO()
        with redirect_stdout(text_stdout):
            code = cli_main(["doctor", "--profile", "local-dev"])
        self.assertEqual(code, 0)
        self.assertIn("aiplane doctor for profile local-dev", text_stdout.getvalue())

        json_stdout = StringIO()
        with redirect_stdout(json_stdout):
            code = cli_main(["doctor", "--profile", "local-dev", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(json_stdout.getvalue())
        self.assertEqual(payload["name"], "local_coding_doctor")
        self.assertIn("summary", payload)

    def test_doctor_reports_default_endpoint_and_hardware_fit_details(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = local_coding_doctor(profile)

        defaults = next(section for section in payload["sections"] if section["name"] == "model_defaults")
        chat_check = next(check for check in defaults["checks"] if check["name"] == "chat_model")
        self.assertEqual(chat_check["provider"], "ollama")
        self.assertEqual(chat_check["endpoint"], "http://localhost:11434")
        self.assertIn("generation", chat_check["roles"])

        endpoints = next(section for section in payload["sections"] if section["name"] == "endpoints")
        self.assertTrue(any(check["name"] == "endpoint:chat" for check in endpoints["checks"]))

        hardware = next(section for section in payload["sections"] if section["name"] == "hardware")
        self.assertTrue(any(check["name"] == "active_machine" for check in hardware["checks"]))
        fit_names = {check["name"] for check in hardware["checks"]}
        self.assertIn("model_fit:chat_model", fit_names)
        self.assertIn("model_fit:embedding_model", fit_names)

    def test_doctor_reports_reachable_endpoint_for_openai_compatible_default(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with TestHttpServer() as endpoint:
            profile.models["providers"]["vllm"]["enabled"] = True
            profile.models["providers"]["vllm"]["endpoint"] = endpoint
            profile.models["models"]["provider-code-large-vllm"]["enabled"] = True
            profile.models["models"]["provider-code-large-vllm"]["model"] = "test-model"
            profile.models.setdefault("defaults", {})["chat_model"] = "provider-code-large-vllm"
            payload = local_coding_doctor(profile)

        endpoints = next(section for section in payload["sections"] if section["name"] == "endpoints")
        chat_endpoint = next(check for check in endpoints["checks"] if check["name"] == "endpoint:chat")
        self.assertTrue(chat_endpoint["ok"])
        self.assertEqual(chat_endpoint["provider"], "vllm")
        self.assertEqual(chat_endpoint["endpoint"], endpoint)
        self.assertEqual(chat_endpoint["reason"], "model is available")

    def test_doctor_rejects_incompatible_default_alias_for_integration_role(self) -> None:
        with _isolated_test_profile("local-dev") as profile:
            profile.models.setdefault("defaults", {})["chat_model"] = "fixture-embedding-small"
            payload = local_coding_doctor(profile)

        defaults = next(section for section in payload["sections"] if section["name"] == "model_defaults")
        chat_check = next(check for check in defaults["checks"] if check["name"] == "chat_model")
        self.assertFalse(chat_check["ok"])
        self.assertIn("not suitable", chat_check["reason"])

        integrations = next(section for section in payload["sections"] if section["name"] == "integrations")
        continue_check = next(check for check in integrations["checks"] if check["name"] == "integration:continue")
        self.assertFalse(continue_check["ok"])
        self.assertIn("chat:incompatible", continue_check["detail"])

    def test_doctor_integration_readiness_matches_continue_plan_defaults(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = local_coding_doctor(profile)
        integrations = next(section for section in payload["sections"] if section["name"] == "integrations")
        continue_check = next(check for check in integrations["checks"] if check["name"] == "integration:continue")
        plan = IntegrationManager(profile).plan("continue")
        self.assertTrue(continue_check["ok"])
        self.assertEqual(plan["selection"]["chat"]["name"], "fixture-chat-small")
