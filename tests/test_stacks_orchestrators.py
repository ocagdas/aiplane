from __future__ import annotations

from .support import (
    MachineManager,
    OrchestratorCatalog,
    Path,
    Profile,
    StackManager,
    StringIO,
    agent_config,
    cli_main,
    json,
    load_profile,
    parse_yaml,
    patch,
    redirect_stdout,
    shutil,
    tempfile,
    unittest,
)


class StackOrchestratorTests(unittest.TestCase):
    def test_stack_deploy_same_host_executes_mutating_steps(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.create(
                "local_chat_stack",
                "fixture-analysis-small",
                "ollama",
                "local_box",
                access="same_host",
            )

            class Completed:
                returncode = 0
                stdout = "ok"
                stderr = ""

            with patch("aiplane.stacks.subprocess.run", return_value=Completed()) as run:
                result = stacks.deploy("local_chat_stack", yes=True)
            self.assertEqual(result["status"], "executed_same_host_steps")
            self.assertEqual(run.call_count, 3)

    def test_stack_create_plan_doctor_and_export(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            MachineManager(profile).import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            stacks = StackManager(profile)
            created = stacks.create(
                "code_on_gpu",
                "local-code-large",
                "vllm",
                "azure_h100_test",
                endpoint="http://localhost:8000/v1",
            )
            self.assertEqual(created["stack"]["runtime"], "vllm")
            plan = stacks.plan("code_on_gpu")
            self.assertEqual(plan["machine"], "azure_h100_test")
            self.assertEqual(plan["model"], "local-code-large")
            self.assertIn("preflight", plan)
            self.assertTrue(any(check["name"] == "runtime_prerequisites" for check in plan["preflight"]["checks"]))
            self.assertTrue(any(check["name"].startswith("port_available:") for check in plan["preflight"]["checks"]))
            doctor = stacks.doctor("code_on_gpu")
            self.assertTrue(any(check["name"] == "machine_fit" for check in doctor["checks"]))
            self.assertTrue(any(check["name"] == "runtime_prerequisites" for check in doctor["checks"]))
            exported = stacks.export("openai-compatible", "code_on_gpu")
            self.assertEqual(exported["endpoint"], "http://localhost:8000/v1")

    def test_orchestrators_are_catalog_only_in_cli(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["orchestrators", "list"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload[0]["name"], "langgraph")
        self.assertIn("ollama", payload[0]["supported_providers"])
        self.assertIn("vllm", payload[0]["supported_runtimes"])

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "orchestrators",
                    "list",
                    "--provider",
                    "ollama",
                    "--group-by",
                    "provider",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "provider")
        self.assertEqual(set(payload["groups"]), {"ollama"})
        self.assertEqual(payload["groups"]["ollama"][0]["name"], "langgraph")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "orchestrators",
                    "list",
                    "--runtime",
                    "vllm",
                    "--runtime",
                    "tgi",
                    "--group-by",
                    "runtime",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(set(payload["groups"]), {"vllm", "tgi"})

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["orchestrators", "doctor", "langgraph"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "langgraph")

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
                        "orchestrators",
                        "setup",
                        "langgraph",
                        "--runtime",
                        "ollama",
                        "--model",
                        "fixture-analysis-small",
                        "--limit",
                        "timeout=30m",
                        "--tool",
                        "shell=guarded",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["dry_run"])
            text = (profiles_dir / "local-dev" / "orchestrators.yaml").read_text(encoding="utf-8")
            self.assertIn("langgraph:", text)
            self.assertIn("timeout: 30m", text)

    def test_orchestrator_setup_writes_orchestrators_yaml(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("hardware_profiles:\n", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware={"hardware_profiles": {}},
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
                orchestrators={"orchestrators": {}},
            )
            result = OrchestratorCatalog(profile).setup(
                "langgraph",
                runtime="ollama",
                model="fixture-analysis-small",
                dry_run=False,
                yes=True,
            )
            orchestrators_text = (root / "orchestrators.yaml").read_text(encoding="utf-8")
            hardware_text = (root / "hardware.yaml").read_text(encoding="utf-8")
        self.assertEqual(result["results"][-1]["path"], str(root / "orchestrators.yaml"))
        self.assertIn("langgraph:", orchestrators_text)
        self.assertNotIn("langgraph", hardware_text)

    def test_stack_setup_lifecycle_and_artifact_exports(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            created = stacks.setup(
                "coding_agents",
                orchestrator="langgraph",
                runtime="ollama",
                model="fixture-analysis-small",
                machine="local_box",
                limits={"timeout": "30m", "max_parallel_agents": 3},
                tools={"shell": "guarded"},
                roles={
                    "planner": "fixture-analysis-small",
                    "reviewer": "local-code-large",
                },
                approval_mode="ask",
                audit_label="coding_agents",
            )
            self.assertFalse(created["dry_run"])
            shown = stacks.show("coding_agents")["stack"]
            self.assertEqual(shown["orchestrator"], "langgraph")
            self.assertEqual(shown["limits"]["timeout"], "30m")
            self.assertEqual(shown["tools"]["shell"], "guarded")
            self.assertEqual(shown["roles"]["planner"]["model"], "fixture-analysis-small")
            self.assertEqual(shown["roles"]["planner"]["audit_label"], "coding_agents.planner")
            self.assertFalse(shown["roles"]["reviewer"]["uses_primary_model"])
            plan = stacks.plan("coding_agents")
            self.assertEqual(plan["roles"]["reviewer"]["model"], "local-code-large")
            doctor = stacks.doctor("coding_agents")
            self.assertTrue(any(check["name"] == "role_model:planner" and check["ok"] for check in doctor["checks"]))
            prepared = stacks.prepare("coding_agents", dry_run=True)
            self.assertEqual(prepared["action"], "prepare")
            self.assertTrue(prepared["dry_run"])
            self.assertTrue(any(item["name"] == "install orchestrator packages" for item in prepared["commands"]))
            dockerfile = stacks.export("dockerfile", "coding_agents")
            self.assertIn("langgraph", dockerfile["content"])
            self.assertIn("AIPLANE_LIMITS_JSON", dockerfile["content"])
            self.assertEqual(dockerfile["metadata"]["limits"]["timeout"], "30m")
            self.assertEqual(
                dockerfile["metadata"]["roles"]["planner"]["model"],
                "fixture-analysis-small",
            )
            framework = stacks.export("langgraph", "coding_agents")
            self.assertEqual(framework["framework"], "langgraph")
            self.assertIn("planner:", framework["content"])
            self.assertIn("audit_label: coding_agents.planner", framework["content"])
            compose = stacks.export("compose", "coding_agents")
            self.assertIn("AIPLANE_TOOLS_JSON", compose["content"])
            self.assertIn("11434:11434", compose["content"])
            status = stacks.status("coding_agents")
            self.assertEqual(status["orchestrator"], "langgraph")
            self.assertEqual(status["limits"]["max_parallel_agents"], 3)

    def test_stack_role_doctor_allows_managed_service_roles_and_flags_risky_tools(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = json.loads(json.dumps(source.models))
            models_config.setdefault("models", {})["managed-chat"] = {
                "provider": "openai",
                "model": "coding-chat",
                "ownership": "managed_service",
                "roles": ["chat", "planner"],
                "enabled": True,
            }
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "mixed_agents",
                orchestrator="langgraph",
                runtime="ollama",
                model="fixture-analysis-small",
                machine="local_box",
                roles={"planner": "managed-chat"},
                tools={"shell": "unrestricted"},
                approval_mode="auto",
                audit_label="mixed_agents",
            )
            plan = stacks.plan("mixed_agents")
            doctor = stacks.doctor("mixed_agents")
            framework = stacks.export("langgraph", "mixed_agents")
        self.assertEqual(plan["roles"]["planner"]["runtime"], "openai")
        self.assertEqual(plan["roles"]["planner"]["endpoint"], "https://api.openai.com/v1")
        checks = {check["name"]: check for check in doctor["checks"]}
        self.assertTrue(checks["role_runtime_or_endpoint:planner"]["ok"])
        self.assertTrue(checks["role_endpoint:planner"]["ok"])
        self.assertFalse(checks["role_tool_policy:planner:shell"]["ok"])
        self.assertTrue(checks["role_tool_policy:planner:shell"].get("warning"))
        framework_payload = parse_yaml(framework["content"])
        self.assertEqual(framework_payload["roles"]["planner"]["runtime"], "openai")
        self.assertEqual(
            framework_payload["roles"]["planner"]["endpoint"],
            "https://api.openai.com/v1",
        )

    def test_stack_setup_cli_accepts_limits_and_tool_policies(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for key, filename in agent_config.CONFIG_FILES.items():
                (profile_root / filename).write_text(agent_config.dump_yaml(getattr(source, key)), encoding="utf-8")
            profile = load_profile("tmp", Path.cwd(), profiles_dir=profiles_dir)
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "stacks",
                        "setup",
                        "coding_agents",
                        "--orchestrator",
                        "langgraph",
                        "--runtime",
                        "ollama",
                        "--model",
                        "fixture-analysis-small",
                        "--machine",
                        "local_box",
                        "--limit",
                        "timeout=30m",
                        "--tool",
                        "shell=guarded",
                        "--role",
                        "planner=fixture-analysis-small",
                        "--approval-mode",
                        "guarded",
                        "--audit-label",
                        "cli_stack",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["stack"]["limits"]["timeout"], "30m")
            self.assertEqual(payload["stack"]["tools"]["shell"], "guarded")
            self.assertEqual(payload["stack"]["roles"]["planner"]["model"], "fixture-analysis-small")
            self.assertEqual(payload["stack"]["roles"]["planner"]["approval_mode"], "guarded")

    def test_stack_endpoint_plan_checks_shared_gateway_controls(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "shared_stack",
                orchestrator=None,
                runtime="ollama",
                model="fixture-analysis-small",
                machine="local_box",
                access="gateway",
                endpoint_policy="shared",
                endpoint="https://llm.example.com/v1",
                endpoint_auth={
                    "method": "bearer",
                    "api_key_env": "LLM_GATEWAY_API_KEY",
                    "tls": "terminated",
                    "gateway": "caddy",
                },
            )
            ready = stacks.endpoint_plan("shared_stack")
            doctor = stacks.doctor("shared_stack")
            stacks.setup(
                "unsafe_shared_stack",
                orchestrator=None,
                runtime="ollama",
                model="fixture-analysis-small",
                machine="local_box",
                access="gateway",
                endpoint_policy="shared",
                endpoint="http://llm.example.com/v1",
            )
            unsafe = stacks.endpoint_plan("unsafe_shared_stack")
        self.assertTrue(ready["ready_for_policy"])
        self.assertEqual(ready["auth"], {"method": "bearer", "api_key_env": "LLM_GATEWAY_API_KEY"})
        ready_checks = {check["name"]: check for check in ready["checks"]}
        self.assertTrue(ready_checks["endpoint_tls"]["ok"])
        self.assertTrue(ready_checks["endpoint_auth"]["ok"])
        doctor_checks = {check["name"]: check for check in doctor["checks"]}
        self.assertTrue(doctor_checks["endpoint_auth"]["ok"])
        self.assertFalse(unsafe["ready_for_policy"])
        unsafe_checks = {check["name"]: check for check in unsafe["checks"]}
        self.assertFalse(unsafe_checks["endpoint_tls"]["ok"])
        self.assertTrue(unsafe_checks["endpoint_tls"].get("warning"))
        self.assertFalse(unsafe_checks["endpoint_auth"]["ok"])
        self.assertTrue(unsafe["next_steps"])

    def test_stack_endpoint_plan_cli_uses_endpoint_auth_flags(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for key, filename in agent_config.CONFIG_FILES.items():
                (profile_root / filename).write_text(agent_config.dump_yaml(getattr(source, key)), encoding="utf-8")
            profile = load_profile("tmp", Path.cwd(), profiles_dir=profiles_dir)
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "stacks",
                        "setup",
                        "shared_stack",
                        "--runtime",
                        "ollama",
                        "--model",
                        "fixture-analysis-small",
                        "--machine",
                        "local_box",
                        "--access",
                        "gateway",
                        "--endpoint-policy",
                        "shared",
                        "--endpoint",
                        "https://llm.example.com/v1",
                        "--endpoint-auth",
                        "api_key",
                        "--endpoint-auth-env",
                        "LLM_GATEWAY_API_KEY",
                        "--endpoint-tls",
                        "terminated",
                        "--gateway",
                        "apim",
                    ]
                )
            self.assertEqual(code, 0)
            created = json.loads(stdout.getvalue())
            self.assertEqual(created["stack"]["endpoint_auth"]["method"], "api_key")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "stacks",
                        "endpoint-plan",
                        "shared_stack",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ready_for_policy"])
        self.assertEqual(payload["gateway"], "apim")
        self.assertEqual(payload["auth"]["api_key_env"], "LLM_GATEWAY_API_KEY")

    def test_stack_lifecycle_uses_provider_helper_directly(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "local_stack",
                orchestrator=None,
                runtime="ollama",
                model="fixture-analysis-small",
                machine="local_box",
                access="same_host",
            )
            plan = stacks.prepare("local_stack", dry_run=True)
        commands = [item["command"] for item in plan["commands"]]
        self.assertTrue(commands)
        self.assertIn("provider_helper.sh", commands[0][0])
        self.assertNotEqual(commands[0][0], "aiplane")
        self.assertIn("--provider", commands[0])
        self.assertIn("ollama", commands[0])

    def test_stack_lifecycle_reports_outcome_and_runtime_snapshot(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "local_stack",
                orchestrator=None,
                runtime="ollama",
                model="fixture-analysis-small",
                machine="local_box",
                access="same_host",
            )

            class Completed:
                returncode = 0
                stdout = "ok"
                stderr = ""

            with patch("aiplane.stacks.subprocess.run", return_value=Completed()):
                result = stacks.start("local_stack")
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["steps_total"], 1)
        self.assertEqual(result["steps_executed"], 1)
        self.assertIsNone(result["failed_step"])
        self.assertEqual(result["execution_mode"], "same_host")
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertIn("duration_seconds", result)
        self.assertIn("runtime_status_before", result)
        self.assertIn("runtime_status_after", result)
        self.assertIn("available", result["runtime_status_before"])
        self.assertIn("available", result["runtime_status_after"])

    def test_stack_lifecycle_reports_failed_step(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            exported = MachineManager(profile).export_machine("local_box")
            machine_path = root / "local_box.json"
            machine_path.write_text(json.dumps(exported), encoding="utf-8")
            MachineManager(profile).import_file(machine_path)
            stacks = StackManager(profile)
            stacks.setup(
                "local_stack",
                orchestrator=None,
                runtime="ollama",
                model="fixture-analysis-small",
                machine="local_box",
                access="same_host",
            )

            class Failed:
                returncode = 7
                stdout = ""
                stderr = "failed"

            with patch("aiplane.stacks.subprocess.run", return_value=Failed()):
                result = stacks.prepare("local_stack")
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["steps_total"], 2)
        self.assertEqual(result["steps_executed"], 1)
        self.assertEqual(result["failed_step"]["returncode"], 7)

    def test_stack_lifecycle_does_not_execute_remote_stack(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=json.loads(json.dumps(source.hardware)),
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            MachineManager(profile).import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            stacks = StackManager(profile)
            stacks.setup(
                "remote_stack",
                orchestrator=None,
                runtime="vllm",
                model="local-code-large",
                machine="azure_h100_test",
                access="ssh_tunnel",
            )
            with patch("aiplane.stacks.subprocess.run") as run:
                result = stacks.start("remote_stack")
        self.assertEqual(result["status"], "planned_not_executed")
        self.assertIn("same-host/local", result["reason"])
        run.assert_not_called()
