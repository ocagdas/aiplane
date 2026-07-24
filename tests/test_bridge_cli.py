from __future__ import annotations

from types import SimpleNamespace

from aiplane.cli_launch_support import _launch_plan

from .support import (
    AuditLogger,
    Path,
    StringIO,
    _isolated_profiles_dir,
    cli_main,
    json,
    load_profile,
    os,
    redirect_stderr,
    patch,
    redirect_stdout,
    subprocess,
    tempfile,
    unittest,
)


class BridgeCliTests(unittest.TestCase):
    def test_bridge_list_shows_allowlisted_actions(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["bridge", "list"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        actions = {row["action"] for row in payload["actions"]}
        self.assertIn("ollama-launch", actions)
        self.assertIn("ollama-run", actions)

    def test_bridge_exec_dry_run_renders_ollama_run_command(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "bridge",
                    "exec",
                    "ollama-run",
                    "--model",
                    "llama3.1:8b",
                    "--prompt",
                    "Say hello",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["command"], ["ollama", "run", "llama3.1:8b", "Say hello"])

    def test_bridge_exec_runs_allowlisted_command(self) -> None:
        stdout = StringIO()
        with (
            patch("aiplane.cli_execution.shutil.which", return_value="/usr/bin/ollama"),
            patch(
                "aiplane.boundaries.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=["ollama", "list"],
                    returncode=0,
                    stdout="MODEL\n",
                    stderr="",
                ),
            ) as run,
            redirect_stdout(stdout),
        ):
            code = cli_main(["bridge", "exec", "ollama-list"])
        self.assertEqual(code, 0)
        run.assert_called_once()
        self.assertIn("MODEL", stdout.getvalue())

    def test_bridge_exec_rejects_disallowed_parameters(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            code = cli_main(["bridge", "exec", "ollama-launch", "--model", "llama3.1:8b"])
        self.assertEqual(code, 1)
        self.assertIn("does not accept --model", stderr.getvalue())

    def test_launch_dry_run_generates_continue_command(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["launch", "--tool", "continue", "--model", "fixture-chat-small", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "launch_plan")
        self.assertEqual(payload["tool"], "continue")
        self.assertEqual(payload["command"], ["continue"])
        self.assertEqual(payload["selection"]["name"], "fixture-chat-small")

    def test_launch_dry_run_generates_codex_oss_command(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["launch", "--tool", "codex", "--model", "fixture-chat-small", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "codex")
        self.assertEqual(
            payload["command"],
            ["codex", "--oss", "--local-provider", "ollama", "--model", "provider-chat-small:8b"],
        )

    def test_launch_codex_rejects_non_oss_runtime(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["vllm"]["supported_apis"] = ["responses"]
        profile.models["models"]["provider-code-large-vllm"]["enabled"] = True
        with self.assertRaisesRegex(ValueError, "built-in local OSS providers"):
            _launch_plan(profile, "codex", model="provider-code-large-vllm")

    def test_launch_codex_rejects_remote_ollama_endpoint(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["ollama"]["endpoint"] = "http://remote.example:11434/v1"
        with self.assertRaisesRegex(ValueError, "loopback endpoints"):
            _launch_plan(profile, "codex", model="fixture-chat-small")

    def test_launch_dry_run_generates_ollama_launch_command(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "launch",
                    "--tool",
                    "ollama",
                    "--model",
                    "fixture-chat-small",
                    "--app",
                    "vscode",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "ollama")
        self.assertEqual(payload["command"], ["ollama", "launch", "provider-chat-small:8b", "--app", "vscode"])

    def test_launch_dry_run_generates_aider_command_with_api_base(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["launch", "--tool", "aider", "--model", "fixture-chat-small", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "aider")
        self.assertEqual(payload["command"], ["aider", "--model", "openai/provider-chat-small:8b"])
        self.assertEqual(payload["env"]["OPENAI_API_BASE"], "http://localhost:11434/v1")

    def test_launch_exec_runs_plan_command(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            with _isolated_profiles_dir("local-dev") as profiles_dir:
                with patch.dict(
                    os.environ,
                    {"AIPLANE_PROFILES_DIR": str(profiles_dir)},
                ):
                    stdout = StringIO()
                    with (
                        patch("aiplane.cli_execution.shutil.which", return_value="/usr/bin/continue"),
                        patch(
                            "aiplane.boundaries.subprocess.run",
                            return_value=subprocess.CompletedProcess(
                                args=["continue"], returncode=0, stdout="ok\n", stderr=""
                            ),
                        ) as run,
                        redirect_stdout(stdout),
                    ):
                        code = cli_main(
                            [
                                "--workspace",
                                workspace,
                                "launch",
                                "--tool",
                                "continue",
                                "--model",
                                "fixture-chat-small",
                            ]
                        )
        self.assertEqual(code, 0)
        run.assert_called_once()
        called = run.call_args.kwargs
        self.assertEqual(called["cwd"], Path(workspace))
        self.assertEqual(called["env"], None)
        self.assertEqual(called["text"], True)
        self.assertIn("ok", stdout.getvalue())
        self.assertEqual(called["check"], False)

    def test_launch_exec_reports_missing_executable(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            with _isolated_profiles_dir("local-dev") as profiles_dir:
                with patch.dict(
                    os.environ,
                    {"AIPLANE_PROFILES_DIR": str(profiles_dir)},
                ):
                    stdout = StringIO()
                    with (
                        patch("aiplane.cli_execution.shutil.which", return_value=None),
                        patch("aiplane.boundaries.subprocess.run") as run,
                        redirect_stdout(stdout),
                    ):
                        code = cli_main(
                            [
                                "--workspace",
                                workspace,
                                "launch",
                                "--tool",
                                "continue",
                                "--model",
                                "fixture-chat-small",
                            ]
                        )
                    run.assert_not_called()
                    payload = json.loads(stdout.getvalue())
                    self.assertEqual(code, 2)
                    self.assertIn("required executable not found", payload["reason"])

    def test_session_start_dry_run_preview(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            with _isolated_profiles_dir("local-dev") as profiles_dir:
                with patch.dict(
                    os.environ,
                    {"AIPLANE_PROFILES_DIR": str(profiles_dir)},
                ):
                    stdout = StringIO()
                    with redirect_stdout(stdout):
                        code = cli_main(
                            [
                                "--workspace",
                                workspace,
                                "session",
                                "start",
                                "--tool",
                                "continue",
                                "--model",
                                "fixture-chat-small",
                                "--dry-run",
                            ]
                        )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "session_start")
        self.assertEqual(payload["tool"], "continue")
        self.assertEqual(payload["model"], "fixture-chat-small")

    def test_session_start_codex_dry_run_keeps_oss_command_metadata(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["session", "start", "--tool", "codex", "--model", "fixture-chat-small", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["tool"], "codex")
        self.assertEqual(
            payload["launch"]["command"],
            ["codex", "--oss", "--local-provider", "ollama", "--model", "provider-chat-small:8b"],
        )

    def test_session_start_writes_record_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            with _isolated_profiles_dir("local-dev") as profiles_dir:
                with (
                    patch.dict(os.environ, {"AIPLANE_PROFILES_DIR": str(profiles_dir)}),
                    patch(
                        "aiplane.cli_launch_support.uuid.uuid4", return_value=SimpleNamespace(hex="session1234567890")
                    ),
                ):
                    stdout = StringIO()
                    with redirect_stdout(stdout):
                        code = cli_main(
                            [
                                "--workspace",
                                workspace,
                                "session",
                                "start",
                                "--tool",
                                "ollama",
                                "--model",
                                "fixture-chat-small",
                                "--app",
                                "vscode",
                            ]
                        )
                    self.assertEqual(code, 0)
                    payload = json.loads(stdout.getvalue())
                    record_path = Path(payload["record"])
                    self.assertTrue(record_path.exists())
                    session_record = json.loads(record_path.read_text(encoding="utf-8"))
                    self.assertEqual(session_record["session_id"], "session1234567890")
                    self.assertEqual(session_record["model"], "fixture-chat-small")
                    profile = load_profile("local-dev", Path(workspace), profiles_dir=profiles_dir)
                    events = AuditLogger(profile).tail(1)
                    self.assertEqual(events[-1]["event_type"], "session")
                    self.assertEqual(events[-1]["action"], "session.start")
                    self.assertEqual(events[-1]["details"]["session_id"], "session1234567890")
                    self.assertEqual(
                        events[-1]["details"]["command"],
                        ["ollama", "launch", "provider-chat-small:8b", "--app", "vscode"],
                    )
