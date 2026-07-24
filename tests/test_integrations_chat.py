from __future__ import annotations

import tomllib

from aiplane.integration_contracts import EXPORT_CONTRACT_VERSION, TIER1_EXPORT_TOOLS

from .support import (
    IntegrationManager,
    Path,
    Profile,
    StringIO,
    TestHttpServer,
    _REAL_LOAD_PROFILE,
    _isolated_profiles_dir,
    _isolated_test_profile,
    _materialize_test_models,
    agent_config,
    cli_main,
    create_profile,
    json,
    load_profile,
    os,
    patch,
    redirect_stderr,
    redirect_stdout,
    shutil,
    subprocess,
    sys,
    tempfile,
    unittest,
)


class IntegrationChatTests(unittest.TestCase):
    def test_integrations_continue_export_uses_profile_defaults_bundle(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        exported = IntegrationManager(profile).export("continue")
        self.assertEqual(exported.tool, "continue")
        self.assertIn("apiBase: http://localhost:11434/v1", exported.content)
        self.assertIn("model: provider-chat-small:8b", exported.content)
        self.assertIn("tabAutocompleteModel:", exported.content)
        self.assertIn("model: provider-code-base:1.5b", exported.content)
        self.assertIn("embeddingsProvider:", exported.content)
        self.assertIn("model: fixture-embedding-small:latest", exported.content)

    def test_integrations_plan_selects_defaults_best_and_manual_overrides(self) -> None:
        with _isolated_test_profile() as profile:
            manager = IntegrationManager(profile)

            default_plan = manager.plan("continue")
            self.assertEqual(default_plan["selection"]["chat"]["name"], "fixture-chat-small")
            self.assertIn("tool_use", default_plan["selection"]["chat"]["role_capabilities"])
            self.assertEqual(default_plan["selection"]["autocomplete"]["name"], "fixture-code-base")
            self.assertEqual(
                default_plan["selection"]["embedding"]["name"],
                "fixture-embedding-small",
            )

            best_plan = manager.plan("continue", runtime="ollama", select_best=True)
            self.assertEqual(best_plan["constraints"]["runtime"], "ollama")
            self.assertTrue(all(row["runtime"] == "ollama" for row in best_plan["selection"].values()))

            manual = manager.plan(
                "continue",
                chat="fixture-code-small",
                autocomplete="fixture-code-base",
                embedding="fixture-embedding-small",
            )
            self.assertEqual(manual["selection"]["chat"]["name"], "fixture-code-small")
            self.assertEqual(manual["overrides"]["chat"], "fixture-code-small")

    def test_integrations_setup_dry_run_plans_runtime_actions(self) -> None:
        with _isolated_test_profile() as profile:
            result = IntegrationManager(profile).setup("continue", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["plan"]["tool"], "continue")
        self.assertTrue(result["actions"])
        self.assertTrue(all(action["status"] in {"planned", "ok"} for action in result["actions"]))

    def test_integrations_setup_dry_run_installs_missing_ollama_before_start_and_pull(
        self,
    ) -> None:
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
                return_value={
                    "available": False,
                    "reason": "model is not pulled",
                    "provider": "ollama",
                },
            ),
        ):
            result = IntegrationManager(profile).setup(
                "continue",
                chat="fixture-chat-small",
                autocomplete="fixture-chat-small",
                embedding="fixture-chat-small",
                dry_run=True,
            )
        actions = [action["action"] for action in result["actions"]]
        self.assertEqual(actions.count("install"), 1)
        self.assertEqual(actions.count("start"), 1)
        self.assertEqual(actions.count("pull"), 1)
        self.assertLess(actions.index("install"), actions.index("start"))
        self.assertLess(actions.index("start"), actions.index("pull"))

    def test_integrations_setup_pulls_huggingface_gguf_alias_through_ollama(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("models", {})["hf-gguf-chat"] = {
            "provider": "llamacpp",
            "model": "Example/Chat-GGUF",
            "enabled": True,
            "roles": ["chat"],
            "source": "huggingface_gguf",
            "supported_runtimes": ["llamacpp", "ollama"],
            "preferred_runtime": "ollama",
            "capabilities": {
                "scores": {"general_chat": 3, "reasoning": 3, "tool_use": 2},
            },
        }
        completed = subprocess.CompletedProcess(
            ["scripts/provider_helper.sh"],
            0,
            "+ ollama pull hf.co/Example/Chat-GGUF\n",
            "",
        )
        with (
            patch(
                "aiplane.integrations.RuntimeCatalog.runtime_available",
                return_value={"available": True, "reason": "endpoint ok"},
            ),
            patch.object(
                IntegrationManager,
                "_model_presence",
                return_value={
                    "available": False,
                    "reason": "provider is disabled",
                    "provider": "llamacpp",
                },
            ),
            patch.object(IntegrationManager, "_run_with_progress", return_value=completed) as run_with_progress,
        ):
            result = IntegrationManager(profile).setup(
                "openai-compatible",
                model_name="hf-gguf-chat",
                runtime="ollama",
                dry_run=False,
                yes=True,
            )
        pull_actions = [action for action in result["actions"] if action["action"] == "pull"]
        self.assertEqual(len(pull_actions), 1)
        self.assertEqual(pull_actions[0]["status"], "succeeded")
        self.assertEqual(pull_actions[0]["runtime"], "ollama")
        self.assertEqual(pull_actions[0]["model"], "hf-gguf-chat")
        run_with_progress.assert_called_once()

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
                "fixture-chat-small",
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

    def test_integrations_setup_streams_helper_progress_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "progress.py"
            script.write_text(
                "import sys, time\n"
                "print('+ ollama pull command-r7b')\n"
                "sys.stdout.flush()\n"
                "sys.stderr.write('pulling manifest\\r')\n"
                "sys.stderr.flush()\n"
                "time.sleep(0.05)\n"
                "sys.stderr.write('pulling b32d935e114c:   1% 67 MB/5.1 GB 3.3 MB/s 24m53s\\r')\n"
                "sys.stderr.flush()\n",
                encoding="utf-8",
            )
            stderr = StringIO()
            with redirect_stderr(stderr):
                completed = IntegrationManager(load_profile("local-dev", Path.cwd()))._run_with_progress(
                    [sys.executable, str(script)],
                    cwd=Path.cwd(),
                    label="setup: pull ollama for local_chat",
                )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("+ ollama pull command-r7b", completed.stdout)
        self.assertIn("pulling b32d935e114c", completed.stderr)
        progress_output = stderr.getvalue()
        self.assertIn("setup: pull ollama for local_chat", progress_output)
        self.assertIn("+ ollama pull command-r7b", progress_output)
        self.assertIn("67 MB/5.1 GB", progress_output)

    def test_integrations_setup_progress_rejects_windows_execution(self) -> None:
        manager = IntegrationManager(load_profile("local-dev", Path.cwd()))
        cwd = Path.cwd()
        with patch("aiplane.integrations.os.name", "nt"):
            with self.assertRaisesRegex(RuntimeError, "unsupported on Windows"):
                manager._run_with_progress(["echo", "ignored"], cwd=cwd, label="setup: test")

    def test_integrations_setup_progress_requires_pipes(self) -> None:
        class PipeLessProcess:
            stdout = None
            stderr = None

        class PipeLessRunner:
            @staticmethod
            def popen(*args, **kwargs):
                return PipeLessProcess()

        manager = IntegrationManager(load_profile("local-dev", Path.cwd()), command_runner=PipeLessRunner())
        with self.assertRaisesRegex(RuntimeError, "must expose both stdout and stderr pipes"):
            manager._run_with_progress(["echo", "ignored"], cwd=Path.cwd(), label="setup: test")

    def test_integrations_setup_passes_profiles_dir_to_helper(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            profile_root = Path(tmp) / "profiles" / "custom"
            profile_root.mkdir(parents=True)
            profile = Profile(
                "custom",
                profile_root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                source.models,
                source.targets,
                source.orchestrators,
            )
            captured = {}

            def fake_run(command, cwd, label, env=None):
                captured["env"] = env
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(IntegrationManager, "_run_with_progress", side_effect=fake_run):
                action = IntegrationManager(profile)._setup_action(
                    "ollama",
                    "pull",
                    "fixture-chat-small",
                    dry_run=False,
                    execute=True,
                    reason="test pull",
                )

        self.assertEqual(action["status"], "succeeded")
        self.assertEqual(captured["env"]["AIPLANE_PROFILES_DIR"], str(profile_root.parent))

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
                "fixture-chat-small",
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
        with _isolated_profiles_dir() as profiles_dir:
            profiles_arg = ["--profiles-dir", str(profiles_dir)]
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
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
                code = cli_main(profiles_arg + ["integrations", "setup", "continue", "--dry-run"])
            self.assertEqual(code, 0)
            setup = json.loads(stdout.getvalue())
            self.assertTrue(setup["dry_run"])
            self.assertIn("actions", setup)

    def test_integrations_export_continue_uses_planner_constraints(self) -> None:
        with _isolated_test_profile() as profile:
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
            self.assertIn(
                f"model: {planned['selection']['autocomplete']['model']}",
                exported.content,
            )
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
        exported = IntegrationManager(profile).export("continue", "fixture-analysis-small")
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
                    "fixture-code-base",
                    "--embedding",
                    "fixture-embedding-small",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("model: managed-chat-model", output)
        self.assertIn("model: provider-code-base:1.5b", output)
        self.assertIn("model: fixture-embedding-small:latest", output)

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
                        "fixture-code-base",
                        "--embedding",
                        "fixture-embedding-small",
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

        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "invalid-plan.json"
            plan_path.write_text("[]", encoding="utf-8")
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = cli_main(
                    [
                        "integrations",
                        "export",
                        "continue",
                        "--from-plan",
                        str(plan_path),
                    ]
                )
            self.assertEqual(code, 1)
            self.assertIn("saved plan must be a JSON object", stderr.getvalue())

    def test_agents_plan_and_export_cli_print_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            _materialize_test_models(profiles_dir / "local-dev")
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
                        "fixture-analysis-small",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["name"], "agent_plan")
            self.assertEqual(payload["selection"]["model_alias"], "fixture-analysis-small")
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
                        "fixture-analysis-small",
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
            _materialize_test_models(profiles_dir / "local-dev")
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
                            "fixture-analysis-small",
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
                            "fixture-analysis-small",
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
                            "fixture-analysis-small",
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

    def test_integrations_export_allows_remote_endpoint_override(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        exported = IntegrationManager(profile).export(
            "openai-compatible",
            "fixture-analysis-small",
            endpoint="https://llm.example.com/v1",
        )
        self.assertIn("https://llm.example.com/v1", exported.content)

    def test_integrations_roles_cli_shows_required_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            _materialize_test_models(profiles_dir / "local-dev")
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
            _materialize_test_models(profiles_dir / "local-dev")
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
            _materialize_test_models(profiles_dir / "local-dev")
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
                        "fixture-analysis-small",
                        "--endpoint",
                        "http://localhost:11434/v1",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "cline")
        self.assertEqual(payload["selection"]["primary"]["name"], "fixture-analysis-small")
        self.assertEqual(payload["selection"]["primary"]["endpoint"], "http://localhost:11434/v1")

    def test_integrations_export_non_continue_can_select_best(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            _materialize_test_models(profiles_dir / "local-dev")
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

    def test_mcp_plan_has_the_same_compatibility_summary_contract(self) -> None:
        with _isolated_test_profile() as profile:
            plan = IntegrationManager(profile).plan("continue-mcp")
        self.assertEqual(plan["compatibility"]["status"], "compatible")
        self.assertTrue(plan["compatibility"]["renderable"])
        self.assertEqual(plan["compatibility"]["warnings"], [])

    def test_host_client_plan_reports_api_compatibility_and_rejects_foreign_flags(self) -> None:
        with _isolated_test_profile() as profile:
            manager = IntegrationManager(profile)
            plan = manager.plan("copilot-cli", model_name="fixture-chat-small")
            with self.assertRaisesRegex(ValueError, "only supported by host-client"):
                manager.export("continue", output_format="json")
        selected = plan["selection"]["primary"]
        self.assertEqual(selected["selected_api_type"], "chat_completions")
        self.assertEqual(selected["compatibility_warnings"], [])
        self.assertEqual(selected["name"], "fixture-chat-small")
        self.assertEqual(selected["model"], "provider-chat-small:8b")
        self.assertEqual(plan["compatibility"]["status"], "compatible")
        self.assertTrue(plan["compatibility"]["renderable"])

    def test_host_client_exports_are_cross_platform_and_secret_safe(self) -> None:
        with _isolated_test_profile() as profile:
            manager = IntegrationManager(profile)
            payload = json.loads(
                manager.export(
                    "copilot-cli",
                    model_name="fixture-chat-small",
                    api_key_env="AIPLANE_TEST_KEY",
                    offline=True,
                ).content
            )
            posix = manager.export(
                "copilot-cli",
                model_name="fixture-chat-small",
                api_key_env="AIPLANE_TEST_KEY",
                output_format="posix",
            ).content
            powershell = manager.export(
                "copilot-cli",
                model_name="fixture-chat-small",
                api_key_env="AIPLANE_TEST_KEY",
                output_format="powershell",
            ).content
        self.assertEqual(
            payload["environment_refs"],
            {"COPILOT_PROVIDER_API_KEY": "AIPLANE_TEST_KEY"},
        )
        self.assertNotIn("secret-value", json.dumps(payload))
        self.assertIn('export COPILOT_PROVIDER_API_KEY="${AIPLANE_TEST_KEY}"', posix)
        self.assertIn("$env:COPILOT_PROVIDER_API_KEY = $env:AIPLANE_TEST_KEY", powershell)

    def test_codex_export_uses_named_user_profile_and_rejects_anthropic_messages(self) -> None:
        with _isolated_test_profile() as profile:
            manager = IntegrationManager(profile)
            exported = manager.export("codex", model_name="fixture-chat-small")
            parsed = tomllib.loads(exported.content)
            profile.models["models"]["fixture-anthropic"] = {
                "provider": "anthropic",
                "model": "claude-test",
                "roles": ["chat"],
                "supports_tool_calling": True,
                "supports_streaming": True,
            }
            with self.assertRaisesRegex(ValueError, "Responses API"):
                manager.export("codex", model_name="fixture-anthropic")
        self.assertEqual(
            parsed["profiles"]["aiplane-fixture-chat-small"]["model_provider"],
            "ollama",
        )

    def test_codex_rejects_remote_ollama_and_vscode_preserves_endpoint_query(self) -> None:
        with _isolated_test_profile() as profile:
            manager = IntegrationManager(profile)
            with self.assertRaisesRegex(ValueError, "local-only"):
                manager.export(
                    "codex",
                    model_name="fixture-chat-small",
                    endpoint="https://ollama.example.com/v1",
                )
            exported = manager.export(
                "copilot-vscode",
                model_name="fixture-chat-small",
                endpoint="https://gateway.example.com/v1?api-version=2026-01-01",
            )
        url = json.loads(exported.content)[0]["models"][0]["url"]
        self.assertEqual(
            url,
            "https://gateway.example.com/v1/chat/completions?api-version=2026-01-01",
        )

    def test_agent_exports_reject_known_capability_incompatibility(self) -> None:
        with _isolated_test_profile() as profile:
            profile.models["models"]["fixture-chat-small"]["supports_tool_calling"] = False
            manager = IntegrationManager(profile)
            with self.assertRaisesRegex(ValueError, "requires tool calling"):
                manager.export("copilot-vscode", model_name="fixture-chat-small")

    def test_public_copilot_json_stdout_remains_valid_json(self) -> None:
        with _isolated_profiles_dir("local-dev") as profiles_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "export",
                        "copilot-cli",
                        "--model",
                        "fixture-chat-small",
                        "--format",
                        "json",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["alias"], "fixture-chat-small")

    def test_tier1_exports_match_versioned_golden_files(self) -> None:
        self.assertEqual(EXPORT_CONTRACT_VERSION, "1.0")
        self.assertEqual(
            TIER1_EXPORT_TOOLS,
            (
                "continue",
                "aider",
                "openai-compatible",
                "generic-mcp",
                "codex",
                "copilot-cli",
                "copilot-vscode",
            ),
        )
        with _isolated_test_profile() as profile:
            manager = IntegrationManager(profile)
            exports = {
                "continue.yaml": manager.export(
                    "continue",
                    chat="fixture-chat-small",
                    autocomplete="fixture-code-base",
                    embedding="fixture-embedding-small",
                ).content,
                "aider.sh": manager.export("aider", model_name="fixture-analysis-small").content,
                "openai-compatible.json": manager.export(
                    "openai-compatible", model_name="fixture-analysis-small"
                ).content,
                "generic-mcp.json": manager.export("generic-mcp").content,
                "codex.toml": manager.export("codex", model_name="fixture-chat-small").content,
                "copilot-cli.json": manager.export(
                    "copilot-cli",
                    model_name="fixture-chat-small",
                    offline=True,
                ).content,
                "copilot-vscode.json": manager.export(
                    "copilot-vscode",
                    model_name="fixture-chat-small",
                ).content,
            }

        golden_root = Path("tests/golden/integrations/v1")
        for filename, content in exports.items():
            with self.subTest(filename=filename):
                self.assertEqual(content, (golden_root / filename).read_text(encoding="utf-8"))

        self.assertIn("schema: v1", exports["continue.yaml"])
        self.assertIn("aider --model openai/", exports["aider.sh"])
        self.assertEqual(json.loads(exports["openai-compatible.json"])["provider"], "ollama")
        self.assertEqual(
            json.loads(exports["generic-mcp.json"])["mcpServers"]["aiplane"]["args"],
            ["mcp", "serve"],
        )

    def test_integration_list_marks_only_release_blocking_tier1_exports(self) -> None:
        with _isolated_test_profile() as profile:
            rows = IntegrationManager(profile).list()
        tiers = {row["name"]: row for row in rows}
        self.assertEqual(
            {name for name, row in tiers.items() if row["support_tier"] == "tier1"},
            set(TIER1_EXPORT_TOOLS),
        )
        self.assertTrue(all(tiers[name]["contract_version"] == "1.0" for name in TIER1_EXPORT_TOOLS))
        self.assertTrue(
            all(
                row["contract_version"] == "unversioned"
                for name, row in tiers.items()
                if name not in TIER1_EXPORT_TOOLS
            )
        )

    def test_integrations_exports_are_deterministic_for_supported_targets(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = IntegrationManager(profile)
        targets = {
            "continue": {
                "chat": "fixture-chat-small",
                "autocomplete": "fixture-code-base",
                "embedding": "fixture-embedding-small",
            },
            "aider": {"model_name": "fixture-analysis-small"},
            "cline": {"model_name": "fixture-analysis-small"},
            "zed": {"model_name": "fixture-analysis-small"},
            "openai-compatible": {"model_name": "fixture-analysis-small"},
            "vscode-mcp": {},
        }
        for tool, kwargs in targets.items():
            with self.subTest(tool=tool):
                first = manager.export(tool, **kwargs)
                second = manager.export(tool, **kwargs)
                self.assertEqual(first.content, second.content)
                self.assertEqual(first.tool, tool)
                self.assertTrue(first.notes)

    def test_integrations_exports_replay_saved_plans_deterministically(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = IntegrationManager(profile)
        continue_plan = manager.plan(
            "continue",
            chat="fixture-chat-small",
            autocomplete="fixture-code-base",
            embedding="fixture-embedding-small",
        )
        first = manager.export_from_plan(continue_plan)
        second = manager.export_from_plan(continue_plan)
        self.assertEqual(first.content, second.content)
        self.assertIn("version: 0.1.0", first.content)
        self.assertIn("schema: v1", first.content)
        self.assertIn("fixture-chat-small", first.content)

        cline_plan = manager.plan("cline", model_name="fixture-analysis-small")
        self.assertEqual(
            manager.export_from_plan(cline_plan).content,
            manager.export_from_plan(cline_plan).content,
        )

    def test_integrations_export_cline_zed_and_aider(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        cline = IntegrationManager(profile).export("cline", "fixture-analysis-small")
        zed = IntegrationManager(profile).export("zed", "fixture-analysis-small")
        aider = IntegrationManager(profile).export("aider", "fixture-analysis-small")
        self.assertEqual(cline.tool, "cline")
        self.assertIn("baseUrl", cline.content)
        self.assertEqual(zed.tool, "zed")
        self.assertIn("assistant", zed.content)
        self.assertEqual(aider.tool, "aider")
        self.assertIn("aider --model openai/provider-text-small:0.5b", aider.content)

    def test_integrations_export_mcp_client_configs(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        vscode = IntegrationManager(profile).export("vscode-mcp", "fixture-analysis-small")
        continue_mcp = IntegrationManager(profile).export("continue-mcp", "fixture-analysis-small")
        generic = IntegrationManager(profile).export("generic-mcp", "fixture-analysis-small")
        self.assertEqual(vscode.tool, "vscode-mcp")
        self.assertIn('"servers"', vscode.content)
        self.assertIn('"aiplane"', vscode.content)
        self.assertIn("mcpServers:", continue_mcp.content)
        self.assertNotIn("--profile", continue_mcp.content)
        self.assertIn('"mcpServers"', generic.content)

    def test_chat_endpoint_dry_run_previews_runtime_agnostic_plan(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        output = IntegrationManager(profile).run_chat(None, prompt="hello", dry_run=True)
        payload = json.loads(output)
        self.assertEqual(payload["name"], "chat_plan")
        self.assertEqual(payload["model"], "fixture-chat-small")
        self.assertEqual(payload["protocol"], "ollama_api")
        self.assertEqual(payload["prompt"], "hello")

    def test_chat_endpoint_executes_openai_compatible_runtime(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with TestHttpServer() as endpoint:
            profile.models["providers"]["vllm"]["enabled"] = True
            profile.models["providers"]["vllm"]["endpoint"] = endpoint
            profile.models["models"]["provider-code-large-vllm"]["enabled"] = True
            profile.models["models"]["provider-code-large-vllm"]["model"] = "test-model"
            output = IntegrationManager(profile).run_chat("provider-code-large-vllm", prompt="hello")
        self.assertEqual(output, "handled test-model")

    def test_chat_native_ollama_opt_in_resolves_ollama_model(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        command = IntegrationManager(profile).run_chat(None, dry_run=True, native_ollama=True)
        self.assertEqual(command, "ollama run provider-chat-small:8b")
        override = IntegrationManager(profile).run_chat("fixture-analysis-small", dry_run=True, native_ollama=True)
        self.assertEqual(override, "ollama run provider-text-small:0.5b")

    def test_chat_native_ollama_opt_in_resolves_huggingface_gguf_for_ollama(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("models", {})["hf-gguf-chat"] = {
            "provider": "llamacpp",
            "source": "huggingface_gguf",
            "model": "Example/Chat-GGUF",
            "enabled": True,
            "supported_runtimes": ["llamacpp", "ollama"],
            "preferred_runtime": "llamacpp",
            "roles": ["chat"],
        }
        command = IntegrationManager(profile).run_chat("hf-gguf-chat", dry_run=True, native_ollama=True)
        self.assertEqual(command, "ollama run hf.co/Example/Chat-GGUF")

    def test_chat_rejects_non_chat_capable_model(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with self.assertRaisesRegex(ValueError, "not suitable for chat execution"):
            IntegrationManager(profile).run_chat("fixture-embedding-small", prompt="hello", dry_run=True)

    def test_managed_provider_alias_exports_continue_config(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["integrations", "export", "continue", "--model", "managed-chat-small"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("provider: openai", output)
        self.assertIn("model: managed-chat-model", output)
        self.assertIn("apiKey: ${OPENAI_API_KEY}", output)

    def test_agents_manifest_and_export_are_versioned_and_render_only(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "agents",
                    "manifest",
                    "repo-helper",
                    "--model",
                    "fixture-analysis-small",
                    "--framework",
                    "langgraph",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["record_type"], "agent_environment")
        self.assertTrue(payload["render_only"])
        self.assertFalse(payload["execution_boundary"]["runs_agents"])
        self.assertEqual(payload["roles"]["primary"]["model_alias"], "fixture-analysis-small")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "agents",
                    "export",
                    "repo-helper",
                    "--model",
                    "fixture-analysis-small",
                    "--file",
                    "agent-environment.json",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn('"record_type": "agent_environment"', stdout.getvalue())
