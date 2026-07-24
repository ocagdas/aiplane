# Manual Test Checklist

For a shorter copy-paste procedure that captures shareable P0, replay, hardware-calibration, benchmark-calibration, and optional Docker Model Runner evidence, use the [Field Evidence Collection Runbook](evidence-collection.md). This checklist remains the exhaustive feature-acceptance path.

This checklist validates an `aiplane` installation from a clean shell through profiles, hardware, catalogs, model selection, runtime evidence, interactive chat, integrations, agents, reproducibility, stacks, and render-only Kubernetes artifacts.

Use a disposable working directory and a disposable profile. Commands marked **read-only** do not intentionally change state. Commands marked **preview** render a proposed mutation. Commands marked **mutating** require review and may install software, download model weights, or edit the disposable profile. External runtimes remain separate products; skip runner-specific live checks when that runner or suitable hardware is unavailable.

## Test record

Record these before starting:

- [ ] Tester and host:
- [ ] Operating system and architecture:
- [ ] CPU and RAM:
- [ ] GPU/accelerator vendor, devices, and memory:
- [ ] Python version:
- [ ] Aiplane version/install type:
- [ ] Runtime(s) selected for live testing:
- [ ] Profile name: `manual-test`
- [ ] Model alias selected later as `CHAT_ALIAS`:
- [ ] Provider-native model id selected later as `MODEL_ID`:

The examples use POSIX shell syntax. In PowerShell, set variables with `$env:AIPLANE_PROFILE = "manual-test"`; otherwise pass `--profile manual-test` to each command.

## 1. Install and identify the build

Choose exactly one installation path.

Released wheel:

```bash
sha256sum --check SHA256SUMS
gh attestation verify aiplane-*.whl --repo ocagdas/aiplane
uv tool install ./aiplane-VERSION-py3-none-any.whl
```

Alternative isolated installer:

```bash
pipx install ./aiplane-VERSION-py3-none-any.whl
```

Contributor source checkout:

```bash
scripts/setup_env.sh --mode venv --action install --editable
source .venv/bin/activate
```

Confirm the installation:

```bash
aiplane --version
aiplane --help
aiplane profiles templates
```

- [ ] Checksum succeeds for a release artifact.
- [ ] Attestation succeeds when testing a published release.
- [ ] `--version` reports the expected version, install type, and module path.
- [ ] Top-level help separates core, advanced, and experimental commands.
- [ ] Profile templates are listed.

## 2. Create an isolated profile

**Mutating only inside the chosen profile directory:**

```bash
mkdir aiplane-manual-test
cd aiplane-manual-test
export AIPLANE_PROFILE=manual-test
aiplane profiles create manual-test --template local-dev
aiplane profiles list
aiplane profiles validate manual-test
aiplane profiles show manual-test
```

If the installed template has a different name, select one shown by `profiles templates`.

- [ ] Only the `manual-test` profile is created or selected.
- [ ] Validation returns `ok: true`.
- [ ] Output contains no credential values.
- [ ] Re-running creation without an overwrite option does not silently replace edits.

Canonical schema and rendering, **read-only**:

```bash
aiplane profiles schema
aiplane profiles render manual-test
aiplane config format
aiplane config verbosity
```

- [ ] Schema and rendered profile are valid JSON.
- [ ] Rendering is stable across two consecutive runs.

## 3. Baseline onboarding and doctors

**Read-only/preview:**

```bash
aiplane quickstart local-coding --dry-run --no-discovery
aiplane quickstart local-coding --dry-run --no-discovery --format json
aiplane discover
aiplane doctor
aiplane doctor --format json
aiplane environment doctor --required-only
aiplane environment doctor --required-only --format json
aiplane tools matrix
aiplane tools matrix --workflow cloud_vm
aiplane environment doctor --workflow local_runtime --format json
```

- [ ] Preview does not install runtimes or pull models.
- [ ] JSON stdout parses without progress text contamination.
- [ ] Discover output labels detected, configured, generated, and unresolved provenance.
- [ ] Doctor findings include stable identifiers, severity, reason, impact, and remediation metadata.
- [ ] Required environment checks pass, or each failure gives a concrete remedy.

## 4. Hardware discovery and machine evidence

**Read-only:**

