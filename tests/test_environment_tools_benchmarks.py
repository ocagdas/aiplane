from __future__ import annotations

from contextlib import contextmanager

import aiplane.tools as tools_module
from aiplane.cli_presenters import _environment_doctor_text
from aiplane.platform_support import HostPlatform
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
    patch,
    redirect_stderr,
    redirect_stdout,
    shutil,
    tempfile,
    unittest,
)


class EnvironmentToolBenchmarkTests(unittest.TestCase):
    @staticmethod
    def _synthetic_fixture_payload() -> dict[str, object]:
        fixture_path = Path(__file__).parent / "fixtures" / "toolchain-synthetic.json"
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    @contextmanager
    def _synthetic_toolchain(self):
        payload = self._synthetic_fixture_payload()
        tools = payload["tools"]
        runtime_prerequisites = payload["runtime_prerequisites"]
        if not isinstance(tools, list) or not isinstance(runtime_prerequisites, list):
            self.fail("synthetic toolchain fixture is malformed")
        tool_rows = {str(row["name"]): row for row in tools if isinstance(row, dict) and row.get("name")}
        self.assertEqual(set(tool_rows), set(tools_module.TOOLCHAIN))

        def _fake_tool_row(_manager, name: str) -> dict[str, object]:
            return dict(tool_rows[name])

        with (
            patch.object(tools_module.ToolchainManager, "_tool_row", autospec=True, side_effect=_fake_tool_row),
            patch.object(tools_module, "_runtime_prerequisite_rows", autospec=True, return_value=runtime_prerequisites),
        ):
            yield

    def test_synthetic_tool_fixture_matches_toolchain_shape(self) -> None:
        payload = self._synthetic_fixture_payload()
        tools = payload["tools"]
        self.assertIsInstance(tools, list)
        names = {row["name"] for row in tools if isinstance(row, dict)}
        self.assertEqual(names, set(tools_module.TOOLCHAIN))
        required_keys = {
            "name",
            "category",
            "description",
            "needed_for",
            "requirement",
            "command",
            "installed",
            "path",
            "version",
            "health",
            "install_mode",
            "installable_by_aiplane",
            "install_commands",
        }
        for row in tools:
            if not isinstance(row, dict):
                self.fail("synthetic toolchain fixture contains a non-object row")
            self.assertTrue(required_keys.issubset(set(row)))

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
                        "--yes",
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
        with self._synthetic_toolchain(), redirect_stdout(stdout):
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
        with self._synthetic_toolchain(), redirect_stdout(stdout):
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

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["tools", "export", "packer"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("sensitive = true", output)
        self.assertIn("ssh_password  = var.ssh_password", output)
        self.assertNotIn('ssh_password  = "ubuntu"', output)

    def test_environment_doctor_cli_groups_installable_tools(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with self._synthetic_toolchain(), redirect_stdout(stdout), redirect_stderr(stderr):
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
                        "schema_version": "1.0",
                        "name": "custom-code",
                        "version": "1.0",
                        "kind": "quality",
                        "allow_command_evaluators": True,
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
                "fixture-analysis-small",
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


def test_workflow_matrix_treats_iac_tools_as_alternatives() -> None:
    profile = load_profile("local-dev", Path.cwd())

    def fake_row(_manager, name: str) -> dict[str, object]:
        return {
            "name": name,
            "category": "fixture",
            "needed_for": [],
            "requirement": "optional",
            "installed": name in {"azure-cli", "openssh-client", "opentofu"},
            "install_mode": "manual",
            "installable_by_aiplane": False,
        }

    with patch.object(tools_module.ToolchainManager, "_tool_row", autospec=True, side_effect=fake_row):
        payload = tools_module.ToolchainManager(profile).matrix("cloud_vm")
    assert payload["summary"]["tools"] == 7
    assert {row["name"] for category in payload["categories"] for row in category["tools"]} == {
        "azure-cli",
        "openssh-client",
        "opentofu",
        "terraform",
        "pulumi",
        "packer",
        "ansible",
    }
    workflow = payload["task_workflows"][0]
    assert workflow["readiness"] == "ready"
    assert workflow["required_any_of"] == [["opentofu", "terraform", "pulumi"]]
    assert workflow["unsatisfied_alternatives"] == []
    requirements = {row["name"]: row["requirement"] for row in workflow["tools"]}
    assert requirements["azure-cli"] == "mandatory"
    assert requirements["opentofu"] == "alternative"
    assert requirements["packer"] == "optional"


def test_environment_doctor_can_focus_on_one_workflow() -> None:
    profile = load_profile("local-dev", Path.cwd())

    def fake_row(_manager, name: str) -> dict[str, object]:
        return {
            "name": name,
            "category": "fixture",
            "description": name,
            "needed_for": [],
            "requirement": "optional",
            "installed": True,
            "install_mode": "manual",
            "installable_by_aiplane": False,
        }

    with (
        patch.object(tools_module.ToolchainManager, "_tool_row", autospec=True, side_effect=fake_row),
        patch.object(tools_module, "_runtime_prerequisite_rows", return_value=[]),
    ):
        payload = tools_module.ToolchainManager(profile).environment_doctor(
            workflow="cloud_kubernetes",
            include_optional=False,
        )
    assert payload["workflow"] == "cloud_kubernetes"
    assert payload["workflow_readiness"]["readiness"] == "ready"
    checked = {row["name"] for row in payload["installed"]}
    assert checked == {"azure-cli", "kubectl", "opentofu", "terraform", "pulumi"}
    assert "helm" not in checked


def _runtime_workflow_row(runtime: str, usable: bool) -> dict[str, object]:
    return {
        "runtime": runtime,
        "known_runtime": True,
        "ok": usable,
        "available": usable,
        "usable": usable,
        "platform_compatible": True,
        "missing_required": [],
        "missing_optional": [],
        "notes": [],
        "availability": {"available": usable, "reason": "fixture"},
    }


def test_local_runtime_workflow_requires_at_least_one_usable_runner() -> None:
    profile = load_profile("local-dev", Path.cwd())
    manager = tools_module.ToolchainManager(profile)
    unavailable = [_runtime_workflow_row(name, False) for name in ["ollama", "llamacpp", "mlx"]]
    with patch.object(tools_module, "_runtime_prerequisite_rows", return_value=unavailable):
        payload = manager.environment_doctor(workflow="local_runtime", include_optional=False)
    readiness = payload["workflow_readiness"]
    assert readiness["readiness"] == "needs_setup"
    assert readiness["usable_runtimes"] == []
    assert "workflow local_runtime: needs_setup" in _environment_doctor_text(payload)

    available = [*unavailable, _runtime_workflow_row("vllm", True)]
    with patch.object(tools_module, "_runtime_prerequisite_rows", return_value=available):
        payload = manager.environment_doctor(workflow="local_runtime", include_optional=False)
    readiness = payload["workflow_readiness"]
    assert readiness["readiness"] == "ready"
    assert readiness["usable_runtimes"] == ["vllm"]
    text = _environment_doctor_text(payload)
    assert "workflow local_runtime: ready" in text
    assert "usable runtimes: vllm" in text


def test_required_only_workflow_does_not_probe_optional_tools() -> None:
    profile = load_profile("local-dev", Path.cwd())
    probed = []

    def fake_row(_manager, name: str) -> dict[str, object]:
        probed.append(name)
        return {
            "name": name,
            "category": "fixture",
            "description": name,
            "needed_for": [],
            "requirement": "optional",
            "installed": True,
            "install_mode": "manual",
            "installable_by_aiplane": False,
        }

    with (
        patch.object(tools_module.ToolchainManager, "_tool_row", autospec=True, side_effect=fake_row),
        patch.object(tools_module, "_runtime_prerequisite_rows", return_value=[]),
    ):
        tools_module.ToolchainManager(profile).environment_doctor(
            workflow="cloud_vm",
            include_optional=False,
        )
    assert set(probed) == {"azure-cli", "openssh-client", "opentofu", "terraform", "pulumi"}
    assert "packer" not in probed
    assert "ansible" not in probed


def test_runtime_prerequisites_can_skip_optional_tool_probes() -> None:
    profile = load_profile("local-dev", Path.cwd())
    with patch("aiplane.runtime_catalog.shutil.which", return_value=None) as which:
        payload = tools_module.RuntimeCatalog(profile).prerequisites("vllm", include_optional=False)
    assert payload["optional_tools"] == []
    assert payload["missing_optional"] == []
    assert "nvidia-smi" not in [call.args[0] for call in which.call_args_list]


def test_local_runtime_rows_reject_mlx_on_non_apple_platforms() -> None:
    profile = load_profile("local-dev", Path.cwd())

    class Catalog:
        def prerequisites(self, runtime: str, *, include_optional: bool = True) -> dict[str, object]:
            return {
                "known_runtime": True,
                "ok": True,
                "missing_required": [],
                "missing_optional": [],
                "notes": [],
            }

        def runtime_available(self, runtime: str) -> dict[str, object]:
            return {"available": True, "reason": "fixture endpoint is reachable"}

    linux = HostPlatform("Linux", "ubuntu", (), "x86_64")
    with (
        patch.object(tools_module, "RuntimeCatalog", return_value=Catalog()),
        patch.object(tools_module, "detect_host_platform", return_value=linux),
    ):
        row = tools_module._runtime_prerequisite_rows(profile, False, runtimes=["mlx"])[0]
    assert row["platform_compatible"] is False
    assert row["available"] is True
    assert row["usable"] is False


def test_docker_model_runner_requires_a_functional_docker_model_surface() -> None:
    profile = load_profile("local-dev", Path.cwd())

    class Catalog:
        def prerequisites(self, runtime: str, *, include_optional: bool = True) -> dict[str, object]:
            return {
                "known_runtime": True,
                "ok": True,
                "missing_required": [],
                "missing_optional": [],
                "notes": [],
            }

        def runtime_available(self, runtime: str) -> dict[str, object]:
            return {"available": True, "reason": "fixture endpoint is reachable"}

    class DockerModels:
        def __init__(self, command_runner=None):
            pass

        def run(self, action: str):
            return {
                "available": False,
                "reason": "this Docker installation does not provide the docker model command",
            }, 2

    with (
        patch.object(tools_module, "RuntimeCatalog", return_value=Catalog()),
        patch.object(tools_module, "DockerModelRunner", DockerModels),
    ):
        row = tools_module._runtime_prerequisite_rows(
            profile,
            False,
            runtimes=["docker_model_runner"],
        )[0]
    assert row["available"] is False
    assert row["usable"] is False
    assert "does not provide" in row["availability"]["reason"]
