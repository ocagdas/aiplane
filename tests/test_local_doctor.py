from __future__ import annotations

from .support import IntegrationManager, Path, StringIO, cli_main, json, load_profile, redirect_stdout, unittest
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
            {"profile", "environment", "model_defaults", "providers", "integrations", "mcp"},
        )
        defaults = next(section for section in payload["sections"] if section["name"] == "model_defaults")
        default_names = {check["name"] for check in defaults["checks"]}
        self.assertIn("chat_model", default_names)
        self.assertIn("autocomplete_model", default_names)
        self.assertIn("embedding_model", default_names)
        self.assertIn("code_model", default_names)
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

    def test_doctor_integration_readiness_matches_continue_plan_defaults(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = local_coding_doctor(profile)
        integrations = next(section for section in payload["sections"] if section["name"] == "integrations")
        continue_check = next(check for check in integrations["checks"] if check["name"] == "integration:continue")
        plan = IntegrationManager(profile).plan("continue")
        self.assertTrue(continue_check["ok"])
        self.assertEqual(plan["selection"]["chat"]["name"], "local-chat-small")
