from __future__ import annotations

from .support import (
    Path,
    StringIO,
    agent_config,
    cli_main,
    default_profile,
    init_local_config,
    json,
    list_config_templates,
    load_local_config,
    load_profile,
    os,
    patch,
    redirect_stdout,
    resolve_profile_name,
    set_default_profile,
    shutil,
    tempfile,
    unittest,
)


class LocalConfigTests(unittest.TestCase):
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
