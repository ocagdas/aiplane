from __future__ import annotations

from .support import (
    BenchmarkRunner,
    HardwareManager,
    MachineManager,
    ModelCatalog,
    Path,
    Profile,
    ProviderModelsResult,
    ProviderRegistry,
    RuntimeCatalog,
    StringIO,
    _discovered_model_entry,
    _isolated_profiles_dir,
    _isolated_test_profile,
    agent_config,
    cli_main,
    create_profile,
    group_model_rows,
    json,
    load_profile,
    os,
    parse_yaml,
    patch,
    redirect_stderr,
    redirect_stdout,
    shutil,
    tempfile,
    unittest,
)


class ModelProviderTests(unittest.TestCase):
    def test_models_help_lists_clear_cache_command(self) -> None:
        stdout = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stdout(stdout):
                cli_main(["models", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("clear-cache", stdout.getvalue())

    def test_model_catalog_lists_default_models(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        rows = ModelCatalog(profile).list()
        names = {row["name"] for row in rows}
        self.assertIn("fixture-analysis-small", names)
        self.assertNotIn("openai-main", names)
        self.assertIn("local-reasoning-xl", names)
        self.assertIn("codelocal-chat-large", names)
        analysis_model = next(row for row in rows if row["name"] == "fixture-analysis-small")
        self.assertIn("capabilities", analysis_model)
        self.assertEqual(analysis_model["capabilities"]["score_scale"], "0-5")
        self.assertIn("code_generation", analysis_model["capabilities"]["scores"])

    def test_continue_visible_ollama_models_have_catalog_roles(self) -> None:
        with _isolated_test_profile() as profile:
            catalog = ModelCatalog(profile)

            llama = catalog.show("fixture-chat-small")
            self.assertEqual(llama["model"], "provider-chat-small:8b")
            self.assertIn("chat", llama["roles"])

            code_base = catalog.show("fixture-code-base")
            self.assertEqual(code_base["model"], "provider-code-base:1.5b")
            self.assertIn("autocomplete", code_base["roles"])
            self.assertGreaterEqual(code_base["capabilities"]["scores"]["code_completion"], 3)

            embedding_row = catalog.show("fixture-embedding-small")
            self.assertEqual(embedding_row["model"], "fixture-embedding-small:latest")
            self.assertIn("embedding", embedding_row["roles"])
            self.assertEqual(embedding_row["capabilities"]["scores"]["embedding"], 5)

            autocomplete_rows = catalog.filter({"role": "autocomplete"})
            self.assertIn("fixture-code-base", {row["name"] for row in autocomplete_rows})
            embedding_rows = catalog.filter({"role": "embedding"})
            self.assertIn("fixture-embedding-small", {row["name"] for row in embedding_rows})

    def test_model_catalog_refresh_imports_provider_discovered_models(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config.setdefault("models", {})["fixture-chat-small"] = {
            "provider": "ollama",
            "model": "provider-chat-small:8b",
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            )
            discovered = ProviderModelsResult(
                provider="ollama",
                source="provider_api",
                models=[
                    "provider-chat-small:8b",
                    "new-embed-model:latest",
                    "new-coder:1b-base",
                ],
                reason="test discovery",
            )
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                preview = ModelCatalog(profile).refresh("ollama", write=False, verbose=True)
                self.assertEqual(preview["changes"]["would_import"], 2)
                self.assertEqual(preview["results"]["ollama"]["source_models_returned"], 3)
                self.assertEqual(preview["results"]["ollama"]["source_models_already_profiled"], 1)
                self.assertEqual(preview["results"]["ollama"]["source_models_to_import"], 2)
                self.assertEqual(preview["changes"]["would_remove"], 0)
                self.assertNotIn("catalog", preview)
                rows = preview["results"]["ollama"]["model_changes"]
                imported_preview = {row["name"]: row for row in rows if row["refresh_status"] == "would_import"}
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["suitable_runtimes"],
                    ["ollama"],
                )
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["preferred_runtime"],
                    "ollama",
                )
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["ownership"],
                    "self_managed",
                )
                self.assertEqual(
                    imported_preview["ollama-new-embed-model-latest"]["local_presence"],
                    "pulled",
                )
                self.assertFalse((root / "models.yaml").exists())

                written = ModelCatalog(profile).refresh("ollama", write=True, verbose=True)

            self.assertEqual(written["changes"]["imported"], 2)
            self.assertEqual(written["changes"]["removed"], 0)
            self.assertTrue((root / "models.discovered.yaml").exists())
            if (root / "models.yaml").exists():
                self.assertIn(
                    "fixture-chat-small:",
                    (root / "models.yaml").read_text(encoding="utf-8"),
                )
            rows = written["results"]["ollama"]["model_changes"]
            names = {row["name"] for row in rows}
            self.assertIn("ollama-new-embed-model-latest", names)
            self.assertIn("ollama-new-coder-1b-base", names)
            discovered_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
            self.assertIn("This file is generated by aiplane model discovery", discovered_text)
            self.assertIn("Do not edit it manually", discovered_text)
            self.assertIn("enabled: true", discovered_text)

    def test_models_refresh_default_omits_provider_and_per_model_sections(self) -> None:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:1b"], "test discovery")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "ollama",
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["changes"]["would_import"], 1)
        self.assertNotIn("results", payload)
        self.assertNotIn("provider_summary", payload)
        self.assertEqual(payload["verbosity"], 0)

    def test_models_refresh_verbosity_one_adds_provider_summary(self) -> None:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:1b"], "test discovery")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "ollama",
                        "--dry-run",
                        "--verbosity",
                        "1",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertNotIn("results", payload)
        self.assertEqual(payload["verbosity"], 1)
        self.assertEqual(payload["provider_summary"][0]["provider"], "ollama")
        self.assertGreaterEqual(payload["provider_summary"][0]["model_changes_count"], 1)
        self.assertEqual(payload["provider_summary"][0]["changes"]["would_import"], 1)

    def test_models_refresh_cli_reports_configured_provider_failure_as_json(
        self,
    ) -> None:
        with patch.dict(os.environ, {"AZURE_OPENAI_ENDPOINT": "", "AZURE_OPENAI_API_KEY": ""}):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "azure_openai",
                        "--dry-run",
                        "--verbosity",
                        "1",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["changes"]["would_import"], 0)
        summary = payload["provider_summary"][0]
        self.assertEqual(summary["provider"], "azure_openai")
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["source_contacted"], False)
        self.assertIn("Azure OpenAI discovery needs", summary["error"])
        self.assertIn("providers show azure_openai", payload["next_steps"][0])

    def test_models_refresh_cli_previews_with_mocked_provider(self) -> None:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:1b"], "test discovery")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "ollama",
                        "--dry-run",
                        "--verbosity",
                        "2",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["changes"]["would_import"], 1)
        self.assertNotIn("catalog", payload)
        rows = payload["results"]["ollama"]["model_changes"]
        imported = [row for row in rows if row["refresh_status"] == "would_import"]
        self.assertEqual(imported[0]["suitable_runtimes"], ["ollama"])
        self.assertEqual(imported[0]["ownership"], "self_managed")
        self.assertFalse(payload["write"])

    def test_models_refresh_cli_can_disable_new_imports_and_groups_provider_results(
        self,
    ) -> None:
        discovered = ProviderModelsResult("ollama", "provider_api", ["new-model:1b"], "test discovery")
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "models",
                        "refresh",
                        "--profile",
                        "local-dev",
                        "--provider",
                        "ollama",
                        "--disable-new",
                        "--dry-run",
                        "--verbosity",
                        "2",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["write"])
        self.assertFalse(payload["new_entries_enabled"])
        imported = [
            row for row in payload["results"]["ollama"]["model_changes"] if row["refresh_status"] == "would_import"
        ]
        self.assertEqual(imported[0]["enabled"], False)

    def test_models_refresh_all_reports_mocked_provider_success_and_failure(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            name: model
            for name, model in models_config["models"].items()
            if name in {"fixture-analysis-small", "provider-code-large-vllm"}
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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

            def fake_models(provider: str, **kwargs) -> ProviderModelsResult:
                if provider == "ollama":
                    return ProviderModelsResult("ollama", "provider_api", ["fresh:1b"], "mock ok")
                if provider == "huggingface":
                    raise RuntimeError("mock failure")
                return ProviderModelsResult(provider, "profile_catalog", [], "empty")

            with patch.object(ProviderRegistry, "models", side_effect=fake_models):
                result = ModelCatalog(profile).refresh_all(write=False)
        self.assertGreaterEqual(result["providers_total"], 2)
        self.assertEqual(result["providers_failed"], 1)
        self.assertEqual(result["results"]["ollama"]["ownership"], "self_managed")
        self.assertEqual(result["results"]["ollama"]["status"], "would_update")
        self.assertEqual(result["results"]["huggingface"]["ownership"], "self_managed")
        self.assertEqual(result["results"]["huggingface"]["status"], "failed")
        self.assertNotIn("catalog", result)

    def test_models_refresh_all_still_uses_model_providers_after_catalog_clear(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {"curated": {"provider": "ollama", "model": "curated:1b", "enabled": True}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(source.root, root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            profile.models["models"] = models_config["models"]
            catalog = ModelCatalog(profile)
            catalog.clear_imported(write=False, include_curated=True)
            discovered = ProviderModelsResult("ollama", "source_api", ["fresh:1b"], "mock ok")

            def fake_models(provider: str, **kwargs) -> ProviderModelsResult:
                if provider == "ollama":
                    return discovered
                return ProviderModelsResult(provider, "profile_catalog", [], "empty")

            with patch.object(ProviderRegistry, "models", side_effect=fake_models):
                result = catalog.refresh_all(write=False)
        self.assertIn("ollama", result["results"])
        self.assertEqual(result["results"]["ollama"]["source_discovery_method"], "source_api")
        self.assertEqual(result["results"]["ollama"]["source_models_to_import"], 1)

    def test_models_enable_disable_rejects_discovered_cache_entry(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {"models": {}}
            generated_config = {
                "models": {
                    "discovered_local": {
                        "provider": "ollama",
                        "source": "ollama",
                        "model": "llama3.2:3b",
                        "enabled": True,
                        "imported_by": "aiplane_refresh",
                    }
                }
            }
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
            with self.assertRaisesRegex(ValueError, "discovered model entry is cache state"):
                ModelCatalog(profile).set_enabled("discovered_local", False)
            discovered_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
        self.assertIn("enabled: true", discovered_text)

    def test_models_refresh_reset_cache_previews_clear_before_refresh(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles_dir = root / "profiles"
            shutil.copytree(source.root, profiles_dir / "local-dev")
            profile_root = profiles_dir / "local-dev"
            discovered_config = {
                "models": {
                    "ollama-old-model-latest": {
                        "provider": "ollama",
                        "source": "ollama",
                        "model": "old-model:latest",
                        "enabled": True,
                        "imported_by": "aiplane_refresh",
                    }
                }
            }
            (profile_root / "models.discovered.yaml").write_text(
                agent_config.dump_yaml(discovered_config),
                encoding="utf-8",
            )
            discovered = ProviderModelsResult("ollama", "provider_api", ["fresh:1b"], "mock ok")
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                stdout = StringIO()
                with redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "models",
                            "refresh",
                            "--profile",
                            "local-dev",
                            "--provider",
                            "ollama",
                            "--reset-cache",
                            "--dry-run",
                            "--verbosity",
                            "2",
                        ]
                    )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["reset_cache"]["name"], "model_catalog_clear_cache")
        self.assertEqual(payload["reset_cache"]["provider"], "ollama")
        self.assertGreaterEqual(payload["reset_cache"]["would_remove"], 1)
        self.assertIn(
            {"name": "ollama", "count": payload["reset_cache"]["would_remove"]},
            payload["reset_cache"]["provider_counts"],
        )
        self.assertEqual(payload["changes"]["would_import"], 1)

    def test_model_catalog_clear_cache_removes_only_refresh_imports(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {"curated": {"provider": "ollama", "model": "curated:1b", "enabled": True}}
        for index in range(55):
            models_config["models"][f"imported-{index:02d}"] = {
                "provider": "vllm",
                "source": "huggingface",
                "model": f"org/model-{index:02d}",
                "enabled": True,
                "imported_by": "aiplane_refresh",
            }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            preview = ModelCatalog(profile).clear_imported(write=False)
            self.assertEqual(preview["would_remove"], 56)
            self.assertEqual(
                preview["provider_counts"],
                [{"name": "huggingface", "count": 55}, {"name": "ollama", "count": 1}],
            )
            self.assertEqual(preview["curated_provider_counts"], [{"name": "ollama", "count": 1}])
            self.assertTrue(preview["include_curated"])
            self.assertNotIn("model_changes", preview)

            keep_curated = ModelCatalog(profile).clear_imported(write=False, include_curated=False)
            self.assertEqual(keep_curated["would_remove"], 55)
            self.assertEqual(keep_curated["provider_counts"], [{"name": "huggingface", "count": 55}])
            self.assertEqual(keep_curated["curated_provider_counts"], [])
            self.assertFalse(keep_curated["include_curated"])

            written = ModelCatalog(profile).clear_imported(write=True, include_curated=False)
            self.assertEqual(written["removed"], 55)
            self.assertEqual(written["provider_counts"], [{"name": "huggingface", "count": 55}])
            self.assertEqual(written["curated_provider_counts"], [])
            written_text = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("curated:", written_text)
            self.assertNotIn("imported-00:", written_text)

    def test_discovered_huggingface_image_classifier_does_not_default_to_chat_roles(
        self,
    ) -> None:
        entry = _discovered_model_entry(
            "huggingface",
            "AdamCodd/vit-base-nsfw-detector",
            enable=True,
            source_metadata={"pipeline_tag": "image-classification"},
        )
        self.assertEqual(entry["roles"], ["image_classification"])
        self.assertNotIn("chat", entry["roles"])
        self.assertEqual(entry["preferred_runtime"], "vllm")

    def test_discovered_huggingface_media_pipeline_tags_map_to_media_roles(
        self,
    ) -> None:
        cases = [
            ({"pipeline_tag": "text-to-speech"}, "text_to_speech", "transformers", 0),
            ({"pipeline_tag": "text-to-image"}, "image_generation", "diffusers", 12),
            ({"pipeline_tag": "text-to-video"}, "video_generation", "diffusers", 8),
        ]
        for metadata, role, runtime, min_vram in cases:
            with self.subTest(role=role):
                entry = _discovered_model_entry("huggingface", f"org/{role}", enable=False, source_metadata=metadata)
                self.assertEqual(entry["roles"], [role])
                self.assertEqual(entry["source"], "huggingface")
                self.assertEqual(entry["provider"], runtime)
                self.assertEqual(entry["preferred_runtime"], runtime)
                if role == "image_generation" or role == "video_generation":
                    self.assertEqual(entry["supported_runtimes"], ["diffusers", "comfyui"])
                if role == "text_to_speech":
                    self.assertEqual(entry["supported_runtimes"], ["transformers"])
                self.assertEqual(entry["min_vram_gb"], min_vram)
                self.assertGreater(entry["capability_scores"][role], 0)
                self.assertFalse(entry["enabled"])

    def test_models_promote_generated_moves_alias_to_curated_catalog(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {},
            }
            generated_config = {
                "models": {
                    "generated-provider-chat": {
                        "provider": "ollama",
                        "model": "provider-text-small:0.5b",
                        "source": "ollama",
                        "roles": ["chat"],
                        "enabled": True,
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

            preview = ModelCatalog(profile).promote_generated(
                "generated-provider-chat",
                new_name="reviewed-provider-chat",
                write=False,
            )
            self.assertEqual(preview["would_promote"], 1)
            self.assertIn("next_steps", preview)
            self.assertIn("without --dry-run", preview["next_steps"][0])
            self.assertIn(
                "generated-provider-chat",
                (root / "models.discovered.yaml").read_text(encoding="utf-8"),
            )

            written = ModelCatalog(profile).promote_generated(
                "generated-provider-chat", new_name="reviewed-provider-chat", write=True
            )
            self.assertEqual(written["promoted"], 1)
            self.assertIn("next_steps", written)
            self.assertIn("models.yaml", written["next_steps"][0])
            curated_text = (root / "models.yaml").read_text(encoding="utf-8")
            generated_text = (root / "models.discovered.yaml").read_text(encoding="utf-8")
            self.assertIn("reviewed-provider-chat:", curated_text)
            self.assertIn("promoted_from: generated-provider-chat", curated_text)
            self.assertIn("discovered_entry: generated-provider-chat", curated_text)
            self.assertNotIn("imported_by", curated_text)
            self.assertIn("generated-provider-chat:", generated_text)

    def test_models_promote_refuses_curated_alias_collision_without_overwrite(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models_config = {
                "providers": {"ollama": {"runtime": "ollama"}},
                "models": {
                    "generated-provider-chat": {
                        "provider": "ollama",
                        "model": "existing",
                        "source": "ollama",
                        "enabled": True,
                    }
                },
            }
            generated_config = {
                "models": {
                    "generated-provider-chat": {
                        "provider": "ollama",
                        "model": "provider-text-small:0.5b",
                        "source": "ollama",
                        "enabled": True,
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

            with self.assertRaises(ValueError):
                ModelCatalog(profile).promote_generated("generated-provider-chat", write=False)

            preview = ModelCatalog(profile).promote_generated("generated-provider-chat", write=False, overwrite=True)
            self.assertTrue(preview["target_exists"])
            self.assertTrue(preview["overwrite"])

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

    def test_refresh_verbose_rows_use_model_source_and_runtime_endpoint_names(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            "speech": {
                "provider": "transformers",
                "source": "huggingface",
                "model": "Provider/speech-to-text-large",
                "enabled": True,
                "preferred_runtime": "faster_whisper",
            }
        }
        profile = Profile(
            name="tmp",
            root=Path.cwd(),
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
        discovered = ProviderModelsResult(
            "huggingface",
            "source_api",
            ["Provider/speech-to-text-large"],
            "live source",
            {"Provider/speech-to-text-large": {"downloads": 3}},
        )
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            result = ModelCatalog(profile).refresh("huggingface", write=False, verbose=True)
        row = result["results"]["huggingface"]["model_changes"][0]
        self.assertNotIn("provider", row)
        self.assertEqual(
            row["model"],
            {"id": "Provider/speech-to-text-large", "source": "huggingface"},
        )
        self.assertEqual(row["runtime_endpoint"], "transformers")
        self.assertEqual(row["preferred_runtime"], "faster_whisper")
        self.assertIn("faster_whisper", row["suitable_runtimes"])

    def test_model_catalog_refresh_updates_source_metadata_and_preserves_curated_fields(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            "curated-provider-chat": {
                "provider": "vllm",
                "source": "huggingface",
                "model": "Provider/Code-Large-Instruct",
                "enabled": True,
                "roles": ["manual_role"],
                "notes": "keep this note",
                "preferred_runtime": "transformers",
                "capability_scores": {"code_generation": 5, "debugging_refactor": 4},
                "capability_score_source": "manual",
                "source_metadata": {"downloads": 1},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            discovered = ProviderModelsResult(
                "huggingface",
                "source_api",
                ["Provider/Code-Large-Instruct"],
                "live source",
                {
                    "Provider/Code-Large-Instruct": {
                        "downloads": 99,
                        "pipeline_tag": "text-generation",
                    }
                },
            )
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                preview = ModelCatalog(profile).refresh("huggingface", write=False, verbose=True)
                self.assertEqual(preview["changes"]["would_update"], 1)
                self.assertIn("next_steps", preview)
                self.assertIn(
                    "aiplane models refresh --provider huggingface",
                    preview["next_steps"][0],
                )
                self.assertEqual(preview["results"]["huggingface"]["source_models_to_update"], 1)
                self.assertEqual(
                    preview["results"]["huggingface"]["profile_curated_models_before_refresh"],
                    1,
                )
                self.assertEqual(
                    preview["results"]["huggingface"]["profile_refresh_imported_models_before_refresh"],
                    0,
                )
                written = ModelCatalog(profile).refresh("huggingface", write=True, verbose=True)

            self.assertEqual(written["changes"]["updated"], 1)
            model = profile.models["models"]["curated-provider-chat"]
            self.assertEqual(
                model["source_metadata"],
                {"downloads": 99, "pipeline_tag": "text-generation"},
            )
            self.assertEqual(model["roles"], ["manual_role"])
            self.assertEqual(model["notes"], "keep this note")
            self.assertEqual(model["preferred_runtime"], "transformers")
            self.assertEqual(model["capability_score_source"], "manual")
            self.assertEqual(model["capability_scores"]["code_generation"], 5)

    def test_model_catalog_refresh_updates_refresh_imported_fields_from_source(
        self,
    ) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config["models"] = {
            "hf-old": {
                "provider": "vllm",
                "source": "huggingface",
                "model": "org/old-embed",
                "enabled": True,
                "roles": ["chat"],
                "imported_by": "aiplane_refresh",
                "source_metadata": {"downloads": 1},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            discovered = ProviderModelsResult(
                "huggingface",
                "source_api",
                ["org/old-embed"],
                "live source",
                {"org/old-embed": {"downloads": 2}},
            )
            with patch.object(ProviderRegistry, "models", return_value=discovered):
                written = ModelCatalog(profile).refresh("huggingface", write=True, verbose=True)
            self.assertEqual(written["changes"]["updated"], 1)
            generated_models = ModelCatalog(profile).generated_config["models"]
            self.assertEqual(generated_models["hf-old"]["roles"], ["embedding"])
            self.assertEqual(generated_models["hf-old"]["source_metadata"], {"downloads": 2})

    def test_model_catalog_refresh_prunes_live_discovery_but_not_fallback(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config.setdefault("models", {})["fixture-chat-small"] = {
            "provider": "ollama",
            "model": "provider-chat-small:8b",
            "enabled": True,
        }
        models_config.setdefault("models", {})["fixture-analysis-small"] = {
            "provider": "ollama",
            "model": "provider-text-small:0.5b",
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            live = ProviderModelsResult(
                "ollama",
                "provider_api",
                ["provider-chat-small:8b"],
                "live runtime inventory",
            )
            with patch.object(ProviderRegistry, "models", return_value=live):
                preview = ModelCatalog(profile).refresh("ollama", write=False, verbose=True)
                self.assertEqual(preview["changes"]["would_remove"], 0)
                self.assertTrue(preview["results"]["ollama"]["prune_enabled"])
                self.assertIn(
                    "fixture-analysis-small:",
                    (root / "models.yaml").read_text(encoding="utf-8"),
                )

                written = ModelCatalog(profile).refresh("ollama", write=True, verbose=True)

            self.assertEqual(written["changes"]["removed"], 0)
            written_text = (root / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("fixture-analysis-small:", written_text)
            self.assertIn("fixture-chat-small:", written_text)

            fallback_profile = Profile(
                name="tmp",
                root=root,
                workspace=Path.cwd(),
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(models_config)),
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            fallback = ProviderModelsResult(
                "ollama",
                "profile_catalog",
                ["provider-chat-small:8b"],
                "offline fallback",
            )
            with patch.object(ProviderRegistry, "models", return_value=fallback):
                fallback_result = ModelCatalog(fallback_profile).refresh("ollama", write=True)
            self.assertFalse(fallback_result["results"]["ollama"]["prune_enabled"])
            self.assertEqual(fallback_result["changes"]["removed"], 0)

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
                with patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened:
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

    def test_provider_registry_lists_providers(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        rows = ProviderRegistry(profile).list()
        names = {row["name"] for row in rows}
        self.assertIn("ollama", names)
        for managed in ["openai", "anthropic", "azure_openai", "ollama_cloud"]:
            self.assertIn(managed, names)
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["azure_openai"]["catalog_adapter"], "azure_openai")
        self.assertEqual(by_name["azure_openai"]["ownership"], "managed_service")
        self.assertEqual(by_name["openai"]["catalog_adapter"], "openai")
        self.assertEqual(by_name["openai"]["endpoint_family"], "openai")
        self.assertEqual(by_name["openai"]["typical_runtimes"], [])
        self.assertEqual(by_name["openai"]["auth"], {"required": True, "method": "bearer"})
        self.assertEqual(by_name["nvidia"]["ownership"], "self_managed")
        ollama = by_name["ollama"]
        self.assertIn("ollama", ollama["typical_runtimes"])

        enabled_names = {row["name"] for row in ProviderRegistry(profile).list(status="enabled")}
        disabled_names = {row["name"] for row in ProviderRegistry(profile).list(status="disabled")}
        self.assertIn("ollama", enabled_names)
        self.assertNotIn("local_file", enabled_names)
        self.assertIn("local_file", disabled_names)
        self.assertIn("azure_speech", disabled_names)

    def test_provider_list_cli_groups_by_ownership(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "list", "--group-by", "ownership"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["group_by"], "ownership")
        self.assertEqual(list(payload["groups"])[:2], ["self_managed", "managed_service"])
        self.assertIn("self_managed", payload["groups"])
        self.assertIn("managed_service", payload["groups"])
        self.assertTrue(any(row["name"] == "nvidia" for row in payload["groups"]["self_managed"]))
        self.assertTrue(any(row["name"] == "openai" for row in payload["groups"]["managed_service"]))

    def test_provider_list_cli_filters_by_status(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "list", "--status", "disabled"])
        self.assertEqual(code, 0)
        rows = json.loads(stdout.getvalue())
        names = {row["name"] for row in rows}
        self.assertIn("local_file", names)
        self.assertTrue(all(not row["enabled"] for row in rows))
        self.assertTrue(all(row["ownership"] in {"self_managed", "managed_service"} for row in rows))

    def test_provider_endpoint_types_cli_lists_supported_api_shapes(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "endpoint-types"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "provider_types")
        families = {row["name"] for row in payload["endpoint_families"]}
        adapters = {row["name"] for row in payload["catalog_adapters"]}
        self.assertIn("custom_openai_compatible", families)
        self.assertIn("azure_openai", families)
        self.assertIn("profile_catalog", adapters)
        self.assertIn("huggingface", adapters)
        self.assertIn("openai", adapters)

    def test_provider_add_cli_rejects_unsupported_api_family(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            cli_main(["providers", "add", "bad_gateway", "--endpoint-family", "not_real_api"])
        self.assertIn("invalid choice", stderr.getvalue())

    def test_provider_enable_disable_cli_updates_user_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profiles" / "local-dev", root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            disabled = ProviderRegistry(profile).set_enabled("ollama", False)
            self.assertFalse(disabled["enabled"])
            user_config = profile.root / "model-providers.user.yaml"
            self.assertTrue(user_config.exists())
            self.assertFalse(ProviderRegistry(profile).model_providers(include_removed=True)["ollama"]["enabled"])
            enabled = ProviderRegistry(profile).set_all_enabled(True)
            self.assertIn("ollama", enabled["providers"])
            self.assertTrue(ProviderRegistry(profile).model_providers()["ollama"]["enabled"])

    def test_provider_defaults_can_be_initialized_and_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_root = root / "local-dev"
            profile_root.mkdir()
            profile = Profile("local-dev", profile_root, root, {}, {}, {}, {}, {}, {}, {}, {}, {})
            registry = ProviderRegistry(profile)
            initialized = registry.init_defaults()
            self.assertIn("ollama", initialized["providers"])
            with self.assertRaises(ValueError):
                registry.init_defaults()
            cleared = registry.clear_config("all")
            self.assertTrue(cleared["suppresses_hardcoded_fallback"])
            self.assertEqual(ProviderRegistry(profile).list(status="all"), [])
            reinitialized = registry.init_defaults(overwrite=True)
            self.assertIn("huggingface", reinitialized["providers"])
            self.assertIn("nvidia", reinitialized["providers"])
            nvidia = registry.model_providers()["nvidia"]
            self.assertEqual(nvidia["catalog_adapter"], "huggingface")
            self.assertEqual(nvidia["huggingface_author"], "nvidia")
            self.assertEqual(nvidia["typical_runtimes"], ["vllm", "tgi", "transformers"])

    def test_provider_update_defaults_preserves_enabled_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_root = root / "local-dev"
            profile_root.mkdir()
            (profile_root / "model-providers.yaml").write_text(
                "ollama:\n"
                "  description: stale ollama description\n"
                "  typical_runtimes: [old_runtime]\n"
                "  catalog_adapter: profile_catalog\n"
                "  enabled: false\n"
                "huggingface:\n"
                "  description: stale huggingface description\n"
                "  typical_runtimes: [vllm]\n"
                "  catalog_adapter: huggingface\n"
                "  enabled: true\n",
                encoding="utf-8",
            )
            profile = Profile("local-dev", profile_root, root, {}, {}, {}, {}, {}, {}, {}, {}, {})
            result = ProviderRegistry(profile).update_defaults()
            providers = ProviderRegistry(profile).model_providers(include_removed=True)
        self.assertEqual(result["name"], "model_provider_defaults_update")
        self.assertIn("nvidia", result["added"])
        self.assertIn("ollama", result["preserved_enabled"])
        self.assertFalse(providers["ollama"]["enabled"])
        self.assertEqual(providers["ollama"]["typical_runtimes"], ["ollama"])
        self.assertEqual(
            providers["ollama"]["description"],
            "Ollama model library and local pull store",
        )
        self.assertTrue(providers["huggingface"]["enabled"])
        self.assertIn("nvidia", providers)

    def test_provider_update_defaults_leaves_user_disabled_override_untouched(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profile-templates" / "local-dev", root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            registry = ProviderRegistry(profile)
            registry.set_enabled("nvidia", False)
            result = registry.update_defaults()
            providers = ProviderRegistry(profile).model_providers(include_removed=True)
            user_config = parse_yaml((profile.root / "model-providers.user.yaml").read_text(encoding="utf-8"))
        self.assertIn("nvidia", result["updated"])
        self.assertFalse(providers["nvidia"]["enabled"])
        self.assertFalse(user_config["nvidia"]["enabled"])

    def test_provider_update_defaults_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profile-templates" / "local-dev", root / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(root),
                        "providers",
                        "update-defaults",
                        "--profile",
                        "local-dev",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "model_provider_defaults_update")
        self.assertIn("nvidia", payload["providers"])
        self.assertIn("nvidia", payload["preserved_enabled"])

    def test_provider_registry_reads_legacy_source_provider_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_root = root / "local-dev"
            profile_root.mkdir()
            (profile_root / "source-providers.yaml").write_text(
                "legacyhub:\n"
                "  description: Legacy provider\n"
                "  typical_runtimes: [vllm]\n"
                "  catalog_adapter: profile_catalog\n"
                "  enabled: true\n",
                encoding="utf-8",
            )
            profile = Profile(
                "local-dev",
                profile_root,
                root,
                {},
                {},
                {},
                {},
                {},
                {},
                {"models": {}},
                {},
                {},
            )
            rows = ProviderRegistry(profile).list(status="all")
            self.assertEqual([row["name"] for row in rows], ["legacyhub"])

    def test_provider_doctor_filters_by_model_provider(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        statuses = ProviderRegistry(profile).doctor("ollama")
        names = {status.name for status in statuses}
        self.assertIn("fixture-analysis-small", names)
        self.assertNotIn("provider-code-large-vllm", names)

    def test_provider_doctor_cli_runs_without_provider_argument(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["providers", "doctor", "--profile", "local-dev"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload)
        self.assertEqual(next(iter(payload[0].keys())), "name")

    def test_provider_clear_cli_defaults_to_all_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profiles" / "local-dev", root / "local-dev")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(root),
                        "providers",
                        "clear",
                        "--profile",
                        "local-dev",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["scope"], "all")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            self.assertEqual(ProviderRegistry(profile).list(status="all"), [])

    def test_provider_add_and_remove_use_user_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path.cwd() / "profiles" / "local-dev", root / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=root)
            registry = ProviderRegistry(profile)
            added = registry.add(
                "myhub",
                description="Private hub",
                typical_runtimes=["vllm"],
                catalog_adapter="huggingface",
            )
            self.assertEqual(added["catalog_adapter"], "huggingface")
            self.assertEqual(added["ownership"], "self_managed")
            managed = registry.add(
                "my_gateway",
                description="Managed gateway",
                ownership="managed_service",
                endpoint_family="custom_openai_compatible",
                catalog_adapter="profile_catalog",
                endpoint="https://gateway.example.com/v1",
                api_key_env="MY_GATEWAY_API_KEY",
                auth_method="bearer",
            )
            self.assertEqual(managed["endpoint_family"], "custom_openai_compatible")
            self.assertEqual(managed["auth"], {"required": True, "method": "bearer"})
            self.assertEqual(managed["typical_runtimes"], [])
            self.assertIn("myhub", registry.model_providers())
            removed = registry.remove("myhub")
            self.assertTrue(removed["removed"])
            self.assertNotIn("myhub", registry.model_providers())
            self.assertIn("myhub", registry.model_providers(include_removed=True))

    def test_provider_show_includes_configured_models(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        provider = ProviderRegistry(profile).show("ollama")
        model_names = {row["name"] for row in provider["profile_models"]}
        self.assertIn("fixture-analysis-small", model_names)

    def test_provider_models_lists_source_catalog_entries(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = ProviderRegistry(profile).models("huggingface")
        self.assertEqual(result.source, "profile_catalog")
        self.assertIn("Provider/Code-Large-Instruct", result.models)

    def test_provider_models_can_query_ollama_online_adapter_with_mocked_http(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        html = '<a href="/library/provider-chat">provider-chat</a><a href="/library/provider-code">provider-code</a>'

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return html.encode("utf-8")

        with patch("aiplane.providers.urlopen", return_value=FakeResponse()):
            result = ProviderRegistry(profile).models("ollama", online=True, query="code", limit=5)
        self.assertEqual(result.source, "source_api")
        self.assertEqual(result.models, ["provider-code"])

    def test_provider_models_can_query_online_adapter_with_mocked_http(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = [{"modelId": "Provider/Test-Coder"}]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch("aiplane.providers.urlopen", return_value=FakeResponse()):
            result = ProviderRegistry(profile).models("huggingface", online=True, query="code", limit=1)
        self.assertEqual(result.source, "source_api")
        self.assertEqual(result.models, ["Provider/Test-Coder"])

    def test_provider_models_can_query_nvidia_huggingface_scope_with_mocked_http(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = [{"modelId": "nvidia/Nemotron-Test", "author": "nvidia"}]
        requested_urls: list[str] = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        def fake_urlopen(request, timeout=20):
            requested_urls.append(str(request.full_url))
            return FakeResponse()

        with patch("aiplane.providers.urlopen", side_effect=fake_urlopen):
            result = ProviderRegistry(profile).models("nvidia", online=True, query="Nemotron", limit=1)
        self.assertEqual(result.provider, "nvidia")
        self.assertEqual(result.source, "source_api")
        self.assertEqual(result.models, ["nvidia/Nemotron-Test"])
        self.assertIn("author=nvidia", requested_urls[0])
        self.assertIn("search=Nemotron", requested_urls[0])

    def test_provider_models_can_query_openai_compatible_catalog_with_mocked_http(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"] = {
            "ownership": "managed_service",
            "protocol": "openai_compatible",
            "endpoint": "https://api.example.test/v1",
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
        }
        payload = {
            "data": [
                {"id": "general-chat", "object": "model", "owned_by": "provider"},
                {"id": "coding-chat", "object": "model", "owned_by": "provider"},
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).models("openai", online=True, query="coding", limit=5)
        self.assertEqual(result.source, "provider_api")
        self.assertEqual(result.models, ["coding-chat"])
        self.assertEqual(result.model_metadata["coding-chat"]["owned_by"], "provider")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/v1/models")
        self.assertEqual(request.headers.get("Authorization"), "Bearer test-key")

    def test_provider_models_can_query_azure_openai_deployments_with_mocked_http(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["azure_openai"]["endpoint"] = "https://example.openai.azure.com"
        payload = {"data": [{"id": "coding-chat", "model": "managed-chat-model"}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}),
            patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).models("azure_openai", online=True, query="coding", limit=5)
        self.assertEqual(result.source, "provider_api")
        self.assertEqual(result.models, ["coding-chat"])
        request = opened.call_args.args[0]
        self.assertIn("/openai/deployments", request.full_url)
        self.assertEqual(request.headers.get("Api-key"), "test-key")

    def test_provider_models_can_query_elevenlabs_voices_with_mocked_http(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["elevenlabs"]["enabled"] = True
        profile.models.setdefault("models", {})
        payload = {"voices": [{"voice_id": "voice-alpha", "name": "Demo Voice", "category": "premade"}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key"}),
            patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).models("elevenlabs", online=True, query="demo", limit=5)
        self.assertEqual(result.source, "provider_api")
        self.assertEqual(result.models, ["voice-alpha"])
        self.assertEqual(result.model_metadata["voice-alpha"]["pipeline_tag"], "text-to-speech")
        request = opened.call_args.args[0]
        self.assertIn("/voices", request.full_url)
        self.assertEqual(request.headers.get("Xi-api-key"), "test-key")

    def test_provider_test_command_checks_openai_compatible_credential(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"] = {
            "ownership": "managed_service",
            "runtime": "openai_api",
            "protocol": "openai_compatible",
            "endpoint": "https://api.example.test/v1",
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
        }
        payload = {"data": [{"id": "managed-chat"}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("aiplane.providers.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).test_connection("openai")
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "openai_compatible_models")
        self.assertEqual(result["items_seen"], 1)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/v1/models")
        self.assertEqual(request.headers.get("Authorization"), "Bearer test-key")
        self.assertNotIn("test-key", json.dumps(result))

    def test_provider_test_cli_uses_named_credential_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cred_path = Path(tmp) / "credentials.yaml"
            cred_path.write_text(
                "providers:\n"
                "  openai:\n"
                "    accounts:\n"
                "      personal:\n"
                "        api_key: dummy-api-key-value-123456\n"
                "        endpoint: https://api.example.test/v1\n",
                encoding="utf-8",
            )
            payload = {"data": [{"id": "managed-chat"}]}

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(payload).encode("utf-8")

            stdout = StringIO()
            with (
                patch.dict(os.environ, {"AIPLANE_CREDENTIALS": str(cred_path)}),
                patch("aiplane.providers.urlopen", return_value=FakeResponse()),
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    [
                        "providers",
                        "test",
                        "--profile",
                        "local-dev",
                        "openai",
                        "--credential-ref",
                        "openai.personal",
                    ]
                )
            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["ok"])
            self.assertEqual(result["credential_ref"], "openai.personal")
            self.assertEqual(result["endpoint"], "https://api.example.test/v1")
            self.assertNotIn("dummy-api-key-value", stdout.getvalue())

    def test_elevenlabs_refresh_imports_managed_tts_voice(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["elevenlabs"]["enabled"] = True
        discovered = ProviderModelsResult(
            "elevenlabs",
            "provider_api",
            ["voice-alpha"],
            "mocked",
            {"voice-alpha": {"pipeline_tag": "text-to-speech", "name": "Demo Voice"}},
        )
        with patch.object(ProviderRegistry, "models", return_value=discovered):
            result = ModelCatalog(profile).refresh("elevenlabs", write=False, enable=True, online=True, verbose=True)
        rows = result["results"]["elevenlabs"]["model_changes"]
        entry = next(row for row in rows if row["name"] == "elevenlabs-voice-alpha")
        self.assertEqual(entry["model"]["source"], "elevenlabs")
        self.assertEqual(entry["ownership"], "managed_service")
        self.assertEqual(entry["preferred_runtime"], "elevenlabs")
        self.assertEqual(entry["suitable_runtimes"], [])
        self.assertFalse(entry["local"])
        self.assertIn("text_to_speech", entry["roles"])
        direct_entry = {
            "provider": "elevenlabs",
            "model": "voice-alpha",
            "source": "elevenlabs",
            "roles": ["text_to_speech"],
            "local": False,
        }
        self.assertEqual(RuntimeCatalog(profile).compatible_runtimes_for_entry(direct_entry), [])

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
