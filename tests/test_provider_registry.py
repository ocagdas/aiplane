from __future__ import annotations

from .support import (
    ModelCatalog,
    Path,
    Profile,
    ProviderModelsResult,
    ProviderRegistry,
    RuntimeCatalog,
    StringIO,
    cli_main,
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


class ProviderRegistryTests(unittest.TestCase):
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
            shutil.copytree(
                Path(os.environ.get("AIPLANE_PROFILES_DIR", Path.cwd() / "profiles")) / "local-dev",
                root / "local-dev",
            )
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
            shutil.copytree(
                Path(os.environ.get("AIPLANE_PROFILES_DIR", Path.cwd() / "profiles")) / "local-dev",
                root / "local-dev",
            )
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
            shutil.copytree(
                Path(os.environ.get("AIPLANE_PROFILES_DIR", Path.cwd() / "profiles")) / "local-dev",
                root / "local-dev",
            )
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

        with patch("aiplane.boundaries.urlopen", return_value=FakeResponse()):
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

        with patch("aiplane.boundaries.urlopen", return_value=FakeResponse()):
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

        with patch("aiplane.boundaries.urlopen", side_effect=fake_urlopen):
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
            patch("aiplane.boundaries.urlopen", return_value=FakeResponse()) as opened,
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
            patch("aiplane.boundaries.urlopen", return_value=FakeResponse()) as opened,
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
            patch("aiplane.boundaries.urlopen", return_value=FakeResponse()) as opened,
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
            patch("aiplane.boundaries.urlopen", return_value=FakeResponse()) as opened,
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
                patch("aiplane.boundaries.urlopen", return_value=FakeResponse()),
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

    def test_provider_diagnose_is_secret_free_and_non_networked(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with patch("aiplane.boundaries.urlopen") as opened:
            payload = ProviderRegistry(profile).diagnose("openai")
        self.assertFalse(payload["network_contacted"])
        self.assertEqual(payload["contract_version"], "1.0")
        self.assertEqual(payload["providers"][0]["catalog_adapter"], "openai")
        self.assertFalse(payload["providers"][0]["ready"])
        opened.assert_not_called()

    def test_provider_diagnose_reports_missing_credential_reference(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"]["credential_ref"] = "openai.missing"
        payload = ProviderRegistry(profile).diagnose("openai")
        credential = next(check for check in payload["providers"][0]["checks"] if check["name"] == "credential")
        self.assertFalse(credential["ok"])
        self.assertEqual(credential["detail"], "reference not found")

    def test_anthropic_catalog_discovery_uses_models_api(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        payload = {
            "data": [
                {
                    "id": "claude-test",
                    "display_name": "Claude Test",
                    "type": "model",
                    "created_at": "2026-01-01T00:00:00Z",
                }
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
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("aiplane.boundaries.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).models("anthropic", online=True, query="test", limit=5)
        self.assertEqual(result.models, ["claude-test"])
        self.assertEqual(result.model_metadata["claude-test"]["display_name"], "Claude Test")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/models")
        self.assertEqual(request.headers.get("X-api-key"), "test-key")
        self.assertEqual(request.headers.get("Anthropic-version"), "2023-06-01")

    def test_custom_openai_discovery_can_be_unauthenticated(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["local_gateway"] = {
            "ownership": "managed_service",
            "endpoint_family": "custom_openai_compatible",
            "catalog_adapter": "openai",
            "endpoint": "http://127.0.0.1:4000/v1",
            "auth": {"required": False, "method": "none"},
            "enabled": True,
        }
        payload = {"data": [{"id": "local-chat"}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with (
            patch.object(
                ProviderRegistry,
                "model_providers",
                return_value={"local_gateway": profile.models["providers"]["local_gateway"]},
            ),
            patch("aiplane.boundaries.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ProviderRegistry(profile).models("local_gateway", online=True)
        self.assertEqual(result.models, ["local-chat"])
        self.assertIsNone(opened.call_args.args[0].headers.get("Authorization"))
