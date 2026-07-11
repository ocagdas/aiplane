from __future__ import annotations

from .support import (
    HardwareManager,
    MachineManager,
    Path,
    Profile,
    StringIO,
    agent_config,
    cli_main,
    cli_module,
    create_profile,
    json,
    load_profile,
    patch,
    redirect_stderr,
    redirect_stdout,
    tempfile,
    unittest,
)


class HardwareMachineTests(unittest.TestCase):
    def test_machines_discover_cli_rejects_runtime_argument(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            cli_main(["machines", "discover", "azure", "--region", "uksouth", "--runtime", "vllm"])
        self.assertIn("unrecognized arguments: --runtime vllm", stderr.getvalue())

    def test_hardware_template_uses_normalized_machine_fields_only(self) -> None:
        data = agent_config.parse_yaml(
            (Path.cwd() / "profile-templates/local-dev/hardware.yaml").read_text(encoding="utf-8")
        )
        selected_values = data["selected"]["values"]
        self.assertNotIn("type", selected_values)
        self.assertNotIn("cpu", selected_values)
        self.assertNotIn("gpu", selected_values)
        for template in data["hardware_profiles"].values():
            self.assertNotIn("configurable_options", template)
            self.assertNotIn("type", template)
            self.assertNotIn("vendor", template)
            self.assertNotIn("gpu", template)

    def test_hardware_show_includes_only_selection_summary_by_default(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        config = HardwareManager(profile).show()
        self.assertNotIn("hardware_profiles", config)
        self.assertIn("active_selection", config)
        self.assertIn("effective_machine", config)

    def test_hardware_show_cli_outputs_summary_payload(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["hardware", "show", "--profile", "local-dev"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("active_selection", payload)
        self.assertIn("effective_machine", payload)
        self.assertNotIn("hardware_profiles", payload)

    def test_hardware_show_cli_outputs_text_when_format_text(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "hardware",
                    "show",
                    "--profile",
                    "local-dev",
                    "--format",
                    "text",
                ]
            )
        self.assertEqual(code, 0)
        rows = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(rows[0], "hardware show")
        self.assertIn("active_selection", rows)
        self.assertIn("effective_machine", rows)
        self.assertTrue(any("NAME" in line and "ORIGIN" in line and "CUSTOM" in line for line in rows))
        self.assertFalse(rows[1].startswith("{"))

    def test_hardware_show_list_types_includes_template_names(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = HardwareManager(profile).show_types()
        names = [row["name"] for row in payload["types"]]
        self.assertIn("nvidia_dgx_spark_style", names)
        self.assertIn("amd_ryzen_ai_max_halo_style", names)

    def test_hardware_show_list_types_cli_outputs_available_types(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["hardware", "show", "--list-types", "--profile", "local-dev"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "hardware_types")
        names = [row["name"] for row in payload["types"]]
        self.assertIn("local_auto", names)
        self.assertIn("cloud_gpu_vm", names)

    def test_hardware_discover_has_cpu_memory_and_template_matches(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        discovered = HardwareManager(profile).discover()
        self.assertIn("cpu_count", discovered)
        self.assertIn("memory_gb", discovered)
        self.assertIn("gpus", discovered)
        self.assertIn("closest_profiles", discovered)
        self.assertLessEqual(len(discovered["closest_profiles"]), 3)
        self.assertTrue(all("name" in row for row in discovered["closest_profiles"]))

    def test_hardware_closest_profiles_excludes_zero_score_gpu_templates(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = HardwareManager(profile)

        discovered = {"gpus": [], "memory_gb": 64}
        closest = manager._closest_profiles(discovered)
        names = {row["name"] for row in closest}
        self.assertIn("cpu_laptop", names)
        self.assertNotIn("nvidia_consumer_gpu", names)
        self.assertNotIn("nvidia_workstation_gpu", names)
        self.assertTrue(all(row["score"] > 0 for row in closest))

    def test_hardware_discover_can_select_closest_and_clear_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "hardware",
                        "discover",
                        "--profile",
                        "local-dev",
                        "--select-closest",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            preview = json.loads(stdout.getvalue())
            self.assertTrue(preview["would_select"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "hardware",
                        "discover",
                        "--profile",
                        "local-dev",
                        "--select-closest",
                    ]
                )
            self.assertEqual(code, 0)
            selected = json.loads(stdout.getvalue())
            self.assertEqual(selected["selected"], preview["would_select"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "hardware",
                        "clear",
                        "--profile",
                        "local-dev",
                    ]
                )
            self.assertEqual(code, 0)
            cleared = json.loads(stdout.getvalue())
            self.assertTrue(cleared["cleared"])
            self.assertEqual(cleared["selection"]["origin"], "local_auto")

    def test_hardware_doctor_checks_model_fit(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        fits = HardwareManager(profile).doctor("fixture-analysis-small")
        self.assertEqual(len(fits["needs_fit_check"]), 1)
        self.assertIn("provider-text-small:0.5b", fits["needs_fit_check"][0]["model"])

    def test_hardware_doctor_groups_remote_models_after_local_fit_checks(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"] = {
            "ownership": "managed_service",
            "runtime": "openai_api",
            "protocol": "openai_compatible",
            "endpoint": "https://api.openai.com/v1",
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
        }
        profile.models.setdefault("models", {})["openai-main"] = {
            "provider": "openai",
            "model": "gpt-4.1",
            "roles": ["analysis"],
            "local": False,
            "enabled": True,
        }
        grouped = HardwareManager(profile).doctor()
        self.assertIn("needs_fit_check", grouped)
        self.assertIn("no_local_fit_check_required", grouped)
        self.assertTrue(grouped["needs_fit_check"])
        remote_models = {row["model"] for row in grouped["no_local_fit_check_required"]}
        self.assertIn("gpt-4.1", remote_models)

    def test_hardware_recommend_hides_not_recommended_by_default(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = HardwareManager(profile).recommend()
        self.assertIn("criteria", result)
        self.assertEqual(list(result["models"].keys()), ["recommended", "usable", "remote_or_cloud"])
        self.assertNotIn("not_recommended", result["models"])
        self.assertGreaterEqual(result["hidden"]["not_recommended_count"], 1)
        first_group = result["models"]["recommended"] or result["models"]["usable"]
        self.assertIn("capabilities", first_group[0])
        self.assertIn("capability_avg_score", first_group[0])
        self.assertEqual(
            list(first_group[0].keys())[:10],
            [
                "name",
                "model",
                "provider",
                "capability_avg_score",
                "level",
                "enabled",
                "min_ram_gb",
                "recommended_ram_gb",
                "min_vram_gb",
                "recommended_vram_gb",
            ],
        )
        scores = [row["capability_avg_score"] for row in result["models"]["recommended"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_hardware_recommend_includes_runtime_and_policy_metadata(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = HardwareManager(profile).recommend()
        rows = [row for group in result["models"].values() for row in group]
        local_rows = [
            row
            for row in rows
            if row["runtime_compatibility_score"] >= 0 and row["runtime_compatibility"]["state"] != "not_applicable"
        ]
        self.assertTrue(local_rows)
        sample = local_rows[0]
        self.assertIn("runtime_compatibility", sample)
        self.assertIn("runtime_compatibility_score", sample)
        self.assertIn("runtime_recommendation", sample)
        self.assertIn("policy_decision", sample)
        self.assertIn("allowed", sample["policy_decision"])

    def test_hardware_recommend_can_include_not_recommended(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = HardwareManager(profile).recommend(include_not_recommended=True)
        self.assertEqual(
            list(result["models"].keys()),
            ["recommended", "usable", "remote_or_cloud", "not_recommended"],
        )
        names = {row["name"] for rows in result["models"].values() for row in rows}
        self.assertIn("local-reasoning-large", names)
        self.assertIn("local-code-large", names)

    def test_hardware_recommend_includes_latest_benchmark_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / ".aiplane" / "benchmarks"
            root.mkdir(parents=True)
            benchmark = {
                "created_at": "2026-06-19T00:00:00+00:00",
                "model_name": "fixture-analysis-small",
                "summary": {"average_score": 88, "average_elapsed_ms": 1234},
            }
            (root / "20260619T000000Z-fixture-analysis-small.json").write_text(json.dumps(benchmark), encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = HardwareManager(profile).recommend()
            rows = [row for group in result["models"].values() for row in group]
            model_row = next(row for row in rows if row["name"] == "fixture-analysis-small")
            self.assertEqual(model_row["latest_benchmark"]["summary"]["average_score"], 88)

    def test_hardware_schema_and_active_machine_are_available(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        manager = HardwareManager(profile)
        schema = manager.schema()
        self.assertEqual(schema["name"], "machine_schema")
        self.assertIn("memory_gb", schema["fields"])
        active = manager.active_config()
        self.assertIn("machine", active)
        self.assertIn("cpu", active["machine"])
        self.assertIn("memory", active["machine"])

    def test_hardware_recommend_uses_custom_active_machine(self) -> None:
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
            manager = HardwareManager(profile)
            profile.models["models"]["local-code-large"]["enabled"] = True

            manager.use_template(
                "cloud_gpu_vm",
                {
                    "machine_tag": "azure_h100_test",
                    "provider": "azure",
                    "stock_sku": "Standard_NC40ads_H100_v5",
                    "memory_gb": 320,
                    "gpu_vendor": "nvidia",
                    "gpu_model": "H100 NVL",
                    "gpu_count": 1,
                    "vram_gb": 94,
                },
            )
            result = manager.recommend()
            self.assertEqual(result["machine"]["stock"]["machine_tag"], "azure_h100_test")
            self.assertEqual(result["machine"]["gpu"]["vram_gb"], 94)
            recommended_names = {row["name"] for row in result["models"]["recommended"]}
            self.assertIn("local-code-large", recommended_names)

    def test_machine_export_import_recommend_and_remote_plan(self) -> None:
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
            manager = MachineManager(profile)
            exported = manager.export_machine("this_pc")
            export_path = root / "this_pc.machine.json"
            export_path.write_text(json.dumps(exported), encoding="utf-8")
            imported = manager.import_file(export_path, overrides={"memory_gb": 128, "vram_gb": 48})
            self.assertEqual(imported["name"], "this_pc")
            rows = manager.list()
            self.assertIn("this_pc", {row["name"] for row in rows})
            recommendation = manager.recommend(model="local-code-large", runtime="vllm")
            self.assertEqual(recommendation["machines"][0]["level"], "recommended")
            remote = manager.profile_remote_plan("gpu_box_01", "gpu.example.com", user="dev")
            self.assertEqual(remote["mode"], "ssh_remote_profile")
            self.assertIn("ssh", remote["steps"][1]["command"][0])

    def test_machine_azure_discovery_includes_quota_and_restrictions(self) -> None:
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
            calls = []

            class Completed:
                def __init__(self, stdout, returncode=0):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = ""

            class PriceResponse:
                def __init__(self, payload):
                    self._payload = payload

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return None

                def read(self):
                    return json.dumps(self._payload).encode("utf-8")

            def fake_run(command, **kwargs):
                calls.append(command)
                if command[:3] == ["az", "account", "show"]:
                    return Completed(
                        json.dumps(
                            {
                                "environmentName": "AzureCloud",
                                "state": "Enabled",
                                "isDefault": True,
                                "name": "sub",
                                "id": "sub-id",
                                "tenantId": "tenant",
                                "user": {"name": "u", "type": "user"},
                            }
                        )
                    )
                if command[:3] == ["az", "vm", "list-skus"]:
                    return Completed(
                        json.dumps(
                            [
                                {
                                    "name": "Standard_NC40ads_H100_v5",
                                    "restrictions": [
                                        {
                                            "type": "Location",
                                            "reasonCode": "NotAvailableForSubscription",
                                            "values": ["uksouth"],
                                        }
                                    ],
                                }
                            ]
                        )
                    )
                if command[:3] == ["az", "vm", "list-usage"]:
                    return Completed(
                        json.dumps(
                            [
                                {
                                    "name": {
                                        "value": "cores",
                                        "localizedValue": "Total Regional vCPUs",
                                    },
                                    "currentValue": 4,
                                    "limit": 100,
                                    "unit": "Count",
                                }
                            ]
                        )
                    )
                return Completed("", returncode=1)

            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", side_effect=fake_run),
                patch(
                    "aiplane.machines.urlopen",
                    return_value=PriceResponse(
                        {
                            "Items": [
                                {
                                    "armSkuName": "Standard_NC40ads_H100_v5",
                                    "currencyCode": "USD",
                                    "unitPrice": 12.34,
                                    "unitOfMeasure": "1 Hour",
                                    "meterName": "NC40ads H100 v5",
                                    "productName": "Virtual Machines NCads H100 v5",
                                    "skuName": "NC40ads H100 v5",
                                }
                            ]
                        }
                    ),
                ),
            ):
                result = MachineManager(profile).discover_azure("uksouth", workload="inference_large", limit=1)
            self.assertEqual(result["discovery"]["method"], "live")
            self.assertTrue(result["quota"]["ok"])
            self.assertEqual(result["quota"]["items"][0]["remaining"], 96)
            self.assertEqual(
                result["candidates"][0]["restrictions"][0]["reason_code"],
                "NotAvailableForSubscription",
            )
            self.assertEqual(result["candidates"][0]["pricing"]["currency"], "USD")
            self.assertEqual(result["candidates"][0]["pricing"]["unit"], "per_hour")

    def test_machine_azure_discovery_supports_resource_and_vendor_filters(self) -> None:
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
            manager = MachineManager(profile)
            with patch("aiplane.machines.shutil.which", return_value=None):
                cpu_only = manager.discover_azure(
                    "uksouth",
                    workload="compile_build",
                    gpu_vendor="none",
                    min_cpu_cores=20,
                    min_ram_gb=100,
                    limit=10,
                )
                gpu_heavy = manager.discover_azure(
                    "uksouth",
                    workload="inference_large",
                    gpu_vendor="nvidia",
                    min_cpu_cores=30,
                    min_ram_gb=300,
                    min_vram_gb=80,
                    limit=10,
                )
            self.assertEqual([row["name"] for row in cpu_only["candidates"]], ["azure_standard_e32s_v5"])
            self.assertEqual(
                {row["name"] for row in gpu_heavy["candidates"]},
                {"azure_standard_nc40ads_h100_v5", "azure_standard_nd96asr_v4"},
            )

    def test_machines_discover_azure_verbosity_streams_az_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)

            class Completed:
                def __init__(self, stdout, returncode=0, stderr=""):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr

            class PriceResponse:
                def __init__(self, payload):
                    self._payload = payload

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return None

                def read(self):
                    return json.dumps(self._payload).encode("utf-8")

            def fake_run(command, **kwargs):
                if command[:3] == ["az", "account", "show"]:
                    return Completed(
                        json.dumps(
                            {
                                "environmentName": "AzureCloud",
                                "state": "Enabled",
                                "isDefault": True,
                                "name": "sub",
                                "id": "sub-id",
                                "tenantId": "tenant",
                                "user": {"name": "u", "type": "user"},
                            }
                        )
                    )
                if command[:3] == ["az", "vm", "list-skus"]:
                    return Completed(json.dumps([{"name": "Standard_NC40ads_H100_v5"}]))
                if command[:3] == ["az", "vm", "list-usage"]:
                    return Completed("[]")
                return Completed("", returncode=1, stderr="unexpected command")

            stdout = StringIO()
            stderr = StringIO()
            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", side_effect=fake_run),
                patch("aiplane.machines.urlopen", return_value=PriceResponse({"Items": []})),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "machines",
                        "discover",
                        "azure",
                        "--profile",
                        "local-dev",
                        "--region",
                        "uksouth",
                        "--workload",
                        "inference_large",
                        "--limit",
                        "1",
                    ]
                )
            self.assertEqual(code, 0)
            progress = stderr.getvalue()
            self.assertIn("[az] running: az account show --output json", progress)
            self.assertIn("[az] running: az vm list-skus --location uksouth", progress)
            self.assertIn("\x1b[1A", progress)
            self.assertNotIn("[az] stdout:", progress)

            stdout = StringIO()
            stderr = StringIO()
            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", side_effect=fake_run),
                patch("aiplane.machines.urlopen", return_value=PriceResponse({"Items": []})),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "machines",
                        "discover",
                        "azure",
                        "--profile",
                        "local-dev",
                        "--region",
                        "uksouth",
                        "--workload",
                        "inference_large",
                        "--limit",
                        "1",
                        "--verbosity",
                        "1",
                    ]
                )
            self.assertEqual(code, 0)
            verbose_progress = stderr.getvalue()
            self.assertIn("[az] completed (exit 0): az vm list-skus --location uksouth", verbose_progress)
            self.assertIn('"name": "Standard_NC40ads_H100_v5"', verbose_progress)
            self.assertIn('"id": "[redacted]"', verbose_progress)

    def test_az_command_progress_redacts_sensitive_command_values(self) -> None:
        rendered = cli_module._redact_command_for_stderr(
            [
                "az",
                "vm",
                "list-skus",
                "--subscription",
                "11111111-2222-3333-4444-555555555555",
                "API_KEY=secret-value",
            ]
        )
        self.assertIn("--subscription [redacted]", rendered)
        self.assertIn("API_KEY=[redacted]", rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("11111111-2222-3333-4444-555555555555", rendered)

    def test_machine_azure_discovery_records_method_and_live_overrides_offline_cache(
        self,
    ) -> None:
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
            manager = MachineManager(profile)
            with patch("aiplane.machines.shutil.which", return_value=None):
                offline = manager.discover_azure("uksouth", workload="inference_large", limit=2)
            self.assertEqual(offline["discovery"]["method"], "offline")
            self.assertTrue(offline["discovery"]["cache"]["written"])
            self.assertEqual(offline["discovery"]["cache"]["action"], "created")

            class Completed:
                returncode = 0
                stdout = json.dumps([{"name": "Standard_NC40ads_H100_v5"}])
                stderr = ""

            class PriceResponse:
                def __init__(self, payload):
                    self._payload = payload

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return None

                def read(self):
                    return json.dumps(self._payload).encode("utf-8")

            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", return_value=Completed()),
                patch("aiplane.machines.urlopen", return_value=PriceResponse({"Items": []})),
            ):
                live = manager.discover_azure("uksouth", workload="inference_large", limit=2)
            self.assertEqual(live["discovery"]["method"], "live")
            self.assertEqual(live["discovery"]["cache"]["previous_method"], "offline")
            self.assertEqual(live["discovery"]["cache"]["action"], "overrode_previous")
            cache = json.loads((root / "machine-discovery-cache.json").read_text(encoding="utf-8"))
            only_entry = next(iter(cache.values()))
            self.assertEqual(only_entry["discovery"]["method"], "live")
            self.assertEqual(
                only_entry["candidates"][0]["machine"]["stock"]["stock_sku"],
                "Standard_NC40ads_H100_v5",
            )

    def test_machine_cache_validate_and_azure_status_cli(self) -> None:
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
            manager = MachineManager(profile)
            manager.import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            self.assertTrue(manager.validate("azure_h100_test")["ok"])
            with patch("aiplane.machines.shutil.which", return_value=None):
                status = manager.azure_status(region="uksouth", run_sku_probe=True)
            self.assertFalse(status["cli_available"])

            class AccountCompleted:
                returncode = 0
                stdout = json.dumps(
                    {
                        "environmentName": "AzureCloud",
                        "state": "Enabled",
                        "isDefault": True,
                        "name": "Test Subscription",
                        "id": "sub-123",
                        "tenantId": "tenant-456",
                        "user": {"name": "user@example.com", "type": "user"},
                    }
                )
                stderr = ""

            with (
                patch("aiplane.machines.shutil.which", return_value="/usr/bin/az"),
                patch("aiplane.machines.subprocess.run", return_value=AccountCompleted()),
            ):
                logged_in = manager.azure_status()
            self.assertEqual(logged_in["account"]["user_name"], "[redacted]")
            self.assertEqual(logged_in["account"]["user_name_hint"], "[redacted]")
            self.assertEqual(logged_in["account"]["subscription_id"], "[redacted]")
            self.assertEqual(logged_in["account"]["subscription_id_hint"], "...-123")
            self.assertEqual(logged_in["account"]["tenant_id"], "[redacted]")
            self.assertEqual(logged_in["account"]["tenant_id_hint"], "...-456")
            self.assertTrue(logged_in["account"]["redacted"])
            with patch("aiplane.machines.shutil.which", return_value=None):
                manager.discover_azure("uksouth", workload="inference_large", limit=1)
            listed = manager.cache_list()
            self.assertEqual(len(listed["entries"]), 1)
            cleared = manager.cache_clear()
            self.assertEqual(cleared["remaining"], 0)

    def test_machine_azure_discovery_and_import_sku(self) -> None:
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
            manager = MachineManager(profile)
            with patch("aiplane.machines.shutil.which", return_value=None):
                discovered = manager.discover_azure("uksouth", workload="inference_large", limit=2)
            self.assertEqual(discovered["provider"], "azure")
            self.assertEqual(discovered["discovery"]["method"], "offline")
            self.assertTrue(discovered["candidates"])
            imported = manager.import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            self.assertEqual(imported["machine"]["stock"]["stock_sku"], "Standard_NC40ads_H100_v5")
            self.assertIn("azure_h100_test", {row["name"] for row in manager.list()})

    def test_hardware_use_template_copies_selected_values(self) -> None:
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
            manager = HardwareManager(profile)
            active = manager.use_template("nvidia_consumer_gpu", {"vram_gb": 16})
            self.assertEqual(active["origin"], "nvidia_consumer_gpu")
            self.assertTrue(active["custom"])
            self.assertEqual(active["values"]["vram_gb"], 16)
            self.assertEqual(
                source.hardware["hardware_profiles"]["nvidia_consumer_gpu"]["vram_gb"],
                "8-24",
            )
