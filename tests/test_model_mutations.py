from __future__ import annotations

from .support import (
    ModelCatalog,
    Path,
    Profile,
    StringIO,
    agent_config,
    cli_main,
    json,
    load_profile,
    redirect_stdout,
    tempfile,
    unittest,
)


class ModelMutationTests(unittest.TestCase):
    def test_models_add_writes_curated_profile_entry(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {},
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "ollama-llama3-2-3b": {
                                "provider": "ollama",
                                "model": "llama3.2:3b",
                                "roles": ["chat", "analysis"],
                                "supported_runtimes": ["ollama"],
                                "capability_scores": {
                                    "general_chat": 4,
                                    "code_generation": 3,
                                },
                                "capability_score_source": "catalog_heuristic",
                                "imported_by": "aiplane_refresh",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
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

            result = ModelCatalog(profile).add_model(
                "local_chat",
                provider="ollama",
                model_id="llama3.2:3b",
                roles=["chat"],
                supported_runtimes=["ollama"],
                preferred_runtime="ollama",
                notes="Local chat model",
                settings={"min_ram_gb": 8, "min_vram_gb": 0},
                write=True,
            )

            self.assertEqual(result["added"], 1)
            self.assertEqual(result["discovered_entry"], "ollama-llama3-2-3b")
            self.assertEqual(result["model"]["model"], "llama3.2:3b")
            self.assertEqual(result["model"]["discovered_entry"], "ollama-llama3-2-3b")
            self.assertEqual(result["model"]["capability_scores"]["general_chat"], 4)
            self.assertEqual(result["model"]["capability_score_source"], "catalog_heuristic")
            written = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("local_chat:", written)
            self.assertIn("discovered_entry: ollama-llama3-2-3b", written)
            self.assertIn("roles: [chat]", written)
            self.assertIn("min_ram_gb: 8", written)

    def test_models_add_can_create_direct_local_file_entry(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"providers": {}, "models": {}}
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
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
            result = ModelCatalog(profile).add_model(
                "local_gguf",
                provider="local_file",
                model_id="/models/mistral.Q4_K_M.gguf",
                roles=["chat", "analysis"],
                supported_runtimes=["llamacpp"],
                notes="Local GGUF on this machine",
                write=True,
            )
            written = (root / "models.yaml").read_text(encoding="utf-8")
        self.assertEqual(result["added"], 1)
        self.assertIsNone(result["discovered_entry"])
        self.assertEqual(result["model"]["provider"], "local_file")
        self.assertEqual(result["model"]["source"], "local_file")
        self.assertEqual(result["model"]["model"], "/models/mistral.Q4_K_M.gguf")
        self.assertEqual(result["model"]["preferred_runtime"], "llamacpp")
        self.assertIn("local_gguf:", written)
        self.assertNotIn("discovered_entry", written)

    def test_models_add_can_use_discovered_entry_name_and_rejects_missing_discovery(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {},
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "ollama-llama3-2-3b": {
                                "provider": "ollama",
                                "model": "llama3.2:3b",
                                "roles": ["chat", "analysis"],
                                "supported_runtimes": ["ollama"],
                                "imported_by": "aiplane_refresh",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
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

            result = ModelCatalog(profile).add_model(
                "local_chat",
                discovered_name="ollama-llama3-2-3b",
                roles=["chat"],
                write=False,
            )
            self.assertEqual(result["model"]["model"], "llama3.2:3b")
            self.assertEqual(result["model"]["discovered_entry"], "ollama-llama3-2-3b")

            with self.assertRaisesRegex(ValueError, "discovered model entry not found"):
                ModelCatalog(profile).add_model("missing", provider="ollama", model_id="missing:1b", write=False)
            with self.assertRaisesRegex(ValueError, "discovered model entry not found"):
                ModelCatalog(profile).add_model("missing", discovered_name="ollama-missing", write=False)

    def test_models_remove_deletes_profile_owned_alias_by_name(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "defaults": {"chat_model": "curated_local"},
                "models": {
                    "curated_local": {
                        "provider": "local_file",
                        "model": "/models/a.gguf",
                        "enabled": True,
                    }
                },
            }
            generated_config = {
                "models": {
                    "discovered_local": {
                        "provider": "local_file",
                        "source": "local_file",
                        "model": "/models/b.gguf",
                        "imported_by": "aiplane_refresh",
                    }
                }
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
            (root / "models.discovered.yaml").write_text(agent_config.dump_yaml(generated_config), encoding="utf-8")
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
            preview = ModelCatalog(profile).remove_model("curated_local", write=False)
            self.assertTrue(preview["would_remove_curated"])
            self.assertEqual(preview["would_remove_defaults"], ["chat_model"])
            removed = ModelCatalog(profile).remove_model("curated_local", write=True)
            self.assertTrue(removed["removed_curated"])
            self.assertEqual(removed["removed_defaults"], ["chat_model"])
            curated_text = (root / "models.yaml").read_text(encoding="utf-8")
            discovered_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
        self.assertNotIn("curated_local:", curated_text)
        self.assertNotIn("chat_model:", curated_text)
        self.assertIn("discovered_local:", discovered_text)

    def test_models_remove_cli_dry_run_reports_profile_owned_alias(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "defaults": {"local_file_model": "local_gguf"},
                        "models": {
                            "local_gguf": {
                                "provider": "local_file",
                                "source": "local_file",
                                "model": "/models/mistral.Q4_K_M.gguf",
                                "enabled": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "remove",
                        "--profile",
                        "tmp",
                        "local_gguf",
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "model_catalog_remove")
        self.assertTrue(payload["would_remove_curated"])
        self.assertEqual(payload["would_remove_defaults"], ["local_file_model"])

    def test_models_add_cli_accepts_local_file_without_discovery(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(
                agent_config.dump_yaml({"defaults": {}, "models": {}}), encoding="utf-8"
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "add",
                        "--profile",
                        "tmp",
                        "local_gguf",
                        "--provider",
                        "local_file",
                        "--model",
                        "/models/mistral.Q4_K_M.gguf",
                        "--runtime",
                        "llamacpp",
                        "--role",
                        "chat",
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["would_add"], 1)
        self.assertIsNone(payload["discovered_entry"])
        self.assertEqual(payload["model"]["provider"], "local_file")
        self.assertEqual(payload["model"]["preferred_runtime"], "llamacpp")

    def test_models_clone_creates_second_entry_with_overrides(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {
                    "local_chat": {
                        "provider": "ollama",
                        "model": "llama3.2:3b",
                        "roles": ["chat"],
                        "enabled": True,
                    }
                },
            }
            (root / "models.yaml").write_text(agent_config.dump_yaml(models_config), encoding="utf-8")
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

            result = ModelCatalog(profile).clone_model(
                "local_chat",
                "local_fast_draft",
                roles=["completion"],
                notes="Fast draft model for local coding tasks.",
                write=True,
            )

            self.assertEqual(result["cloned"], 1)
            self.assertEqual(result["model"]["model"], "llama3.2:3b")
            self.assertEqual(result["model"]["roles"], ["completion"])
            written = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("local_fast_draft:", written)
            self.assertIn("cloned_from: local_chat", written)
            self.assertIn("Fast draft model", written)

    def test_models_add_cli_dry_run_does_not_write(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(
                agent_config.dump_yaml({"providers": {"ollama": {"runtime": "ollama"}}, "models": {}}),
                encoding="utf-8",
            )
            (profile_root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "ollama-llama3-2-3b": {
                                "provider": "ollama",
                                "model": "llama3.2:3b",
                                "source": "ollama",
                                "roles": ["chat", "analysis"],
                                "supported_runtimes": ["ollama"],
                                "imported_by": "aiplane_refresh",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "add",
                        "--profile",
                        "tmp",
                        "local_chat",
                        "--provider",
                        "ollama",
                        "--model",
                        "llama3.2:3b",
                        "--role",
                        "chat",
                        "--runtime",
                        "ollama",
                        "--set",
                        "min_ram_gb=8",
                        "--dry-run",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["would_add"], 1)
            self.assertEqual(payload["discovered_entry"], "ollama-llama3-2-3b")
            self.assertEqual(payload["model"]["discovered_entry"], "ollama-llama3-2-3b")
            self.assertNotIn("capability_scores", payload["model"])
            self.assertIn("without --dry-run", payload["next_steps"][0])
            self.assertNotIn(
                "local_chat:",
                (profile_root / "models.yaml").read_text(encoding="utf-8"),
            )

    def test_models_promote_cli_dry_run(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            profile_root = profiles_dir / "tmp"
            profile_root.mkdir(parents=True)
            for name, data in {
                "hardware.yaml": source.hardware,
                "backends.yaml": source.backends,
                "repository.yaml": source.repository,
                "tools.yaml": source.tools,
                "approvals.yaml": source.approvals,
                "environment.yaml": source.environment,
                "targets.yaml": source.targets,
                "orchestrators.yaml": source.orchestrators,
            }.items():
                (profile_root / name).write_text(agent_config.dump_yaml(data), encoding="utf-8")
            (profile_root / "models.yaml").write_text(
                agent_config.dump_yaml({"providers": {"ollama": {"runtime": "ollama"}}, "models": {}}),
                encoding="utf-8",
            )
            (profile_root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(
                    {
                        "models": {
                            "generated-provider-chat": {
                                "provider": "ollama",
                                "model": "provider-text-small:0.5b",
                                "source": "ollama",
                                "enabled": True,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "models",
                        "promote",
                        "--profile",
                        "tmp",
                        "generated-provider-chat",
                        "--as",
                        "reviewed-provider-chat",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["name"], "model_catalog_promote")
            self.assertEqual(payload["target"], "reviewed-provider-chat")
            self.assertEqual(payload["would_promote"], 1)
            self.assertIn("next_steps", payload)
            self.assertTrue(payload["keep_discovered"])
            self.assertIn("without --dry-run", payload["next_steps"][0])
