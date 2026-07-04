from __future__ import annotations

from .support import (
    ApprovalHandler,
    AuditLogger,
    BenchmarkRunner,
    EnvironmentManager,
    Path,
    Profile,
    StringIO,
    ToolExecutor,
    cli_main,
    json,
    load_profile,
    redirect_stderr,
    redirect_stdout,
    shutil,
    tempfile,
    unittest,
)


class EnvironmentToolBenchmarkTests(unittest.TestCase):
    def test_tool_command_accepts_passthrough_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(
                Path.cwd() / "profile-templates" / "local-dev",
                profiles_dir / "local-dev",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--workspace",
                        str(workspace),
                        "--profiles-dir",
                        str(profiles_dir),
                        "tool",
                        "--profile",
                        "local-dev",
                        "run_tests",
                        "python",
                        "-c",
                        "print('ok')",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertIn("ok", stdout.getvalue())

    def test_tool_read_and_write_with_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = load_profile("local-dev", workspace)
            executor = ToolExecutor(profile, AuditLogger(profile), ApprovalHandler(assume_yes=True))
            executor.run("write_file", ["note.txt", "hello"])
            self.assertEqual(executor.run("read_file", ["note.txt"]), "hello")

    def test_environment_system_plan(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.environment["active"] = "system"
        plan = EnvironmentManager(profile).plan(["python", "-m", "unittest"])
        self.assertEqual(plan.mode, "system")
        self.assertEqual(plan.command, ["python", "-m", "unittest"])

    def test_environment_lists_and_switches_active_mode(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "environment.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=json.loads(json.dumps(source.environment)),
                models=source.models,
                targets=source.targets,
            )
            manager = EnvironmentManager(profile)
            rows = manager.list_modes()
            self.assertIn("system", {row["name"] for row in rows})
            result = manager.use("venv")
            self.assertEqual(result["active"], "venv")
            self.assertIn("active: venv", (root / "environment.yaml").read_text(encoding="utf-8"))
            self.assertEqual(manager.active_mode(), "venv")

    def test_environment_use_rejects_unknown_mode(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with self.assertRaises(ValueError):
            EnvironmentManager(profile).use("missing")

    def test_environment_docker_resource_plan(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.environment["active"] = "docker"
        profile.environment["modes"]["docker"]["cpus"] = 4
        profile.environment["modes"]["docker"]["memory"] = "8g"
        profile.environment["modes"]["docker"]["gpus"] = "all"
        profile.environment["modes"]["docker"]["devices"] = ["/dev/dri"]
        plan = EnvironmentManager(profile).plan(["python", "-V"])
        self.assertIn("--cpus", plan.command)
        self.assertIn("--memory", plan.command)
        self.assertIn("--gpus", plan.command)
        self.assertIn("--device", plan.command)
        self.assertIn("/dev/dri", plan.command)

    def test_audit_log_is_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            audit = AuditLogger(profile)
            ToolExecutor(profile, audit, ApprovalHandler(assume_yes=True)).run("write_file", ["audit.txt", "ok"])
            events = audit.tail(1)
            self.assertEqual(events[0]["event_type"], "tool")
            json.dumps(events[0])

    def test_tools_doctor_and_install_dry_run_cli(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "doctor", "openssh-client"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "tools_doctor")
        self.assertEqual(payload["tools"][0]["name"], "openssh-client")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "install", "openssh-client", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "openssh-client")
        self.assertTrue(payload["dry_run"])
        self.assertIn("commands", payload)

    def test_tools_doctor_includes_vm_and_provider_agnostic_iac_tools(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "doctor"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        tools = {row["name"]: row for row in payload["tools"]}
        for name in [
            "opentofu",
            "terraform",
            "pulumi",
            "vagrant",
            "packer",
            "devcontainer-cli",
            "ruff",
            "black",
        ]:
            self.assertIn(name, tools)
            self.assertEqual(tools[name]["requirement"], "optional")
        self.assertEqual(tools["opentofu"]["category"], "iac")
        self.assertEqual(tools["pulumi"]["category"], "iac")
        self.assertEqual(tools["vagrant"]["category"], "vm")
        self.assertEqual(tools["packer"]["category"], "image-build")
        self.assertEqual(tools["devcontainer-cli"]["category"], "container")
        self.assertEqual(tools["ruff"]["category"], "quality")
        self.assertEqual(tools["black"]["category"], "quality")

    def test_tools_matrix_cli_groups_tasks_and_capabilities(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "matrix"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "tools_matrix")
        self.assertIn("summary", payload)
        self.assertGreaterEqual(payload["summary"]["mandatory"], 2)
        self.assertIn("workflows", payload)
        self.assertIn("workflows", payload["summary"])
        self.assertIn("workflows_complete", payload["summary"])
        self.assertIn("workflows_partial", payload["summary"])
        self.assertIn("workflows_needing_setup", payload["summary"])
        categories = {category["name"]: category for category in payload["categories"]}
        workflows = {workflow["name"]: workflow for workflow in payload["workflows"]}
        self.assertIn("iac", categories)
        self.assertIn("quality", categories)
        self.assertIn("iac", workflows)
        self.assertIn("quality", workflows)
        self.assertEqual(workflows["iac"]["tools"], len(categories["iac"]["tools"]))
        quality_tools = {tool["name"]: tool for tool in categories["quality"]["tools"]}
        self.assertIn("ruff", quality_tools)
        self.assertIn("black", quality_tools)
        self.assertIn(workflows["iac"]["readiness"], {"complete", "partial", "needs_setup"})
        self.assertIn(
            "provider-agnostic infrastructure provisioning",
            workflows["iac"]["primary_tasks"],
        )
        self.assertIn("missing_tools", workflows["iac"])
        iac_tools = {tool["name"]: tool for tool in categories["iac"]["tools"]}
        self.assertTrue(iac_tools["opentofu"]["plan_available"])
        self.assertTrue(iac_tools["opentofu"]["export_available"])
        self.assertEqual(iac_tools["opentofu"]["requirement"], "optional")
        remote_tools = {tool["name"]: tool for tool in categories["remote"]["tools"]}
        self.assertEqual(remote_tools["openssh-client"]["requirement"], "mandatory")
        self.assertIn("SSH tunnels", remote_tools["openssh-client"]["needed_for"])
        self.assertEqual(workflows["remote"]["mandatory"], 1)

    def test_tools_plan_and_export_cli_are_non_mutating_starters(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "plan", "vagrant"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "tools_plan")
        self.assertEqual(payload["tool"], "vagrant")
        self.assertIn("Vagrantfile", payload["artifacts"])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "export", "opentofu"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("terraform {", output)
        self.assertIn("tofu plan", output)

    def test_environment_doctor_cli_groups_installable_tools(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main(["environment", "doctor", "--required-only", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("checking tool", stderr.getvalue())
        self.assertIn("\r", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "environment_doctor")
        self.assertIn("summary", payload)
        self.assertIn("active_environment", payload)
        self.assertIn("missing_installable_by_aiplane", payload)
        self.assertIn("runtime_prerequisites", payload)
        self.assertIn("runtime_prerequisites_checked", payload["summary"])
        runtimes = {row["runtime"]: row for row in payload["runtime_prerequisites"]}
        self.assertIn("ollama", runtimes)
        self.assertIn("vllm", runtimes)
        self.assertIn("purpose", runtimes["ollama"])
        self.assertIn(
            "aiplane runtimes prerequisites ollama",
            runtimes["ollama"]["setup_commands"],
        )

    def test_environment_plan_cli_outputs_execution_plan(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["environment", "plan", "python", "--version"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("mode", payload)
        self.assertIn("command", payload)
        self.assertIn("cwd", payload)
        self.assertIn("description", payload)
        self.assertNotIn("notes", payload)

    def test_environment_doctor_text_format_outputs_human_table(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["environment", "doctor", "--required-only"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("environment doctor for profile", output)
        self.assertIn("NAME", output)
        self.assertIn("TYPE", output)
        self.assertIn("STATUS", output)
        self.assertIn("REQUIRED", output)
        self.assertIn("WHY", output)
        self.assertIn("mandatory", output)
        self.assertIn("runtime", output)
        tool_lines = [line for line in output.splitlines() if "  tool" in line]
        mandatory_indexes = [index for index, line in enumerate(tool_lines) if " mandatory" in line]
        optional_indexes = [index for index, line in enumerate(tool_lines) if " optional" in line]
        if mandatory_indexes and optional_indexes:
            self.assertLess(max(mandatory_indexes), min(optional_indexes))
        for indexes in [mandatory_indexes, optional_indexes]:
            installed_indexes = [index for index in indexes if " installed" in tool_lines[index]]
            missing_indexes = [index for index in indexes if " missing" in tool_lines[index]]
            if installed_indexes and missing_indexes:
                self.assertLess(max(installed_indexes), min(missing_indexes))

    def test_benchmark_framework_cli_plans_and_install_dry_run(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["benchmarks", "doctor", "aiplane-smoke"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "benchmark_tools_doctor")
        self.assertTrue(payload["frameworks"][0]["available"])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["benchmarks", "install", "lm-evaluation-harness", "--dry-run"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "lm-evaluation-harness")
        self.assertTrue(payload["dry_run"])
        self.assertIn("lm_eval", payload["commands"][0])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "benchmarks",
                    "plan",
                    "vllm-serving",
                    "--model",
                    "local-code-large",
                    "--endpoint",
                    "http://localhost:8000/v1",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "vllm-serving")
        self.assertEqual(payload["commands"][1]["command"][0:3], ["vllm", "bench", "serve"])

    def test_custom_benchmark_spec_dry_run_plans_evaluator_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "bench.json"
            spec.write_text(
                json.dumps(
                    {
                        "name": "custom-code",
                        "tasks": {
                            "unit": {
                                "prompt": "Write a Python function.",
                                "expected_terms": ["def"],
                                "evaluator": {
                                    "command": [
                                        "python",
                                        "-c",
                                        'print(\'{\\"score\\": 77, \\"passed\\": true}\')',
                                    ]
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            profile = load_profile("local-dev", Path.cwd())
            result = BenchmarkRunner(profile).run(
                "local-analysis-small",
                task="unit",
                dry_run=True,
                save=False,
                spec_path=spec,
                environment_mode="system",
            )
        self.assertEqual(result["name"], "custom-code")
        self.assertEqual(result["environment_mode"], "system")
        self.assertEqual(result["results"][0]["evaluation"]["type"], "command")
        self.assertIn("command", result["results"][0]["evaluation"])