```bash
aiplane hardware schema
aiplane hardware discover
aiplane hardware active
aiplane hardware doctor
aiplane hardware scoring
aiplane hardware recommend
aiplane hardware export-machine --name manual-host > manual-host.machine.yaml
aiplane machines list
aiplane machines recommend
```

Optional disposable import, **mutating profile state**:

```bash
aiplane machines import manual-host.machine.yaml
aiplane machines show manual-host
```

- [ ] CPU architecture, logical/physical cores, and RAM are plausible.
- [ ] Every accelerator is represented separately with vendor, API, and memory evidence where discoverable.
- [ ] Multiple or heterogeneous GPUs are not collapsed into a fictitious single device.
- [ ] Apple Silicon reports unified-memory/Metal facts; NVIDIA reports CUDA facts; AMD reports ROCm/Vulkan facts only when observed.
- [ ] Missing vendor tools lower confidence or produce unresolved fields rather than invented values.
- [ ] Exported machine evidence can be inspected without importing it.

## 5. Provider and model discovery

Start with a bounded preview. Network-backed providers are optional.

```bash
aiplane providers list
aiplane providers diagnose
aiplane providers diagnose openai
aiplane runtimes sources
aiplane models refresh --provider ollama --limit 20 --dry-run --verbosity 2
aiplane models refresh --provider huggingface --query text-generation --limit 20 --dry-run --verbosity 2
```

When the preview is acceptable, refresh the selected provider, **mutating the ignored discovery cache**:

```bash
aiplane models refresh --provider ollama --limit 100
aiplane models refresh --provider huggingface --query text-generation --limit 100
```

- [ ] Preview identifies its source and proposed changes.
- [ ] Refresh reports added/updated/unchanged counts.
- [ ] The enriched materialized catalog is regenerated automatically.
- [ ] No API keys, authorization headers, or credential values appear in generated catalog data.
- [ ] A temporarily unavailable provider produces a structured failure/fallback rather than corrupting curated profile entries.

## 6. Query the enriched catalog

These commands are **read-only**. They should show aliases next to provider-native model ids by default.

```bash
aiplane models list --identity both --format text --limit 20
aiplane models list --identity alias --limit 20
aiplane models list --identity model --limit 20
aiplane models list --runtime ollama --role chat --enabled-only --identity both
aiplane models list --current-machine --role chat --sort-by parameters --limit 20
aiplane models list --ram-gb 32 --vram-gb 8 --gpu-vendor nvidia --accelerator-api cuda --max-parameters-b 14
aiplane models list --property quantization=q4 --min-benchmark-score 50 --sort-by benchmark
aiplane models list --group-by runtime --format json
aiplane models list --catalog-cache off --format json > full-scan.json
aiplane models list --catalog-cache rebuild --format json > indexed.json
aiplane recommend --intent coding --format text
aiplane recommend --intent throughput --format json
```

- [ ] Text output places alias and native id adjacent.
- [ ] `--identity alias` and `--identity model` emit one selected identity per line.
- [ ] Runtime, role, property, benchmark, provider, parameter, hardware, vendor, and accelerator filters behave independently and in combination.
- [ ] Indexed and full-scan query results are equivalent for the same filters.
- [ ] Corrupting or removing the ignored materialized cache causes a safe rebuild on the next auto query.

Optional on-demand catalog performance evidence:

```bash
AIPLANE_RUN_PERFORMANCE=1 python -m pytest -q tests/performance/test_catalog_query_performance.py
```

- [ ] The 1k, 10k, and 100k cases run only when opted in.
- [ ] Results are treated as host-local regression evidence, not a universal speed claim.

## 7. Select and inspect a compatible chat alias

Choose one alias from the preceding output and substitute it below:

```bash
export CHAT_ALIAS=YOUR_ALIAS
export RUNTIME=ollama
aiplane models show "$CHAT_ALIAS"
aiplane runtimes model "$CHAT_ALIAS" --include-gui
aiplane hardware assess "$CHAT_ALIAS"
aiplane hardware recommend --runtime "$RUNTIME"
```

- [ ] `models show` distinguishes alias, native id, source/provider, ownership, and supported runtimes.
- [ ] The assessment separates hard eligibility from scored ranking.
- [ ] Weight, KV-cache, offload, tensor-parallel, and CPU assumptions are explicit.
- [ ] Unknown architecture data remains unresolved instead of producing fake precision.

