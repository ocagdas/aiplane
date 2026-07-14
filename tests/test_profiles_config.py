from __future__ import annotations

from .support import (
    ModelCatalog,
    Path,
    PolicyEngine,
    RuntimeCatalog,
    StringIO,
    _REAL_LOAD_PROFILE,
    _materialize_test_models,
    agent_config,
    cli_main,
    cli_module,
    contains_secret,
    create_profile,
    default_profile,
    init_local_config,
    json,
    list_config_templates,
    list_profile_templates,
    load_local_config,
    load_profile,
    os,
    patch,
    redact,
    redirect_stdout,
    remove_profile,
    repair_profile,
    resolve_profile_name,
    set_default_profile,
    shutil,
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
            completed = cli_module.subprocess.CompletedProcess(
                args=["provider_helper"], returncode=0, stdout="pulled\n", stderr=""
            )
            stdout = StringIO()
            with (
                patch("aiplane.cli._run_provider_helper", return_value=completed) as helper,
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
            completed = cli_module.subprocess.CompletedProcess(
                args=["provider_helper"],
                returncode=0,
                stdout="dry-run pull\n",
                stderr="",
            )
            stdout = StringIO()
            with (
                patch("aiplane.cli._run_provider_helper", return_value=completed) as helper,
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
            with patch.dict(os.environ, {"AIPLANE_PROFILES_DIR": ""}):
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

    def test_config_format_cli_can_set_and_show_global_and_profile_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("format: text\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "format", "--path", str(config_path)])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIsNone(payload["profile"])
            self.assertIsNone(payload["command"])
            self.assertEqual(payload["format"], "text")
            self.assertEqual(payload["resolved_format"], "text")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "format", "json", "--path", str(config_path)])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["format"], "json")
            self.assertEqual(payload["resolved_format"], "json")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "format",
                        "json",
                        "--profile",
                        "local-dev",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["profile"], "local-dev")
            self.assertIsNone(payload["command"])
            self.assertEqual(payload["profile_format"], "json")
            self.assertIsNone(payload["command_format"])
            self.assertEqual(payload["resolved_format"], "json")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "format",
                        "text",
                        "--command",
                        "models list",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIsNone(payload["profile"])
            self.assertEqual(payload["command"], "models list")
            self.assertEqual(payload["command_format"], "text")
            self.assertEqual(payload["resolved_format"], "text")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "format", "--clear", "--path", str(config_path)])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["format"], "text")
            self.assertIsNone(payload["profile"])
            self.assertIsNone(payload["command"])
            self.assertEqual(payload["resolved_format"], "text")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "format",
                        "--clear",
                        "--profile",
                        "local-dev",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIsNone(payload["profile_format"])
            self.assertEqual(payload["resolved_format"], "text")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "format",
                        "--clear",
                        "--command",
                        "models list",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIsNone(payload["command_format"])
            self.assertEqual(payload["resolved_format"], "text")

    def test_config_verbosity_cli_can_set_and_show_global_profile_and_command_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("verbosity: 0\n", encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "verbosity", "--path", str(config_path)])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIsNone(payload["profile"])
            self.assertIsNone(payload["command"])
            self.assertEqual(payload["verbosity"], 0)
            self.assertEqual(payload["resolved_verbosity"], 0)

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "verbosity", "1", "--path", str(config_path)])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["verbosity"], 1)
            self.assertEqual(payload["resolved_verbosity"], 1)

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "verbosity",
                        "2",
                        "--profile",
                        "local-dev",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["profile"], "local-dev")
            self.assertEqual(payload["profile_verbosity"], 2)
            self.assertIsNone(payload["command_verbosity"])
            self.assertEqual(payload["resolved_verbosity"], 2)

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "verbosity",
                        "1",
                        "--command",
                        "models list",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["command"], "models list")
            self.assertEqual(payload["command_verbosity"], 1)
            self.assertEqual(payload["resolved_verbosity"], 1)

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["config", "verbosity", "--clear", "--path", str(config_path)])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["verbosity"], 0)
            self.assertIsNone(payload["profile"])
            self.assertIsNone(payload["command"])
            self.assertEqual(payload["resolved_verbosity"], 0)

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "verbosity",
                        "--clear",
                        "--profile",
                        "local-dev",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIsNone(payload["profile_verbosity"])
            self.assertEqual(payload["resolved_verbosity"], 0)

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "config",
                        "verbosity",
                        "--clear",
                        "--command",
                        "models list",
                        "--path",
                        str(config_path),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIsNone(payload["command_verbosity"])
            self.assertEqual(payload["resolved_verbosity"], 0)

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
        self.assertIn("Primary workflow", output)
        self.assertIn("Configure, check, and connect", output)
        self.assertIn("aiplane discover", output)
        self.assertIn("aiplane quickstart local-coding", output)
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
