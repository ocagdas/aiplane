from __future__ import annotations

from .support import (
    ModelCatalog,
    Path,
    RuntimeCatalog,
    StringIO,
    _REAL_LOAD_PROFILE,
    _materialize_test_models,
    agent_config,
    cli_main,
    cli_module,
    create_profile,
    json,
    list_profile_templates,
    load_profile,
    os,
    patch,
    redirect_stdout,
    remove_profile,
    repair_profile,
    subprocess,
    tempfile,
    unittest,
)


class ProfileConfigTests(unittest.TestCase):
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
            original_resource_root = agent_config.resource_root
            original_profiles_root = os.environ.pop("AIPLANE_PROFILES_DIR", None)
            agent_config.project_root = lambda: root
            agent_config.resource_root = lambda: root
            try:
                created = create_profile("custom", template="base")
            finally:
                agent_config.project_root = original_project_root
                agent_config.resource_root = original_resource_root
                if original_profiles_root is not None:
                    os.environ["AIPLANE_PROFILES_DIR"] = original_profiles_root
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
            original_resource_root = agent_config.resource_root
            original_profiles_root = os.environ.pop("AIPLANE_PROFILES_DIR", None)
            agent_config.project_root = lambda: root
            agent_config.resource_root = lambda: root
            try:
                created = create_profile("custom", template="base", profiles_dir=custom_profiles)
                self.assertEqual(agent_config.list_profiles(custom_profiles), ["custom"])
            finally:
                agent_config.project_root = original_project_root
                agent_config.resource_root = original_resource_root
                if original_profiles_root is not None:
                    os.environ["AIPLANE_PROFILES_DIR"] = original_profiles_root
            self.assertEqual(created, custom_profiles / "custom")

    def test_remove_profile_previews_without_yes_and_deletes_with_yes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            profile_path = profiles_dir / "local-dev"

            preview = remove_profile("local-dev", profiles_dir=profiles_dir)

            self.assertTrue(preview["would_remove"])
            self.assertTrue(preview["requires_yes"])
            self.assertFalse(preview["removed"])
            self.assertTrue(profile_path.exists())

            removed = remove_profile("local-dev", profiles_dir=profiles_dir, yes=True)

            self.assertTrue(removed["removed"])
            self.assertFalse(profile_path.exists())

    def test_profiles_remove_cli_previews_and_removes_profile_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            profile_path = profiles_dir / "local-dev"

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "remove",
                        "local-dev",
                    ]
                )

            self.assertEqual(code, 0)
            preview = json.loads(stdout.getvalue())
            self.assertTrue(preview["would_remove"])
            self.assertTrue(profile_path.exists())

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "remove",
                        "local-dev",
                        "--yes",
                    ]
                )

            self.assertEqual(code, 0)
            removed = json.loads(stdout.getvalue())
            self.assertTrue(removed["removed"])
            self.assertFalse(profile_path.exists())

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

    def test_quickstart_local_coding_dry_run_reports_public_flow_without_writes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "quickstart",
                        "local-coding",
                        "--dry-run",
                        "--no-discovery",
                        "--format",
                        "json",
                    ]
                )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(code, 0)
            self.assertEqual(payload["name"], "quickstart_local_coding")
            self.assertTrue(payload["dry_run"])
            self.assertTrue(payload["bootstrap"]["would_create"])
            self.assertFalse((profiles_dir / "local-dev").exists())
            self.assertIn("aiplane quickstart local-coding --name local-dev", payload["commands"])
            self.assertIn("aiplane discover --profile local-dev", payload["commands"])
            self.assertIn("aiplane doctor --profile local-dev", payload["commands"])
            self.assertIn("aiplane recommend --profile local-dev", payload["commands"])
            self.assertIsNone(payload["doctor"])

    def test_quickstart_local_coding_text_lists_next_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "quickstart",
                        "local-coding",
                        "--no-discovery",
                        "--no-hardware-discovery",
                        "--format",
                        "text",
                    ]
                )
            output = stdout.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("local coding quickstart for profile local-dev", output)
            self.assertIn("profile validation: ok", output)
            self.assertIn("aiplane doctor --profile local-dev", output)
            self.assertIn("aiplane export continue --profile local-dev", output)
            self.assertTrue((profiles_dir / "local-dev" / "models.yaml").exists())

    def test_public_onboarding_commands_are_wired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "quickstart",
                            "local-coding",
                            "--no-discovery",
                            "--no-hardware-discovery",
                            "--format",
                            "json",
                        ]
                    ),
                    0,
                )

            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    cli_main(
                        ["--profiles-dir", str(profiles_dir), "discover", "--profile", "local-dev", "--format", "json"]
                    ),
                    0,
                )
            discover = json.loads(stdout.getvalue())
            self.assertEqual(discover["name"], "environment_discovery")
            self.assertIn("provenance", discover)
            self.assertIn("detected_values", discover["provenance"]["summary"])
            self.assertIn("discovered_values", discover["provenance"]["summary"])
            self.assertEqual(discover["next_command"], "aiplane doctor --profile local-dev")

            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    cli_main(["--profiles-dir", str(profiles_dir), "discover", "--profile", "local-dev"]),
                    0,
                )
            discover_text = stdout.getvalue()
            self.assertIn("configuration sources (counted records):", discover_text)
            self.assertIn("built_in=", discover_text)
            self.assertIn("discovered_cache=", discover_text)
            self.assertIn("profile_configured=", discover_text)

            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    cli_main(
                        ["--profiles-dir", str(profiles_dir), "recommend", "--profile", "local-dev", "--format", "json"]
                    ),
                    0,
                )
            recommendation = json.loads(stdout.getvalue())
            self.assertIn("models", recommendation)
            self.assertIn("recommended", recommendation["models"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    cli_main(["--profiles-dir", str(profiles_dir), "export", "vscode-mcp", "--profile", "local-dev"]), 0
                )
            self.assertIn("mcp", stdout.getvalue().lower())

    def test_quickstart_local_coding_pull_model_executes_runtime_pull_by_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            _materialize_test_models(profiles_dir / "local-dev")
            completed = subprocess.CompletedProcess(
                args=["provider_helper"], returncode=0, stdout="pulled\n", stderr=""
            )
            stdout = StringIO()
            with (
                patch("aiplane.cli_public_workflows._run_provider_helper", return_value=completed) as helper,
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "quickstart",
                        "local-coding",
                        "--no-discovery",
                        "--no-hardware-discovery",
                        "--pull-model",
                        "fixture-chat-small",
                        "--format",
                        "json",
                    ]
                )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(code, 0)
            self.assertEqual(payload["pull"]["model"], "fixture-chat-small")
            self.assertEqual(payload["pull"]["runtime"], "ollama")
            self.assertTrue(payload["pull"]["executed"])
            self.assertFalse(payload["pull"]["dry_run"])
            helper.assert_called_once()
            self.assertFalse(helper.call_args.kwargs["dry_run"])
            self.assertEqual(helper.call_args.kwargs["profiles_dir"], profiles_dir)
            self.assertIn(
                "aiplane runtimes pull ollama --model fixture-chat-small",
                payload["commands"],
            )
            self.assertNotIn(
                "aiplane runtimes pull ollama --model fixture-chat-small --dry-run",
                payload["commands"],
            )

    def test_quickstart_local_coding_pull_model_dry_run_previews_runtime_pull(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "quickstart",
                            "local-coding",
                            "--no-discovery",
                            "--no-hardware-discovery",
                        ]
                    ),
                    0,
                )
            _materialize_test_models(profiles_dir / "local-dev")
            completed = subprocess.CompletedProcess(
                args=["provider_helper"],
                returncode=0,
                stdout="dry-run pull\n",
                stderr="",
            )
            stdout = StringIO()
            with (
                patch("aiplane.cli_public_workflows._run_provider_helper", return_value=completed) as helper,
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "quickstart",
                        "local-coding",
                        "--no-discovery",
                        "--no-hardware-discovery",
                        "--pull-model",
                        "fixture-chat-small",
                        "--dry-run",
                        "--format",
                        "json",
                    ]
                )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(code, 0)
            self.assertEqual(payload["pull"]["model"], "fixture-chat-small")
            self.assertEqual(payload["pull"]["runtime"], "ollama")
            self.assertFalse(payload["pull"]["executed"])
            self.assertTrue(payload["pull"]["dry_run"])
            helper.assert_called_once()
            self.assertTrue(helper.call_args.kwargs["dry_run"])
            self.assertEqual(helper.call_args.kwargs["profiles_dir"], profiles_dir)
            self.assertIn(
                "aiplane runtimes pull ollama --model fixture-chat-small --dry-run",
                payload["commands"],
            )

    def test_profiles_bootstrap_local_includes_hardware_discovery(self) -> None:
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
                        "--select-closest-hardware",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["hardware_discovery_requested"])
            self.assertTrue(payload["hardware"]["selected"])

    def test_profiles_bootstrap_local_creates_template_profile_without_discovery(
        self,
    ) -> None:
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
            self.assertEqual(
                ModelCatalog(profile).providers()["ollama"]["origin"],
                "default_runtime_catalog",
            )

    def test_profiles_bootstrap_local_uses_refresh_default_limit_when_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            stdout = StringIO()
            refresh_result = {
                "name": "model_catalog_refresh",
                "changes": {"would_import": 0},
                "results": {"ollama": {"status": "ok", "changes": {}}},
            }
            with (
                patch.object(ModelCatalog, "refresh", return_value=refresh_result) as refresh,
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "bootstrap-local",
                        "--provider",
                        "ollama",
                        "--no-hardware-discovery",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertNotIn("limit", refresh.call_args.kwargs)

    def test_profiles_bootstrap_local_passes_refresh_limit_when_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            stdout = StringIO()
            refresh_result = {
                "name": "model_catalog_refresh",
                "changes": {"would_import": 0},
                "results": {"ollama": {"status": "ok", "changes": {}}},
            }
            with (
                patch.object(ModelCatalog, "refresh", return_value=refresh_result) as refresh,
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "bootstrap-local",
                        "--provider",
                        "ollama",
                        "--limit",
                        "42",
                        "--no-hardware-discovery",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(refresh.call_args.kwargs["limit"], 42)

    def test_profiles_bootstrap_local_preserves_existing_profile_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "profiles",
                            "bootstrap-local",
                            "--no-discovery",
                            "--no-hardware-discovery",
                        ]
                    ),
                    0,
                )
            profile_path = profiles_dir / "local-dev"
            sentinel_path = profile_path / "user-customization.txt"
            sentinel_path.write_text("keep me\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "bootstrap-local",
                        "--no-discovery",
                        "--no-hardware-discovery",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["created"])
            self.assertEqual(sentinel_path.read_text(encoding="utf-8"), "keep me\n")

            with redirect_stdout(StringIO()):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "profiles",
                        "bootstrap-local",
                        "--overwrite",
                        "--no-discovery",
                        "--no-hardware-discovery",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertFalse(sentinel_path.exists())
