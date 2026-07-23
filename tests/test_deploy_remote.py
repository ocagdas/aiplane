from __future__ import annotations

from aiplane.artifact_validation import validate_deployment_artifacts

from .artifact_fixtures import copy_profile_targets, profile_with_target_iac, profile_with_targets

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

        with patch("aiplane.boundaries.subprocess.run", return_value=Completed()) as run:
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
                patch("aiplane.boundaries.subprocess.run") as run,
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
                patch("aiplane.boundaries.subprocess.run", return_value=completed) as run,
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

    def test_remote_tunnel_plan_rejects_invalid_host(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        mutated_targets = copy_profile_targets(source)
        mutated_targets["targets"]["gpu_workstation_ssh"]["ssh"]["host"] = "gpu-workstation with space"

        profile = profile_with_targets(source, mutated_targets)

        with self.assertRaises(ValueError) as exc:
            RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")

        self.assertIn("whitespace", str(exc.exception))

    def test_remote_tunnel_plan_rejects_invalid_user(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        mutated_targets = copy_profile_targets(source)
        mutated_targets["targets"]["gpu_workstation_ssh"]["ssh"]["user"] = "bad user"

        profile = profile_with_targets(source, mutated_targets)

        with self.assertRaises(ValueError) as exc:
            RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")

        self.assertIn("ssh.user", str(exc.exception))

    def test_remote_tunnel_plan_rejects_invalid_port(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        mutated_targets = copy_profile_targets(source)
        mutated_targets["targets"]["gpu_workstation_ssh"]["ssh"]["port"] = 70000

        profile = profile_with_targets(source, mutated_targets)

        with self.assertRaises(ValueError) as exc:
            RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")

        self.assertIn("must be an integer in the range 1-65535", str(exc.exception))

    def test_remote_tunnel_plan_rejects_invalid_endpoint(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        mutated_targets = copy_profile_targets(source)
        mutated_targets["targets"]["gpu_workstation_ssh"]["endpoint"] = "localhost:11434/v1"

        profile = profile_with_targets(source, mutated_targets)

        with self.assertRaises(ValueError) as exc:
            RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")

        self.assertIn("must use http or https", str(exc.exception))

    def test_remote_tunnel_plan_uses_ssh_local_forwarding(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = RemoteManager(profile).tunnel_plan("gpu_workstation_ssh")
        self.assertEqual(plan["type"], "ssh_tunnel")
        self.assertIn("-L", plan["command"])
        self.assertEqual(plan["endpoint"], "http://localhost:11434/v1")
        self.assertEqual(plan["connection"]["ide_endpoint"], "http://localhost:11434/v1")
        self.assertIn("remote_service", plan["connection"])

    def test_remote_tunnel_cli_plan_is_json_and_references_endpoint(self) -> None:
        with _isolated_profiles_dir() as profiles_dir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "remote",
                        "tunnel",
                        "plan",
                        "--profile",
                        "local-dev",
                        "--target",
                        "gpu_workstation_ssh",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["target"], "gpu_workstation_ssh")
        self.assertEqual(payload["type"], "ssh_tunnel")
        self.assertEqual(payload["endpoint"], "http://localhost:11434/v1")
        self.assertEqual(payload["command"][0], "ssh")
        self.assertIn("-L", payload["command"])
        self.assertEqual(payload["required_tools"], ["ssh"])

    def test_machines_profile_remote_plan_cli(self) -> None:
        with _isolated_profiles_dir() as profiles_dir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "machines",
                        "profile-remote-plan",
                        "--profile",
                        "local-dev",
                        "--name",
                        "gpu_workstation_copy",
                        "--host",
                        "gpu-workstation.example.internal",
                        "--user",
                        "dev",
                        "--port",
                        "2200",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "gpu_workstation_copy")
        self.assertEqual(payload["mode"], "ssh_remote_profile")
        self.assertEqual(len(payload["steps"]), 3)
        self.assertEqual(payload["steps"][0]["command"][0], "ssh")
        self.assertEqual(payload["steps"][0]["command"][1], "-p")
        self.assertEqual(payload["steps"][0]["command"][2], "2200")
        self.assertEqual(payload["steps"][1]["command"][0], "ssh")
        self.assertEqual(payload["steps"][1]["command"][1], "-p")
        self.assertEqual(payload["steps"][1]["command"][3], "dev@gpu-workstation.example.internal")
        self.assertIn("export machine profile", payload["steps"][1]["name"])

    def test_remote_tunnel_lifecycle_is_guarded_and_identity_verified(self) -> None:
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

            class Inspector:
                identity = {"source": "fake", "start": "one"}
                terminated: list[int] = []

                def capture(self, pid):
                    return dict(self.identity)

                def matches(self, pid, identity):
                    return identity == self.identity

                def terminate_if_matches(self, pid, identity):
                    if not self.matches(pid, identity):
                        return False
                    self.terminated.append(pid)
                    return True

            class Process:
                pid = 12345

            inspector = Inspector()
            manager = RemoteManager(profile, process_inspector=inspector)
            with self.assertRaises(PermissionError):
                manager.tunnel_start("gpu_workstation_ssh")
            with (
                patch("aiplane.remote.shutil.which", return_value="/usr/bin/ssh"),
                patch("aiplane.boundaries.subprocess.Popen", return_value=Process()),
            ):
                started = manager.tunnel_start("gpu_workstation_ssh", yes=True)

            self.assertEqual(started["status"], "started")
            self.assertTrue(Path(started["state_file"]).exists())
            self.assertEqual(manager.tunnel_status("gpu_workstation_ssh")["state"], "running")
            stopped = manager.tunnel_stop("gpu_workstation_ssh", yes=True)
            self.assertEqual(stopped["status"], "stopped")
            self.assertEqual(inspector.terminated, [12345])
            self.assertFalse(Path(started["state_file"]).exists())


def test_deploy_render_is_deterministic_secret_free_and_schema_linked() -> None:
    profile = load_profile("local-dev", Path.cwd())
    manager = DeployManager(profile)
    first = manager.render("azure_gpu_vm")
    second = manager.render("azure_gpu_vm")
    assert first == second
    assert first["$schema"] == "schemas/aiplane-deployment-artifacts-v1.schema.json"
    assert first["render_only"] is True
    assert first["apply_supported"] is False
    assert {"main.tf", "aiplane.pkr.hcl", "inventory.ini", "playbook.yml"} <= set(first["files"])
    serialized = json.dumps(first).lower()
    assert "client_secret" not in serialized
    assert "private_key" not in serialized
    for name, content in first["files"].items():
        import hashlib

        assert first["checksums"][name] == hashlib.sha256(content.encode()).hexdigest()


def test_deploy_render_cli_can_print_one_artifact() -> None:
    stdout = StringIO()
    with _isolated_profiles_dir() as profiles_dir, redirect_stdout(stdout):
        code = cli_main(
            [
                "--profiles-dir",
                str(profiles_dir),
                "deploy",
                "render",
                "--target",
                "aks_gpu_pool",
                "--file",
                "main.tf",
            ]
        )
    assert code == 0
    assert 'provider "azurerm"' in stdout.getvalue()
    assert "kubectl apply" not in stdout.getvalue()


def test_deploy_render_rejects_inventory_injection() -> None:
    source = load_profile("local-dev", Path.cwd())
    targets = copy_profile_targets(source)
    targets["targets"]["gpu_workstation_ssh"]["ssh"]["user"] = "operator\nmalicious=true"
    profile = profile_with_targets(source, targets)
    with unittest.TestCase().assertRaisesRegex(ValueError, "unsupported inventory characters"):
        DeployManager(profile).render("gpu_workstation_ssh")


def test_deployment_artifact_application_validation_rejects_checksum_drift() -> None:
    payload = DeployManager(load_profile("local-dev", Path.cwd())).render("azure_gpu_vm")
    assert validate_deployment_artifacts(payload) is payload

    missing = json.loads(json.dumps(payload))
    missing["checksums"] = {}
    with unittest.TestCase().assertRaisesRegex(ValueError, "checksums must be a non-empty object"):
        validate_deployment_artifacts(missing)

    mismatch = json.loads(json.dumps(payload))
    mismatch["checksums"].pop(next(iter(mismatch["checksums"])))
    with unittest.TestCase().assertRaisesRegex(ValueError, "keys must match"):
        validate_deployment_artifacts(mismatch)


def test_cloud_artifacts_select_matching_iac_family_and_safe_preview() -> None:
    source = load_profile("local-dev", Path.cwd())
    selections = {
        "opentofu": ({"main.tf"}, ["tofu fmt -check"]),
        "terraform": ({"main.tf"}, ["terraform fmt -check"]),
        "pulumi": ({"Pulumi.yaml", "requirements.txt", "__main__.py"}, ["pulumi preview --diff"]),
    }
    for target_name in ["azure_gpu_vm", "aks_gpu_pool"]:
        for selected, (required_files, validation_commands) in selections.items():
            manager = DeployManager(profile_with_target_iac(source, target_name, selected))
            workflow = manager.workflow_plan(target_name)
            payload = manager.render(target_name)

            assert workflow["iac"] == selected
            assert workflow["iac_tool"] == {
                "name": selected,
                "command": "tofu" if selected == "opentofu" else selected,
                "doctor_command": f"aiplane tools doctor {selected}",
                "setup_plan_command": f"aiplane tools plan {selected}",
            }
            assert selected in workflow["recommended_tools"]
            assert not ({"opentofu", "terraform", "pulumi"} - {selected}) & set(workflow["recommended_tools"])
            assert payload["iac"] == selected
            assert payload["artifact_readiness"] == "scaffold"
            assert payload["unresolved_inputs"]
            assert required_files <= set(payload["files"])
            if target_name == "azure_gpu_vm":
                assert {"aiplane.pkr.hcl", "inventory.ini", "playbook.yml"} <= set(payload["files"])
            assert payload["validation_commands"] == validation_commands
            assert payload["next_commands"] == []
            assert all(" apply" not in item and " up" not in item for item in validation_commands)

            if selected == "pulumi":
                assert "main.tf" not in payload["files"]
                assert "runtime:\n  name: python" in payload["files"]["Pulumi.yaml"]
                assert "pulumi-azure-native" in payload["files"]["requirements.txt"]
                compile(payload["files"]["__main__.py"], "__main__.py", "exec")
            else:
                assert "Pulumi.yaml" not in payload["files"]
                assert "__main__.py" not in payload["files"]


def test_cloud_iac_defaults_to_opentofu_and_rejects_unknown_implementations() -> None:
    source = load_profile("local-dev", Path.cwd())
    targets = copy_profile_targets(source)
    targets["targets"]["azure_gpu_vm"].pop("iac", None)
    manager = DeployManager(profile_with_targets(source, targets))
    assert manager.workflow_plan("azure_gpu_vm")["iac"] == "opentofu"
    assert manager.render("azure_gpu_vm")["validation_commands"] == ["tofu fmt -check"]

    targets["targets"]["azure_gpu_vm"]["iac"] = "cloudformation"
    manager = DeployManager(profile_with_targets(source, targets))
    with unittest.TestCase().assertRaisesRegex(ValueError, "target iac must be"):
        manager.render("azure_gpu_vm")


def test_deployment_validation_rejects_iac_file_and_command_drift() -> None:
    source = load_profile("local-dev", Path.cwd())
    payload = DeployManager(profile_with_target_iac(source, "azure_gpu_vm", "pulumi")).render("azure_gpu_vm")

    wrong_command = json.loads(json.dumps(payload))
    wrong_command["validation_commands"] = ["terraform fmt -check"]
    with unittest.TestCase().assertRaisesRegex(ValueError, "pulumi preview"):
        validate_deployment_artifacts(wrong_command)

    wrong_family = json.loads(json.dumps(payload))
    wrong_family["files"]["main.tf"] = "# drift\n"
    import hashlib

    wrong_family["checksums"]["main.tf"] = hashlib.sha256(b"# drift\n").hexdigest()
    with unittest.TestCase().assertRaisesRegex(ValueError, "no HCL module"):
        validate_deployment_artifacts(wrong_family)


def test_non_cloud_artifacts_cannot_claim_an_iac_implementation() -> None:
    payload = DeployManager(load_profile("local-dev", Path.cwd())).render("gpu_workstation_ssh")
    payload["iac"] = "opentofu"
    with unittest.TestCase().assertRaisesRegex(ValueError, "must not declare"):
        validate_deployment_artifacts(payload)


def test_remote_scaffold_does_not_recommend_ansible_execution_with_unresolved_user() -> None:
    payload = DeployManager(load_profile("local-dev", Path.cwd())).render("gpu_workstation_ssh")
    assert payload["artifact_readiness"] == "scaffold"
    assert payload["unresolved_inputs"] == ["ssh.user"]
    assert payload["next_commands"] == []
    assert all("--check" not in command for command in payload["validation_commands"])
