from __future__ import annotations

from .support import (
    Path,
    PolicyEngine,
    StringIO,
    cli_main,
    contains_secret,
    json,
    load_profile,
    redact,
    redirect_stdout,
    tempfile,
    unittest,
)


class GovernanceCliTests(unittest.TestCase):
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
        self.assertIn("environment doctor and configuration compiler", output)
        self.assertIn("Core workflow:", output)
        self.assertIn("Advanced and supporting:", output)
        self.assertIn("Experimental:", output)
        self.assertLess(output.index("Core workflow:"), output.index("Advanced and supporting:"))
        self.assertLess(output.index("Advanced and supporting:"), output.index("Experimental:"))
        self.assertIn("Outcome: a profile-aware readiness report", output)
        self.assertIn("Next command:", output)
        self.assertIn("aiplane quickstart local-coding --dry-run", output)
        self.assertIn("docs/project/command-coverage.md", output)
        self.assertNotIn("aiplane launch --tool continue", output)
        self.assertNotIn("aiplane session start --tool ollama", output)
        self.assertIn("hardware", output)

    def test_profiles_help_points_to_hardware_discovery_commands(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli_main(["profiles", "--help"])
        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("aiplane hardware discover", output)
        self.assertIn("aiplane hardware export-machine", output)
        self.assertIn("aiplane profiles remove old-local --dry-run", output)

    def test_command_help_mentions_argument_purpose(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli_main(["integrations", "export", "--help"])
        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("Print configuration", output)
        self.assertIn("Override provider endpoint", output)
        self.assertIn("Endpoint examples", output)

    def test_launch_and_session_help_mentions_command_shapes(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli_main(["launch", "--help"])
        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("Launch a configured assistant tool", output)
        self.assertIn("aiplane launch --tool aider --model fixture-chat-small", output)
        self.assertIn("--tool", output)

    def test_session_help_mentions_start_recording(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli_main(["session", "start", "--help"])
        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("Start a minimal session metadata record", output)
        self.assertIn("--tool", output)
        self.assertIn("--transcript", output)

    def test_policy_allows_read_and_requires_write_approval(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        policy = PolicyEngine(profile)
        read = policy.tool_decision("read_file")
        write = policy.tool_decision("write_file")
        self.assertFalse(read.requires_approval)
        self.assertEqual(read.outcome, "allowed")
        self.assertTrue(write.requires_approval)
        self.assertEqual(write.outcome, "approval_required")

    def test_policy_explain_supports_new_policy_actions(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.repository["allowed_providers"] = ["ollama", "openai"]
        profile.models.setdefault("models", {})["policy-demo"] = {
            "provider": "ollama",
            "local": True,
            "enabled": True,
            "roles": ["chat"],
        }

        policy = PolicyEngine(profile)
        self.assertEqual(policy.explain("provider:ollama").outcome, "allowed")
        self.assertEqual(policy.explain("backend:cloud").outcome, "allowed")
        self.assertEqual(policy.explain("model:policy-demo").outcome, "allowed")
        self.assertEqual(policy.explain("provider:forbidden").outcome, "blocked")
        self.assertEqual(policy.explain("model:missing-model").outcome, "blocked")

    def test_policy_explain_cli_reports_allow_and_deny_decisions(self) -> None:
        stdout_allow = StringIO()
        with redirect_stdout(stdout_allow):
            code = cli_main(["policy", "explain", "--action", "provider:ollama", "--profile", "local-dev"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout_allow.getvalue())
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["outcome"], "allowed")
        self.assertEqual(payload["matched_rule"], "repository.allowed_providers")

        stdout_deny = StringIO()
        with redirect_stdout(stdout_deny):
            code = cli_main(["policy", "explain", "--action", "model:missing-model", "--profile", "local-dev"])
        payload = json.loads(stdout_deny.getvalue())
        self.assertFalse(payload["allowed"])
        self.assertIn(payload["reason"], {"unknown model 'missing-model'", "model not allowed: missing-model"})

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