## 8. Verify six-runner parity and prerequisites

**Read-only:**

```bash
aiplane runtimes list --include-gui --format json
aiplane runtimes capabilities
aiplane runtimes capabilities ollama
aiplane runtimes capabilities llamacpp
aiplane runtimes capabilities mlx
aiplane runtimes capabilities docker_model_runner
aiplane runtimes capabilities lmstudio
aiplane runtimes capabilities vllm
aiplane runtimes prerequisites all
```

- [ ] Each primary runner reports detection, inventory, identity mapping, fit, health, endpoint export, and lifecycle state.
- [ ] States distinguish supported, planned-only, and runtime-managed operations.
- [ ] MLX is first-class and clearly constrained to compatible Apple Silicon/macOS environments.
- [ ] GUI/runtime-managed limitations are explicit rather than represented as blanket support.

Runner-specific read checks; run only installed runners:

```bash
aiplane runtimes status ollama
aiplane runtimes list-runtime-models ollama
aiplane runtimes status docker_model_runner
aiplane runtimes list-runtime-models docker_model_runner
aiplane runtimes status lmstudio
aiplane runtimes list-runtime-models lmstudio
aiplane runtimes status vllm
aiplane runtimes list-runtime-models vllm
aiplane runtimes status llamacpp
aiplane runtimes list-runtime-models llamacpp
aiplane runtimes status mlx
aiplane runtimes list-runtime-models mlx
```

- [ ] Installed-model output preserves catalog alias/native-id mapping where a configured alias exists.
- [ ] Active-only runners report the served model rather than claiming a full disk inventory.
- [ ] Missing runners fail with install/configuration guidance.

## 9. Render artifact and launch evidence

Use the runtime selected with `CHAT_ALIAS`:

```bash
aiplane runtimes artifact-lock --model "$CHAT_ALIAS"
aiplane runtimes launch-manifest "$RUNTIME" --model "$CHAT_ALIAS"
aiplane runtimes launch-manifest vllm --model "$CHAT_ALIAS" --host 0.0.0.0 --port 8000 --context-tokens 8192 --gpu-device 0 --tensor-parallel 1
aiplane runtimes bundle "$RUNTIME" --model "$CHAT_ALIAS" --mode auto --format json
aiplane runtimes bundle "$RUNTIME" --model "$CHAT_ALIAS" --mode auto --format selected-file
# Exercise all Docker-only settings with a vLLM-compatible alias:
aiplane runtimes bundle vllm --model provider-code-large-vllm --mode docker --cache-volume manual-model-cache --gpu-device all --env HF_HOME --auth-env HF_TOKEN --context-tokens 8192 --tensor-parallel 1
# Confirm unsupported settings fail instead of being ignored:
aiplane runtimes bundle vllm --model provider-code-large-vllm --mode conda --gpu-device 0
```

- [ ] Artifact lock includes alias, native model id, source, revision/file, checksum/digest, format, quantization, and completeness.
- [ ] Missing immutable revision/checksum remains null and `complete` is false.
- [ ] Launch manifest is versioned, secret-free, render-only, and includes exact command, endpoint, health path, device selection, context, and parallel/offload inputs.
- [ ] vLLM uses `vllm serve`; MLX uses `python -m mlx_lm.server`.
- [ ] No process starts while rendering evidence.
- [ ] Bundle JSON reports an explicit reproducibility level and blockers; mutable `latest` images are recipe-deterministic, not reproducible builds.
- [ ] llama.cpp rejects `--mode docker`; native mode remains available.

## 10. Preview, install, and prepare a runtime/model

Always preview first:

```bash
aiplane runtimes install "$RUNTIME" --dry-run
aiplane runtimes start "$RUNTIME" --model "$CHAT_ALIAS" --dry-run
aiplane runtimes pull "$RUNTIME" --model "$CHAT_ALIAS" --dry-run
aiplane models pull "$CHAT_ALIAS" --for-runtime "$RUNTIME" --dry-run
```

On a supported host, review and run only the operations you intend, **mutating external runtime state**:

```bash
aiplane runtimes install "$RUNTIME"
aiplane runtimes start "$RUNTIME" --model "$CHAT_ALIAS"
aiplane runtimes pull "$RUNTIME" --model "$CHAT_ALIAS"
aiplane runtimes status "$RUNTIME"
aiplane runtimes list-runtime-models "$RUNTIME"
```

