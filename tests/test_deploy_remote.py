from __future__ import annotations

from .support import (
    DeployManager,
    _isolated_profiles_dir,
    Path,
    Profile,
    RemoteManager,
    StringIO,
    cli_main,
    json,
    load_profile,
    patch,
    redirect_stderr,
    redirect_stdout,
    subprocess,
    tempfile,
    unittest,
)


class DeployRemoteTests(unittest.TestCase):
    def test_deploy_workflow_plan_separates_cloud_vm_aks_and_remote_workstation(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = DeployManager(profile)
        vm = manager.workflow_plan("azure_gpu_vm")
        aks = manager.workflow_plan("aks_gpu_pool")
        remote = manager.workflow_plan("gpu_workstation_ssh")
        self.assertEqual(vm["workflow"], "cloud_vm")
        self.assertTrue(vm["boundaries"]["cloud_resource_provisioning"])
        self.assertIn("az", vm["recommended_tools"])
        self.assertIn("SSH/Ansible/cloud-init", {phase["tool_owner"] for phase in vm["phases"]})
        self.assertEqual(aks["workflow"], "cloud_kubernetes")
        self.assertIn("kubectl", aks["recommended_tools"])
        self.assertEqual(remote["workflow"], "remote_workstation")
        self.assertTrue(remote["boundaries"]["remote_existing_machine_setup"])
        self.assertFalse(remote["boundaries"]["cloud_resource_provisioning"])

    def test_deploy_workflow_plan_cli_is_non_mutating(self) -> None:
        stdout = StringIO()
        with _isolated_profiles_dir() as profiles_dir:
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "deploy",
                        "workflow-plan",
                        "--target",
                        "azure_gpu_vm",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["workflow"], "cloud_vm")
        self.assertEqual(payload["mutation_policy"]["apply"], "guarded_cli_only")
        self.assertTrue(payload["phases"])

    def test_deploy_plan_uses_az_first_for_aks_target(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = DeployManager(profile).plan("aks_gpu_pool")
        self.assertEqual(plan["workflow"], "cloud_kubernetes")
        self.assertEqual(plan["first_control_tool"], "az")
        self.assertIn("az", plan["required_tools"])
        self.assertEqual(plan["config"]["cluster"], "ai-coding-aks")
        first_command = plan["steps"][0]["command"]
        self.assertEqual(first_command[:2], ["az", "account"])

    def test_deploy_plan_supports_azure_vm_target(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = DeployManager(profile).plan("azure_gpu_vm")
        self.assertEqual(plan["type"], "azure_vm")
        self.assertEqual(plan["workflow"], "cloud_vm")
        self.assertTrue(plan["workflow_boundaries"]["cloud_resource_provisioning"])
        self.assertEqual(plan["first_control_tool"], "az")
        self.assertIn("ssh", plan["required_tools"])
        self.assertIn("training_finetune", plan["resource_classes"])
        commands = [step["command"] for step in plan["steps"]]
        self.assertTrue(any(command[:3] == ["az", "vm", "create"] for command in commands))

    def test_deploy_apply_supports_guarded_azure_vm_steps(self) -> None:
        profile = load_profile("local-dev", Path.cwd())

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        with patch("aiplane.deploy.subprocess.run", return_value=Completed()) as run:
            result = DeployManager(profile).apply("azure_gpu_vm", yes=True)
        self.assertEqual(result["target"], "azure_gpu_vm")
        self.assertTrue(result["results"])
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any(command[:3] == ["az", "vm", "create"] for command in commands))

    def test_deploy_apply_cli_requires_explicit_yes(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with _isolated_profiles_dir() as profiles_dir:
            with (
                patch("aiplane.deploy.subprocess.run") as run,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "deploy",
                        "apply",
                        "--target",
                        "azure_gpu_vm",
                    ]
                )
        self.assertEqual(code, 1)
        self.assertIn("deploy apply is mutating", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        run.assert_not_called()

    def test_deploy_apply_cli_runs_only_with_yes(self) -> None:
        completed = subprocess.CompletedProcess(["az"], 0, "ok", "")
        stdout = StringIO()
        with _isolated_profiles_dir() as profiles_dir:
            with (
                patch("aiplane.deploy.subprocess.run", return_value=completed) as run,
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "deploy",
                        "apply",
                        "--target",
                        "azure_gpu_vm",
                        "--yes",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["target"], "azure_gpu_vm")
        run.assert_called()

    def test_deploy_apply_requires_yes(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with self.assertRaises(PermissionError):
            DeployManager(profile).apply("aks_gpu_pool")

    def test_remote_tunnel_plan_uses_ssh_local_forwarding(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")
        self.assertEqual(plan["type"], "ssh_tunnel")
        self.assertIn("-L", plan["command"])
        self.assertEqual(plan["endpoint"], "http://localhost:11434/v1")
        self.assertEqual(plan["connection"]["ide_endpoint"], "http://localhost:11434/v1")
        self.assertIn("remote_service", plan["connection"])

    def test_remote_tunnel_lifecycle_is_guarded_and_status_uses_pid_file(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            profile = Profile(
                name="tmp",
                root=source.root,
                workspace=workspace,
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=source.models,
                targets=source.targets,
            )
            manager = RemoteManager(profile)
            with self.assertRaises(PermissionError):
                manager.tunnel_start("gpu_workstation_ssh")

            class Process:
                pid = 12345

            with (
                patch("aiplane.remote.shutil.which", return_value="/usr/bin/ssh"),
                patch("aiplane.remote.subprocess.Popen", return_value=Process()),
            ):
                started = manager.tunnel_start("gpu_workstation_ssh", yes=True)
            self.assertEqual(started["status"], "started")
            self.assertTrue((workspace / ".aiplane" / "remote" / "gpu_workstation_ssh.pid").exists())
            with patch("aiplane.remote.os.kill") as kill:
                status = manager.tunnel_status("gpu_workstation_ssh")
            self.assertTrue(status["running"])
            kill.assert_called_with(12345, 0)
            with patch("aiplane.remote.os.kill") as kill:
                stopped = manager.tunnel_stop("gpu_workstation_ssh", yes=True)
            self.assertEqual(stopped["status"], "stopped")
            kill.assert_called_with(12345, 15)
