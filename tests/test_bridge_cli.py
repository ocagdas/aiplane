from __future__ import annotations

from .support import (
    StringIO,
    cli_main,
    json,
    patch,
    redirect_stderr,
    redirect_stdout,
    subprocess,
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
            patch("aiplane.cli.shutil.which", return_value="/usr/bin/ollama"),
            patch(
                "aiplane.cli.subprocess.run",
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
