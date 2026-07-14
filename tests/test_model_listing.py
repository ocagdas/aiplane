from __future__ import annotations

from .support import (
    BenchmarkRunner,
    HardwareManager,
    MachineManager,
    ModelCatalog,
    Path,
    Profile,
    ProviderRegistry,
    RuntimeCatalog,
    StringIO,
    _discovered_model_entry,
    _isolated_profiles_dir,
    _isolated_test_profile,
    _materialize_test_models,
    agent_config,
    cli_main,
    create_profile,
    group_model_rows,
    json,
    load_profile,
    os,
    patch,
    redirect_stdout,
    shutil,
    tempfile,
    unittest,
)


class ModelListingTests(unittest.TestCase):
    def test_model_defaults_can_be_shown_and_changed(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text("", encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(source.models)),
                targets=source.targets,
            )
            catalog = ModelCatalog(profile)
            self.assertEqual(
                catalog.default_model("self_managed_model")["name"],
                "fixture-analysis-small",
            )
            changed = catalog.set_default("self_managed_model", "fixture-code-small")
            self.assertEqual(changed["name"], "fixture-code-small")
            self.assertIn(
                "self_managed_model: fixture-code-small",
                (root / "models.yaml").read_text(encoding="utf-8"),
            )

    def test_model_output_groups_runtime_and_provider_kind_without_cli(self) -> None:
        with _isolated_test_profile() as profile:
            catalog = ModelCatalog(profile)
            rows = catalog.list()

            by_runtime = group_model_rows(profile, rows, "runtime")
            self.assertEqual(by_runtime["group_by"], "runtime")
            self.assertIn("vllm", by_runtime["groups"])
            self.assertIn("no_runtime", by_runtime["groups"])

            by_provider_kind = group_model_rows(profile, rows, "provider-kind")
            self.assertEqual(by_provider_kind["group_by"], "provider-kind")
            self.assertIn("self_managed", by_provider_kind["groups"])
            self.assertIn("managed_service", by_provider_kind["groups"])
            self.assertIn("ollama", by_provider_kind["groups"]["self_managed"])
            self.assertIn("openai", by_provider_kind["groups"]["managed_service"])

    def test_models_list_and_defaults_support_grouping(self) -> None:
        with _isolated_profiles_dir() as profiles_dir:
            profiles_arg = ["--profiles-dir", str(profiles_dir)]

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--group-by",
                        "provider",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["group_by"], "provider")
            self.assertIn("ollama", payload["groups"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--group-by",
                        "runtime",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIn("vllm", payload["groups"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--group-by",
                        "ownership",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["group_by"], "ownership")
            self.assertIn("self_managed", payload["groups"])
            self.assertIn("managed_service", payload["groups"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--group-by",
                        "provider-kind",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["group_by"], "provider-kind")
            self.assertIn("self_managed", payload["groups"])
            self.assertIn("ollama", payload["groups"]["self_managed"])
            self.assertIn("managed_service", payload["groups"])
            self.assertIn("openai", payload["groups"]["managed_service"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
                        "models",
                        "defaults",
                        "--profile",
                        "local-dev",
                        "--group-by",
                        "provider",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["group_by"], "provider")
            self.assertIn("ollama", payload["defaults"])

    def test_models_list_filters_sorts_and_limits_cli(self) -> None:
        with _isolated_profiles_dir() as profiles_dir:
            profiles_arg = ["--profiles-dir", str(profiles_dir)]

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--capability",
                        "code_generation>=3",
                        "--capability",
                        "debugging>=2",
                        "--self-managed-only",
                    ]
                )
            self.assertEqual(code, 0)
            rows = json.loads(stdout.getvalue())
            self.assertTrue(rows)
            self.assertTrue(all(row["ownership"] == "self_managed" for row in rows))
            self.assertIn("top_capabilities", rows[0])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    profiles_arg
                    + [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--capability",
                        "coding>=3",
                        "--vram-gb",
                        "96",
                        "--self-managed-only",
                        "--sort-by",
                        "avg",
                        "--limit",
                        "3",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertLessEqual(len(payload), 3)

    def test_models_list_can_filter_by_active_hardware(self) -> None:
        with _isolated_profiles_dir() as profiles_dir:
            profiles_arg = ["--profiles-dir", str(profiles_dir)]
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(profiles_arg + ["models", "list", "--profile", "local-dev", "--fits-hardware"])
            self.assertEqual(code, 0)
            rows = json.loads(stdout.getvalue())
            self.assertTrue(rows)
            machine = HardwareManager(load_profile("local-dev", Path.cwd(), profiles_dir=profiles_dir)).machine()
            memory = machine["memory"]["ram_gb"] or machine["memory"].get("unified_memory_gb")
            self.assertTrue(all(float(row.get("min_ram_gb") or 0) <= float(memory) for row in rows))

    def test_models_list_fits_hardware_treats_no_gpu_as_zero_vram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            create_profile("tmp", profiles_dir=profiles_dir)
            profile_root = profiles_dir / "tmp"
            models_config = {
                "models": {
                    "cpu_ok": {
                        "provider": "test_provider",
                        "model": "cpu-ok:1b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["ollama"],
                        "min_ram_gb": 8,
                        "min_vram_gb": 0,
                    },
                    "gpu_required": {
                        "provider": "test_provider",
                        "model": "gpu-required:7b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["ollama"],
                        "min_ram_gb": 8,
                        "min_vram_gb": 8,
                    },
                }
            }
            hardware_config = {
                "active": "local_auto",
                "selected": {
                    "origin": "local_auto",
                    "custom": False,
                    "values": {
                        "machine_tag": "local_auto",
                        "provider": "local",
                        "placement": "same_host",
                        "substrate": "native",
                        "cpu_architecture": "auto",
                        "cpu_cores": "auto",
                        "cpu_threads": "auto",
                        "memory_gb": 32,
                        "gpu_vendor": "none",
                        "gpu_model": "none",
                        "gpu_count": 0,
                        "vram_gb": 0,
                        "total_vram_gb": 0,
                        "memory_architecture": "discrete_or_system",
                    },
                },
                "hardware_profiles": {"local_auto": {}},
            }
            (profile_root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (profile_root / "hardware.yaml").write_text(agent_config.dump_yaml(hardware_config), encoding="utf-8")

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "list",
                        "--profile",
                        "tmp",
                        "--provider",
                        "test_provider",
                        "--role",
                        "chat",
                        "--fits-hardware",
                        "--enabled-only",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual([row["name"] for row in json.loads(stdout.getvalue())], ["cpu_ok"])

    def test_models_list_can_filter_by_named_machine_and_machine_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            create_profile("tmp", profiles_dir=profiles_dir)
            profile_root = profiles_dir / "tmp"
            models_config = {
                "models": {
                    "fits_t4": {
                        "provider": "test_provider",
                        "model": "example-7b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["vllm"],
                        "min_ram_gb": 16,
                        "min_vram_gb": 12,
                        "required_gpu_vendor": "nvidia",
                        "required_accelerator_apis": ["cuda"],
                    },
                    "too_large_for_t4": {
                        "provider": "test_provider",
                        "model": "example-14b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["vllm"],
                        "min_ram_gb": 32,
                        "min_vram_gb": 24,
                        "required_gpu_vendor": "nvidia",
                        "required_accelerator_apis": ["cuda"],
                    },
                    "wrong_accelerator": {
                        "provider": "test_provider",
                        "model": "example-7b-rocm",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["vllm"],
                        "min_ram_gb": 16,
                        "min_vram_gb": 8,
                        "required_gpu_vendor": "amd",
                        "required_accelerator_apis": ["rocm"],
                    },
                }
            }
            (profile_root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = load_profile("tmp", Path.cwd(), profiles_dir=profiles_dir)
            MachineManager(profile).import_azure_sku(
                "Standard_NC4as_T4_v3",
                "uksouth",
                name="azure_t4_test",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "list",
                        "--profile",
                        "tmp",
                        "--provider",
                        "test_provider",
                        "--runtime",
                        "vllm",
                        "--role",
                        "chat",
                        "--machine",
                        "azure_t4_test",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual([row["name"] for row in json.loads(stdout.getvalue())], ["fits_t4"])

    def test_models_list_fits_hardware_enforces_vendor_and_api_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            create_profile("tmp", profiles_dir=profiles_dir)
            profile_root = profiles_dir / "tmp"
            models_config = {
                "models": {
                    "amd_ok": {
                        "provider": "test_provider",
                        "model": "amd-ok:7b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["ollama"],
                        "min_ram_gb": 8,
                        "min_vram_gb": 8,
                        "required_gpu_vendor": "amd",
                        "required_accelerator_apis": ["rocm"],
                    },
                    "nvidia_only": {
                        "provider": "test_provider",
                        "model": "nvidia-only:7b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["ollama"],
                        "min_ram_gb": 8,
                        "min_vram_gb": 8,
                        "required_gpu_vendor": "nvidia",
                        "required_accelerator_apis": ["cuda"],
                    },
                }
            }
            hardware_config = {
                "active": "local_auto",
                "selected": {
                    "origin": "local_auto",
                    "custom": False,
                    "values": {
                        "machine_tag": "local_auto",
                        "provider": "local",
                        "placement": "same_host",
                        "substrate": "native",
                        "cpu_architecture": "auto",
                        "cpu_cores": "auto",
                        "cpu_threads": "auto",
                        "memory_gb": 32,
                        "gpu_vendor": "amd",
                        "gpu_model": "Radeon",
                        "gpu_count": 1,
                        "vram_gb": 16,
                        "total_vram_gb": 16,
                        "accelerator_apis": ["rocm"],
                    },
                },
                "hardware_profiles": {"local_auto": {}},
            }
            (profile_root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (profile_root / "hardware.yaml").write_text(agent_config.dump_yaml(hardware_config), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "list",
                        "--profile",
                        "tmp",
                        "--provider",
                        "test_provider",
                        "--role",
                        "chat",
                        "--fits-hardware",
                        "--enabled-only",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual([row["name"] for row in json.loads(stdout.getvalue())], ["amd_ok"])

    def test_models_list_fits_machine_shorthand_alias_matches_machine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            create_profile("tmp", profiles_dir=profiles_dir)
            profile_root = profiles_dir / "tmp"
            models_config = {
                "models": {
                    "fits_t4": {
                        "provider": "test_provider",
                        "model": "example-7b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["vllm"],
                        "min_ram_gb": 16,
                        "min_vram_gb": 12,
                        "required_gpu_vendor": "nvidia",
                        "required_accelerator_apis": ["cuda"],
                    },
                    "too_large_for_t4": {
                        "provider": "test_provider",
                        "model": "example-14b",
                        "enabled": True,
                        "roles": ["chat"],
                        "supported_runtimes": ["vllm"],
                        "min_ram_gb": 32,
                        "min_vram_gb": 24,
                        "required_gpu_vendor": "nvidia",
                        "required_accelerator_apis": ["cuda"],
                    },
                }
            }
            (profile_root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = load_profile("tmp", Path.cwd(), profiles_dir=profiles_dir)
            imported = MachineManager(profile).import_azure_sku(
                "Standard_NC4as_T4_v3",
                "uksouth",
                name="azure_t4_test",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "list",
                        "--profile",
                        "tmp",
                        "--provider",
                        "test_provider",
                        "--runtime",
                        "vllm",
                        "--role",
                        "chat",
                        "--fits-machine",
                        "azure_t4_test",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual([row["name"] for row in json.loads(stdout.getvalue())], ["fits_t4"])

            machine_path = root / "azure_t4_test.machine.json"
            machine_path.write_text(json.dumps(imported), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "list",
                        "--profile",
                        "tmp",
                        "--provider",
                        "test_provider",
                        "--runtime",
                        "vllm",
                        "--role",
                        "chat",
                        "--machine-file",
                        str(machine_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual([row["name"] for row in json.loads(stdout.getvalue())], ["fits_t4"])

    def test_models_list_name_only_supports_cli_alias_selection(self) -> None:
        with _isolated_profiles_dir() as profiles_dir:
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    ["--profiles-dir", str(profiles_dir)]
                    + [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--runtime",
                        "ollama",
                        "--role",
                        "chat",
                        "--name-only",
                        "--limit",
                        "2",
                    ]
                )
            self.assertEqual(code, 0)
            names = [line.strip() for line in stdout.getvalue().splitlines() if line.strip()]
            self.assertGreaterEqual(len(names), 1)
            self.assertTrue(all(line and "{" not in line and "}" not in line for line in names))

    def test_models_list_name_only_cannot_use_group_by(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--name-only",
                    "--group-by",
                    "runtime",
                    "--limit",
                    "2",
                ]
            )
        self.assertEqual(code, 1)

    def test_models_list_text_verbosity_zero_is_table(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--format",
                    "text",
                    "--verbosity",
                    "0",
                    "--limit",
                    "3",
                ]
            )
        self.assertEqual(code, 0)
        rows = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0], "models")
        self.assertIn("ALIAS", rows[1])
        self.assertIn("PROVIDER", rows[1])
        self.assertIn("MODEL", rows[1])

    def test_models_list_text_verbosity_one_falls_back_to_json_with_warning(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "list",
                    "--profile",
                    "local-dev",
                    "--format",
                    "text",
                    "--verbosity",
                    "1",
                    "--limit",
                    "3",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue().splitlines()
        self.assertTrue(output[0].startswith("Warning: models list --format text with verbosity 1+ uses JSON payload."))
        payload = json.loads("\n".join(output[1:]))
        self.assertIsInstance(payload, list)
        self.assertGreaterEqual(len(payload), 1)

    def test_models_list_filters_and_sorts_by_provider_popularity(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"huggingface": {"runtime": "vllm"}},
                "models": {},
            }
            discovered_config = {
                "models": {
                    "hf-low": {
                        "provider": "vllm",
                        "model": "org/low",
                        "source": "huggingface",
                        "roles": ["chat"],
                        "enabled": True,
                        "source_metadata": {"likes": 5, "downloads": 1000},
                    },
                    "hf-high": {
                        "provider": "vllm",
                        "model": "org/high",
                        "source": "huggingface",
                        "roles": ["chat"],
                        "enabled": True,
                        "source_metadata": {"likes": 50, "downloads": 500},
                    },
                    "hf-downloads": {
                        "provider": "vllm",
                        "model": "org/downloads",
                        "source": "huggingface",
                        "roles": ["embedding"],
                        "enabled": True,
                        "source_metadata": {"likes": 10, "downloads": "2,500"},
                    },
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(discovered_config), encoding="utf-8")
            profile = Profile(
                "tmp",
                root,
                Path.cwd(),
                source.hardware,
                source.backends,
                source.repository,
                source.tools,
                source.approvals,
                source.environment,
                models_config,
                source.targets,
                source.orchestrators,
            )

            catalog = ModelCatalog(profile)
            rows = catalog.sort_rows(catalog.filter({"roles": ["chat"], "min_likes": 10}), sort_by="likes")
            self.assertEqual([row["name"] for row in rows], ["hf-high"])
            self.assertEqual(rows[0]["likes"], 50)

            rows = catalog.sort_rows(catalog.filter({"source": "huggingface"}), sort_by="downloads")
            self.assertEqual(rows[0]["name"], "hf-downloads")
            self.assertEqual(rows[0]["downloads"], 2500)

    def test_models_pull_can_plan_huggingface_download(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "pull",
                    "--profile",
                    "local-dev",
                    "--source",
                    "huggingface",
                    "--model-id",
                    "Provider/Code-Large-Instruct",
                    "--for-runtime",
                    "vllm",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["source"], "huggingface")
        self.assertEqual(payload["runtime"], "vllm")
        self.assertIn("snapshot_download", " ".join(payload["command"]))

    def test_model_catalog_dry_run_analysis_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "sample.py"
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = ModelCatalog(profile).test_prompt("fixture-analysis-small", "analysis", target, dry_run=True)
            self.assertEqual(result.backend, "dry_run")
            self.assertIn("Explain what this code does", result.text)
            self.assertIn("def add", result.text)

    def test_model_benchmark_dry_run_reports_tasks_without_saving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            result = BenchmarkRunner(profile).run("fixture-analysis-small", task="all", dry_run=True, save=False)
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["summary"]["previewed"], 4)
            self.assertEqual(result["summary"]["average_score"], 0)
            self.assertTrue(all(row["passed"] is None for row in result["results"]))
            self.assertEqual(
                {row["task"] for row in result["results"]},
                {"analysis", "completion", "generation", "reasoning"},
            )
            self.assertNotIn("saved_to", result)

    def test_models_benchmark_cli_uses_positional_model_alias(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "models",
                    "benchmark",
                    "fixture-analysis-small",
                    "--dry-run",
                    "--no-save",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["model_name"], "fixture-analysis-small")
        self.assertEqual(payload["summary"]["previewed"], 4)

    def test_model_catalog_cloud_doctor_checks_env_var(self) -> None:
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
            "model": "managed-chat-model",
            "roles": ["analysis"],
            "local": False,
            "enabled": True,
        }
        statuses = {status.name: status for status in ModelCatalog(profile).doctor()}
        self.assertIn("OPENAI_API_KEY", statuses["openai-main"].reason)

    def test_managed_service_models_do_not_mix_into_runtime_groups(self) -> None:
        with _isolated_test_profile() as profile:
            profile.models["models"]["managed-chat-small"]["preferred_runtime"] = "ollama"
            profile.models["models"]["managed-chat-small"]["supported_runtimes"] = ["ollama"]
            catalog = ModelCatalog(profile)
            managed = catalog.show("managed-chat-small")
            self.assertEqual(managed["provider"], "openai")
            self.assertEqual(managed["ownership"], "managed_service")
            self.assertIsNone(managed["runtime"])
            self.assertIsNone(managed["runtime_endpoint"])
            self.assertEqual(managed["supported_runtimes"], [])
            self.assertFalse(catalog.filter({"runtime": "openai"}))
            ollama_matches = {row["name"] for row in catalog.filter({"runtime": "ollama"})}
            self.assertNotIn("managed-chat-small", ollama_matches)

            stdout = StringIO()
            with (
                patch("aiplane.cli.load_profile", return_value=profile),
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "models",
                        "list",
                        "--profile",
                        "local-dev",
                        "--group-by",
                        "runtime",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIn("no_runtime", payload["groups"])
            self.assertTrue(any(row["name"] == "managed-chat-small" for row in payload["groups"]["no_runtime"]))
            self.assertFalse(any(row["name"] == "managed-chat-small" for row in payload["groups"].get("ollama", [])))

            with self.assertRaisesRegex(ValueError, "managed-service model"):
                RuntimeCatalog(profile).set_preferred_runtime("managed-chat-small", "ollama")
            with self.assertRaisesRegex(ValueError, "cannot be bundled"):
                RuntimeCatalog(profile).bundle_plan("ollama", "managed-chat-small")
            with self.assertRaisesRegex(ValueError, "cannot define local runtime fields"):
                catalog.complete("managed-chat-small", "hello")

    def test_model_show_includes_provider_config(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        model = ModelCatalog(profile).show("fixture-analysis-small")
        self.assertEqual(model["provider"], "ollama")
        self.assertIn("endpoint", model["provider_config"])
        self.assertIn("capabilities", model)
        self.assertIn("benchmark_refs", model["capabilities"])

    def test_provider_models_can_query_azure_openai_with_named_credential(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cred_path = Path(tmp) / "credentials.yaml"
            cred_path.write_text(
                "providers:\n"
                "  azure_openai:\n"
                "    accounts:\n"
                "      business_a:\n"
                "        api_key: dummy-azure-key-value-123456\n",
                encoding="utf-8",
            )
            old = os.environ.get("AIPLANE_CREDENTIALS")
            os.environ["AIPLANE_CREDENTIALS"] = str(cred_path)
            profile = load_profile("local-dev", Path.cwd())
            profile.models["providers"]["azure_openai"]["endpoint"] = "https://example.openai.azure.com"
            profile.models["providers"]["azure_openai"]["credential_ref"] = "azure_openai.business_a"
            payload = {"data": [{"id": "news-deployment", "model": "managed-chat-model"}]}

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(payload).encode("utf-8")

            try:
                with patch("aiplane.boundaries.urlopen", return_value=FakeResponse()) as opened:
                    result = ProviderRegistry(profile).models("azure_openai", online=True, limit=5)
                self.assertEqual(result.models, ["news-deployment"])
                self.assertEqual(
                    opened.call_args.args[0].headers.get("Api-key"),
                    "dummy-azure-key-value-123456",
                )
            finally:
                if old is None:
                    os.environ.pop("AIPLANE_CREDENTIALS", None)
                else:
                    os.environ["AIPLANE_CREDENTIALS"] = old

    def test_models_list_can_rank_and_limit_by_repeated_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            _materialize_test_models(profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "list",
                        "--runtime",
                        "ollama",
                        "--role",
                        "chat",
                        "--role",
                        "autocomplete",
                        "--enabled-only",
                        "--sort-by",
                        "role",
                        "--limit",
                        "2",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(len(payload), 2)
        self.assertIn("role_score", payload[0])
        self.assertGreaterEqual(payload[0]["role_score"], payload[1]["role_score"])

    def test_models_enable_disable_cli_updates_profile_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            shutil.copytree(Path("profile-templates") / "local-dev", profiles_dir / "local-dev")
            _materialize_test_models(profiles_dir / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "disable",
                        "fixture-analysis-small",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["enabled"])
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=profiles_dir)
            self.assertFalse(ModelCatalog(profile).show("fixture-analysis-small")["enabled"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "enable",
                        "fixture-analysis-small",
                    ]
                )
            self.assertEqual(code, 0)
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=profiles_dir)
            self.assertTrue(ModelCatalog(profile).show("fixture-analysis-small")["enabled"])

    def test_disabled_general_candidate_is_configured(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        general_row = ModelCatalog(profile).show("fixture-general-small")
        self.assertEqual(general_row["model"], "provider-general-small:3b")
        self.assertFalse(general_row["enabled"])

    def test_models_list_rows_include_resource_requirements(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "models": {
                    "gpu_model": {
                        "provider": "vllm",
                        "source": "huggingface",
                        "model": "org/model-7b",
                        "enabled": True,
                        "min_ram_gb": 16,
                        "recommended_ram_gb": 32,
                        "min_vram_gb": 8,
                        "recommended_vram_gb": 16,
                        "resource_estimate_source": "configured",
                        "required_gpu_vendor": "nvidia",
                        "required_accelerator_apis": ["cuda"],
                    }
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            rows = ModelCatalog(profile).filter({"gpu_vendor": "nvidia", "accelerator_api": "cuda"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["min_ram_gb"], 16.0)
        self.assertEqual(rows[0]["recommended_ram_gb"], 32.0)
        self.assertEqual(rows[0]["min_vram_gb"], 8.0)
        self.assertEqual(rows[0]["recommended_vram_gb"], 16.0)
        self.assertEqual(rows[0]["resource_estimate_source"], "configured")
        self.assertEqual(rows[0]["gpu_vendor_requirement"], "nvidia")
        self.assertEqual(rows[0]["accelerator_api_requirements"], ["cuda"])
        self.assertEqual(ModelCatalog(profile).filter({"gpu_vendor": "amd"}), [])

    def test_discovered_model_resource_requirements_are_marked_as_heuristic(
        self,
    ) -> None:
        entry = _discovered_model_entry("ollama", "example-model:7b", enable=True)
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"models": {}}
            generated_config = {"models": {"ollama-example-model-7b": entry}}
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            rows = ModelCatalog(profile).filter({"max_min_ram_gb": 64, "max_min_vram_gb": 64})
        self.assertEqual(
            rows[0]["resource_estimate_source"],
            "catalog_heuristic:parameter_size_and_role",
        )
        self.assertEqual(rows[0]["min_ram_gb"], entry["min_ram_gb"])
        self.assertEqual(rows[0]["min_vram_gb"], entry["min_vram_gb"])
        self.assertEqual(rows[0]["gpu_vendor_requirement"], "generic")

    def test_discovered_model_resource_requirements_can_come_from_provider_metadata(
        self,
    ) -> None:
        entry = _discovered_model_entry(
            "huggingface",
            "org/example-model",
            enable=True,
            source_metadata={
                "min_ram_gb": 24,
                "min_vram_gb": 10,
                "resource_estimate_source": "provider_catalog:huggingface_metadata",
            },
        )
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"models": {}}
            generated_config = {"models": {"huggingface-org-example-model": entry}}
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            rows = ModelCatalog(profile).filter({"max_min_ram_gb": 64, "max_min_vram_gb": 64})
        self.assertEqual(rows[0]["min_ram_gb"], 24.0)
        self.assertEqual(rows[0]["min_vram_gb"], 10.0)
        self.assertEqual(rows[0]["resource_estimate_source"], "provider_catalog:huggingface_metadata")

    def test_models_list_can_filter_and_sort_by_parameter_count(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "models": {
                    "small": {
                        "provider": "ollama",
                        "model": "example:3b",
                        "enabled": True,
                        "roles": ["chat"],
                    },
                    "medium": {
                        "provider": "ollama",
                        "model": "example:14b",
                        "enabled": True,
                        "roles": ["chat"],
                    },
                    "large": {
                        "provider": "ollama",
                        "model": "example:40B",
                        "enabled": True,
                        "roles": ["chat"],
                    },
                    "unknown": {
                        "provider": "ollama",
                        "model": "example:latest",
                        "enabled": True,
                        "roles": ["chat"],
                    },
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=models_config,
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            catalog = ModelCatalog(profile)
            rows = catalog.filter({"min_parameters_b": 7, "max_parameters_b": 35})
            sorted_rows = catalog.sort_rows(rows, sort_by="parameters")
        self.assertEqual([row["name"] for row in sorted_rows], ["medium"])
        self.assertEqual(sorted_rows[0]["parameter_count_b"], 14.0)

    def test_models_filter_can_require_saved_benchmark_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = workspace / ".aiplane" / "benchmarks"
            root.mkdir(parents=True)
            (root / "20260101T000000Z-fixture-analysis-small.json").write_text(
                json.dumps({"summary": {"average_score": 91, "passed": 1, "failed": 0}}),
                encoding="utf-8",
            )
            profile = load_profile("local-dev", workspace)
            rows = ModelCatalog(profile).filter({"min_benchmark_score": 90})
        names = {row["name"] for row in rows}
        self.assertIn("fixture-analysis-small", names)