- [ ] Preview shows commands and shared artifact/launch evidence when an alias is known.
- [ ] Unsupported platforms stop before running installer commands.
- [ ] Removal/clear requires both explicit target review and `--yes`; verify with `--dry-run`, but do not perform destructive cleanup during a shared-machine test.
- [ ] MLX mutating operations remain plan-only and tell the tester to run the reviewed launch command externally.

Native runner cross-checks when installed:

```bash
ollama list
docker model status --json
docker model list --json
lms status
lms ls --json
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/v1/models
curl -fsS http://localhost:8080/health
```

- [ ] Aiplane’s status/inventory agrees with the native runner view.

## 11. Endpoint chat

First preview:

```bash
aiplane chat --model "$CHAT_ALIAS" --prompt "Reply with exactly: ready" --dry-run
```

Then run a single prompt and an interactive session:

```bash
aiplane chat --model "$CHAT_ALIAS" --prompt "Reply with exactly: ready"
aiplane chat --model "$CHAT_ALIAS"
```

At the prompt, send `hello`, then `/exit`.

Optional native Ollama path:

```bash
aiplane chat --model "$CHAT_ALIAS" --native-ollama --dry-run
aiplane chat --model "$CHAT_ALIAS" --native-ollama
```

- [ ] The CLI expects an Aiplane alias, not an unreviewed native id.
- [ ] Preview prints the resolved alias, native id, runtime/provider, and endpoint/command.
- [ ] Single and interactive chat return model text.
- [ ] `/exit` ends the interactive session cleanly.

## 12. Benchmarking, measurements, and custom hooks

**Preview/read-only:**

```bash
aiplane models benchmark "$CHAT_ALIAS" --task analysis --dry-run --no-save
aiplane benchmarks list
aiplane benchmarks doctor
aiplane benchmarks plan aiplane-smoke --model "$CHAT_ALIAS"
aiplane hardware scoring
```

Run a saved smoke benchmark only after the endpoint works:

```bash
aiplane models benchmark "$CHAT_ALIAS" --task all
aiplane models list --require-benchmark --sort-by benchmark
aiplane benchmarks compare --by runtime --model "$CHAT_ALIAS"
aiplane benchmarks compare --by model --runtime "$RUNTIME"
```

Validate a versioned custom suite and preview an external measurement import:

```bash
aiplane benchmarks suite-validate path/to/suite.json
aiplane benchmarks import path/to/measurements.json --dry-run
```

- [ ] Smoke scores are scoped to the named/versioned suite and are not presented as universal quality.
- [ ] Benchmark records include runtime evidence.
- [ ] Native prompt/output token counts, elapsed time, TTFT, and throughput appear only when the runtime exposes them; unavailable values remain null.
- [ ] Comparison leaders appear only for at least two distinct values under explicit suite comparability metadata.
- [ ] TTFT leaders contain a non-empty telemetry source; provenance-free TTFT cannot become a leader.
- [ ] Quality, performance, throughput, elapsed time, and TTFT remain separate rather than collapsing into a universal score.
- [ ] Custom command evaluators run in the selected environment boundary and return structured scores.
- [ ] User scoring extensions are declarative, versioned, bounded, and provenance-labelled.
- [ ] External measurement import is preview-first and rejects invalid contracts.

## 13. Integration exports

All commands in this section are **read-only** unless `setup` is run without `--dry-run`.

```bash
aiplane integrations list
aiplane integrations roles continue
aiplane integrations plan continue --select-best --runtime "$RUNTIME"
aiplane integrations setup continue --chat "$CHAT_ALIAS" --runtime "$RUNTIME" --dry-run
aiplane integrations export continue --chat "$CHAT_ALIAS"
aiplane integrations export codex --model "$CHAT_ALIAS"
aiplane integrations export copilot-cli --model "$CHAT_ALIAS"
aiplane integrations export copilot-vscode --model "$CHAT_ALIAS"
aiplane integrations export openai-compatible --model "$CHAT_ALIAS" --endpoint http://localhost:11434/v1
```

Use `integrations <subcommand> --help` if a target needs role-specific flags in the installed build.

