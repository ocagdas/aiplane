from __future__ import annotations

import copy
from unittest.mock import patch

from .support import (
    IntegrationManager,
    MachineManager,
    StackManager,
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
from aiplane.hardware import HardwareFit
from aiplane.integration_contracts import ALL_INTEGRATION_TOOLS
from aiplane.local_doctor import local_coding_doctor, local_coding_doctor_text


class LocalDoctorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._ollama_probe = patch(
            "aiplane.model_execution.ModelExecution._probe_ollama_backend",
            return_value=(False, "synthetic Ollama endpoint unavailable", []),
        )
        cls._ollama_probe.start()
        cls._hardware_probe = patch(
            "aiplane.local_doctor.HardwareManager.active_config",
            return_value={
                "name": "synthetic-host",
                "origin": "test_fixture",
                "machine": {
                    "name": "synthetic-host",
                    "placement": "same_host",
                    "cpu": {"architecture": "x86_64", "cores": 8, "threads": 16},
                    "memory": {"ram_gb": 32, "unified_memory_gb": None},
                    "gpu": {"vendor": "none", "count": 0, "vram_gb": 0, "total_vram_gb": 0},
                    "accelerator_apis": ["cpu"],
                    "os": "linux",
                },
            },
        )
        cls._hardware_probe.start()
        cls._hardware_fit = patch(
            "aiplane.local_doctor.HardwareManager.check_model_fit",
            return_value=HardwareFit("synthetic-model", True, "fits synthetic host"),
        )
        cls._hardware_fit.start()
        cls._environment_probe = patch(
            "aiplane.local_doctor.ToolchainManager.environment_doctor",
            return_value={
                "summary": {
                    "tools_checked": 1,
                    "tools_installed": 1,
                    "tools_missing_installable_by_aiplane": 0,
                    "tools_missing_manual_or_platform_specific": 0,
                    "runtime_prerequisites_checked": 1,
                    "runtime_prerequisites_missing": 0,
                }
            },
        )
        cls._environment_probe.start()
        cls._baseline_profile = load_profile("local-dev", Path.cwd())
        cls._baseline_doctor_payload = local_coding_doctor(cls._baseline_profile)
        cls._baseline_doctor_text = local_coding_doctor_text(cls._baseline_doctor_payload)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._environment_probe.stop()
        cls._hardware_fit.stop()
        cls._hardware_probe.stop()
        cls._ollama_probe.stop()
        super().tearDownClass()

    @classmethod
    def _baseline_payload(cls) -> dict[str, object]:
        return cls._baseline_doctor_payload

    def test_local_coding_doctor_reports_wedge_sections(self) -> None:
        payload = self._baseline_payload()
        self.assertEqual(payload["name"], "local_coding_doctor")
        self.assertEqual(payload["profile"], "local-dev")
        section_names = {section["name"] for section in payload["sections"]}
        self.assertEqual(
            section_names,
            {
                "profile",
                "environment",
                "model_defaults",
                "endpoints",
                "hardware",
                "providers",
                "policy",
                "remote",
                "integrations",
                "mcp",
            },
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

        remote = next(section for section in payload["sections"] if section["name"] == "remote")
        remote_checks = {check["name"]: check for check in remote["checks"]}
        self.assertIn("remote_targets_configured", remote_checks)
        self.assertIn("remote_stacks_configured", remote_checks)
        self.assertGreaterEqual(remote_checks["remote_targets_configured"]["detail"].count("configured"), 1)

        integrations = next(section for section in payload["sections"] if section["name"] == "integrations")
        integration_check_names = {check["name"] for check in integrations["checks"]}
        self.assertEqual(integration_check_names, {f"integration:{tool}" for tool in ALL_INTEGRATION_TOOLS})

    def test_local_coding_doctor_includes_remote_tunnel_readiness(self) -> None:
        payload = self._baseline_payload()

        remote = next(section for section in payload["sections"] if section["name"] == "remote")
        remote_checks = {check["name"]: check for check in remote["checks"]}
        self.assertIn("remote_target:gpu_workstation_ssh", remote_checks)
        target_check = remote_checks["remote_target:gpu_workstation_ssh"]
        self.assertIn("tool_available", target_check)

    def test_local_coding_doctor_includes_remote_stack_doctor_checks(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        machine_mgr = MachineManager(profile)
        machine_mgr.import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_remote")

        stacks = StackManager(profile)
        stacks.setup(
            "remote_stack",
            orchestrator=None,
            runtime="ollama",
            model="fixture-chat-small",
            machine="azure_h100_remote",
            access="ssh_tunnel",
        )

        payload = local_coding_doctor(profile)
        remote = next(section for section in payload["sections"] if section["name"] == "remote")
        remote_checks = {check["name"]: check for check in remote["checks"]}
        self.assertIn("remote_stacks_configured", remote_checks)
        self.assertIn("stack_doctor:remote_stack", remote_checks)
        remote_stack_check = remote_checks["stack_doctor:remote_stack"]
        self.assertIn("reason", remote_stack_check)

    def test_local_coding_doctor_includes_actionable_severity_sections(self) -> None:
        payload = self._baseline_payload()
        sections = payload["sections"]
        self.assertTrue(all(isinstance(check, dict) for section in sections for check in section["checks"]))
        self.assertIn("checks_by_severity", payload["summary"])
        total = payload["summary"]["checks"]
        self.assertEqual(
            payload["summary"]["checks_by_severity"]["blocking"]
            + payload["summary"]["checks_by_severity"]["advisory"]
            + payload["summary"]["checks_by_severity"]["pass"],
            total,
        )
        summary = {
            check_key: check
            for section in sections
            for check_key, check in [
                (f"{section['name']}::{check['name']}", check) for check in section["checks"] if isinstance(check, dict)
            ]
        }
        self.assertTrue(all("severity" in check for check in summary.values()))
        blocking = [check for check in summary.values() if check.get("severity") == "blocking"]
        advisory = [check for check in summary.values() if check.get("severity") == "advisory"]
        if blocking:
            self.assertTrue(any(check.get("action") for check in blocking))
        if advisory:
            self.assertTrue(any(check.get("action") for check in advisory))
        actionable = blocking + advisory
        for check in actionable:
            self.assertIn("impact", check)
            remediation = check.get("remediation")
            self.assertIsInstance(remediation, dict)
            self.assertIn("command", remediation)
            self.assertIn("mutates", remediation)
            self.assertIn("dry_run_supported", remediation)

    def test_doctor_contract_v1_covers_every_finding_and_exit_semantics(self) -> None:
        payload = self._baseline_payload()
        self.assertEqual(payload["contract_version"], "1.0")
        self.assertEqual(
            payload["exit_codes"],
            {
                "healthy": {"code": 0, "meaning": "all findings pass"},
                "advisory": {"code": 1, "meaning": "no blockers; one or more advisory findings"},
                "blocking": {"code": 2, "meaning": "one or more blocking findings"},
            },
        )
        expected_outcome = (
            "blocking"
            if payload["summary"]["blocking"]
            else "advisory"
            if payload["summary"]["warnings"]
            else "healthy"
        )
        self.assertEqual(payload["outcome"], expected_outcome)
        self.assertEqual(payload["exit_code"], payload["exit_codes"][expected_outcome]["code"])

        findings = [check for section in payload["sections"] for check in section["checks"]]
        self.assertEqual(len({finding["id"] for finding in findings}), len(findings))
        for finding in findings:
            self.assertIn(finding["severity"], {"blocking", "advisory", "pass"})
            self.assertIsInstance(finding["reason"], str)
            self.assertTrue(finding["impact"])
            self.assertEqual(finding["affected_resource"]["profile"], "local-dev")
            self.assertTrue(finding["affected_resource"]["type"])
            self.assertTrue(finding["affected_resource"]["name"])
            remediation = finding["remediation"]
            self.assertIn(remediation["mutation"], {"none", "read_only", "mutating"})
            self.assertIsInstance(remediation["mutates"], bool)
            self.assertIsInstance(remediation["dry_run_supported"], bool)
            if finding["severity"] == "pass":
                self.assertIsNone(remediation["command"])
            else:
                self.assertTrue(remediation["command"].startswith("aiplane "))

    def test_every_blocker_has_a_deterministic_non_placeholder_next_action(self) -> None:
        profile = copy.deepcopy(self._baseline_profile)
        for provider in profile.models.get("providers", {}).values():
            if isinstance(provider, dict):
                provider["enabled"] = False
        first = local_coding_doctor(profile)
        second = local_coding_doctor(profile)
        first_actions = {
            finding["id"]: finding["remediation"]["command"]
            for section in first["sections"]
            for finding in section["checks"]
            if finding["severity"] == "blocking"
        }
        second_actions = {
            finding["id"]: finding["remediation"]["command"]
            for section in second["sections"]
            for finding in section["checks"]
            if finding["severity"] == "blocking"
        }
        self.assertTrue(first_actions)
        self.assertEqual(first_actions, second_actions)
        self.assertTrue(all(command and "<" not in command for command in first_actions.values()))
        self.assertTrue(all(not command.startswith("aiplane doctor ") for command in first_actions.values()))

    def test_local_coding_doctor_text_is_human_readable(self) -> None:
        output = self._baseline_doctor_text
        self.assertIn("aiplane doctor for profile local-dev", output)
        self.assertIn("model_defaults", output)
        self.assertIn("integrations", output)
        self.assertIn("contract: 1.0; exit_code:", output)
        self.assertIn("next steps:", output)

    def test_doctor_cli_outputs_text_and_json(self) -> None:
        # Domain checks are exercised against the real doctor payload above.
        # Reuse that result here so this test owns only CLI formatting and exit semantics.
        with patch(
            "aiplane.cli_public.local_coding_doctor",
            return_value=self._baseline_payload(),
        ) as doctor:
            text_stdout = StringIO()
            with redirect_stdout(text_stdout):
                code = cli_main(["doctor", "--profile", "local-dev"])
            self.assertIn(code, {0, 1, 2})
            self.assertIn("aiplane doctor for profile local-dev", text_stdout.getvalue())

            json_stdout = StringIO()
            with redirect_stdout(json_stdout):
                code = cli_main(["doctor", "--profile", "local-dev", "--format", "json"])

        self.assertEqual(doctor.call_count, 2)
        self.assertIn(code, {0, 1, 2})
        payload = json.loads(json_stdout.getvalue())
        self.assertEqual(code, payload["exit_code"])
        self.assertEqual(payload["name"], "local_coding_doctor")
        self.assertIn("summary", payload)

    def test_doctor_reports_default_endpoint_and_hardware_fit_details(self) -> None:
        payload = self._baseline_payload()

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

    def test_doctor_reports_reachable_endpoint_for_openai_compatible_default(
        self,
    ) -> None:
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

    def test_doctor_rejects_incompatible_default_alias_for_integration_role(
        self,
    ) -> None:
        with _isolated_test_profile("local-dev") as profile:
            profile.models.setdefault("defaults", {})["chat_model"] = "fixture-embedding-small"
            payload = local_coding_doctor(profile)

        defaults = next(section for section in payload["sections"] if section["name"] == "model_defaults")
        chat_check = next(check for check in defaults["checks"] if check["name"] == "chat_model")
        self.assertFalse(chat_check["ok"])
        self.assertIn("not suitable", chat_check["reason"])

        integrations = next(section for section in payload["sections"] if section["name"] == "integrations")
        continue_check = next(check for check in integrations["checks"] if check["name"] == "integration:continue")
        self.assertTrue(continue_check["ok"])
        self.assertTrue(continue_check["warning"])
        self.assertIn("chat:incompatible", continue_check["detail"])

    def test_doctor_integration_readiness_matches_continue_plan_defaults(self) -> None:
        profile = self._baseline_profile
        payload = self._baseline_payload()
        integrations = next(section for section in payload["sections"] if section["name"] == "integrations")
        continue_check = next(check for check in integrations["checks"] if check["name"] == "integration:continue")
        plan = IntegrationManager(profile).plan("continue")
        self.assertTrue(continue_check["ok"])
        self.assertEqual(plan["selection"]["chat"]["name"], "fixture-chat-small")

    def test_doctor_policy_section_flags_disallowed_default_provider(self) -> None:
        profile = copy.deepcopy(self._baseline_profile)
        profile.repository["allowed_providers"] = ["openai"]
        payload = local_coding_doctor(profile)
        policy = next(section for section in payload["sections"] if section["name"] == "policy")
        model_policy = next(check for check in policy["checks"] if check["name"] == "model_policy:fixture-chat-small")
        self.assertFalse(model_policy["ok"])
        self.assertIn("not allowed", model_policy["detail"])

    def test_doctor_policy_section_flags_blocked_cloud_backends(self) -> None:
        profile = copy.deepcopy(self._baseline_profile)
        profile.repository["classification"] = "client_sensitive"
        payload = local_coding_doctor(profile)
        policy = next(section for section in payload["sections"] if section["name"] == "policy")
        cloud_check = next(check for check in policy["checks"] if check["name"] == "cloud_backends")
        self.assertFalse(cloud_check["ok"])
        self.assertIn("client-sensitive", cloud_check["detail"])
