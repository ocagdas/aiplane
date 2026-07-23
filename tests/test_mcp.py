from __future__ import annotations

from .support import (
    ACCELERATOR_API_CHOICES,
    AiplaneMcpServer,
    AuditLogger,
    BytesIO,
    GPU_VENDOR_CHOICES,
    MODEL_FILTER_SCHEMA_PROPERTIES,
    MODEL_SORT_CHOICES,
    MachineManager,
    Path,
    Profile,
    ProviderModelsResult,
    ProviderRegistry,
    StringIO,
    StackManager,
    _read_message,
    _write_message,
    _materialize_test_models,
    agent_config,
    create_profile,
    json,
    load_profile,
    mcp_manifest,
    mcp_module,
    patch,
    tempfile,
    unittest,
)


class McpTests(unittest.TestCase):
    def test_mcp_manifest_exposes_guarded_write_tools(self) -> None:
        manifest = mcp_manifest()
        self.assertEqual(manifest["status"], "guarded_write_stdio_available")
        self.assertEqual(manifest["transport"], "stdio")
        self.assertTrue(manifest["tools"])
        names = {tool["name"] for tool in manifest["tools"]}
        self.assertIn("aiplane.docs.list", names)
        self.assertIn("aiplane.docs.read", names)
        self.assertIn("aiplane.models.defaults", names)
        self.assertIn("aiplane.models.list", names)
        self.assertIn("aiplane.models.refresh", names)
        self.assertIn("aiplane.models.use", names)
        self.assertIn("aiplane.runtimes.status", names)
        self.assertIn("aiplane.runtimes.bundle", names)
        self.assertIn("aiplane.agents.manifest", names)
        self.assertIn("aiplane.providers.diagnose", names)
        self.assertIn("aiplane.hardware.assess", names)
        self.assertTrue(any(tool["mutates"] for tool in manifest["tools"]))
        self.assertTrue(
            all(tool["mutates"] for tool in manifest["write_tools"] if tool["name"] != "aiplane.remote.tunnel.status")
        )

    def test_mcp_server_lists_tools(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertIsNotNone(response)
        tools = response["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertIn("aiplane.models.list", names)
        self.assertIn("inputSchema", tools[0])

    def test_mcp_server_calls_read_only_tool(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "aiplane.profiles.list", "arguments": {}},
            }
        )
        self.assertIsNotNone(response)
        result = response["result"]
        self.assertIn("local-dev", result["structuredContent"]["profiles"])
        self.assertEqual(result["content"][0]["type"], "text")

    def test_mcp_hardware_assess_forwards_explicit_assumptions(self) -> None:
        expected = {"placement": {"eligible": True}, "score": {"selection_score": 80}}
        with patch("aiplane.mcp.HardwareManager.assess", return_value=expected) as assess:
            response = AiplaneMcpServer(Path.cwd()).handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 203,
                    "method": "tools/call",
                    "params": {
                        "name": "aiplane.hardware.assess",
                        "arguments": {
                            "model": "fixture-analysis-small",
                            "runtime": "ollama",
                            "context_tokens": 32768,
                            "score_profile": "throughput",
                        },
                    },
                }
            )
        self.assertEqual(response["result"]["structuredContent"], expected)
        assess.assert_called_once_with(
            "fixture-analysis-small",
            runtime="ollama",
            context_tokens=32768,
            score_profile="throughput",
        )

    def test_mcp_docs_tools_list_and_read_docs(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        listing = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 201,
                "method": "tools/call",
                "params": {"name": "aiplane.docs.list", "arguments": {}},
            }
        )
        self.assertIsNotNone(listing)
        docs = listing["result"]["structuredContent"]["docs"]
        self.assertTrue(any(row["path"] == "docs/user/mcp.md" for row in docs))

        read = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 202,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.docs.read",
                    "arguments": {"path": "docs/user/mcp.md", "max_chars": 400},
                },
            }
        )
        self.assertIsNotNone(read)
        payload = read["result"]["structuredContent"]
        self.assertEqual(payload["path"], "docs/user/mcp.md")
        self.assertIn("MCP", payload["content"])

    def test_mcp_provider_list_supports_status_and_ownership_grouping(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 25,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.providers.list",
                    "arguments": {"status": "all", "group_by": "ownership"},
                },
            }
        )
        self.assertIsNotNone(response)
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["group_by"], "ownership")
        self.assertEqual(list(payload["groups"])[:2], ["self_managed", "managed_service"])
        self.assertIn("self_managed", payload["groups"])
        self.assertIn("managed_service", payload["groups"])
        self.assertTrue(any(row["name"] == "nvidia" for row in payload["groups"]["self_managed"]))
        self.assertTrue(any(row["name"] == "openai" for row in payload["groups"]["managed_service"]))

    def test_mcp_server_can_list_ranked_models(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 24,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.models.list",
                    "arguments": {
                        "capabilities": {"code_generation": 3, "debugging_refactor": 2},
                        "ownership": "self_managed",
                        "vram_gb": 96,
                        "sort_by": "avg",
                        "limit": 3,
                    },
                },
            }
        )
        self.assertIsNotNone(response)
        result = response["result"]["structuredContent"]
        self.assertLessEqual(len(result["models"]), 3)
        self.assertTrue(all(row["ownership"] == "self_managed" for row in result["models"]))

    def test_mcp_model_list_schema_uses_shared_model_filter_contract(self) -> None:
        schema = mcp_module.TOOL_SCHEMAS["aiplane.models.list"]
        properties = schema["properties"]
        for name in MODEL_FILTER_SCHEMA_PROPERTIES:
            self.assertIn(name, properties)
        self.assertEqual(properties["sort_by"]["enum"], MODEL_SORT_CHOICES)
        self.assertEqual(properties["gpu_vendor"]["enum"], GPU_VENDOR_CHOICES)
        self.assertEqual(properties["accelerator_api"]["enum"], ACCELERATOR_API_CHOICES)

    def test_mcp_models_refresh_schema_uses_verbosity_levels(self) -> None:
        schema = mcp_module.TOOL_SCHEMAS["aiplane.models.refresh"]
        properties = schema["properties"]
        self.assertIn("verbosity", properties)
        self.assertNotIn("verbose", properties)
        self.assertEqual(properties["verbosity"]["enum"], [0, 1, 2])

    def test_mcp_model_list_supports_parameter_filters_and_sorting(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 26,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.models.list",
                    "arguments": {
                        "role": ["chat"],
                        "min_parameters_b": 7,
                        "max_parameters_b": 14,
                        "sort_by": "parameters",
                        "limit": 3,
                    },
                },
            }
        )
        self.assertIsNotNone(response)
        rows = response["result"]["structuredContent"]["models"]
        self.assertGreater(len(rows), 0)
        parameter_counts = [float(row["parameter_count_b"] or 0) for row in rows]
        self.assertTrue(all(7 <= count <= 14 for count in parameter_counts))
        self.assertEqual(parameter_counts, sorted(parameter_counts, reverse=True))

    def test_mcp_model_list_can_filter_by_named_machine(self) -> None:
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
            MachineManager(profile).import_azure_sku("Standard_NC4as_T4_v3", "uksouth", name="azure_t4_test")
            server = AiplaneMcpServer(Path.cwd(), default_profile="tmp", profiles_dir=profiles_dir)
            response = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 261,
                    "method": "tools/call",
                    "params": {
                        "name": "aiplane.models.list",
                        "arguments": {
                            "provider": "test_provider",
                            "runtime": "vllm",
                            "role": ["chat"],
                            "machine": "azure_t4_test",
                        },
                    },
                }
            )
        self.assertIsNotNone(response)
        rows = response["result"]["structuredContent"]["models"]
        self.assertEqual([row["name"] for row in rows], ["fits_t4"])

    def test_mcp_server_can_show_model_and_provider_models(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        model_response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.models.show",
                    "arguments": {"model": "fixture-analysis-small"},
                },
            }
        )
        self.assertIsNotNone(model_response)
        self.assertEqual(
            model_response["result"]["structuredContent"]["model"],
            "provider-text-small:0.5b",
        )
        provider_response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 23,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.providers.models",
                    "arguments": {"provider": "huggingface"},
                },
            }
        )
        self.assertIsNotNone(provider_response)
        self.assertEqual(provider_response["result"]["structuredContent"]["provider"], "huggingface")

    def test_mcp_write_tools_can_update_model_default(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(
                agent_config.dump_yaml(json.loads(json.dumps(source.models))),
                encoding="utf-8",
            )
            profile = Profile(
                name="tmp",
                root=root,
                workspace=root,
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(source.models)),
                targets=source.targets,
            )
            with patch("aiplane.mcp.load_profile", return_value=profile):
                server = AiplaneMcpServer(Path.cwd(), allow_writes=True)
                allowed = server.handle_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 31,
                        "method": "tools/call",
                        "params": {
                            "name": "aiplane.models.use",
                            "arguments": {
                                "confirm": True,
                                "role": "code_model",
                                "model": "fixture-code-small",
                            },
                        },
                    }
                )
            self.assertIsNotNone(allowed)
            self.assertEqual(allowed["result"]["structuredContent"]["name"], "fixture-code-small")
            self.assertIn(
                "code_model: fixture-code-small",
                (root / "models.yaml").read_text(encoding="utf-8"),
            )
            events = AuditLogger(profile).tail(1)
            self.assertEqual(events[0]["event_type"], "mcp")
            self.assertEqual(events[0]["action"], "aiplane.models.use")
            self.assertEqual(events[0]["decision"], "allowed")

    def test_mcp_mutating_failures_are_audited(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.yaml").write_text(
                agent_config.dump_yaml(json.loads(json.dumps(source.models))),
                encoding="utf-8",
            )
            profile = Profile(
                name="tmp",
                root=root,
                workspace=root,
                hardware=source.hardware,
                backends=source.backends,
                repository=source.repository,
                tools=source.tools,
                approvals=source.approvals,
                environment=source.environment,
                models=json.loads(json.dumps(source.models)),
                targets=source.targets,
                orchestrators=source.orchestrators,
            )
            with patch("aiplane.mcp.load_profile", return_value=profile):
                response = AiplaneMcpServer(root, allow_writes=True).handle_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 32,
                        "method": "tools/call",
                        "params": {
                            "name": "aiplane.models.use",
                            "arguments": {
                                "confirm": True,
                                "role": "code_model",
                                "model": "missing-model",
                            },
                        },
                    }
                )
            self.assertIsNotNone(response)
            self.assertIn("error", response)
            events = AuditLogger(profile).tail(1)
            self.assertEqual(events[0]["event_type"], "mcp")
            self.assertEqual(events[0]["action"], "aiplane.models.use")
            self.assertEqual(events[0]["decision"], "failed")

    def test_mcp_can_plan_integrations_and_inspect_orchestrators(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        roles = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.integrations.roles",
                    "arguments": {"tool": "continue"},
                },
            }
        )
        self.assertEqual(
            [role["name"] for role in roles["result"]["structuredContent"]["roles"]],
            ["chat", "autocomplete", "embedding"],
        )

        plan = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.integrations.plan",
                    "arguments": {
                        "tool": "openai-compatible",
                        "model": "fixture-analysis-small",
                    },
                },
            }
        )
        self.assertEqual(
            plan["result"]["structuredContent"]["selection"]["primary"]["name"],
            "fixture-analysis-small",
        )

        orchestrators = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 33,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.orchestrators.list",
                    "arguments": {"runtime": ["ollama"], "group_by": "runtime"},
                },
            }
        )
        self.assertEqual(orchestrators["result"]["structuredContent"]["group_by"], "runtime")
        self.assertIn("ollama", orchestrators["result"]["structuredContent"]["groups"])

        shown = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.orchestrators.show",
                    "arguments": {"name": "langgraph"},
                },
            }
        )
        self.assertEqual(shown["result"]["structuredContent"]["name"], "langgraph")

    def test_mcp_can_inspect_machines_and_plan_stacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            create_profile("local-dev", profiles_dir=profiles_dir)
            _materialize_test_models(profiles_dir / "local-dev")
            profile = load_profile("local-dev", Path.cwd(), profiles_dir=profiles_dir)
            MachineManager(profile).import_azure_sku("Standard_NC40ads_H100_v5", "uksouth", name="azure_h100_test")
            StackManager(profile).setup(
                "code_on_gpu",
                orchestrator="langgraph",
                runtime="vllm",
                model="provider-code-large-vllm",
                machine="azure_h100_test",
                endpoint="http://localhost:8000/v1",
            )

            server = AiplaneMcpServer(Path.cwd(), profiles_dir=profiles_dir)
            machines = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 41,
                    "method": "tools/call",
                    "params": {"name": "aiplane.machines.list", "arguments": {}},
                }
            )
            self.assertIn(
                "azure_h100_test",
                {row["name"] for row in machines["result"]["structuredContent"]},
            )

            recommendation = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "tools/call",
                    "params": {
                        "name": "aiplane.machines.recommend",
                        "arguments": {
                            "model": "local-code-large",
                            "runtime": "vllm",
                            "limit": 1,
                        },
                    },
                }
            )
            self.assertEqual(
                recommendation["result"]["structuredContent"]["machines"][0]["name"],
                "azure_h100_test",
            )

            stack_plan = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 43,
                    "method": "tools/call",
                    "params": {
                        "name": "aiplane.stacks.plan",
                        "arguments": {"name": "code_on_gpu"},
                    },
                }
            )
            self.assertEqual(stack_plan["result"]["structuredContent"]["machine"], "azure_h100_test")
            self.assertEqual(stack_plan["result"]["structuredContent"]["orchestrator"], "langgraph")

            stack_export = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 45,
                    "method": "tools/call",
                    "params": {
                        "name": "aiplane.stacks.export",
                        "arguments": {"artifact": "langgraph", "name": "code_on_gpu"},
                    },
                }
            )
            self.assertEqual(stack_export["result"]["structuredContent"]["framework"], "langgraph")
            self.assertIn(
                "framework: langgraph",
                stack_export["result"]["structuredContent"]["content"],
            )

            stack_doctor = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 44,
                    "method": "tools/call",
                    "params": {
                        "name": "aiplane.stacks.doctor",
                        "arguments": {"name": "code_on_gpu"},
                    },
                }
            )
            self.assertTrue(
                any(check["name"] == "machine_fit" for check in stack_doctor["result"]["structuredContent"]["checks"])
            )

    def test_mcp_can_export_non_continue_integrations(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.integrations.export",
                    "arguments": {"tool": "cline", "model": "fixture-analysis-small"},
                },
            }
        )
        self.assertIsNotNone(response)
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["tool"], "cline")
        self.assertIn("openai-compatible", payload["content"])

    def test_mcp_can_preview_refresh_and_runtime_status(self) -> None:
        source = load_profile("local-dev", Path.cwd())
        models_config = json.loads(json.dumps(source.models))
        models_config.setdefault("models", {})["fixture-chat-small"] = {
            "provider": "ollama",
            "model": "provider-chat-small:8b",
            "enabled": True,
        }
        discovered = ProviderModelsResult(
            "ollama",
            "provider_api",
            ["provider-chat-small:8b", "fresh-model:1b"],
            "test discovery",
        )
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
            )
            with (
                patch("aiplane.mcp.load_profile", return_value=profile),
                patch.object(ProviderRegistry, "models", return_value=discovered),
            ):
                server = AiplaneMcpServer(Path.cwd())
                response = server.handle_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 33,
                        "method": "tools/call",
                        "params": {
                            "name": "aiplane.models.refresh",
                            "arguments": {"provider": "ollama", "dry_run": True},
                        },
                    }
                )
        self.assertIsNotNone(response)
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["write"])
        self.assertEqual(payload["changes"]["would_import"], 1)
        self.assertEqual(payload["changes"]["would_remove"], 0)
        self.assertEqual(payload["results"]["ollama"]["source_models_returned"], 2)
        self.assertEqual(payload["results"]["ollama"]["source_models_already_profiled"], 1)
        self.assertTrue(payload["results"]["ollama"]["source_contacted"])
        self.assertTrue(payload["results"]["ollama"]["prune_enabled"])
        self.assertNotIn("catalog", payload)
        self.assertIn("ollama", payload["results"])

        response = AiplaneMcpServer(Path.cwd()).handle_message(
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.runtimes.status",
                    "arguments": {"runtime": "ollama"},
                },
            }
        )
        self.assertIsNotNone(response)
        self.assertEqual(response["result"]["structuredContent"][0]["name"], "ollama")

    def test_mcp_stdio_message_framing_round_trips(self) -> None:
        stream = BytesIO()
        message = {"jsonrpc": "2.0", "id": 3, "result": {"ok": True}}
        _write_message(stream, message)
        stream.seek(0)
        self.assertEqual(_read_message(stream), message)

    def test_mcp_stdio_message_framing_rejects_missing_content_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing Content-Length"):
            _read_message(BytesIO(b"Content-Type: application/json\r\n\r\n{}"))

    def test_mcp_stdio_message_framing_rejects_empty_content_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty value"):
            _read_message(BytesIO(b"Content-Length:\r\n\r\n"))

    def test_mcp_stdio_message_framing_rejects_non_integer_content_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            _read_message(BytesIO(b"Content-Length: abc\r\n\r\n"))

    def test_mcp_serve_stdio_handles_malformed_header_without_traceback(self) -> None:
        class _In:
            def __init__(self, payload: bytes):
                self.buffer = BytesIO(payload)

        stderr = StringIO()
        with (
            patch.object(mcp_module.sys, "stdin", _In(b"Content-Length: bad\r\n\r\n")),
            patch.object(mcp_module.sys, "stderr", stderr),
        ):
            code = mcp_module.serve_stdio(Path.cwd())
        self.assertEqual(code, 2)
        self.assertIn("framing error", stderr.getvalue())

    def test_mcp_safe_render_contracts_match_cli_services(self) -> None:
        server = AiplaneMcpServer(Path.cwd())
        diagnosed = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 81,
                "method": "tools/call",
                "params": {"name": "aiplane.providers.diagnose", "arguments": {"provider": "openai"}},
            }
        )
        self.assertFalse(diagnosed["result"]["structuredContent"]["network_contacted"])

        bundle = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 82,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.runtimes.bundle",
                    "arguments": {
                        "runtime": "ollama",
                        "model": "fixture-analysis-small",
                        "cache_volume": "ollama-cache",
                        "gpu_devices": ["all"],
                    },
                },
            }
        )
        self.assertEqual(bundle["result"]["structuredContent"]["record_type"], "runtime_bundle")

        manifest = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 83,
                "method": "tools/call",
                "params": {
                    "name": "aiplane.agents.manifest",
                    "arguments": {"name": "demo", "model": "fixture-analysis-small"},
                },
            }
        )
        self.assertEqual(manifest["result"]["structuredContent"]["record_type"], "agent_environment")
        self.assertFalse(manifest["result"]["structuredContent"]["execution_boundary"]["runs_agents"])