- [ ] Exports print configuration but do not start Continue, Codex, Copilot, or VS Code.
- [ ] Output uses the alias/native model id required by the target and the reviewed endpoint.
- [ ] Secret fields are environment-variable references or placeholders, never credential values.
- [ ] Managed endpoints can be exported when their provider, protocol, and credential reference are configured.
- [ ] Codex custom providers use a supported OpenAI-compatible protocol; provider/auth changes target user-level configuration when required by the host client.

## 14. Agent and orchestrator planning

**Read-only/render-only:**

```bash
aiplane agents templates
aiplane agents plan manual-agent --framework langgraph --model "$CHAT_ALIAS"
aiplane agents manifest manual-agent --framework langgraph --model "$CHAT_ALIAS"
aiplane agents export manual-agent --framework langgraph --model "$CHAT_ALIAS" --file agent.py
aiplane agents export manual-agent --framework langgraph --model "$CHAT_ALIAS" --file agent-environment.yaml
aiplane agents export manual-agent --framework crewai --model "$CHAT_ALIAS" --file framework-config.yaml
aiplane agents export manual-agent --framework autogen --model "$CHAT_ALIAS" --file framework-config.yaml
aiplane agents export manual-agent --framework semantic_kernel --model "$CHAT_ALIAS" --file framework-config.yaml
aiplane agents export manual-agent --framework llamaindex_workflows --model "$CHAT_ALIAS" --file framework-config.yaml
aiplane agents export manual-agent --framework openhands --model "$CHAT_ALIAS" --file framework-config.yaml
aiplane orchestrators list
aiplane orchestrators show langgraph
aiplane orchestrators setup langgraph --runtime "$RUNTIME" --model "$CHAT_ALIAS" --dry-run
aiplane orchestrators doctor langgraph
```

- [ ] Plans contain reviewed model alias, native id, endpoint, tool policy, approval mode, limits, and audit label where configured.
- [ ] The manifest is schema version `1.0`, is marked `render_only`, and says Aiplane does not run agents.
- [ ] Each framework config contains its framework-specific topology key and readiness checks.
- [ ] Single-role frameworks report a readiness mismatch when given multiple roles.
- [ ] Starter output contains no secret values and explicitly says it installs nothing and runs no agents.
- [ ] Aiplane configures and validates the environment; it does not silently launch an autonomous workflow.

## 15. Machines and stacks

Use the imported `manual-host` machine and a compatible runtime/model:

```bash
aiplane stacks setup manual-stack --runtime "$RUNTIME" --model "$CHAT_ALIAS" --machine manual-host --access same_host --dry-run
# For a Docker-managed runtime path, add: --runtime-substrate docker
aiplane stacks setup manual-stack --runtime "$RUNTIME" --model "$CHAT_ALIAS" --machine manual-host --access same_host
aiplane stacks show manual-stack
aiplane stacks plan manual-stack
aiplane agents manifest manual-stack-agents --stack manual-stack
aiplane stacks doctor manual-stack
aiplane stacks endpoint-plan manual-stack
aiplane stacks prepare manual-stack --dry-run
aiplane stacks prepare manual-stack
aiplane stacks start manual-stack --dry-run
aiplane stacks start manual-stack
aiplane stacks status manual-stack
# Run mutating same-host operations only after reviewing previews:
aiplane stacks prepare manual-stack --yes
aiplane stacks start manual-stack --yes
```

- [ ] Stack plan includes fit, runtime status, endpoint security, artifact lock, and launch manifest.
- [ ] Doctor has a `runtime_evidence_rendered` check.
- [ ] An incompatible runtime/model tuple produces an explicit evidence failure reason.
- [ ] Lifecycle previews include the same evidence contracts.
- [ ] Omitting `--yes` returns `confirmation_required` and executes no command.
- [ ] A Docker Model Runner stack resolves the alias to its native model id, uses `http://localhost:12434/engines/v1`, and renders native `docker model` commands.
- [ ] Remote targets remain planned-not-executed unless an explicitly supported guarded boundary exists.

## 16. Render-only Kubernetes artifacts

This feature never calls `kubectl` or Helm.

