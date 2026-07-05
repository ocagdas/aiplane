from __future__ import annotations

from .support import (
    AuditLogger,
    BackendResult,
    CodeTaskResult,
    CodeTaskRunner,
    ModelCatalog,
    OllamaBackend,
    Path,
    Profile,
    Router,
    RuntimeCatalog,
    StringIO,
    TestHttpServer,
    cli_main,
    json,
    load_profile,
    ollama_model_id,
    os,
    patch,
    redirect_stdout,
    runtime_pull_support,
    shutil,
    subprocess,
    tempfile,
    unittest,
)


class RuntimeExecutionTests(unittest.TestCase):
    def test_router_blocks_secret_cloud_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            router = Router(profile, AuditLogger(profile))
            with self.assertRaises(PermissionError):
                router.route("token=abcdefghijklmnop", prefer_escalation=True)

    def test_router_run_dry_run_selects_enabled_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            result = Router(profile, AuditLogger(profile)).route(
                "explain setup", dry_run=True
            )
            self.assertEqual(result.backend, "dry_run")
            self.assertFalse(result.escalated)
            self.assertIn("fixture-analysis-small", result.text)
            self.assertIn("provider-text-small:0.5b", result.text)

    def test_router_uses_profile_self_managed_model_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            profile.models["defaults"]["self_managed_model"] = "fixture-code-small"
            result = Router(profile, AuditLogger(profile)).route(
                "explain setup", dry_run=True
            )
            self.assertIn("fixture-code-small", result.text)

    def test_router_run_dry_run_can_use_explicit_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            result = Router(profile, AuditLogger(profile)).route(
                "explain setup", model_name="fixture-code-small", dry_run=True
            )
            self.assertIn("fixture-code-small", result.text)
            self.assertIn("provider-code-small:1.5b", result.text)

    def test_router_blocks_local_model_when_hardware_minimums_fail_unless_overridden(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            profile.models.setdefault("models", {})["too-large-local"] = {
                "provider": "ollama",
                "model": "huge:latest",
                "local": True,
                "enabled": True,
                "min_ram_gb": 100000,
                "min_vram_gb": 0,
            }
            router = Router(profile, AuditLogger(profile))
            with self.assertRaisesRegex(RuntimeError, "hardware requirements"):
                router.route(
                    "explain setup", model_name="too-large-local", dry_run=True
                )
            result = router.route(
                "explain setup",
                model_name="too-large-local",
                dry_run=True,
                ignore_hardware_fit=True,
            )
            self.assertEqual(result.backend, "dry_run")

    def test_router_run_blocks_managed_service_model_when_policy_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = load_profile("local-dev", Path(tmp))
            profile.repository["allow_cloud"] = False
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
            with self.assertRaises(PermissionError):
                Router(profile, AuditLogger(profile)).route(
                    "explain setup", model_name="openai-main", dry_run=True
                )

    def test_code_analyze_dry_run_includes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "sample.py"
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = CodeTaskRunner(profile, AuditLogger(profile)).analyze(
                "fixture-analysis-small", target, dry_run=True
            )
            self.assertTrue(result.dry_run)
            self.assertIn("Analyze this code file", result.output)
            self.assertIn("def add", result.output)

    def test_code_complete_dry_run_uses_line_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / "sample.py"
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            result = CodeTaskRunner(profile, AuditLogger(profile)).complete(
                "fixture-analysis-small", target, 2, dry_run=True
            )
            self.assertIn("Before cursor", result.output)
            self.assertIn("After cursor", result.output)

    def test_code_write_dry_run_builds_prompt(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        result = CodeTaskRunner(profile, AuditLogger(profile)).write(
            "fixture-analysis-small", "add email validation", dry_run=True
        )
        self.assertIn("add email validation", result.output)

    def test_runtime_pull_helpers_resolve_ollama_compatible_huggingface_gguf(
        self,
    ) -> None:
        profile = load_profile("local-dev", Path.cwd())
        model = {
            "provider": "llamacpp",
            "source": "huggingface_gguf",
            "model": "Example/Chat-GGUF",
            "supported_runtimes": ["llamacpp", "ollama"],
        }
        self.assertEqual(ollama_model_id(profile, model), "hf.co/Example/Chat-GGUF")
        self.assertEqual(
            runtime_pull_support(
                "ollama",
                {
                    "provider": "llamacpp",
                    "source": "huggingface_gguf",
                    "model": "Example/Chat-GGUF",
                },
            )["supported"],
            True,
        )
        unsupported = runtime_pull_support(
            "llamacpp",
            {
                "provider": "llamacpp",
                "source": "huggingface_gguf",
                "model": "Example/Chat-GGUF",
            },
        )
        self.assertFalse(unsupported["supported"])
        self.assertIn("direct GGUF URLs", unsupported["reason"])

    def test_code_write_executes_huggingface_gguf_alias_through_ollama(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("models", {})["hf-gguf-chat"] = {
            "provider": "llamacpp",
            "source": "huggingface_gguf",
            "model": "Example/Chat-GGUF",
            "enabled": True,
            "supported_runtimes": ["llamacpp", "ollama"],
            "preferred_runtime": "ollama",
            "roles": ["chat"],
        }

        class FakeOllama:
            def chat(self, model: str, prompt: str):
                return BackendResult("ollama", f"{model}: {prompt[:12]}")

        with (
            patch(
                "aiplane.runtime_catalog.RuntimeCatalog.runtime_available",
                return_value={"name": "ollama", "available": True, "reason": "ok"},
            ),
            patch(
                "aiplane.model_catalog.ModelCatalog._ollama_backend",
                return_value=FakeOllama(),
            ),
        ):
            result = CodeTaskRunner(profile, AuditLogger(profile)).write(
                "hf-gguf-chat", "add email validation", dry_run=False
            )
        self.assertFalse(result.dry_run)
        self.assertIn("hf.co/Example/Chat-GGUF", result.output)

    def test_ollama_backend_timeout_message_points_to_runtime_commands(self) -> None:
        backend = OllamaBackend(timeout_seconds=3)
        with patch("aiplane.backends.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(
                RuntimeError, "Ollama request timed out"
            ) as raised:
                backend.chat("hf.co/Example/Chat-GGUF", "hello")
        message = str(raised.exception)
        self.assertIn("aiplane runtimes status ollama", message)
        self.assertIn(
            "aiplane runtimes pull ollama --model hf.co/Example/Chat-GGUF", message
        )
        self.assertNotIn("ollama serve", message)

    def test_code_write_cli_passes_timeout_override(self) -> None:
        stdout = StringIO()
        with (
            patch.object(
                CodeTaskRunner,
                "write",
                return_value=CodeTaskResult(
                    "write", "fixture-analysis-small", "prompt", "ok", False
                ),
            ) as write,
            redirect_stdout(stdout),
        ):
            code = cli_main(
                [
                    "code",
                    "write",
                    "--model",
                    "fixture-analysis-small",
                    "--task",
                    "add email validation",
                    "--timeout-seconds",
                    "180",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().strip(), "ok")
        self.assertEqual(write.call_args.kwargs["timeout_seconds"], 180)

    def test_code_runner_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            outside = Path(tmp) / "outside.py"
            outside.write_text("print('x')", encoding="utf-8")
            profile = load_profile("local-dev", workspace)
            with self.assertRaises(PermissionError):
                CodeTaskRunner(profile, AuditLogger(profile)).analyze(
                    "fixture-analysis-small", outside, dry_run=True
                )

    def test_code_task_rejects_non_task_capable_model_even_on_dry_run(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with self.assertRaisesRegex(ValueError, "not suitable for write execution"):
            CodeTaskRunner(profile, AuditLogger(profile)).write(
                "fixture-embedding-small", "add email validation", dry_run=True
            )

    def test_model_complete_supports_openai_compatible_backend(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["openai"] = {
            "ownership": "managed_service",
            "runtime": "openai",
            "protocol": "openai_compatible",
            "endpoint": "https://api.example.test/v1",
            "enabled": True,
            "api_key_env": "OPENAI_API_KEY",
        }
        profile.models.setdefault("models", {})["openai-main"] = {
            "provider": "openai",
            "model": "gpt-demo",
            "roles": ["chat"],
            "local": False,
            "enabled": True,
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "openai ok"}}]}
                ).encode("utf-8")

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("aiplane.backends.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ModelCatalog(profile).complete("openai-main", "hello")
        self.assertEqual(result.backend, "openai_compatible")
        self.assertEqual(result.text, "openai ok")
        request = opened.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://api.example.test/v1/chat/completions"
        )
        self.assertEqual(request.headers.get("Authorization"), "Bearer test-key")

    def test_model_complete_supports_anthropic_messages_backend(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["anthropic"] = {
            "ownership": "managed_service",
            "runtime": "anthropic",
            "protocol": "anthropic_api",
            "endpoint": "https://api.anthropic.test",
            "enabled": True,
            "api_key_env": "ANTHROPIC_API_KEY",
        }
        profile.models.setdefault("models", {})["claude-main"] = {
            "provider": "anthropic",
            "model": "claude-demo",
            "roles": ["chat"],
            "local": False,
            "enabled": True,
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {"content": [{"type": "text", "text": "anthropic ok"}]}
                ).encode("utf-8")

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("aiplane.backends.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ModelCatalog(profile).complete("claude-main", "hello")
        self.assertEqual(result.backend, "anthropic_messages")
        self.assertEqual(result.text, "anthropic ok")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.test/v1/messages")
        self.assertEqual(request.headers.get("X-api-key"), "test-key")
        self.assertEqual(request.headers.get("Anthropic-version"), "2023-06-01")

    def test_model_complete_supports_azure_openai_backend(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        profile.models.setdefault("providers", {})["azure_openai"] = {
            "ownership": "managed_service",
            "runtime": "azure_openai",
            "protocol": "azure_openai",
            "endpoint": "https://example.openai.azure.com",
            "api_version": "2024-02-01",
            "enabled": True,
            "api_key_env": "AZURE_OPENAI_API_KEY",
        }
        profile.models.setdefault("models", {})["azure-main"] = {
            "provider": "azure_openai",
            "model": "demo-deployment",
            "roles": ["chat"],
            "local": False,
            "enabled": True,
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "azure ok"}}]}
                ).encode("utf-8")

        with (
            patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}),
            patch("aiplane.backends.urlopen", return_value=FakeResponse()) as opened,
        ):
            result = ModelCatalog(profile).complete("azure-main", "hello")
        self.assertEqual(result.backend, "azure_openai")
        self.assertEqual(result.text, "azure ok")
        request = opened.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://example.openai.azure.com/openai/deployments/demo-deployment/chat/completions?api-version=2024-02-01",
        )
        self.assertEqual(request.headers.get("Api-key"), "test-key")

    def test_runtime_catalog_maps_sources_and_models(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        catalog = RuntimeCatalog(profile)
        mapped = catalog.map()
        self.assertIn("Hugging Face Hub", mapped["diagram"])
        runtimes = {row["name"] for row in catalog.list()}
        self.assertIn("vllm", runtimes)
        self.assertIn("llamacpp", runtimes)
        self.assertNotIn("lmstudio", runtimes)
        grouped = catalog.models_by_runtime("vllm")
        names = {row["name"] for row in grouped["models"]["vllm"]}
        self.assertIn("provider-code-large-vllm", names)
        nvidia_entry = {
            "provider": "nvidia",
            "model": "nvidia/Nemotron-Test",
            "source": "nvidia",
        }
        self.assertEqual(
            catalog.compatible_runtimes_for_entry(nvidia_entry),
            ["vllm", "tgi", "transformers"],
        )

    def test_runtime_catalog_shows_model_runtimes_and_preference(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        info = RuntimeCatalog(profile).runtimes_by_model("provider-code-large-vllm")
        runtime_names = {row["name"] for row in info["runtimes"]}
        self.assertIn("vllm", runtime_names)
        self.assertIn("tgi", runtime_names)
        self.assertEqual(info["preferred_runtime"], "vllm")

    def test_runtime_bundle_plan_renders_dockerfile_and_conda_yaml(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        plan = RuntimeCatalog(profile).bundle_plan(
            "vllm", model_name="provider-code-large-vllm", mode="docker"
        )
        self.assertEqual(plan["name"], "vllm-provider-code-large-vllm-docker")
        self.assertEqual(plan["selected_file"], "Dockerfile")
        self.assertIn("FROM python:3.13-slim", plan["files"]["Dockerfile"])
        self.assertIn("Provider/Code-Large-Instruct", plan["files"]["Dockerfile"])
        self.assertIn("name: aiplane-vllm", plan["files"]["environment.yaml"])

    def test_runtime_preference_can_be_changed(self) -> None:
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
            changed = RuntimeCatalog(profile).set_preferred_runtime(
                "provider-code-large-vllm", "tgi"
            )
            self.assertEqual(changed["preferred_runtime"], "tgi")
            self.assertIn(
                "preferred_runtime: tgi",
                (root / "models.yaml").read_text(encoding="utf-8"),
            )

    def test_ollama_helper_status_is_human_readable(self) -> None:
        root = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            (bindir / "ollama").write_text(
                '#!/usr/bin/env bash\nif [[ "$1" == "--version" ]]; then echo \'ollama version is 1.2.3\'; elif [[ "$1" == "list" ]]; then echo \'NAME ID SIZE MODIFIED\'; fi\n',
                encoding="utf-8",
            )
            (bindir / "curl").write_text(
                '#!/usr/bin/env bash\nprintf \'%s\' \'{"models":[{"name":"provider-text-small:0.5b","model":"provider-text-small:0.5b","size":397821516,"details":{"parameter_size":"494.03M","quantization_level":"Q4_K_M"},"capabilities":["completion","tools"]}]}\'\n',
                encoding="utf-8",
            )
            for path in bindir.iterdir():
                path.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
            completed = subprocess.run(
                [
                    "scripts/provider_helper.sh",
                    "--provider",
                    "ollama",
                    "--action",
                    "status",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Ollama status", completed.stdout)
        self.assertIn("api_running: yes", completed.stdout)
        self.assertIn("models: 1", completed.stdout)
        self.assertIn("provider-text-small:0.5b", completed.stdout)
        self.assertNotIn("+ curl", completed.stdout)
        self.assertNotIn('"models"', completed.stdout)

    def test_setup_env_can_be_sourced_without_ending_shell(self) -> None:
        root = Path.cwd()
        completed = subprocess.run(
            [
                "bash",
                "-lc",
                (
                    "set +e +u +o pipefail; "
                    "source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable --dry-run; "
                    "status=$?; "
                    "case $- in *e*) errexit=on ;; *) errexit=off ;; esac; "
                    "case $- in *u*) nounset=on ;; *) nounset=off ;; esac; "
                    "if set -o | grep -q '^pipefail[[:space:]]*on'; then pipefail=on; else pipefail=off; fi; "
                    "printf 'after-source status=%s errexit=%s nounset=%s pipefail=%s\\n' "
                    '"$status" "$errexit" "$nounset" "$pipefail"; '
                    "exit $status"
                ),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("after-source status=0", completed.stdout)
        self.assertIn("errexit=off", completed.stdout)
        self.assertIn("nounset=off", completed.stdout)
        self.assertIn("pipefail=off", completed.stdout)

    def test_setup_env_install_bootstraps_profile_before_doctor(self) -> None:
        root = Path.cwd()
        syntax = subprocess.run(
            ["bash", "-n", "scripts/setup_env.sh"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        completed = subprocess.run(
            [
                "scripts/setup_env.sh",
                "--mode",
                "local",
                "--action",
                "install",
                "--editable",
                "--python",
                "python",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        bootstrap = "python -m aiplane profiles bootstrap-local --no-discovery"
        doctor = "python -m aiplane profiles list"
        self.assertIn(bootstrap, completed.stdout)
        self.assertIn(doctor, completed.stdout)
        self.assertLess(
            completed.stdout.index(bootstrap), completed.stdout.index(doctor)
        )

    def test_setup_env_conda_install_repairs_existing_env_without_python(self) -> None:
        root = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            fakebin = Path(tmp) / "bin"
            fakebin.mkdir()
            log_path = Path(tmp) / "conda.log"
            state_path = Path(tmp) / "python-installed"
            conda = fakebin / "conda"
            conda.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$CONDALOG"
if [[ "$1 $2" == "env list" ]]; then
  printf 'aiplane /tmp/aiplane\n'
  exit 0
fi
if [[ "$1" == "run" ]]; then
  if [[ "${4:-}" == "python" && "${5:-}" == "--version" && ! -f "$CONDA_PYTHON_INSTALLED" ]]; then
    printf 'python: command not found\n' >&2
    exit 127
  fi
  if [[ "${4:-}" == "python" && ! -f "$CONDA_PYTHON_INSTALLED" ]]; then
    exit 127
  fi
  exit 0
fi
if [[ "$1" == "install" ]]; then
  touch "$CONDA_PYTHON_INSTALLED"
  exit 0
fi
exit 0
""",
                encoding="utf-8",
            )
            conda.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH', '')}"
            env["CONDALOG"] = str(log_path)
            env["CONDA_PYTHON_INSTALLED"] = str(state_path)
            completed = subprocess.run(
                [
                    "scripts/setup_env.sh",
                    "--mode",
                    "conda",
                    "--conda-env",
                    "aiplane",
                    "--action",
                    "install",
                    "--editable",
                    "--activate",
                    "0",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            conda_log = log_path.read_text(encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "Conda environment exists but does not contain Python: aiplane",
            completed.stderr,
        )
        self.assertIn("+ conda install -n aiplane python=3.13 -y", completed.stdout)
        self.assertIn("install -n aiplane python=3.13 -y", conda_log)

    def test_provider_helper_runtime_dry_runs(self) -> None:
        root = Path.cwd()
        syntax = subprocess.run(
            ["bash", "-n", "scripts/provider_helper.sh"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        install = subprocess.run(
            [
                "scripts/provider_helper.sh",
                "--provider",
                "vllm",
                "--action",
                "install",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertIn("pip install vllm", install.stdout)
        start = subprocess.run(
            [
                "scripts/provider_helper.sh",
                "--provider",
                "tgi",
                "--action",
                "start",
                "--model",
                "Provider/Code-Large-Instruct",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(start.returncode, 0, start.stderr)
        self.assertIn("text-generation-inference", start.stdout)
        ollama_docker = subprocess.run(
            [
                "scripts/provider_helper.sh",
                "--provider",
                "ollama",
                "--action",
                "start",
                "--substrate",
                "docker",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ollama_docker.returncode, 0, ollama_docker.stderr)
        self.assertIn("docker run", ollama_docker.stdout)
        self.assertIn("ollama/ollama:latest", ollama_docker.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            profile_dir = profiles_dir / "local-dev"
            shutil.copytree(Path("profile-templates/local-dev"), profile_dir)
            (profile_dir / "models.yaml").write_text(
                """models:
  hf_gguf_chat:
    provider: llamacpp
    source: huggingface_gguf
    model: Example/Chat-GGUF
    enabled: true
    supported_runtimes: [llamacpp, ollama]
    preferred_runtime: llamacpp
    roles: [chat]
  hf_gguf_discovered_without_runtime_copy:
    provider: llamacpp
    source: huggingface_gguf
    model: Example/Discovered-GGUF
    enabled: true
    preferred_runtime: llamacpp
    roles: [chat]
""",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["AIPLANE_PROFILES_DIR"] = str(profiles_dir)
            ollama_hf = subprocess.run(
                [
                    "scripts/provider_helper.sh",
                    "--provider",
                    "ollama",
                    "--action",
                    "pull",
                    "--profile",
                    "local-dev",
                    "--model",
                    "hf_gguf_chat",
                    "--dry-run",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            ollama_remove = subprocess.run(
                [
                    "scripts/provider_helper.sh",
                    "--provider",
                    "ollama",
                    "--action",
                    "remove",
                    "--profile",
                    "local-dev",
                    "--model",
                    "hf_gguf_chat",
                    "--dry-run",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            ollama_discovered = subprocess.run(
                [
                    "scripts/provider_helper.sh",
                    "--provider",
                    "ollama",
                    "--action",
                    "pull",
                    "--profile",
                    "local-dev",
                    "--model",
                    "hf_gguf_discovered_without_runtime_copy",
                    "--dry-run",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            ollama_clear = subprocess.run(
                [
                    "scripts/provider_helper.sh",
                    "--provider",
                    "ollama",
                    "--action",
                    "clear",
                    "--profile",
                    "local-dev",
                    "--dry-run",
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(ollama_hf.returncode, 0, ollama_hf.stderr)
        self.assertIn("ollama pull hf.co/Example/Chat-GGUF", ollama_hf.stdout)
        self.assertEqual(ollama_remove.returncode, 0, ollama_remove.stderr)
        self.assertIn("ollama rm hf.co/Example/Chat-GGUF", ollama_remove.stdout)
        self.assertEqual(ollama_discovered.returncode, 0, ollama_discovered.stderr)
        self.assertIn(
            "ollama pull hf.co/Example/Discovered-GGUF", ollama_discovered.stdout
        )
        self.assertEqual(ollama_clear.returncode, 0, ollama_clear.stderr)
        self.assertIn("ollama list | awk", ollama_clear.stdout)
        self.assertIn("xargs -r -n1 ollama rm", ollama_clear.stdout)

    def test_runtime_helper_receives_custom_profiles_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles_dir = Path(tmp) / "profiles"
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    cli_main(
                        [
                            "--profiles-dir",
                            str(profiles_dir),
                            "quickstart",
                            "local-coding",
                            "--no-discovery",
                            "--no-hardware-discovery",
                        ]
                    ),
                    0,
                )
            completed = subprocess.CompletedProcess(
                args=["provider_helper"], returncode=0, stdout="", stderr=""
            )
            with patch("aiplane.cli.subprocess.run", return_value=completed) as run:
                code = cli_main(
                    [
                        "--profiles-dir",
                        str(profiles_dir),
                        "runtimes",
                        "start",
                        "vllm",
                        "--profile",
                        "local-dev",
                        "--model",
                        "provider-code-large-vllm",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(
                run.call_args.kwargs["env"]["AIPLANE_PROFILES_DIR"], str(profiles_dir)
            )

    def test_runtime_lifecycle_reports_unavailable_helper_for_planned_runtime(
        self,
    ) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["runtimes", "install", "diffusers", "--dry-run"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "runtime_helper_unavailable")
        self.assertFalse(payload["supported_by_aiplane_helper"])
        self.assertIn("install_hint", payload)

    def test_runtime_prerequisites_reports_missing_ubuntu_tools(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with patch("aiplane.runtime_catalog.shutil.which", return_value=None):
            payload = RuntimeCatalog(profile).prerequisites("vllm")
        self.assertEqual(payload["name"], "runtime_prerequisites")
        self.assertEqual(payload["runtime"], "vllm")
        self.assertFalse(payload["ok"])
        missing = {row["name"] for row in payload["missing_required"]}
        self.assertIn("python", missing)
        self.assertIn("pip", missing)
        self.assertIn("apt-get install", payload["ubuntu_install_hint"])

    def test_runtime_install_preflight_blocks_when_required_tools_missing(self) -> None:
        stdout = StringIO()
        with (
            patch("aiplane.runtime_catalog.shutil.which", return_value=None),
            redirect_stdout(stdout),
        ):
            code = cli_main(["runtimes", "install", "--profile", "local-dev", "vllm"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["runtime"], "vllm")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["missing_required"])

    def test_runtime_remove_and_clear_require_confirmation(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                ["runtimes", "remove", "ollama", "--model", "fixture-chat-small"]
            )
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "runtime_destructive_confirmation_required")
        self.assertEqual(payload["action"], "remove")

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(["runtimes", "clear", "ollama"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["action"], "clear")

    def test_aiplane_runtime_lifecycle_delegates_to_provider_helper(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "start",
                    "--profile",
                    "local-dev",
                    "vllm",
                    "--model",
                    "Provider/Code-Large-Instruct",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("vllm.entrypoints.openai.api_server", output)
        self.assertIn("Provider/Code-Large-Instruct", output)

    def test_aiplane_runtime_update_installed_and_repull_dry_runs(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "update-installed",
                    "--profile",
                    "local-dev",
                    "all",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Updating helper-managed runtimes", output)
        self.assertIn("pip install --upgrade vllm", output)
        self.assertIn(
            "docker pull ghcr.io/huggingface/text-generation-inference", output
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "repull",
                    "--profile",
                    "local-dev",
                    "ollama",
                    "--model",
                    "all",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("ollama list", stdout.getvalue())

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "start",
                    "--profile",
                    "local-dev",
                    "ollama",
                    "--substrate",
                    "docker",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("docker run", stdout.getvalue())
        self.assertIn("ollama/ollama:latest", stdout.getvalue())

        profile = load_profile("local-dev", Path.cwd())
        profile.models["providers"]["ollama"]["substrate"] = "docker"
        stdout = StringIO()
        with (
            patch("aiplane.cli.load_profile", return_value=profile),
            redirect_stdout(stdout),
        ):
            code = cli_main(
                ["runtimes", "start", "--profile", "local-dev", "ollama", "--dry-run"]
            )
        self.assertEqual(code, 0)
        self.assertIn("docker run", stdout.getvalue())

    def test_aiplane_runtime_bundle_cli_prints_selected_file(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = cli_main(
                [
                    "runtimes",
                    "bundle",
                    "--profile",
                    "local-dev",
                    "vllm",
                    "--model",
                    "provider-code-large-vllm",
                    "--format",
                    "dockerfile",
                ]
            )
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("FROM python:3.13-slim", output)
        self.assertIn("Provider/Code-Large-Instruct", output)

    def test_model_catalog_executes_openai_compatible_runtime(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        with TestHttpServer() as endpoint:
            profile.models["providers"]["vllm"]["enabled"] = True
            profile.models["providers"]["vllm"]["endpoint"] = endpoint
            profile.models["models"]["provider-code-large-vllm"]["enabled"] = True
            profile.models["models"]["provider-code-large-vllm"]["model"] = "test-model"
            result = ModelCatalog(profile).complete("provider-code-large-vllm", "hello")
        self.assertEqual(result.backend, "openai_compatible")
        self.assertEqual(result.text, "handled test-model")