```bash
aiplane stacks render-kubernetes manual-stack --image registry.example/runtime@sha256:REVIEWED --device-class gpu.example.com --namespace aiplane-test --replicas 1 --claim-count 1 --cpu 4 --memory 32Gi --cache-size 100Gi
aiplane stacks render-kubernetes manual-stack --image registry.example/runtime@sha256:REVIEWED --device-class gpu.example.com --file resourceclaim.yaml
aiplane stacks render-kubernetes manual-stack --image registry.example/runtime@sha256:REVIEWED --device-class gpu.example.com --file deployment.yaml
aiplane stacks render-kubernetes manual-stack --image registry.example/runtime@sha256:REVIEWED --device-class gpu.example.com --file service.yaml
aiplane stacks render-kubernetes manual-stack --image registry.example/runtime@sha256:REVIEWED --device-class gpu.example.com --file values.yaml
```

- [ ] Family contains exactly ResourceClaim, Deployment, Service, and Helm values.
- [ ] Two identical invocations are byte-for-byte deterministic.
- [ ] ResourceClaim uses the reviewed DRA device class and count.
- [ ] Deployment consumes the runtime launch command and health path.
- [ ] CPU/memory/cache settings, probes, non-root security context, dropped capabilities, and image pull policy are present.
- [ ] Output declares `render_only: true`, `apply_supported: false`, and `review_required: true`.
- [ ] Output contains no Secret object or credential value.
- [ ] Invalid names, quantities, replicas, claim counts, service types, and image pull policies fail before rendering.
- [ ] No cluster mutation occurs.

## 17. Profile archive, restore, comparison, drift, and replay

Use paths outside the profile directory to avoid self-inclusion surprises.

```bash
aiplane profiles archive manual-test --output manual-test.profile.json --dry-run
aiplane profiles archive manual-test --output manual-test.profile.json
aiplane profiles restore manual-test.profile.json --as manual-restored
aiplane profiles restore manual-test.profile.json --as manual-restored --yes
aiplane profiles validate manual-restored
aiplane profiles compare manual-test manual-restored
aiplane profiles drift manual-restored
```

For replay, restore and re-archive on two independent disposable clients, then run:

```bash
aiplane profiles replay-check manual-test.profile.json --source archive --client-archive client-a.profile.json --client-archive client-b.profile.json
```

- [ ] Preview performs no write.
- [ ] Archive is deterministic and includes checksums and explicit inclusion/exclusion rules.
- [ ] Credentials, runtime weights, caches, logs, and machine-local state are excluded.
- [ ] Restore never overwrites an existing profile silently.
- [ ] Exact copies classify as exact; hardware-only compatible variance classifies as capability-equivalent.
- [ ] Replay evidence includes derived artifact locks without embedding model weights.

## 18. MCP and policy/audit read surfaces

```bash
aiplane mcp manifest
aiplane policy explain --action provider:ollama
aiplane policy list
aiplane policy drift
aiplane policy grant --action tool:write_file --reason "manual acceptance window" --expires-in 30m --yes
# Copy the id from policy list before revoking:
aiplane policy revoke GRANT_ID --yes
aiplane audit tail --limit 50
```

Optional protocol smoke in a disposable shell:

```bash
aiplane mcp serve
```

Send a valid MCP initialize request from an MCP client, inspect the tool list, then terminate the stdio process.

- [ ] Manifest exposes structured read/planning tools.
- [ ] Mutating tools remain guarded; arbitrary shell execution is not exposed.
- [ ] Policy output explains allowed, approval-required, temporarily-approved, blocked, and overridden decisions.
- [ ] Grants are action-scoped, expiring, ignored workspace-local JSON; grant and revoke events are audited.
- [ ] `policy drift` reports expired or stale grants, and malformed local state fails closed.
- [ ] Audit output redacts secrets.


## 18A. Render deployment starters without applying them

**Read-only:**

```bash
aiplane deploy workflow-plan --target azure_gpu_vm
aiplane deploy render --target azure_gpu_vm
aiplane deploy render --target azure_gpu_vm --file main.tf
aiplane deploy render --target aks_gpu_pool
aiplane deploy render --target gpu_workstation_ssh
```

- [ ] Each JSON family is schema-linked, `render_only: true`, `apply_supported: false`, and checksummed.
- [ ] Azure VM output includes `main.tf`, `aiplane.pkr.hcl`, `inventory.ini`, and `playbook.yml`.
- [ ] AKS output points workload rendering to `stacks render-kubernetes`; it does not run `kubectl` or an IaC apply.
- [ ] SSH workstation output uses only the configured host/user/port and contains no credential value.
- [ ] Repeating a render produces byte-identical JSON and file content.
- [ ] Cloud output reports `artifact_readiness: scaffold`, non-empty `unresolved_inputs`, one selected `iac`, and no plan/apply/up command in `next_commands`.
- [ ] Changing a disposable target copy among `iac: opentofu`, `iac: terraform`, and `iac: pulumi` selects only the matching IaC tool and artifact family. Pulumi emits `Pulumi.yaml`, `requirements.txt`, and `__main__.py` with `pulumi preview --diff`; HCL selections emit `main.tf`. None emits an apply/up command.

## 18B. Verify provider-aware local VM planning

**Read-only:**

```bash
aiplane environment doctor --workflow local_vm
aiplane tools plan vagrant
aiplane tools export vagrant
aiplane deploy workflow-plan --target local_dev_vm
aiplane deploy render --target local_dev_vm
aiplane deploy render --target local_dev_vm --file Vagrantfile
```

- [ ] The workflow names `local_dev_vm` and its selected provider.
- [ ] Vagrant without a usable provider reports `needs_setup`, with provider-specific remediation.
- [ ] `provider: virtualbox`, `libvirt`, `hyperv`, or `vmware_desktop` renders the matching `config.vm.provider` block.
- [ ] The artifact reports `vm_provider`, contains `Vagrantfile` plus `playbook.yml`, and recommends only `vagrant validate`; it does not run `vagrant up`.
- [ ] With multiple local VM targets, `local_vm_default` selects the target used by `tools plan/export vagrant`.

Optional official-tool validation in a disposable directory:

```bash
AIPLANE_RUN_EXTERNAL_VALIDATORS=1 python -m pytest -q tests/test_external_artifact_validation.py -rs
```

- [ ] Installed validators run; unavailable tools and unusable VM providers skip with an explicit reason.
- [ ] Ansible syntax validation does not connect to the configured host.
- [ ] Pulumi uses a disposable local backend and preview only.

## 19. Failure and safety checks

Run these previews or intentionally invalid reads:

```bash
aiplane models show definitely-not-an-alias
aiplane chat --model definitely-not-an-alias --prompt hello
aiplane runtimes launch-manifest vllm --model definitely-not-an-alias
aiplane runtimes remove ollama --model "$CHAT_ALIAS" --dry-run
aiplane runtimes clear ollama --dry-run
aiplane deploy apply --target azure_gpu_vm
```

- [ ] Unknown aliases fail as aliases; they are not passed blindly to a runtime.
- [ ] Destructive runtime operations preview exact targets and require `--yes` to execute.
- [ ] Deployment apply refuses to mutate without explicit confirmation and prerequisite plans.
- [ ] Errors do not print secret values or Python tracebacks unless `--debug` was explicitly requested.

## 20. Contributor regression gate

From a source checkout:

```bash
python -m aiplane profiles validate local-dev
python -m aiplane environment doctor --required-only
python -m aiplane environment doctor --required-only --format json
python -m pytest
python -m ruff format --check src tests
python -m ruff check src tests
```

Optional synthetic catalog benchmark and installed-tool artifact validation:

```bash
AIPLANE_RUN_PERFORMANCE=1 python -m pytest -q tests/performance/test_catalog_query_performance.py
AIPLANE_RUN_EXTERNAL_VALIDATORS=1 python -m pytest -q tests/test_external_artifact_validation.py -rs
```

- [ ] Profile validation passes.
- [ ] Required text and JSON doctors pass.
- [ ] Full tests pass; optional performance tests skip unless opted in.
- [ ] Formatting and lint pass.

## 21. Final test report

- [ ] Installation channel and version recorded.
- [ ] Hardware evidence reviewed for accuracy.
- [ ] Provider/catalog refresh result recorded.
- [ ] Alias and native model id recorded.
- [ ] Runtime and endpoint recorded.
- [ ] Artifact lock completeness recorded.
- [ ] Launch manifest reviewed.
- [ ] Chat result recorded.
- [ ] Benchmark suite/version and native metric availability recorded.
- [ ] Integration exports reviewed for secret safety.
- [ ] Stack evidence and Kubernetes artifact determinism confirmed.
- [ ] Archive/restore/replay result recorded.
- [ ] Skipped optional runners/providers explained.
- [ ] Failures include command, exit code, redacted output, platform facts, and expected versus actual result.
