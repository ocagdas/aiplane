# Project Plan

This is the single source of truth for current project status, command maturity, roadmap, integration direction, prioritized backlog, preview gates, release readiness, external-trial evidence, demo execution, and session handoff.

Keep the sections in this file aligned with behavior, user documentation, CLI help, and focused tests. Product boundary and architecture principles remain in [Strategy](strategy.md); contributor policy remains in [Agent Guidance](agent-guidance.md).

## Contents

- [Current Status and Session Handoff](#current-status-and-session-handoff)
- [Command Coverage](#command-coverage)
- [Roadmap](#roadmap)
- [Integration Roadmap](#integration-roadmap)
- [Product Adoption Backlog](#product-adoption-backlog)
- [Developer-Preview Scope Freeze](#developer-preview-scope-freeze)
- [P0 Maintainer Checklist](#p0-maintainer-checklist)
- [External Trial Evidence](#external-trial-evidence)
- [Public Launch Review](#public-launch-review)
- [Public Demo Plan](#public-demo-plan)

## Current Status and Session Handoff

This file is the short resume point for future `aiplane` development sessions. Use it together with [Agent Guidance](agent-guidance.md), [Project Roadmap](project-plan.md#roadmap), [Strategy](strategy.md), and [Command Coverage](project-plan.md#command-coverage).


### Current Milestone

The approved P0 host-client export exception is implemented locally. `codex`, `copilot-cli`, and `copilot-vscode` are Tier-1 v1 plan/setup/export targets. Codex emits user-level named-profile TOML and requires Responses for custom providers; Copilot CLI emits canonical secret-safe JSON plus POSIX/PowerShell renderings; VS Code emits Custom Endpoint JSON for chat/agent use. Explicit model context/output, tool-calling, streaming, and provider API metadata now flow into plans and compatibility checks. The primary demo exports one reviewed alias to all three hosts without installing, launching, or editing them. Current-client smoke evidence remains required before release promotion. Validation: focused integration/documentation contracts 73 passed plus 13 subtests; full suite 518 passed; focused Ruff, profile validation, and required text/JSON environment doctor checks passed. The repository patch wrapper hit the documented `bwrap: loopback` failure, so edits used narrow `perl`/`ex` rewrites with immediate diff, syntax, format, and test verification.

**Current engineering target: P1 clean-environment replay trials and field evidence; the external-beta P0 evidence gate remains open.**

The P2 hardware-placement foundation is implementation-complete. Discovery now
normalizes per-device evidence on Linux, macOS, and Windows; preserves
heterogeneous devices and topology; and reports free/total memory where the
platform source provides it. `hardware assess` and enhanced
`hardware recommend` expose parameter/quantization weight estimates, exact KV
cache only with sufficient architecture metadata, runtime-specific single GPU,
homogeneous multi-GPU, offload and CPU modes, blockers, assumptions and
confidence. A versioned placement-readiness score keeps hard eligibility
separate, renormalizes only available evidence with coverage, excludes ordinary
smoke results from measured quality/performance, and accepts only declarative
data extensions. Cross-machine calibration and richer MIG/NUMA evidence remain
future evidence work.

Validation for the hardware-placement and scoring milestone: focused hardware,
platform, MCP, schema and architecture coverage passes 84 tests plus 7 subtests;
documentation contracts pass; the full suite passes 581 tests with 3 optional
performance benchmarks skipped; focused Ruff and formatting checks pass; and
profile validation plus required text/JSON environment doctors pass. The patch
wrapper repeatedly hit the documented loopback sandbox failure, so narrowly
scoped assertion-guarded edits were used and then formatter, diff, contract and
full-suite validation were applied.

Project planning is consolidated in this undated `project-plan.md`. Current status, command coverage, roadmap, integration direction, adoption backlog, preview and launch gates, trial evidence, demo flow, and session handoff are maintained as sections here; the former standalone planning files have been removed, and CLI help plus documentation contracts now target this file.

The README adoption surface now leads with one concise outcome, places the safe read-only preview in the first screen, explains value through concrete user questions, keeps the four-command public workflow visible, and collapses the longer local evaluator walkthrough behind progressive disclosure. The developer-preview boundary, mutation warnings, alias/native-model distinction, replay contract, and exact end-to-end command order remain intact and contract-tested. Validation for this documentation slice: the focused README/packaging gate passes 34 tests, the quick format/lint/contract/smoke gate passes 37 tests, and the full suite passes 533 tests plus 23 subtests.

P1 profile portability is implementation-complete for the local CLI boundary: editable YAML remains the backup/replay source of truth; `profiles render` is canonical read-only evidence; deterministic `profiles archive` and preview-by-default `profiles restore` implement the versioned inclusion/exclusion manifest, checksums, credential rejection, path validation, atomic new-profile creation, and never-overwrite conflict behavior. Read-only `profiles compare` accepts profile/archive operands and `profiles drift` assesses live current-machine variance. They classify exact, capability-equivalent, materially incompatible, and unresolved evidence with per-fact provenance. `export` continues to compile target-tool configuration without mutation. Cross-machine field evidence remains part of the P1 trial gate.

Validation for this P1 slice: 13 focused archive/restore/comparison/drift tests pass; the combined profile and documentation contract gate passes 70 tests; the full suite passes 533 tests plus 23 subtests. Deterministic fixtures cover exact, capability-equivalent, materially incompatible, and unresolved results, command immutability, profile/archive operands, and byte-stable Continue export after archive/restore. A real disposable CLI round trip previously proved dry-run archive, archive write, preview restore, confirmed restore, named validation in a multi-profile root, and byte-identical restoration of all ten portable YAML files. Cross-machine field recordings remain an evidence gate, not an implementation claim.

Quickstart progress and terminology are aligned: `quickstart local-coding` updates one deterministic phase-status line on stderr without contaminating stdout, and public entrypoints define the environment doctor as a read-only readiness diagnosis addressing model/task/hardware fit and reproducibility.

P0.5 quickstart sufficiency is complete: provider discovery is opt-in, repeat runs preserve profile edits, empty profiles receive at most two no-YAML setup paths plus a no-runtime dry-run plan, and configured profiles receive one exact Continue export action. Validation: focused quickstart suite 6 passed; quick gate 19 passed; full suite 436 passed; required profile and environment doctor checks passed.

P0.6 stable doctor contract v1 is complete: all findings expose stable IDs, severity, reason, impact, affected resources, and uniform remediation/mutation/dry-run metadata; blocker actions are deterministic and payload exit semantics are authoritative. Validation: focused doctor/contract suite 29 passed; focused doctor suite 14 passed; quick gate 19 passed; full suite 438 passed; required profile and environment doctor checks passed.

P0.7 Tier-1 deterministic exports are implemented: seven v1 golden contracts define the release boundary, advanced exporters are explicitly unversioned, and installed-wheel CI performs real MCP stdio verification on every supported OS.

P0.8 public profile schema v1 is complete: packaged JSON Schema, canonical read-only rendering, deterministic merge semantics, validation paths/remedies, and a no-silent-migration pre-1.0 policy.

The end-to-end local evaluator path is now explicit in README and the public demo
plan: install, profile bootstrap, hardware inspection, provider refresh, hardware-
aware alias selection, promotion, runtime/model setup, Codex/Copilot host-client exports, and
interactive endpoint chat. `models list` defaults to adjacent alias/native-model
identities and supports `--identity alias|model|both`; this replaces the ambiguous
`--name-only` interface during the pre-1.0 preview. Validation: focused identity checks 4 passed; combined model/integration/documentation/governance suite 113 passed plus 10 subtests; full suite 512 passed plus 20 subtests; focused Ruff, profile validation, and required environment doctor passed.

Must

1. Completed: top-level `aiplane discover` coverage and execution for the public onboarding flow.
2. Completed: `aiplane quickstart local-coding` now carries discovery provenance and prints the public core command sequence.
3. Completed: discovery/bootstrap output now distinguishes detected, built-in, provider-discovered cache, profile-configured, and unresolved provenance records.
4. Completed: blocking/advisory doctor findings now include structured remediation command metadata, impact, mutability, and dry-run support fields.
5. Completed: deterministic exports cover Continue, Aider, Cline, Zed, OpenAI-compatible, and MCP clients; Tier-1 formats have golden contracts.
6. Completed for deterministic fixture coverage: recommendation ranking covers the planned hardware/policy cases; external calibration remains ongoing.
7. Completed: public onboarding has top-level `discover`, `doctor`, `recommend`, and `export` commands with help text and tests.
8. Validate clean onboarding on multiple environments and classify failures.

Should

1. Completed for current behavior: policy decisions now expose stable `allowed`, `approval_required`, and `blocked` outcomes; temporary approvals and audited overrides remain future governance work.
2. Completed: user docs are split by maturity with Start here, Common workflows, and Advanced concepts sections, and command examples call out mutating-state behavior and verifiable outcomes.

Scope freeze until sprint targets complete:

- No new orchestrators, cloud providers, benchmark frameworks, or runtime types.
- Priority remains onboarding determinism, actionability, provenance, deterministic exports, and clean-machine evidence.

Post-P0 model-placement foundations now separate hard compatibility, model-variant/resource estimates, measured runtime performance, task-quality evidence, user score contributions, and policy. Versioned benchmark/evidence and external launch contracts keep runtime execution delegated to external runtimes; native TPS/TTFT/token capture, representative cross-machine calibration, and deeper near-miss evidence remain ongoing.

Post-P0 runtime and agent-environment coverage is explicit and implemented at contract level. `runtimes capabilities` covers Ollama, llama.cpp, MLX, Docker Model Runner, LM Studio, and vLLM, tracking detection, installed/served-model inventory, identity mapping, fit, health, endpoint export, and guarded or plan-only lifecycle separately instead of claiming blanket support. MLX is a first-class Apple Silicon runtime with render-only launch and install plans. Agent manifests continue to compile existing profile/stack YAML into framework starter configuration while preserving the boundary that Aiplane configures and validates agents but does not execute autonomous workflows. Platform-specific live evidence remains an open acceptance task.

Evidence/reproducibility contracts now include versioned JSON/YAML benchmark suites, repeated quality summaries, preview-first external measurement import, artifact locks, exact render-only external-runner launch manifests, and evidence-backed per-role routing with alternatives and policy constraints. Node REST scheduling and community benchmark exchange remain research gates rather than promises; they require user evidence plus authentication, privacy, poisoning/provenance, abuse, versioning, and maintenance decisions.

The cloud/VM/workstation render, workflow-aware tool doctor, and six-runner packaging milestones are implementation-complete. Validation covers deterministic secret-free deployment families, contextual mandatory/alternative/optional readiness, truthful auto/Docker/Conda/native bundle modes, SHA-256 file evidence, and framework exports across six runners with three orchestrators. The final full suite passes 652 tests with 3 optional tests skipped and 23 subtests; Ruff format/lint, profile validation, required environment doctor JSON, target render, and runtime bundle command smokes pass. Live provider/platform checks remain separate evidence work and do not broaden Aiplane into an infrastructure or agent runner.

### Current Public Status

High-level implemented areas:

- profiles, deterministic portable profile archive/restore with explicit exclusions and checksums, local config, ignored credential references, provider credential tests, and validation;
- environment planning/doctor checks for system Python, `venv`, Conda, and Docker, with setup helpers that bootstrap ignored `profiles/local-dev` before profile-aware checks;
- provider/model catalogs including NVIDIA Hugging Face-scoped open model discovery, OpenAI-compatible `/v1/models` discovery, structural shipped profile config, ignored discovery cache review, direct profile-owned model add/clone, runtime/source mapping, local model defaults, local AI quickstart with opt-in model pull preview/execution plus doctor summaries, protocol-backed single-prompt execution for Ollama/OpenAI-compatible/Azure OpenAI/Anthropic, and benchmark smoke checks;
- hardware discovery, machine inventory, Azure SKU discovery/import, and stack planning;
- tool doctors/plans/exports for infrastructure, quality, and automation tools;
- integration role inspection, setup, and exports for Continue, Cline, Zed, Aider, OpenAI-compatible clients, and MCP client snippets, with setup planning supported helper install/start/pull actions and skipping unsupported source/runtime pull combinations;
- starter agent app planning/export plus a versioned `skills/aiplane/SKILL.md` assistant workflow package;
- MCP stdio server with read tools, provider ownership/status grouping, machine recommendation, stack list/show/plan/doctor, integration role/plan inspection, orchestrator list/show inspection, and narrow audited writes;
- policy decisions, expiring action-scoped local approvals/overrides, drift reporting, secret redaction, and audit foundations.

Known in-progress areas:

- richer managed-provider discovery and provider-specific live credential tests;
- managed-service endpoint binding for stacks/orchestrator exports without mixing those models into self-managed runtime-fit checks;
- stack role metadata is implemented for planner/coder/reviewer-style model bindings, including managed-service role endpoint binding and warning-level doctor checks for risky tool-policy/approval combinations; framework-specific topology/readiness starters and MCP stack export read parity now exist; the first `aiplane` agent skill package documents safe assistant workflows and MCP usage;
- remote lifecycle execution and supported-platform live acceptance for Docker Model Runner; native same-host Docker Model Runner plan/prepare/start/stop/restart handling is implemented;
- deploy workflow classification now separates local install, local VM, remote workstation/VM, cloud VM, and cloud Kubernetes boundaries with non-mutating `deploy workflow-plan`;
- `deploy apply` now requires explicit `--yes`, and broad cloud apply remains intentionally out of scope until provider-specific guardrails are ready;
- live-provider review and provider-specific expansion beyond the implemented Azure/SSH/local render families;
- broader deployment apply paths;
- endpoint authentication/gateway planning now exists at stack level through endpoint auth/TLS/gateway metadata and `stacks endpoint-plan`; top-level `aiplane doctor` now gives a read-only local AI workflow stack readiness summary with selected endpoint readiness, capability, and hardware-fit details; richer runtime-agnostic chat/task UX beyond single-prompt execution remains planned;
- versioned placement/scoring and benchmark evidence, quantization/context/KV-cache/runtime-aware assessment, repeat summaries, safe deterministic graders, and role comparison are implemented foundations; native TTFT/token capture, comparable local calibration, and deeper near-miss evidence remain ongoing;
- continued test-suite performance/isolation hardening. Default tests should use synthetic fixture profiles, temp roots, mocked subprocess/network boundaries, and controlled generated caches; real disk/cache/tool dependencies should be explicit and isolated in dev setup.

### Validation Baseline

Latest checks from this session:

```bash
python -m aiplane profiles validate local-dev
python -m aiplane environment doctor --required-only
python -m aiplane environment doctor --required-only --format json
python -m aiplane quickstart local-coding --dry-run --no-discovery
python -m aiplane quickstart local-coding --dry-run --no-discovery --format json
python -m aiplane quickstart local-coding --dry-run --no-discovery --pull-model MODEL_ALIAS
python -m aiplane doctor --profile local-dev
python -m aiplane doctor --profile local-dev --format json
python -m aiplane config format
python -m aiplane hardware show --list-types
python -m pytest -q
python -m aiplane tools matrix
python -m aiplane tools matrix --workflow cloud_vm
python -m aiplane environment doctor --workflow local_runtime --format json
python -m aiplane tools plan opentofu
python -m aiplane agents templates
python -m aiplane stacks list
python -m aiplane models list
python -m aiplane models clear-cache --dry-run
python -m aiplane deploy workflow-plan --target azure_gpu_vm
python -m aiplane deploy render --target azure_gpu_vm
python -m aiplane deploy apply --target azure_gpu_vm
python -m aiplane models refresh --provider huggingface --query text-to-video --dry-run --verbosity 2 --limit 2
python -m pytest -q tests/test_models_providers.py tests/test_runtimes_execution.py tests/test_integrations_chat.py -k "models_list_and_defaults_support_grouping or managed_service_models_do_not_mix_into_runtime_groups or model_catalog_cloud_doctor_checks_env_var or runtime_catalog_maps_sources_and_models or integrations_export_continue_uses_planner_constraints"
python -m aiplane models list --profile local-dev --group-by provider-kind
python -m aiplane models list --profile local-dev --group-by runtime
python -m pytest tests/test_models_providers.py -q -k "models_add or models_clone or models_promote"
conda run --no-capture-output -n aiplane scripts/check.sh
```

Results:

- Provider, runtime-packaging, and agent-environment hardening is complete at the reviewed contract boundary. Offline provider diagnostics, Anthropic model discovery, optional-auth local OpenAI-compatible discovery, schema-linked runtime bundles, and profile/stack agent manifests are available through CLI and safe MCP read tools. Focused acceptance passes 156 tests plus 13 subtests; the full serial suite passes 611 tests with 3 optional tests skipped and 23 subtests. Ruff format/lint, profile validation, and required-only environment doctor checks in text and JSON pass. The parallel check wrapper reached format/lint but could not start pytest because this environment lacks the optional pytest-xdist plugin; the complete serial suite is authoritative for this run. The external jsonschema package is also absent, while schema syntax, required fields, packaging, and representative payloads are covered by repository tests. The documented loopback sandbox failure required narrow asserted rewrites with immediate diff verification.

- CLI ownership restructuring is complete: `cli_public.py`, `cli_execution.py`, `cli_providers.py`, and `cli_runtimes.py` now own their parser and dispatch contracts. `cli.py` decreased from 3,171 to 456 lines and is now limited to parser composition and command dispatch. Launch/session planning, profile views/validation, presentation/progress reporting, and public onboarding workflows have focused owners; architecture contracts prevent those responsibilities from drifting back into the root.

- Python 3.12 clean-wheel CI now installs the pinned `setuptools==83.0.0` backend through the dev extra. This satisfies the packaging test's deliberate `--no-build-isolation` contract instead of relying on runner-preinstalled build tooling.

- Parallel-test evaluation is complete: `pytest-xdist==3.8.0` is pinned, and three consecutive four-worker full-suite runs passed using file-level scheduling in 17.06s, 16.93s, and 17.72s. `scripts/check.sh` now defaults to four workers; the `AIPLANE_TEST_WORKERS=0` serial troubleshooting path also passed all 344 tests in 42.06s.

- Test performance hardening removes artificial and machine-dependent delays: the runtime progress test uses an injected 10 ms reporting interval while production remains at two seconds, and the synthetic hardware recommendation matrix stubs hardware discovery instead of invoking host GPU probes. Focused timings fell from 2.18s to 0.11s and from 1.51s to 0.53s respectively.

- Shared test infrastructure now provides reusable recording command/HTTP fakes and in-process CLI stdout/stderr capture alongside the existing isolated synthetic-profile fixtures. Boundary contract and quick-smoke tests use these helpers, establishing the migration pattern without changing production behavior or weakening assertions.

- Large-owner decomposition now separates model execution/readiness from catalog state and stack role policy from stack configuration/lifecycle. `model_catalog.py` decreased from 2,320 to 1,848 lines and `stacks.py` from 1,190 to 1,017. The former 2,530-line model test owner is split into four focused suites; the former 1,207-line profile/config suite is split into three.
- Process and HTTP boundaries are now repository-wide: backends, model/runtime catalogs, remote tunnels, benchmarks, tools, hardware, orchestrators, CLI execution helpers, and the previously migrated domains all accept or use `CommandRunner`/`HttpTransport`. Only `boundaries.py` calls `subprocess` or `urllib` directly, and a contract test prevents regressions.
- CLI ownership cleanup now delegates governance, deploy/remote, environment/benchmark/tools, hardware/machines, and orchestrator/stacks in addition to the existing config, profiles, models, and integrations modules. Each extracted module owns both parser registration and dispatch; all top-level help surfaces and focused domain suites pass. `src/aiplane/cli.py` decreased from 4,602 to 3,164 lines without changing the public entrypoint.
- The quick gate no longer names the empty legacy `test_mvp.py`; it runs ten contracts plus four intentional smoke checks for profile loading, CLI dispatch, non-mutating planning, and JSON output. Shared injectable command and HTTP boundaries now cover every external-I/O owner. Model refresh reconciliation, stack lifecycle, static tool catalogs, and provider-registry tests were decomposed into focused modules.
- CLI config and profile parser/dispatch ownership now lives in focused `cli_config.py` and `cli_profiles.py` modules behind the single public entrypoint. Test profiles are materialized on disk and use the real production loader instead of globally monkeypatching CLI/MCP loader functions. CI runs the full gate on Python 3.11 and focused contract/clean-wheel validation on Python 3.12 and 3.13.

- Non-destructive bootstrap now preserves existing editable profiles by default across direct CLI, install, and activation flows; explicit `--overwrite` remains covered. Static wheels now include config/profile templates plus provider/Ollama runtime helpers, and a clean-venv wheel test verifies template listing, bootstrap, config initialization, profile preservation, helper lookup, and helper delegation.
- Profile validation passed with `ok: true`.
- `environment doctor --required-only` passed with `2/2` mandatory tools installed; runtime prerequisite checks now come from provider/runtime config rather than shipped model defaults.
- JSON environment doctor passed with mandatory tools installed and runtime prerequisite rows for Ollama and vLLM.
- `aiplane quickstart local-coding --dry-run --no-discovery` passed in JSON and text modes, previewing the local profile bootstrap and printing the doctor/export/MCP command sequence without writing profile files; quickstart model pulls are opt-in with `--pull-model MODEL_ALIAS` once a profile-owned or discovered alias exists, and `--dry-run --pull-model MODEL_ALIAS` previews without pulling model weights.
- Top-level `aiplane doctor --profile local-dev` passed in text and JSON modes. It is read-only and summarizes profile status, required/optional environment checks, configured model defaults with provider/endpoint details, selected role-default endpoint readiness, active hardware and role-model fit, provider readiness, Continue/Aider role capability readiness, MCP manifest and local AI read-surface readiness, and next safe steps.
- The full suite now uses a session-scoped copy of shipped profile templates plus synthetic model fixtures, never the ignored local provider-discovery cache; external network access remains blocked. The latest full gate passed `346 tests in 16.34s with four file-scheduled workers`, including the clean-wheel installation test; the source-only suite remains substantially faster than the earlier `119.85s` developer-cache-loaded baseline. `scripts/check.sh quick` passed formatting, lint, ten contract checks, and four intentional smoke checks in `0.24s` of pytest time. Runtime helper subprocesses receive `AIPLANE_PROFILES_DIR` for custom profile roots.
- `tools matrix` passed and reported `16` tools, `2` mandatory, `14` optional, `11` installable by `aiplane`, `7` exports available, and `9` workflow categories: `4` complete, `1` partial, and `4` needing setup on this machine.
- `tools plan opentofu` passed and reported OpenTofu as optional/manual with non-mutating IaC plan guidance.
- `models list` returned an empty list for the clean structural profile template until discovery or local model entries are added.
- `models list --machine` and `models list --machine-file` are implemented and tested; they derive RAM, VRAM, GPU vendor, and accelerator API filters from named/imported machine profiles or portable machine files while leaving parameter-count filters explicit.
- `models list --fits-machine` is now a shorthand alias for `--machine`.
- Hardware-fit filtering now treats no-GPU machines as `vram=0`, `gpu_vendor=none`, and `accelerator_api=cpu`, so GPU-required entries are excluded consistently.
- `machines discover azure` now accepts explicit candidate filters (`--gpu-vendor`, `--min-cpu-cores`, `--min-ram-gb`, `--min-vram-gb`) and streams redacted Azure CLI progress to stderr by default (`--verbosity 0` keeps one active command line with a 2-second dot ticker), with optional per-command output logging at `--verbosity 1`.
- `machines discover azure` no longer accepts `--runtime`; Azure machine discovery is now explicitly machine/resource scoped to avoid implying runtime-specific VM properties.
- Live `machines discover azure` results now include per-candidate retail unit pricing (when available) from Azure Retail Prices (`unit_price`, `currency`, `unit`, `unit_of_measure`) so machine candidate review can include cost context.
- `bridge list/exec` now exposes a strict allowlisted external-runtime relay surface (currently Ollama shorthand actions only) so `aiplane` can delegate selected native commands without opening arbitrary shell passthrough.
- `config format` and `config verbosity` now support profile-aware and command-aware defaults; `models list --format text` uses compact output at verbosity 0 and warns/falls back to JSON at verbosity 1+; `hardware show` uses `--list-types` for template discovery.
- `models clear-cache --dry-run` passed with `include_curated: true` and zero removals on the clean cache.
- `deploy workflow-plan --target azure_gpu_vm` passed and classified the target as `cloud_vm` with explicit cloud provisioning boundaries, `az`/SSH/IaC/Packer/Ansible tool ownership, and read-only MCP policy.
- `deploy apply --target azure_gpu_vm` without `--yes` correctly failed before mutation with `error: deploy apply is mutating; run deploy plan first`.
- Hugging Face `text-to-video` refresh dry-run contacted the source API, reported `profile_models_before_refresh: 0`, and mapped returned candidates to `video_generation` on the `diffusers` runtime.
- Continue integration planning is now documented as a discovery-first demo step: refresh provider catalogs into the ignored discovery cache, derive chat/autocomplete/embedding aliases, then pass explicit role aliases to plan/export.
- Focused provider-kind, managed-service runtime separation, and Ollama Docker-substrate dry-run tests passed. The Docker dry-run path prints `docker pull ollama/ollama:latest` and `docker run ... ollama/ollama:latest` without starting containers.
- Agent template listing passed with `langgraph` and `simple-openai` templates.
- Focused provider/stack tests passed for OpenAI-compatible online catalog discovery, Azure OpenAI discovery, endpoint-type help, stack framework export metadata, and managed-service role doctor warnings.
- Focused endpoint/lifecycle tests passed for `stacks endpoint-plan`, endpoint auth/TLS/gateway flags, shared endpoint warnings, and same-host lifecycle timing/status reporting.
- Stack listing passed and returned an empty configured stack list.

- `aiplane --version` now reports effective version, package metadata version, module version, install type, and module path so wheel, static, editable, installed, and direct source-checkout runs can be distinguished during setup verification.

### Current Follow-Up Work

Provider discovery and model import now has an implemented foundation: structural shipped model templates, discovery-backed add/promote/clone flows, refresh next-step guidance, machine-derived `models list` filtering, OpenAI-compatible `/v1/models` discovery, Azure OpenAI deployment discovery, ElevenLabs voice discovery, and structured managed-provider refresh failures for missing live catalog configuration. Remaining work in that area is richer provider-specific live discovery and credential tests where provider APIs justify dedicated adapters.

The roadmap milestones are now grouped into three bands:

- **Post-Merge Foundation**: architecture/codebase cleanup, MCP and agent skill hardening, and orchestrator-backed multi-agent workflow metadata.
- **Product Hardening**: provider discovery/import, runtime/stack endpoint hardening, cloud/VM/workstation workflows, and tool doctor expansion.
- **Later Expansion**: runtime packaging, IDE launch/session integrations, benchmark quality, and test-suite isolation.

The architecture cleanup slice now centralizes integration role contracts, model list grouping, model resource estimates, runtime pull compatibility, runtime/source/provider definitions, shared CLI parse/progress helpers, and focused CLI modules for config, profiles, governance, deployment/remote, setup/tooling, hardware/machines, orchestrators/stacks, integrations, and models. Continue splitting `src/aiplane/cli.py` by command family where it reduces real ownership pressure, not just to move code around.

MCP is implemented and tested, but it is still a hand-maintained adapter. It now includes model filters with named-machine/current-machine fit selectors, machine recommendations, stack list/show/plan/doctor checks, integration role/plan, and orchestrator list/show read surfaces. Future MCP sync should focus on safe gaps only, while leaving model pulls, installs, cloud apply, secret writes, and arbitrary shell execution blocked or CLI-only.

The first versioned `aiplane` skill package exists at `skills/aiplane/SKILL.md`. It documents safe workflows for coding assistants: read the guidance docs, inspect profiles/providers/models/runtimes separately, prefer doctor/plan/dry-run/export, use MCP when a structured read/planning tool exists, keep docs/tests aligned, and run focused checks before proposing PRs.

Orchestrator support now has stack role metadata over reviewed model aliases and endpoints: planner/coder/reviewer/researcher/tool-runner roles, tool policies, approval modes, limits, audit labels, managed-service endpoint bindings, doctor checks, and starter exports for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands. Runtime/stack hardening now adds endpoint auth/TLS/gateway planning and clearer same-host lifecycle result metadata. `aiplane` should keep configuring and validating those workflows, not execute autonomous agent conversations directly.

The remote-workstation replay and evidence-led schema/provenance implementation milestones are complete. `profiles replay-check` now verifies one approved source against at least two distinct client-produced archives in one deterministic read-only result, while independently restored profiles retain byte-stable supported exports. Profile validation now rejects ambiguous booleans, negative/non-finite recommendation resources, contradictory minimum/recommended thresholds, and malformed or duplicate role/runtime/accelerator lists, while accepting explicit null defaults. Recommendation JSON labels configured, detected, generated, measured, and unresolved sources, benchmark sample counts, contextual-only benchmark use, and uncertainty without presenting catalog scores as measured quality. Physical-client and independent-user execution remains part of the separate P1 field-evidence gate.

Validation for these two milestones: the combined replay/schema/recommendation/profile/documentation gate passes 100 tests plus 7 subtests; the full suite passes 538 tests plus 23 subtests. Ruff format and lint pass across `src` and `tests`; named profile validation and required environment doctor checks pass in text and JSON. A disposable CLI trial created one approved source and two independent client profile roots, restored and re-archived both clients, and produced an exact two-client `replay_ready: true` result without modifying the archives.

The five feature milestones are implementation-complete. Their former catch-all test module is now split by support catalog, integration import, adapter protocol, Docker Model Runner, and Kubernetes artifact ownership. Docker Model Runner status correctly reports that this host's Docker installation lacks the Docker model command, so cross-platform live evidence remains explicitly open.

The maintainability, shared-evidence, and pre-1.0 release-hardening milestones are implementation-complete. CLI parser ownership is separate from dispatch, reducing `cli.py` from 510 to 305 lines. All five public planning surfaces share the versioned evidence contract. Tracked changelog notes, SHA-256 verification, signed build provenance, hosted attestation verification, and upgrade/rollback instructions are wired into the release path. Focused coverage passes 156 tests plus 20 subtests; the full sequential suite passes 564 tests plus 23 subtests. Repository-wide Ruff format and lint pass. The normal full check could not invoke its parallel scheduler in this shell because the declared `pytest-xdist` development dependency is absent; the complete test set passed sequentially instead. A hosted release remains required to produce external attestation and publication evidence.

The model-catalog materialization milestone is also implementation-complete. Refresh now produces an ignored, versioned, atomically written enriched catalog; indexed and full-scan filters have exact equivalence coverage; corrupt or stale caches recover automatically; and secret-bearing source properties are excluded. On this development host, the opt-in synthetic benchmark returned indexed-query medians of 0.18 ms for 1k, 1.43 ms for 10k, and 34.32 ms for 100k rows; these figures are local regression evidence, not portable guarantees. Validation passes 114 focused tests plus 3 subtests, all three opt-in scale tests, and the full 569-test suite plus 23 subtests; profile validation and both required-only environment doctor formats pass. Ruff format and lint pass for every changed Python file.


The repeatable benchmark and runtime-evidence milestone is implementation-complete. Versioned JSON/YAML suites, deterministic validation, repeat statistics and uncertainty, safe built-in graders, explicitly opted-in trusted command graders, preview-first external measurement import, data-only scoring extensions, artifact locks, render-only runtime launch manifests, and evidence-backed role comparisons are available. Pull previews, benchmark records, stack plan/doctor, replay comparison, and stack lifecycle share those contracts. Ollama native duration/token/throughput fields and OpenAI-compatible usage counters populate benchmark evidence when exposed; TTFT and other unavailable metrics remain null. Cross-machine calibration and complete artifact integrity still depend on external evidence rather than inference.

The six-runner parity, workflow evidence integration, and render-only Kubernetes family milestones are implementation-complete. The Kubernetes compiler emits schema-linked ResourceClaim, Deployment, Service, and Helm values; consumes the reviewed launch command/health path; includes DRA count, resource quantities, probes, cache storage, and baseline container security controls; and remains secret-free with no apply path. The manual acceptance path is consolidated in [Manual Test Checklist](../user/manual-test-checklist.md). Validation passes 603 tests with 3 opt-in performance tests skipped; Ruff format/lint, profile validation, and required-only environment doctor checks in text and JSON pass.

### Next Useful Work

1. Active P1 evidence gate: run the clean-machine onboarding and replay trials with the [Field Evidence Collection Runbook](../user/evidence-collection.md) when maintainer time or external participants are available; do not claim P0 closure or external-beta readiness before then.
2. P2 placement calibration: use the same runbook to collect comparable evidence on representative NVIDIA, AMD, Intel, Apple, Windows and heterogeneous multi-GPU machines; harden MIG/NUMA details and calibrate resource overhead without changing the transparent scoring contract.
3. P2 evidence calibration: use the same runbook to exercise benchmark suites, measurement import, artifact/launch evidence, repeated quality, role routing, and native telemetry on materially different machines and runtimes; add streaming TTFT only where backend APIs expose an exact measurement.
4. Active evidence follow-up: gather clean-machine Docker Model Runner results with the same runbook on supported Docker Desktop/Engine platforms. This host does not provide the Docker model command and therefore is not cross-platform live evidence.
5. Release and adoption follow-up: publish an eligible immutable release with hosted verification evidence, and observe draft imports, contributor fixtures, and render-only Kubernetes artifacts before adding any apply service or node scheduling API.


### July 2026 Safety and Structure Review

The persistent prioritized register is
[Code Quality and Safety Review — July 2026](code-quality-review-2026-07.md).
SEC-1 and ARCH-1 are complete. SEC-1 focused tests cover non-TTY denial without mutation, explicit per-invocation `--yes`, read-only execution, passthrough arguments, and audit denial. ARCH-1 reduces `cli.py` from 1,570 to 456 lines with dedicated launch, profile, presenter, and public-workflow modules plus structural drift tests. Validation: focused suite 89 passed, quick gate 14 passed, full suite 349 passed. REL-2 is also complete: audit-tail recovery skips malformed and likely truncated final records while keeping stdout valid JSONL and warnings metadata-only; focused recovery/audit/tool coverage passes 24 tests; quick gate 14 passed; full suite 353 passed. SAFE-1 is complete: SSH tunnel state is versioned, atomic, collision-resistant, and identity-verified before signalling; stale or reused PIDs are never killed. Focused remote/boundary coverage passes 23 tests, expanded integration coverage passes 70 tests, the production Linux inspector check passed, quick gate 14 passed, and full suite 357 passed. COMPAT-1 was added to the prioritized register to inventory and gate Linux-, Ubuntu/Debian-, systemd-, procfs-, Bash-, package-manager-, and GPU-tool-specific operations, with explicit help/doctor/documentation and synthetic cross-platform tests.
 REL-1 and SEC-3 are complete: production text persistence is atomic and serialized across threads/processes with bounded, non-nestable IPC locking and transactional YAML updates; audit writes are durable, secret redaction covers command-aware and structured inputs, and tool/MCP audit failures omit raw outputs, arguments, and exception messages. Focused persistence/redaction coverage passes 10 tests, expanded relevant coverage passes 96 tests, quick gate 14 passed, and full suite 367 passed.
 SEC-4 is complete: tunnel and remote-profile planning share strict host, username, port, and HTTP(S) endpoint validation; option-like destinations fail before command construction, IPv6 forwarding is bracketed, and remote shell values are quoted. Focused remote/validation coverage passes 49 tests, quick gate 14 passed, full suite 396 passed, and representative CLI valid/rejection checks passed.
 SEC-2 and REL-3 are complete: MCP is read-only by default and requires both operator `--allow-writes` and per-call `confirm=true` before manager dispatch; blocked attempts are audited. The CLI redacts expected errors, sanitizes unexpected failures unless debug is explicitly enabled, handles broken pipes quietly, and returns 130 on interruption. Focused MCP contracts pass 37 tests; focused CLI boundary/governance smoke coverage passes 26 tests; the combined suite passes 63 tests; the real pipefail check, quick gate (14 tests), and full suite (409 tests) pass.
 COMPAT-1 and ARCH-2 are complete. Platform capabilities centralize distro/WSL behavior, block unsupported runtime mutations, and skip non-Linux probes; focused compatibility coverage passes 78 tests. Model persistence/reconciliation and Azure pricing/CLI boundaries are decomposed with structural drift tests; focused architecture coverage passes 64 tests. The combined suite passes 117 tests; the final full suite passes 422 tests. The evaluated external product/adoption/monetization backlog is `docs/project/project-plan.md#product-adoption-backlog`.

 DOC-1 is complete. README and user onboarding now use `aiplane export continue`, the empty workflow heading is removed, and documentation contracts prevent ambiguous exports, empty adjacent sections, and workflow-number drift. Focused contract suite: 13 passed; quick gate: 17 passed; full suite: 425 passed.

 The product positioning/default-help backlog item is complete. Public entrypoints consistently lead with “environment doctor and configuration compiler,” developer-preview maturity is aligned with package alpha metadata, and top-level help groups every command into explicit core, advanced/supporting, or experimental tiers with one dry-run next action. Focused positioning/help suite: 30 passed; quick gate: 18 passed; full suite: 426 passed; required profile and environment-doctor checks passed in text and JSON modes.

 The standard installation/release-channel implementation is complete; CI owns patch commits and artifact tags, intentional minor/major versions publish automatically, and a maintainer may deliberately publish a selected patch tag. GitHub Release wheels require no clone; `scripts/verify_install_channels.py` validates pip, pipx, and uv tool lifecycles in isolated homes; CI covers Ubuntu, macOS, and Windows; release tags must match `pyproject.toml` before validated wheel/sdist publication. Local focused packaging contracts passed 16 tests, all three real final-wheel installer lifecycles passed, quick gate passed 19 tests, full suite passed 427 tests, and required profile/environment doctor checks passed.

 README and package metadata breadth cleanup is complete: detailed agentic/provisioning/benchmark/stack/MCP marketing lists are removed, advanced commands are described only as a subordinate maturity surface, contribution and documentation links lead the narrow workflow, and package keywords now target diagnostics/configuration/reproducibility. Regression contracts prevent the stale broad headings and keywords returning. Focused contracts/packaging: 16 passed; quick gate: 19 passed; full suite: 427 passed. The final overall documentation consistency sweep is tracked at the bottom of P0, after all numbered P0 work and the user demonstrations.

 P0.4 platform CI is implementation-complete. The Ubuntu/macOS/Windows matrix runs 15 synthetic platform tests plus clean installed-wheel portable workflow smoke through pip, pipx, and uv. Windows SSH lifecycle is now gated before process/state access with explicit help and `unsupported_platform`; runtime mutation gates cover Fedora, WSL, macOS, and Windows before helper dispatch. Focused platform/remote suite: 79 passed; local real final-wheel lifecycles: all three passed; quick gate: 19 passed; full suite: 434 passed; required doctors passed. Cross-OS runner results will be produced when CI runs on push.

 P0.9 is complete: docs/project/threat-model.md maps all eight required security areas to deterministic tests and explicit residual limitations; SECURITY.md links it and uses the current product boundary. Focused security validation: 62 passed; full suite: 449 passed.

 The interim README/documentation consistency sweep after the earlier implementation milestones corrected stale quickstart outcome text, positive control-plane positioning, top-level help breadth, and obsolete P0 item-number references. Contract tests preserve those corrections. The unnumbered P0 completion gate remains open: run the three independent-user demonstrations, then repeat the final README/documentation sweep before closing P0. Focused consistency gate: 76 passed; full suite: 449 passed.

 The public demo plan has been replaced with three newbie-focused videos capped below three minutes: local Ollama onboarding, local-only policy with honest YAML/config backup and byte-identical restore proof, and existing remote-GPU machine import/access planning/export. A fourth automation/MCP video remains deferred pending user evidence. The plan explicitly separates canonical archival, filesystem restoration, template repair, credentials, caches, audit/tunnel state, and runtime-owned weights.

 Test profiling and one safe optimization are complete. Baseline four-worker suite: 450 passed in 36.46s / 37.04s wall; packaging lifecycle test 25.45s. The packaging test no longer reruns the independent install/reinstall/uninstall verifier already owned by OS-matrix and release gates. After: 450 passed in 19.71s / 20.26s wall; packaging test 8.69s. Six workers passed in 17.21s / 17.78s wall and remain an opt-in local setting; the portable default stays at four.

 The latest external review has a tracked evaluation at `docs/project/reviews/dev-mvp-0.5-latest-review-evaluation.md`. Numbered P0 now contains only current release/adoption actions; the independent-user and final-documentation gates remain unnumbered and open. The durable CI recommendation is protected checks on the main/release path, not a permanent feature-branch trigger.

 The macOS/Windows install-channel CI regressions are fixed. Tier-1 verification uses the stable relative model ID `portable-smoke.gguf`; all OSes exercise read-only tunnel planning; macOS/Windows assert unsupported runtime-helper mutation; only Windows asserts unsupported tunnel lifecycle. The verifier cannot start a tunnel on Linux or macOS in its platform contract. Behavioral synthetic tests cover Linux, Darwin, and Windows. Focused suite: 41 passed; rebuilt-wheel real pip lifecycle passed.
P0.1 is complete with a contract-enforced seven-command primary adoption cut and two subordinate validation recordings. P0.2 repository implementation is hardened: CI-owned tags, generated preview notes, checksum generation/verification, complete-asset enforcement, full-gate release automation, supported-platform guidance, and rollback guidance are present. P0.2 remains open until one public release contains and verifies the required wheel, source distribution, and checksum assets.

P0.3-P0.6 local implementation is complete: clean-wheel lifecycle verification has a canonical evidence format; `CI / Release gate` aggregates quality, compatibility, and cross-OS install jobs; repository protection requirements are explicit; trial records have a deterministic sanitizer/shape validator; and the preview scope freeze has an exception contract. Public-artifact evidence, hosted ruleset activation, and independent-user trials remain maintainer/external actions.

Post-merge no-clone candidates are now automated: a successful protected `main` push builds a wheel only after `CI / Release gate`, verifies its SHA-256 manifest, writes commit/run provenance, and uploads a 30-day artifact named with package version plus the short version-commit SHA. This is prerelease test evidence, not the immutable public P0 release.

CI-owned versioning now uses the narrowly scoped `aiplane-versioning` GitHub App token, trusts loop suppression only for that event actor, rejects PR edits and non-increasing direct versions, serializes patch mutation, and retries from latest `main`. Patch tags retain validated Actions artifacts without automatic public publication; intentional minor/major tags publish complete wheel/source/checksum releases, and successful publication dispatches the nine-job public verification matrix. App installation, secret storage, hosted app proof, and main/tag ruleset activation remain maintainer actions documented in `repository-protection.md`.

## Command Coverage

This table tracks the public CLI surface at a high level. Use it during pre-PR cleanup, release review, and recurring MCP/skills synchronization checkpoints to keep docs, tests, MCP coverage, planned/implemented agent skills, and status claims aligned.

### Public command categories

The primary public surface is deliberately small. Detailed commands remain available, but docs, demos, and onboarding should make it clear which category each command belongs to.

| Category | Commands | Public posture |
| --- | --- | --- |
| Core | `--version`, `discover`, `doctor`, `recommend`, `export`, `quickstart local-coding`, `profiles list/templates/create/repair/remove/bootstrap-local/show/validate`, `policy explain`, `audit tail`, `config templates/init/show/get/set/default-profile/format/verbosity` | Lead with these. They are the environment doctor, recommendation, policy, export, audit, and profile-management surface for the first successful workflow. |
| Supporting | `profiles render/schema/archive/restore/compare/replay-check/drift`, `hardware show/templates/schema/active/use/set/discover/clear/doctor/recommend/export-machine`, `machines import/list/show/validate/recommend/discover/cache-list/cache-clear/azure-status/import-azure-sku/profile-remote-plan`, `runtimes map/list/sources/models/model/use/prerequisites/doctor/bundle/install/start/stop/pull/repull/remove/clear`, `providers list/show/models/test/diagnose/add/endpoint-types/enable/disable/remove/init-defaults/update-defaults/clear/doctor`, `models list/show/defaults/use/add/clone/remove/enable/disable/refresh/promote/clear-cache/catalog-cache/pull/test/benchmark/route`, `integrations list/roles/plan/setup/export`, `mcp manifest/serve`, `tools list/matrix/doctor/plan/export/install`, `environment show/list/active/use/plan/doctor`, `remote tunnel plan/start/status/stop`, `policy list/drift`, `benchmarks list/doctor/plan/suite-validate/import/compare` | Use after onboarding or when troubleshooting a specific runtime, endpoint, hardware, integration, MCP, benchmark, or environment readiness question. |
| Experimental | `deploy list/show/workflow-plan/plan/doctor/apply --yes`, `orchestrators list/show/doctor/setup`, `stacks setup/list/show/plan/doctor/endpoint-plan/status/export/prepare/start/stop/restart`, `agents templates/plan/manifest/export`, `policy grant/revoke`, `run`, `tool [--yes] TOOL [ARGS...]`, `chat`, `bridge list/exec`, `launch`, `session start` | Commands may exist for experiments and advanced users, but they should not lead README, demos, or beta onboarding. They must not block the external beta workflow. |

| Area | Primary commands | Status | Notes |
| --- | --- | --- | --- |
| Version reporting | `--version` | Implemented / core setup verification | Reports effective version, installed package metadata version, module version, install type, and module path for wheel, static, editable, installed, and direct source-checkout runs. |
| Core onboarding | `discover` / `doctor` / `recommend` / `export` | Implemented / primary surface | Core onboarding is wired as the primary public flow: discover, readiness check, recommendation, and artifact export are the first commands shown in onboarding docs. `quickstart` remains a composed convenience path, not required for first success. |
| Doctor contract | `doctor [--format json]` | Implemented / versioned v1 | Every finding has a stable ID, severity, reason, impact, affected resource, uniform remediation/mutation/dry-run metadata, and deterministic blocker action. Payload exit codes are authoritative: 0 healthy, 1 advisory-only, 2 blocking. |
| Tier-1 exports | `export continue`, `export aider`, `export openai-compatible`, `export generic-mcp` | Implemented / versioned v1 | Exact golden files freeze output. The clean installed-wheel matrix validates all four on Linux, macOS, and Windows and performs a real MCP initialize/tools-list stdio exchange. Other exporters are advanced and unversioned. |
| Local AI quickstart | `quickstart local-coding` | Implemented onboarding entrypoint (composes core flow) | Preserves existing profile files, defaults to offline-safe operation, exposes provider discovery only through `--discovery`, updates one deterministic phase-status line on stderr while keeping stdout machine-readable, and reports one exact next action. An empty profile gets at most two no-YAML setup paths; a configured profile gets the exact Continue export/verification command.
| AI workflow stack doctor | `doctor` | Implemented / first public wedge | Read-only aggregate check for the local/hybrid AI workflow stack: profile files, required environment tools, runtime prerequisites, configured model defaults with provider/endpoint details, selected role-default endpoint readiness, active hardware and role-model fit, provider state, repository policy decisions, Continue/Aider role capability readiness, MCP manifest and local AI read-surface readiness, and next safe commands. Use `--format json` for scripts and `--include-optional` to include optional external workflow tools. |
| Local config | `config templates/init/show/get/set/default-profile/format/verbosity` | Implemented | Local `.aiplane/config.yaml` is ignored by git. Added `config format` and `config verbosity` with global, per-profile, and per-command defaults plus precedence (`--format`/`--verbosity` CLI > command override > profile override > global default). |
| Credentials | `credentials list/show` | Implemented / local-only | Reads ignored local credential refs; `list` returns an empty list quietly when no credentials file exists, `show` errors for missing refs, output is redacted, and raw secrets are not printed. |
| Profiles | `profiles list/templates/create/repair/remove/bootstrap-local/show/render/schema/validate/archive/restore/compare/replay-check/drift` | Implemented / schema v1; field replay evidence pending | Editable YAML is the restorable source of truth; `render` prints canonical JSON evidence and is not restore input or target-tool configuration. `archive` writes deterministic, checksummed JSON containing reviewed profile YAML plus an explicit exclusion manifest, rejects raw credential material and symlinked portable files, and supports `--dry-run`; `restore` validates and previews by default, requires `--yes` to atomically create a new profile, and never overwrites an existing profile. `compare` classifies validated profile/archive evidence; `replay-check` aggregates one approved source and at least two distinct client archives; `drift` compares explicit active hardware facts with live discovery. All are read-only and emit provenance-aware exact, capability-equivalent, materially incompatible, or unresolved results. Profile templates are versioned; `repair` restores missing template files without overwriting by default; `remove` previews by default and deletes only with `--yes`; `bootstrap-local` preserves existing edits unless `--overwrite` is explicit and can populate ignored discovery state. |
| Environment/setup | `environment show/list/active/use/plan/doctor` plus `scripts/setup_env.sh` | Implemented / growing | `setup_env.sh --action install` creates the ignored `profiles/local-dev` template profile when missing and preserves it when it already exists with discovery disabled before running profile-aware doctor checks; Conda install mode repairs an existing target env that is missing Python. Static wheel installs include profile/config templates and runtime helper scripts, with clean-wheel coverage in the full test gate. Built-wheel install, verification, upgrade/replacement, and uninstall are also exercised through `pip`, `pipx`, and `uv tool` on Linux, macOS, and Windows CI. `environment doctor` defaults to a human text table grouped with mandatory tools before optional tools and installed tools before missing tools within each group, and writes single-line probe progress to stderr; use `--format json` for scripts. It includes common local runtime prerequisites plus runtimes/services selected by profile model defaults. Expand scope as new tools are integrated. |
| External tools | `tools list/matrix/doctor/plan/export/install` | Implemented / growing | Covers Azure CLI, OpenTofu/Terraform/Pulumi, Vagrant, Packer, Docker/Compose, Dev Container CLI, kubectl, Helm, SSH, Ansible, Ruff/Black quality tooling, and benchmark helpers. Matrix output includes workflow readiness summaries; plan/export prints non-mutating starter workflow artifacts for VM/IaC/devcontainer/configuration tools. |
| Providers/sources | `providers list/show/models/test/add/endpoint-types/enable/disable/remove/init-defaults/update-defaults/clear/doctor` | Implemented / partial discovery | `providers endpoint-types` lists supported provider API families/catalog adapters, `providers list --status enabled|disabled|all` exposes provider state and ownership, and `providers list --group-by ownership` groups by self-managed vs managed-service providers; `providers update-defaults` refreshes profile-local provider defaults while preserving enabled flags. Catalog adapters exist for selected sources, including NVIDIA Hugging Face-scoped discovery, OpenAI-compatible `/v1/models`, Azure OpenAI deployments, and ElevenLabs voices when endpoint/key configuration is present; `providers test` verifies selected managed endpoints/credentials for Azure OpenAI, ElevenLabs, and OpenAI-compatible APIs without printing secrets. Broader managed-provider discovery still needs hardening. |
| Models | `models list/show/defaults/use/add/clone/remove/enable/disable/refresh/promote/clear-cache/catalog-cache/pull/test/benchmark` | Implemented / ongoing | Shipped profile templates keep `models.yaml` structural; `refresh` populates ignored `models.discovered.yaml`, `add` creates profile-owned entries from discovered aliases or discovered provider/model matches and can add direct `local_file` path aliases, `clone` creates second profile-owned entries, `remove` deletes named profile-owned aliases from `models.yaml` without touching discovered cache entries, `promote` copies reviewed discovered entries into `models.yaml` while keeping discovery links, `refresh --reset-cache` combines provider-scoped cache clearing and catalog refresh, `refresh` now uses `--verbosity` levels (`0` top-level summary, `1` adds `provider_summary`, `2` shows full `results` with per-model rows), managed-provider discovery failures are returned as structured JSON with next steps, `clear-cache` includes profile-owned review entries by default with `--keep-curated` as the opt-out, `enable`/`disable` write profile-owned aliases only, `models test` can execute one prompt through Ollama, OpenAI-compatible, Azure OpenAI, and Anthropic Messages protocols, `models list` exposes parameter-count, RAM/VRAM requirement hints plus explicit GPU vendor/API requirements, can derive hardware-fit filters from active hardware, named machines (`--machine`/`--fits-machine`), external machine files, or the currently probed machine, and `models list --group-by provider-kind` separates managed-service providers from self-managed sources; `models list --format text` uses compact output at verbosity 0 with adjacent `ALIAS` and provider-native `MODEL` columns, `--identity alias|model|both` selects one identity or both, and text verbosity 1+ warns/falls back to JSON. Refresh and first use maintain an ignored, versioned enriched query cache with exact indexes and latest benchmark summaries; source digests invalidate it automatically, while `--catalog-cache off|rebuild` and `models catalog-cache status|rebuild|clear` keep the optimization optional and inspectable. Versioned JSON/YAML suites, repeat overrides and uncertainty summaries are implemented; external measurements can be previewed/imported through a provenance-bearing data-only contract, and `models route` compares policy, placement, comparable measured quality, configured task suitability, and user score contributions while retaining alternatives. |
| Runtimes | `runtimes map/list/capabilities/sources/models/model/use/prerequisites/doctor/bundle/artifact-lock/launch-manifest/install/start/stop/pull/repull/remove/clear/...` | Implemented / helper-dependent; six-runner contract complete | Lifecycle delegates to runtime helpers where supported; Ollama supports native and Docker substrate dry-run/start/install paths plus guarded pulled-model remove/clear, while TGI/LocalAI use Docker-backed helper paths. The capability contract covers Ollama, llama.cpp, MLX, Docker Model Runner, LM Studio, and vLLM across detection, installed/served-model inventory, alias/native identity, fit, health, endpoint export, and guarded or plan-only lifecycle, with limitations expressed per capability. Artifact locks and versioned external-runner launch manifests now render source/revision/checksum evidence, runtime requirements, context/device/parallelism settings, endpoint/health metadata, and previewed vendor commands without bundling credentials or runtime-owned weights; unresolved integrity fields remain explicit and incomplete. Managed-service model aliases are not runtime-fit candidates and are rejected by runtime assignment/bundling paths. `runtimes list` supports `--format text|json` with text as the lean default. |
| Hardware | `hardware show/templates/schema/active/use/set/discover/clear/doctor/recommend/assess/scoring/export-machine` | Implemented / calibration ongoing | Discovery normalizes per-device identity, vendor/backend, total/free memory, drivers and bus evidence across Linux NVIDIA/AMD/Intel, Apple/Metal and Windows CIM sources, with explicit unresolved fields and homogeneous grouping. Topology is captured where supported. `assess` estimates weights, KV cache and runtime workspace with stated sources/assumptions, evaluates single-GPU, runtime-declared homogeneous multi-GPU, offload and CPU modes, and never treats summed inventory VRAM as automatically usable. Recommendations apply hard policy/runtime/placement gates, then order eligible local rows using versioned, component-level placement-readiness scoring with evidence coverage. Safe scoring extensions are data-only profile/model values. MIG/NUMA depth and cross-machine calibration remain ongoing. |
| Machines | `machines import/list/show/validate/recommend/discover/cache-list/cache-clear/azure-status/import-azure-sku/profile-remote-plan` | Implemented / remote execution planned | Azure discovery has live/offline/cache paths, supports explicit filters (`--gpu-vendor`, `--min-cpu-cores`, `--min-ram-gb`, `--min-vram-gb`), includes per-candidate unit pricing when Azure retail price data is available, and streams redacted Azure command progress on stderr (`--verbosity 0` shows the active command with a 2s dot ticker, `--verbosity 1` logs each command plus redacted command outputs). |
| Orchestrators | `orchestrators list/show/doctor/setup` | Catalog/readiness implemented | Stacks remain the operational binding point; agent manifests and framework-specific topology/readiness starters capture reviewed role bindings without running agents. |
| Stacks | `stacks setup/list/show/plan/doctor/endpoint-plan/status/export/prepare/start/stop/restart` | Implemented / same-host execution first | Plan/doctor include preflight, role-policy, managed endpoint, endpoint security, and risky tool-policy checks. Every executable lifecycle mutation requires `--yes`; remote/AKS actions remain plans. Docker Model Runner uses exact native commands, alias/native-id resolution, its conventional endpoint, and runtime evidence. Exports include IDE/packaging artifacts plus framework starters. |
| Integrations | `integrations list/roles/plan/setup/export` | Implemented / hardening | Config/export first; no target tool files are edited. Tier-1 v1 now includes Codex named-profile TOML, canonical Copilot CLI JSON with POSIX/PowerShell renderers, and Copilot-in-VS-Code Custom Endpoint JSON alongside Continue, Aider, generic OpenAI-compatible, and generic MCP. Host-client plans expose alias/native model identity, API compatibility, token limits, tool-calling, and streaming metadata; known incompatibilities fail and unknowns warn. `setup` prepares only the selected runtime/model, `--from-plan` replays the saved decision, and raw secret values are never exported. |
| Prompt execution + assistant launch/session | `run`, `tool [--yes] TOOL [ARGS...]`, `chat`, `bridge list/exec`, `launch`, `session start` | Implemented / hardening | `tool` enforces the profile allowlist and workspace boundary; risky tools require interactive approval or explicit per-invocation `--yes` and fail closed without a TTY. `run` sends one prompt through profile policy and currently supports Ollama, OpenAI-compatible chat completions, Azure OpenAI chat completions, and Anthropic Messages; unsupported protocols fail explicitly. `chat` now uses the same endpoint-backed protocol path by default for chat-capable aliases, can read `--prompt`/`--stdin` or an interactive TTY prompt loop, rejects non-chat-capable aliases clearly, and keeps Ollama's native `ollama run` path behind `--native-ollama`. `bridge` is a strict allowlisted runtime CLI relay (currently Ollama actions) with shorthand actions and no arbitrary shell passthrough. `launch` now renders and can execute thin, profile-driven wrappers for supported tools (`continue`, `ollama`, `aider`), applying the same integration and policy checks as export/setup workflows. `session start` persists minimal launch metadata plus transcript path and writes local audit events for session lifecycle traceability without implementing a chat product. |
| Agents | `agents templates/plan/manifest/export` plus `skills/aiplane/SKILL.md` | Versioned manifest and framework starter guidance implemented | Prints non-mutating starter files, a schema-linked agent-environment manifest, and framework-specific topology/readiness YAML for seven supported targets. It preserves multi-role identities, endpoints, policy, approvals, limits, audit labels, and credential references without secrets, writes, package installation, or agent execution. |
| Remote | `remote tunnel plan/start/status/stop` | Implemented / guarded | SSH targets use strict DNS/IP, username, port, and credential-free HTTP(S) endpoint validation; option-like destinations fail before argv construction. Tunnel lifecycle uses collision-resistant versioned state and verifies process identity before signalling; stale/reused PIDs are never killed and malformed state fails closed. On Windows, lifecycle status/start/stop return `unsupported_platform` before process or state access; tunnel planning remains portable. |
| Deploy | `deploy list/show/workflow-plan/plan/doctor/apply --yes` | Partial / guarded | `workflow-plan` classifies local install, local VM, remote workstation/VM, cloud VM, and cloud Kubernetes boundaries without mutation; Azure VM narrow apply requires explicit `--yes`; broad AKS/cloud apply remains planned. |
| MCP | `mcp manifest/serve [--allow-writes]` | Implemented / guarded | The server is read-only by default; narrow writes require operator `--allow-writes` plus per-call `confirm=true`, with blocked/allowed/failed audit outcomes. Read tools exist; providers list supports status/runtime filters and ownership/runtime grouping; model list named-machine/current-machine filters, machines list/show/recommend, stacks list/show/plan/doctor/export, integrations roles/plan, and orchestrators list/show are exposed as safe read/planning tools; broad mutation and arbitrary local machine-file reads remain out of scope. |
| Audit/policy | `audit tail`, `policy explain/list/grant/revoke/drift` | Implemented | Audit appends are IPC-serialized and fsynced; secret sanitation covers structured keys, command flags, token forms, and PEM values. Policy decisions are explainable for canonical tool/provider/model/backend actions. Ignored workspace-local grants are action-scoped, audited, expiring, require explicit confirmation, distinguish approval from override, report stale/expired drift, and fail closed on malformed state without rewriting profile policy. |

## Roadmap

This document is the developer-facing status map. It separates what is implemented from what is in progress, planned, or deferred. For product boundary and architecture direction, see [Strategy](strategy.md).

### Status Labels

- **Implemented**: available in the current CLI, scripts, docs, or tests.
- **In progress**: partially implemented; useful pieces exist, but the area is not complete.
- **Planned**: intended direction, but not implemented yet.
- **Research**: worth investigating before committing to a design.
- **Deferred**: intentionally not a near-term priority.

### Scope Anchors

These anchors are deliberate product constraints, not incidental wording. Change them only with an explicit roadmap/strategy update that says the project is changing course.

- `aiplane` is a local-first environment doctor and configuration compiler for AI workflow environments: profiles, providers, model aliases, runtimes, endpoints, hardware fit, readiness checks, exports, MCP inspection, policy, and audit.
- The strongest public wedge is: **make local and hybrid AI model workflow stacks reproducible, inspectable, policy-aware, and portable from one profile**.
- `aiplane` configures and checks tools such as Ollama, vLLM, Continue, Aider, Cline, MCP clients, OpenAI-compatible endpoints, Anthropic, OpenAI, and Azure OpenAI; it does not replace them.
- Do not grow `aiplane` into a coding agent, full chat UI, inference runtime, general model proxy, model marketplace, IDE extension, production cloud platform, or Terraform/Ansible/Docker replacement.
- Runtime helpers must stay thin delegates to official tools. Deployment features must stay AI-specific, inspectable, previewable, and guarded.
- Orchestrator support means metadata, role bindings, endpoint/policy export, and readiness checks for established frameworks, not running autonomous agent conversations inside `aiplane`.
- MCP remains a structured inspection/planning/export surface with narrow audited writes. Arbitrary shell execution, broad cloud apply, secret writes, runtime installs, and model pulls stay out unless guardrails are explicitly designed and documented.

#### Ecosystem Overlap Register (mvp_0.3 baseline)

This register tracks overlap by layer so scope drift is intentional rather than accidental. A row stays in the table even when overlap is minimal, so boundary decisions remain visible during planning.

| Tooling family | Open-source / paid examples | What it does | Current aiplane overlap | Boundary position |
| --- | --- | --- | --- | --- |
| AI coding assistants | Continue, Aider, Cline, Cursor, Codex-style/Claude Code, JetBrains, Copilot | Runs coding sessions and owns agent interaction model | Exports and plans for endpoints/roles; no agent runtime ownership | In-scope by design: `aiplane` configures and checks, then hands off |
| Local inference runtimes | Ollama, vLLM, TGI, llama.cpp, LocalAI, LM Studio | Serve local model inference and model lifecycle | Provider/runtime mapping, helper wrappers, endpoint-aware runner checks, lifecycle ops where helper exists | Thin delegate only: native tools remain lifecycle authority |
| Managed APIs / services | OpenAI, Anthropic, Azure OpenAI | Hosted APIs with auth and endpoint contracts | Catalog adapters, endpoint/protocol metadata, provider tests, and task/chat execution for supported protocols | In-scope as configured endpoint caller, not marketplace or gateway |
| IDE integration surfaces | VS Code + Continue, Zed, IDE MCP clients | Connect editors/workflow tools to endpoints and MCP | Config snippets, MCP manifests, integration plan/export | In-scope only as config and readiness surfaces |
| Model catalogs | Hugging Face, NVIDIA on HF, local files, media sources | Resolve model IDs/artifacts and discovery metadata | Multiple catalog adapters, discovered cache, add/promote/clone, provider-kind grouping | Core in-scope configuration function |
| Infrastructure tooling | Docker/Compose, OpenSSH, Dev Containers, Terraform/OpenTofu, Vagrant, Packer, Ansible, Helm, kubectl | Build runtime/machine/container/workspace targets | Readiness checks, non-mutating plans, guarded helper calls and generated exports | Boundary is explicit: planning+readiness, not ownership of infra platform |
| Orchestration / workflow frameworks | LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex, OpenHands | Run autonomous agent/workflow execution in application runtime | Stack role metadata, policy labels, starter exports, stack doctor/planner | In-scope as setup/binding/export only |
| Benchmark and validation | lm-eval, vLLM serving benchmarks, Locust | Compare quality/throughput/latency on a workload | Smoke/custom benchmark scaffolding and planning commands | In-scope as aid-to-selection, not a benchmark SaaS replacement |
| Secret / auth / infra services | Azure Speech, ElevenLabs, key-vault style services | Secret handling, hosted services, and shared endpoint control | Credential refs and provider tests are supported; direct secret writes / platform control are not | Explicitly out of scope for the current wedge |

Scope-change protocol: if any overlap row moves toward owning execution, marketplace behavior, or broad platform automation, update Strategy + roadmap anchors explicitly and document the policy change in `project-plan.md#current-status-and-session-handoff` before implementation.




### Public Adoption Wedge and Milestone Priorities

#### Priority 1: Prove the core workflow

The public wedge is now a narrow onboarding path:

```text
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
```

A new user should reach a useful result with one command:

```text
aiplane quickstart local-coding
```

That command should automatically:

1. Detect hardware
2. Detect installed runtimes
3. Detect local models
4. Detect supported coding tools
5. Detect existing endpoint configuration
6. Create a draft profile
7. Run doctor
8. Recommend suitable models
9. Print exact export commands

**Success criteria**

1. No manual YAML editing required for the first successful run
2. No more than two user decisions during onboarding
3. Useful output produced within five minutes
4. The command can run safely in dry run mode
5. Repeated execution does not overwrite manual changes without warning

#### Priority 2: Reduce configuration duplication

**Target**

Track how much configuration is detected automatically.

The workflow should surface a summary like:

```text
Detected values: 24
Generated values: 8
User supplied values: 2
Unresolved values: 1
```

**Success criteria**

1. At least 80 percent of local setup values are discovered or inferred
2. The user should manually enter no more than credentials and policy decisions
3. Every generated value includes provenance
4. Existing Continue, Aider, Cline and endpoint configuration can be imported
5. The tool clearly distinguishes detected, inferred and user supplied values

#### Priority 3: Simplify the public command surface

**Target**

Make these the main commands shown in the README and onboarding:

```text
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
```

Existing detailed commands can remain, but should be treated as advanced commands.

**Success criteria**

1. The first page of the README shows no more than four primary commands
2. A new user can complete the main workflow without understanding stacks, bridges, targets or orchestrators
3. Advanced terminology appears only after the first successful workflow
4. Each primary command has clear text and JSON output
5. Each command produces a suggested next command

#### Priority 4: Make doctor output fully actionable

**Target**

Every blocking or advisory finding must contain:

1. Severity
2. Reason
3. Impact
4. Exact remediation command
5. Whether the command mutates state
6. Whether dry run is supported

**Success criteria**

1. 100 percent of blocking findings contain an exact remediation command
2. 100 percent of mutating commands clearly identify themselves
3. Doctor exit codes distinguish healthy, advisory and blocking states
4. JSON output contains stable fields for CI usage
5. Tests cover every doctor finding category

#### Priority 5: Validate recommendation quality

**Status: Implemented for deterministic fixture coverage; external calibration remains ongoing.**

**Target**

Create test cases covering:

1. CPU only machine
2. Small NVIDIA GPU
3. 24 GB NVIDIA GPU
4. 32 GB NVIDIA GPU
5. AMD GPU
6. Apple unified memory
7. Remote GPU endpoint
8. Cloud managed model
9. Policy restricted environment
10. Unsupported runtime format

For each case, define expected recommended, usable and rejected models.

**Success criteria**

1. Recommendation decisions are deterministic
2. Each recommendation includes ranking rationale
3. Policy blocked models never appear as recommended
4. Runtime incompatible models never appear as recommended
5. Hardware unsuitable models are clearly separated
6. Benchmark data influences ranking only when available
7. Missing benchmark data does not break ranking

#### Priority 6: Prove deterministic exports

**Status: Implemented for supported fixture exports and saved-plan replay coverage.**

**Target**

Generate stable expected outputs for:

1. Continue
2. Aider
3. Cline
4. Zed
5. Generic OpenAI compatible clients
6. MCP clients

**Success criteria**

1. The same profile produces byte stable output where possible
2. Machine specific fields are clearly isolated
3. Every export includes a plan identifier
4. Every export can be reproduced from the plan identifier
5. Export output records profile version and selected model aliases
6. Client configuration changes trigger visible test failures
7. Exporters are version aware where the client format changes

#### Priority 7: Make policy behaviour predictable

**Status: Implemented for current allow / approval-required / blocked decisions; temporary approvals, overrides, and organization audit workflows remain planned governance extensions.**

**Target**

Use a consistent set of policy outcomes:

1. Allowed
2. Allowed with warning
3. Approval required
4. Temporarily approved
5. Blocked
6. Overridden with audit record

**Success criteria**

1. Every model and endpoint decision returns one policy outcome
2. Export commands block disallowed providers
3. Overrides require an explicit reason
4. Temporary approvals have an expiry
5. Every override creates an audit entry
6. Doctor reports policy drift
7. Policy behaviour is identical across CLI, MCP and exports

#### Priority 8: Tighten the product boundary

**Status: Implemented as a command category inventory in command coverage, with README and top-level help leading on the core workflow.**

**Target**

Create a command inventory with three categories.

Core: discovery, doctor, recommendation, policy, export, profile management

Supporting: runtime status, remote endpoint checks, hardware inventory, MCP inspection, benchmark summaries

Deferred from public focus: broad provisioning, general agent execution, rich chat experience, cloud platform behaviour, infrastructure replacement, general workflow orchestration

**Success criteria**

1. README leads only with core commands
2. Public demo spends at least 80 percent of its time on core commands
3. New features require a written explanation of which category they belong to
4. No new top level command is added without a scope review
5. Deferred areas do not block the external beta

#### Priority 9: Test clean machine onboarding

**Target**

Test repeatable onboarding on at least six environments:

1. Ubuntu with Ollama and Continue
2. Ubuntu with vLLM
3. Windows with Ollama
4. macOS with Apple Silicon
5. Clean machine with no AI tools installed
6. Remote workstation with local client

**Success criteria**

1. Installation succeeds from documented steps
2. Discovery completes without manual file changes
3. Doctor produces useful findings
4. At least one working export is generated
5. A tester completes the flow without developer assistance
6. Median time to first useful export is below ten minutes
7. Every failure is classified as product defect, documentation defect or unsupported environment

#### Priority 10: Gather external evidence

**Target**

Recruit ten users from the intended audience:

1. Three local AI power users
2. Two software consultancies
3. Two teams using local and cloud models
4. Two privacy sensitive organisations
5. One developer using a remote GPU workstation

**Success criteria**

1. At least seven complete onboarding
2. At least five generate and use an export
3. At least three use more than one integration
4. At least three report that `aiplane` replaced manual configuration or scripts
5. Record every point where users needed help
6. Collect time to first successful result
7. Collect the number of manual values entered

#### Priority 11: Define adoption metrics

**Target**

Track these metrics:

1. Installation completion rate
2. Discovery completion rate
3. Doctor success rate
4. Time to first useful export
5. Number of detected values
6. Number of manually entered values
7. Number of successful integrations
8. Number of policy blocks correctly explained
9. Number of repeatable profile replays
10. Number of users returning within seven days

**Initial targets**

1. 80 percent onboarding completion
2. Median first export below ten minutes
3. At least 80 percent configuration auto detected
4. At least 70 percent of users successfully use one generated export
5. At least 40 percent successfully use two integrations
6. Fewer than three unexplained errors per ten onboarding sessions

#### Priority 12: Improve documentation structure

**Status: Implemented in the user documentation entrypoints with Start here, Common workflows, and Advanced concepts sections. Clean-machine onboarding commands are added to the public demo plan for Priority 9 trials.**

**Target**

Split documentation by user maturity:

Start here:

1. Install
2. Quickstart
3. Doctor
4. Recommend
5. Export

Common workflows:

1. Local Ollama
2. Local vLLM
3. Remote GPU workstation
4. Managed provider
5. Privacy restricted repository

Advanced concepts:

1. Providers
2. Runtimes
3. Machines
4. Stacks
5. Policies
6. MCP
7. Orchestrators

**Success criteria**

1. The first page contains one primary workflow
2. No advanced concept is required to complete onboarding
3. Every example is tested in CI where practical
4. Every example identifies whether it mutates state
5. Every workflow ends with a verifiable outcome

#### Priority 13: Replay approved profiles across machines

**Status: CLI implementation complete; physical-machine field evidence remains in the separate P1 trial gate. Deterministic archive/restore, explicit exclusions, checksums, credential/path validation, preview-by-default restore, atomic new-profile creation, deterministic profile/archive comparison, provenance-aware destination drift classification, aggregate verification of at least two distinct client-produced archives, synthetic compatibility fixtures, and byte-stable supported-export replay proof are implemented.**

**Target**

Provide a safe, reviewable workflow to back up and replay profile configuration across machines without treating credentials, model weights, caches, or runtime state as portable profile data. Replay must support both identical machines and capability-equivalent machines whose small CPU, RAM, VRAM, or device differences do not change the suitability of the reviewed models, runtimes, endpoints, and policy.

**Success criteria**

1. A documented manifest defines portable profile files and explicitly excluded machine-local state.
2. Archive and restore operations are previewable, reject unsafe paths, preserve the original on conflict, and never include raw credentials.
3. Profile-to-profile and profile-to-current-machine comparison separates exact equality, capability-equivalent variance, material incompatibility, and unresolved evidence.
4. Capability equivalence is based on explicit model/runtime/policy requirements and conservative thresholds, not generic hardware similarity.
5. Identical resolved inputs reproduce byte-stable supported exports; non-material variance is reported without forcing changes.
6. Material differences produce provenance-aware doctor/drift findings and may trigger revised recommendations or blocked exports.
7. Replay is tested across at least two identical VMs, two near-equivalent machines, and one intentionally incompatible destination.
8. The workflow delegates environment, runtime, weight, credential, and infrastructure restoration to Conda/venv, runtime vendors, secret owners, and established infrastructure tools.

#### Priority 14: Make model placement evidence measurable and explainable

**Status: Planned after the P0 evidence gate; existing hardware bands, catalog capability hints, and smoke/custom benchmark results remain separate signals today.**

**Target**

Replace coarse recommendation inputs with a provenance-aware placement assessment while preserving the distinction between compatibility, estimated performance, measured performance, task suitability, and policy. The assessment must configure and evaluate external runtimes; it must not turn `aiplane` into an inference runtime, benchmark service, model marketplace, or rich chat application.

**Success criteria**

1. Model-variant metadata can represent artifact format, quantization, weight size, total and active parameters, native context, configured context, and KV-cache assumptions, with source and confidence recorded for every inferred value.
2. Hard eligibility is evaluated before ranking and reports runtime/API compatibility, policy outcome, memory pool, required memory, available memory, headroom, usable context, and the expected execution/offload mode. Multi-GPU eligibility retains per-device vendor, architecture, capacity, allocation, topology/interconnect, partitioning, and free-memory evidence, and aggregates memory only when the chosen runtime and parallelism mode make it usable.
3. Recommendation output never presents catalog heuristics, formula estimates, local measurements, imported measurements, or user-configured values as interchangeable evidence.
4. Performance benchmark records include throughput, time to first token when measurable, end-to-end latency, prompt/output token counts, repeated-run summaries, runtime/version, model identity, quantization, context, relevant runtime settings, and a privacy-conscious hardware fingerprint.
5. Repeated measurements use robust summaries and retain sample count, timestamp, environment provenance, errors, and comparability metadata; a single successful run is not silently generalized into a universal claim.
6. Local calibration uses only comparable measurements from the same relevant hardware/runtime configuration, records the calibration basis and confidence, remains stable when evidence is missing, and can be disabled or inspected.
7. Task-quality evaluation remains separate from throughput and placement. Built-in checks are labelled as smoke evidence, while custom evaluators can use executable tests, schema validation, exact answers, and tool-call validation.
8. Near-miss results explain the smallest reviewable change that could make a candidate viable, such as a different quantization, smaller context, supported runtime, additional memory, safe offload path, or an existing remote endpoint.
9. Text and JSON output expose component evidence and rationale instead of relying on an opaque universal score; any derived ranking value documents its dimensions, weights, version, and uncertainty.
10. Deterministic fixture coverage spans CPU-only, discrete GPU, unified memory, multi-GPU, dense and mixture-of-experts metadata, local runtimes, remote endpoints, missing evidence, incompatible formats, and policy blocks before real-machine calibration claims are published.
11. A versioned, portable benchmark-suite schema supports YAML and canonical JSON with named roles/tasks, prompts or fixtures, deterministic and stochastic settings, token/time budgets, grader type and version, expected outputs, policy requirements, and explicit secret-free validation. Suites remain reviewable data and do not grant arbitrary code execution.
12. Quality evidence records repeated samples where stochastic inference matters, including seed when supported, temperature and decoding settings, pass/fail distribution, robust score summaries, variance or confidence bounds, failures, and the exact suite/grader version. One regex or keyword match remains smoke evidence, never a general quality claim.
13. Model acquisition produces an inspectable artifact lock containing source and revision, provider-native identity, file or deployment identity, format, quantization, size, checksum when available, license/gating notes, cache ownership, and runtime compatibility. Replay may verify or reacquire artifacts but must not silently bundle credentials or runtime-owned weights.
14. External-runner launch plans have a versioned manifest for runtime/version requirements, model artifact or alias, endpoint and protocol, context/KV settings, device/offload/parallelism parameters, ports, mounts, environment-variable references, health checks, and exact previewed vendor commands. Execution remains delegated to the external runtime and guarded by platform capability and approval policy.
15. Role-routing comparisons report per-role evidence, constraints, policy, uncertainty, and runner/endpoint ownership before recommending a model. They must preserve viable alternatives and must not collapse incomparable task quality, placement, cost, and speed into one unexplained score.
16. Node-level REST scheduling and community benchmark exchange each require a separate research decision covering user evidence, authentication, versioning, poisoning/provenance, privacy, abuse controls, maintenance cost, and why CLI/MCP or local evidence are insufficient. Neither is a committed feature until that gate is approved.

#### Recommended delivery order

##### Milestone 1: External beta readiness

1. Single command onboarding
2. Actionable doctor output
3. Configuration provenance
4. Deterministic exports
5. Recommendation test matrix
6. Simplified README
7. Clean machine tests

Exit target: five external users complete the main workflow without developer assistance.

##### Milestone 2: Team reproducibility

1. Portable profile archive/restore with an explicit exclusion manifest
2. Stable plan and export replay
3. Profile comparison and current-machine drift
4. Capability-equivalence classification for identical, near-equivalent, and incompatible machines
5. Policy state and drift model
6. Shared profile validation
7. Remote workstation replay from multiple clients

Exit target: Two teams reproduce the same approved setup across at least three machines.

##### Milestone 3: Evidence-backed model placement

1. Versioned model-variant and placement-evidence schema
2. Quantization-, context-, KV-cache-, architecture-, and runtime-aware resource assessment
3. Explicit compatibility, headroom, execution-mode, usable-context, and near-miss explanations
4. Standard local performance records with repeated-run summaries and comparable environment fingerprints
5. Inspectable local calibration and model/runtime/machine comparison views
6. Deterministic task-quality evaluators kept separate from placement and performance metrics
7. Recommendation and doctor integration with evidence source, confidence, sample count, and uncertainty
8. Versioned YAML/canonical-JSON benchmark suites with deterministic validation and repeated stochastic quality summaries
9. Artifact locks and exact external-runner launch manifests that support verification and replay without owning runtime state
10. Evidence-backed per-role routing comparisons with policy, uncertainty, and viable alternatives
11. Recorded go/no-go decisions for node REST scheduling and community benchmark exchange

Exit target: deterministic fixtures plus repeated performance and quality runs on at least two materially different local machines produce explainable placement and role-routing decisions, preserve missing-evidence behavior, let maintainers trace every ranking input to its source, and replay one locked artifact plus external-runner launch plan without copying credentials or runtime-owned state.

##### Milestone 4: Commercial validation

1. Central profile registry prototype
2. Signed policy support
3. Central audit collection
4. Fleet inventory
5. Role based administration
6. Organisation reporting

Exit target: At least two organisations agree that team governance capability is valuable enough to pay for.

#### Immediate next sprint (high-priority and blocking)

1. Implemented: add `aiplane discover`
2. Implemented: make `aiplane quickstart local-coding` consume discovery output automatically
3. Implemented: add provenance to generated/detected/user-supplied/unresolved profile values
4. Implemented: ensure every doctor failure includes exact structured remediation metadata
5. Add golden file tests for Continue, Aider, Cline, and MCP exports
6. Run the workflow on three clean environments and document every failure

#### Scope freeze until the sprint completes

Do not add new orchestrators, cloud providers, benchmark frameworks or runtime types until those six targets are complete.

### Current Milestone: External Beta Readiness

The roadmap is now actively executing the priorities above; completed work in each earlier milestone is being stabilized as execution hardens. P0 quickstart sufficiency is implemented with offline-safe defaults, idempotent profile preservation, bounded no-model guidance, and one exact next action.

P0.6 stable doctor contract v1 is implemented with uniform findings and authoritative 0/1/2 exit semantics.
P0.7 Tier-1 export contracts are implemented with four versioned golden formats and cross-OS installed-wheel verification.
P0.8 public profile schema v1 is implemented with external validation and canonical rendering.

### Implemented

- Profile loading, validation, templates, selected/default profile handling, ignored local config, and external profile directory support.
- Ignored local credential references with redacted credential inspection commands and provider connection tests for selected managed endpoints.
- Local AI workflow quickstart with opt-in runtime-helper model pull preview/execution plus top-level local AI workflow stack doctor with profile, environment, provider/endpoint, role default, selected endpoint readiness, hardware-fit, Continue/Aider readiness, and MCP manifest/read-surface summaries; environment planning and doctor checks cover system Python, `venv`, Conda, and Docker execution mode; setup helpers install the CLI and bootstrap ignored `profiles/local-dev` from the shipped template before profile-aware checks.
- Local config now supports profile-aware and command-aware format/verbosity defaults (`text`/`json`, `0`/`1`/`2`) via `config format`/`config verbosity` with precedence: CLI `--format`/`--verbosity` > command override > profile override > global default.
- External tool catalog, doctors, guarded install previews, non-mutating plans, and starter exports for Azure CLI, OpenTofu/Terraform, Pulumi, Vagrant, Packer, Docker/Compose, Dev Container CLI, kubectl, Helm, OpenSSH, Ansible, and benchmark helpers.
- Provider/model catalog foundations for Ollama, Ollama Cloud placeholder, OpenAI-compatible runtimes, OpenAI, Anthropic, Azure OpenAI, ElevenLabs TTS, Hugging Face, NVIDIA Hugging Face-scoped open model repos, GGUF/local files, and user-defined discovery providers. Shipped profile templates keep `models.yaml` structural, runtime/provider endpoint values live as conventional built-in defaults with local override support, and model grouping separates managed-service providers from self-managed runtime sources while preserving managed endpoint metadata for exports, stacks, and orchestrator plans.
- Non-destructive bootstrap plus install/activation flows preserve existing editable profiles unless `--overwrite` is explicit; static wheels include shipped config/profile templates and runtime helper scripts and are verified in a clean venv.
- Ignored discovered provider/model cache flow plus `profiles bootstrap-local`, `models add`, `models clone`, and `models promote` as reviewed paths into editable local profile YAML; `models clear-cache` clears discovered entries and profile-owned review entries by default so discovery can be repopulated from providers, and `models refresh --reset-cache` combines clearing and repopulating for refreshed providers.
- Runtime/source mapping for Ollama, Hugging Face, NVIDIA Hugging Face-style repos, GGUF/local files, vLLM, TGI, Transformers, llama.cpp, LocalAI, LM Studio, and selected media runtimes.
- Runtime helper delegation through `aiplane runtimes ...` where supported by `scripts/provider_helper.sh`, including Ollama native and Docker substrate paths, guarded Ollama pulled-model remove/clear, plus vLLM/TGI-style runtimes.
- Cross-platform per-device hardware discovery, active hardware selection, machine schema/templates, model-fit checks, runtime-aware placement assessment, and explainable placement-readiness recommendations.
- Machine inventory commands for import/list/show/validate/recommend, Azure SKU discovery/import, cache list/clear, Azure status, and remote profiling plans.
- Stack commands for setup/list/show/plan/doctor/status/export plus same-host lifecycle commands `prepare/start/stop/restart`.
- Stack preflight checks for runtime prerequisites, local port availability, endpoint auth policy, and cache-path hints.
- Azure target planning and doctor checks for AKS and VM targets, plus a narrow guarded Azure VM apply path.
- Orchestrator catalog commands for LangGraph, CrewAI, AutoGen, OpenHands, Semantic Kernel, and LlamaIndex Workflows.
- Agent application templates with non-mutating `agents templates/plan/export` commands, plus a versioned `skills/aiplane/SKILL.md` package for assistant workflow guidance.
- Stack artifact exports for Continue, OpenAI-compatible endpoint config, Dockerfile, Conda YAML, starter Docker Compose, and framework starter metadata for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands.
- SSH tunnel plan/start/status/stop for configured remote model endpoints.
- Model list/show/defaults/use/add/clone/remove/enable/disable/refresh/promote/clear-cache/pull/test/benchmark commands.
- Benchmark framework list/doctor/install/plan helpers plus versioned suite validation, repeatable smoke/custom runs, and preview-first external measurement import for smoke/custom checks, lm-evaluation-harness, vLLM serving benchmarks, and Locust-style load tests.
- `aiplane run` for single-prompt routing through configured model defaults with dry-run, policy-gated non-local escalation, and protocol backends for Ollama, OpenAI-compatible chat completions, Azure OpenAI chat completions, and Anthropic Messages.
- Strict allowlisted runtime bridge commands (`bridge list/exec`) for delegating selected native runtime CLIs by shorthand action without exposing arbitrary shell passthrough.
- Integration role inspection plus plan/setup/export for Continue, Cline, Zed, Aider, generic OpenAI-compatible clients, and MCP client snippets; setup can dry-run or execute supported helper install/start/pull actions for selected runtime/model aliases and skips unsupported source/runtime pull combinations with an explicit reason.
- MCP stdio server with read tools and narrow guarded writes for model defaults, hardware selection, runtime preference, model refresh, and SSH tunnel lifecycle. Read/planning tools cover models, providers, hardware, machine recommendations, stack inspection/planning/doctor checks, integrations, orchestrators, runtime status, and tunnel plans.
- Policy checks, expiring action-scoped local approvals/overrides, drift reporting, secret redaction, JSONL audit foundations, and shared JSON output ordering.

### In Progress

- Provider discovery: offline readiness diagnostics, Anthropic `/v1/models`, OpenAI-compatible optional-auth local gateways, Azure OpenAI deployments, ElevenLabs voices, Ollama, Hugging Face, NVIDIA-scoped repos, GGUF, structural templates, and reviewed import flows are implemented. New specialist APIs remain adapter-by-adapter work.
- Runtime and stack lifecycle: versioned bundles render runtime ports, cache mounts, GPU selectors, environment/auth references, context, and tensor-parallel intent without secrets or execution. Stacks persist an explicit native/Docker runtime substrate and forward it through plan and guarded lifecycle helper commands; remote execution and production service management remain early. Single-prompt execution is protocol-based for Ollama/OpenAI-compatible/Azure OpenAI/Anthropic, while richer chat/task UX remains planned.
- Tool integrations: doctors, install previews, plans, and starter exports exist; provider-specific modules/playbooks/templates remain planned.
- Azure deployment: planning, doctor checks, and narrow VM apply exist; broader AKS/cloud apply needs hardening before expansion.
- MCP governance: read tools and audited narrow writes exist; broader write tools require explicit risk controls.
- Benchmarking: versioned smoke/custom suites, repeat summaries, safe built-in graders, explicit opt-in command graders, external measurement import, role comparison, and comparable saved-evidence views across runtime/model/machine/quantization/context exist; native backend TTFT/token telemetry remains adapter-dependent and sandboxed code execution remains planned.
- IDE/CLI integration: Tier-1 print-only Codex, Copilot CLI, and Copilot-in-VS-Code exports now cover local and compatible managed endpoints; deeper Cursor, JetBrains, Windsurf, and Claude Code integration remains research/planned.

### Planned Milestones

#### Post-Merge Foundation

1. **Architecture and codebase cleanup** - Implemented
   - `src/aiplane/cli.py` delegates every command family to focused owners and is limited to parser composition and dispatch. Launch/session planning, profile views/validation, presentation/progress reporting, and public onboarding workflows live in dedicated modules. The root decreased from 3,171 to 456 lines while preserving one public `aiplane` entrypoint.
   - Shared CLI parsing/progress helpers live outside the monolithic CLI so provider refresh, profile bootstrap, hardware/machine/stack settings, and future command modules do not duplicate low-level parsing behavior.
   - Model filter parser choices and MCP schema choices are shared definitions; integration roles are shared contracts. Keep moving shared definitions only where they prevent drift.
   - Keep shell helpers as thin delegates to official tools; avoid growing provider-specific business logic in Bash when Python catalog/runtime code already owns the decision.
   - Preserve inspect-first behavior and coherent early-beta interfaces; do not keep inconsistent flags or compatibility shims until a released interface requires them.

2. **MCP and agent skill hardening** - Implemented / hardening
   - Audit MCP against the current CLI/options and docs; close useful read/planning/export gaps such as newer model filters, integration role planning, stack/orchestrator inspection, machine recommendations, and command coverage where safe.
   - Keep risky operations out of MCP until they have explicit approval, audit, dry-run, and rollback semantics. Runtime installs, model pulls, cloud apply, secret writes, and arbitrary shell execution remain blocked or CLI-only by default.
   - Add a versioned `aiplane` skill target for Codex-style and other skill-capable assistants. The skill should explain the product boundary, profile/provider/model/runtime concepts, preferred commands, MCP usage, docs/test maintenance, and pre-PR/release checks.
   - Add focused tests that compare MCP schemas and behavior with the CLI surfaces they intentionally mirror.
   - Treat MCP/skills synchronization as a recurring checkpoint and pre-PR cleanup task, not a requirement after every small feature.

3. **Orchestrator and multi-agent workflow metadata** - Implemented / hardening
   - Stack setup can carry optional role metadata such as planner, coder, reviewer, researcher, tool-runner, and summarizer while preserving one primary lifecycle model for runtime install/pull/start actions.
   - Role metadata binds reviewed model aliases to provider/runtime or managed endpoint ownership plus tool policy, approval mode, limits, and audit labels; stack plan/doctor/status/export surface the metadata, and doctor warns on disabled role models, missing managed endpoints, and risky tool-policy/approval combinations.
   - Framework starter exports emit reviewed role/endpoint/tool/approval/audit metadata plus framework-specific topology and readiness for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, OpenHands, and the simple OpenAI-compatible client. They remain render-only Aiplane metadata rather than claims of native framework project generation.
   - Completed: schema-linked agent-environment manifests render from direct profile selection or stack YAML, preserving model identities, endpoints, role bindings, tool policy, approvals, limits, audit labels, and credential references. JSON/YAML exports and the MCP read tool are secret-free and explicitly non-executing.
   - Validate agent-environment planning and export against the supported local runner matrix so Ollama, llama.cpp, MLX, Docker Model Runner, LM Studio, and vLLM endpoints can be selected where their protocol and model capabilities satisfy the target framework.
   - Keep `aiplane` as setup/config/policy/export, not the autonomous multi-agent runner.
   - Keep extending doctor/plan checks so they explain missing packages, missing endpoints, model/runtime incompatibility, and unsafe tool-policy combinations before anything is run.

#### Product Hardening

4. **Provider discovery and model import** - Implemented foundation / ongoing provider hardening
   - Shipped `models.yaml` templates stay structural; profile-owned model entries and defaults come from ignored discovery caches, direct local add/clone, or deliberate local promotion.
   - `models promote` is the reviewed flow from discovered provider entry to editable local profile model; use `models add` when the real provider model id is already known but still present in discovery, and `models clone` when one real model needs multiple local purposes.
   - Refresh/promote/add/clone output explains the safe next step from dry-run discovery to discovered entries to traceable profile-owned model entries.
   - `models list` now filters from active hardware, named/imported machines, external machine files, the currently probed machine, and explicit RAM/VRAM/GPU/API/parameter constraints. Parameter count remains explicit because it is a model property rather than a machine-derived fact.
- `models list --format text` now supports compact output at verbosity 0 with explicit warning/fallback to JSON payload at verbosity 1+.
   - Managed-provider online catalog failures, such as an unconfigured Azure OpenAI deployment endpoint/key, now return structured refresh failure JSON with provider-test/show next steps instead of silently looking successful through an empty profile-catalog fallback.
   - OpenAI-compatible `/v1/models`, Azure OpenAI deployment, and ElevenLabs voice discovery now share the managed-provider failure path when endpoint/key configuration is missing. Ongoing hardening remains for richer managed-provider discovery, provider-specific live credential tests, and Anthropic discovery fallbacks where APIs or maintained catalogs allow it.

5. **Runtime, stack lifecycle, and endpoint hardening** - Implemented foundation / ongoing lifecycle hardening
   - Same-host lifecycle result reporting includes execution mode, step counts, failed step, timing fields, stdout/stderr tails, and best-effort runtime status before and after execution.
   - Stack endpoint planning now records endpoint auth/TLS/gateway hints, surfaces `stacks endpoint-plan`, and feeds plan/doctor checks for public/shared endpoint readiness.
   - Stacks can bind managed-service model endpoints where the runtime field represents a hosted protocol or endpoint contract, while keeping those entries out of self-managed runtime fit checks.
   - Remote execution boundaries remain explicit for SSH/Azure/AKS stacks; non-local lifecycle commands still return plans rather than executing.
   - Docker-aware same-host stack lifecycle is implemented with explicit `--yes`, exact native `docker model` commands, alias-to-native-id resolution, the conventional engine endpoint, and runtime evidence in plan/status results. Remote execution and supported-platform live acceptance remain separate work.
   - Completed at contract and adapter level: Docker Model Runner detection, inventory, identity, fit inputs, health, endpoint export, benchmark, and guarded lifecycle use its native command boundary; supported-platform live acceptance remains open.
   - Maintain the implemented `runtimes capabilities` contract for Ollama, llama.cpp, MLX, Docker Model Runner, LM Studio, and vLLM. Track separately: platform detection, installed-model inventory, alias/native-ID resolution, model-fit assessment, health/readiness, endpoint export, benchmark support, and guarded install/pull/start/stop operations.
   - Close inspection and configuration gaps before adding mutation: first normalize discovery, inventory, identity mapping, fit, endpoint, and doctor behavior for all six runners; then add lifecycle helpers only where the vendor exposes a stable, documented, testable command or API.
   - Treat remote endpoints independently from local installation. Ollama, Docker Model Runner, LM Studio, llama-server, MLX servers, and vLLM may be used through configured endpoints even when their local lifecycle is unsupported on the current platform.
   - Completed: artifact-lock and external-runner launch-manifest contracts are integrated into pull previews, stack plan/doctor, benchmark records, replay comparisons, and lifecycle results. Keep vendor commands exact and previewable; do not reinterpret a launch plan as permission to install a runtime, bind a public port, or copy model weights.

6. **Cloud, VM, and workstation workflow hardening** - Implementation complete / live-provider review ongoing
   - Use OpenTofu as the default provider-agnostic IaC target, Terraform as a compatible alternative, and Pulumi as an optional language-native IaC path.
   - Completed: `deploy render` emits deterministic, schema-linked and checksummed target-specific families. Azure VM uses reviewed OpenTofu/Terraform-compatible HCL, an Azure Packer starter, Ansible inventory, and a baseline playbook; AKS emits Azure infrastructure HCL and delegates workload files to the existing Kubernetes renderer; SSH/local VM/local install paths emit Ansible, Vagrant, or Dev Container artifacts as appropriate.
   - Keep local install, local VM provisioning, remote VM provisioning, remote PC setup, and cloud provisioning distinct. `deploy workflow-plan` now exposes those boundaries and recommended tool ownership.
   - Keep mutating target bootstrap behind explicit confirmation; `deploy apply` requires `--yes` and broad cloud apply remains out of scope until provider-specific guardrails are ready.
   - Completed: render-only Kubernetes `ResourceClaim`, `Deployment`, `Service`, and Helm values are deterministic, secret-free, reviewable, schema-linked, and non-mutating. Applying generated artifacts remains a separate future capability behind explicit human review and approval.
   - Keep public demo paths focused on repeatable local, endpoint, MCP, stack, and Azure discovery workflows without unsafe mutation.

7. **Tool/task matrix and setup doctor expansion** - Implemented / requirements grow with integrations
   - Keep `environment doctor` as the default human setup check with text output.
   - Keep every external tool mapped to the workflows it enables, whether it is mandatory or optional, and whether `aiplane` can attempt installation.
   - Grow doctor scope as new tool families are integrated without turning optional workflows into mandatory prerequisites.
   - Completed: `tools matrix --workflow` and `environment doctor --workflow` use explicit end-user workflow contracts. Mandatory tools, optional tools, and any-of alternatives are distinct, so unrelated workflows remain optional and cloud users need one reviewed IaC path rather than every supported IaC CLI.
   - Keep workflow-level readiness summaries in `tools matrix` useful for release review and demos.

#### Later Expansion

8. **Runtime packaging and deployment reproducibility** - Implementation complete / live-platform evidence separate
   - Six-runner capability coverage and MLX metadata/launch planning are implemented; live platform evidence and deeper vendor-specific tuning remain ongoing.
   - Completed: deterministic synthetic coverage exercises all six runners without requiring every vendor runtime on every CI host. Platform-specific live checks supplement, rather than replace, the contract suite.
   - Completed at runtime-bundle boundary: auto mode resolves to an honest Docker, Conda, or native handoff per runner; unsupported substrate requests fail clearly; generated files are deterministic and checksummed. MLX does not claim Linux-container support, while Docker Model Runner and LM Studio do not claim standalone Docker/Conda packaging.
   - Completed: deterministic stack framework export coverage crosses all six primary runners with LangGraph, CrewAI, and AutoGen bindings, while vendor-client live smoke remains a separate compatibility check.
   - Completed at render-contract level: runtime bundles include conventional ports, named cache mounts, explicit GPU selectors, environment/auth variable references, context and tensor-parallel settings, with validation that prevents embedded environment values.
   - Keep image builds, registry pushes, VM creation, and cloud apply explicit and previewable.

9. **IDE, launch, and session integrations** - Implemented / hardening
   - Continue, Cline, Zed, Aider, generic OpenAI-compatible, and MCP config exports are implemented at config level.
   - `aiplane launch` is implemented for stable tools (`continue`, `ollama`, `aider`) with profile-driven model selection, policy checks, and optional `--app` for Ollama tool launching.
   - `aiplane session start` is implemented for thin session handoff metadata, transcript defaults, and local audit records.
   - Add launch wrappers for additional stable CLIs (Codex, Cursor, Claude Code) only when contracts and usage patterns are stable.
   - Keep future `aiplane session` extensions thin: selected model, endpoint, transcript path, and audit metadata, not a full custom chat product.

10. **Benchmark and recommendation quality** - Contracts and local workflow implemented / cross-machine calibration ongoing
   - Implemented: versioned placement and scoring schemas keep hard compatibility, resource estimates, measured evidence, configured task suitability, policy, confidence, weights, contributions, missing-evidence coverage and declarative extensions distinct.
   - Implemented foundation: parameter/quantization weight estimates, architecture-aware KV cache, context, runtime workspace, single GPU, homogeneous multi-GPU, CPU offload and CPU-only modes produce assumptions, blockers and near-miss evidence. Artifact locks and more architecture metadata will improve precision.
   - Implemented: repeated suite runs and imported measurements preserve runtime/model settings, environment fingerprints, decoding, pass rate, robust summaries, uncertainty and comparability metadata. Native runner TTFT/token telemetry remains backend-dependent and unresolved where APIs do not expose it.
   - Implemented: inspectable comparison views group saved evidence across models, runtimes, machines, quantizations, and contexts, emit leaders only for explicit comparable groups with at least two values, and require exact telemetry provenance for TTFT leaders. Benchmark evidence remains optional for deterministic fallback behavior.
   - Add near-miss explanations and confidence/provenance fields to recommendation and doctor output.
   - Keep role/task-quality evaluation separate from throughput and placement; prefer executable or schema-based custom graders, and label built-in keyword checks as smoke evidence.
   - Implemented: portable versioned JSON/YAML benchmark suites with deterministic validation and a safe grader allowlist. Command graders require an explicit suite opt-in and are documented as trusted local execution, not a sandbox.
   - Implemented foundation: repeat indices, recorded decoding settings, pass-rate/score summaries and standard error keep deterministic checks distinct from sampled evidence. Add rubric/judge adapters only with explicit provenance and comparability rules.
   - Implemented: evidence-backed per-role routing retains alternatives, policy/placement constraints, comparable measured quality, configured task suitability, and declarative user score contributions instead of producing one opaque universal score.
   - Keep a node scheduling REST service deferred until demonstrated user demand. CLI/MCP and local evidence already cover most local planning workflows; a new service surface requires evidence that these are insufficient plus explicit authentication, security, provenance, privacy, abuse, versioning, and maintenance decisions. Apply the same separate research gate to any community benchmark exchange.
   - Defer automated generated-code execution until sandboxing and language runners are designed.

11. **Test-suite structure, performance, and isolation** - Structurally complete / incremental
   - Production loaders are no longer globally replaced by the test harness; temporary profile roots contain deterministic synthetic model data and exercise normal disk loading.
   - The quick gate now runs ten contracts plus four intentional smoke checks; the empty legacy aggregate module is no longer included.
   - Shared injectable command/HTTP boundaries now cover every production process and HTTP owner; only `boundaries.py` calls `subprocess` or `urllib` directly, enforced by a contract test.
   - Model refresh reconciliation, stack lifecycle, static tool catalog data, and provider-registry tests now live in focused modules instead of their former large mixed owners.
   - Model pull/execution/endpoint readiness now lives in `model_execution.py`; stack role normalization/policy checks live in `stack_roles.py`. Oversized model and profile/config test owners are split into focused refresh, mutation, listing, lifecycle, config, and governance modules.
   - CI keeps the full Python 3.11 gate and validates contracts plus clean static-wheel installation on Python 3.12 and 3.13.
   - Split the large MVP test module into focused files by area so slow tests and ownership are easier to see. Start with behavior boundaries that already exist in code: profiles/config, providers/models, runtimes/execution, integrations/chat, MCP, machines/stacks, deployment, and CLI smoke coverage.
   - Shared test infrastructure now separates isolated profile/model materialization (`profile_fixtures.py`), recording process/HTTP fakes (`boundary_fakes.py`), and in-process CLI output capture (`cli_fixtures.py`). Continue migrating repeated local doubles when touching their owning suites.
   - Keep the full automated suite useful as a PR gate without letting local discovery caches or external-machine state dominate runtime.
   - Runtime progress timing is injectable for tests, eliminating a two-second sleep while retaining real threaded reporter coverage; synthetic hardware recommendation matrices no longer probe host GPU tools. Continue replacing repeated full-catalog enrichment with cached or single-pass helpers where behavior is unchanged.
   - `pytest-xdist` 3.8.0 is pinned for development. The full gate uses four workers with file-level scheduling after three clean parallel full-suite runs; `AIPLANE_TEST_WORKERS` can tune the count or select `0` for serial troubleshooting.
   - Keep quality intact: move tests and optimize fixtures, not assertions or behavioral coverage.

### Planned But Not Implemented

- Provider-specific production-ready Vagrant/Packer/OpenTofu/Terraform/Pulumi/Ansible/Dev Container modules and apply workflows.
- Custom VS Code extension or marketplace publishing.
- Full custom coding agent, agent orchestrator, autocomplete engine, inference runtime, or general model proxy.
- Direct agent-to-agent runtime execution inside `aiplane`; near-term support should be config, stack binding, policy, and export for established orchestrator frameworks.
- Broad cloud deployment apply for AKS/AWS/generic Kubernetes.
- Production-grade API gateway/auth management for shared endpoints.
- Native backend TTFT/token telemetry, representative cross-machine calibration, and broader consumption of artifact/launch evidence by pull, stack, replay, and lifecycle helpers.
- Node REST scheduling API and community benchmark exchange remain research decisions, not committed product surfaces.
- Arbitrary shell execution through MCP.

### Deferred / Non-Goals

- Replacing Continue, Cline, Cursor, Copilot, Codex CLI, Claude Code, Aider, or similar coding agents.
- Implementing model inference engines inside `aiplane`.
- Becoming a general model proxy competing with LiteLLM/OpenRouter-style tools.
- Hidden IDE policy bypasses or direct model edits without review.

#### Repository Safety Review Register

The prioritized July 2026 code-quality and safety findings are tracked in
[Code Quality and Safety Review — July 2026](code-quality-review-2026-07.md).
SEC-1 is implemented: `aiplane tool` no longer assumes approval; risky operations
require an interactive confirmation or explicit per-invocation `--yes`, while
read-only tools remain non-interactive.

Audit log reads are crash-tolerant: `audit tail` skips malformed/non-object JSONL
records, distinguishes a likely interrupted final append, returns the requested
number of recent valid events where available, and emits metadata-only recovery
warnings on stderr without exposing corrupt content.

SSH tunnel lifecycle state is now identity-safe and collision-resistant. Start saves
versioned atomic JSON containing the PID and captured process identity; status/stop
verify that identity, Linux termination uses `pidfd` when available, stale or reused
PIDs are never signalled, malformed state fails closed, and identity-capture failure
terminates the new unowned process without persisting state.


Configuration and state snapshots now use a shared atomic persistence boundary. Writes use same-directory fsynced temporary files followed by atomic replacement, while audit JSONL uses a serialized fsynced append. Cross-process advisory locks have a bounded deadline, nonblocking jittered polling, and reject nested persistence locks to avoid lock-order deadlocks; transactional YAML mutation preserves concurrent changes.

Audit hardening now minimizes recorded tool data and broadens secret sanitation for sensitive keys, command flags, common provider tokens, bearer values, and PEM material. Tool output, raw command arguments, and exception messages are not persisted or returned through MCP failure details.


SSH command planning now uses a shared strict network-input boundary. Tunnel and remote-profile plans reject option-like or malformed hosts/users, validate ports, accept only credential-free HTTP(S) endpoint URLs, render IPv6 forwarding safely, and shell-quote the remote `aiplane` command.


MCP stdio now fails closed for writes: the server defaults to read-only, operator startup must explicitly pass `--allow-writes`, and each actual mutation must also carry `confirm=true`. Blocked attempts never reach domain managers and are audited without raw payloads.

The CLI process boundary now redacts expected error text, suppresses unexpected exception details by default, handles broken pipes quietly, and returns 130 for interruption. `--debug` or `AIPLANE_DEBUG=true` is an explicit diagnostic opt-in and may expose sensitive local traceback context.


Platform behavior is now an explicit capability contract rather than scattered OS checks. Portable operations work independently of mutation helpers; native Ubuntu/Debian is the supported runtime-helper mutation path, and WSL is inspection-only for those helpers. Hardware discovery uses platform-specific read-only sources on Linux, macOS, and Windows and reports unresolved evidence when a source is unavailable; this does not broaden runtime-helper mutation support.

Model catalog persistence is isolated in `ModelCatalogStore`, provider reconciliation remains in `ModelRefreshCoordinator`, Azure retail pricing is an injectable HTTP service, and Azure CLI execution/redaction/timeouts are a separate adapter. Structural tests prevent those responsibilities returning to the large domain modules.

The external MVP/adoption review was evaluated against current code and recorded as [Product, Adoption, and Monetization Backlog — July 2026](project-plan.md#product-adoption-backlog), including services-first monetization and evidence gates for team/enterprise work.


DOC-1 is complete: public onboarding examples use concrete export targets, the empty README workflow heading is removed, and focused contract tests enforce concrete export commands, nonempty sections, and sequential workflow numbering.


Quickstart observability is implemented: `quickstart local-coding` updates one deterministic phase-status line on stderr while preserving machine-readable stdout. Public wording now leads with the environment-selection and reproducibility problem and defines the environment doctor as a read-only readiness diagnosis.


The positioning and default-help pass is complete. README, package metadata, user entrypoints, strategy, launch review, demo framing, and CLI help lead with the environment doctor and configuration compiler outcome. Top-level help groups all commands into Core workflow, Advanced and supporting, and Experimental tiers, prints one safe next command, and fails its contract test if a command is unclassified.


Standard no-clone installation and release automation are implemented. Versioned GitHub Release wheels are the declared evaluation channel; normal CI validates `pip`, `pipx`, and `uv tool` install/verify/upgrade-or-replace/uninstall lifecycles on Linux, macOS, and Windows. Tag builds must match package version, rebuild wheel and sdist, pass all installer checks, and only then create the release. Bare package-index commands remain deliberately undocumented as available until trusted publishing is enabled and verified.


README and package metadata now keep the environment-doctor/configuration-compiler wedge dominant throughout the page, not only in the opening. Broad parallel execution tracks and specialist feature inventories were replaced by a subordinate advanced/experimental maturity link; package keywords now emphasize environment diagnostics, configuration, and reproducibility. A final P0 public-surface consistency sweep remains explicitly scheduled after all numbered P0 work and the user demonstrations.


The P0 platform CI matrix is implemented. Every Ubuntu, macOS, and Windows packaging job runs the synthetic capability suite and a built-wheel portable workflow from clean temporary workspaces through pip, pipx, and uv. The smoke covers bootstrap, validation, hardware discovery, recommendation, policy, and offline deterministic export. Unsupported runtime mutations and Windows SSH lifecycle status/start/stop fail with `unsupported_platform` before helper execution, process spawn, or state access; tunnel planning remains portable.


P0.9 practical threat modeling is complete. The tracked model covers credential references, redaction and debug limits, generated-config disclosure, external helper boundaries, two-stage MCP write guards, identity-safe tunnel ownership, unsigned profile trust, and local audit sensitivity. Every control row cites deterministic regression tests and every row states its residual limitation. Focused security validation passes 62 tests.

An interim P0 README/documentation consistency sweep followed items 8-9. It corrected quickstart's stale “three next commands” wording to its tested one-action contract, removed remaining positive “control plane” positioning from user/project entrypoints, aligned help and strategy with the narrow product promise, and corrected the P0 range after converting item 10 into an unnumbered gate. This is not the final gate result: repeat the sweep after the three user demonstrations. Focused consistency gate: 76 passed; full suite: 449 passed.

The public demo plan is now a bounded three-video onboarding set: local Ollama readiness/export, local-only policy plus YAML backup/restore and deterministic replay, and laptop-to-existing-remote-GPU planning/export. Each section targets less than three minutes at normal speed, distinguishes template repair from restoration of user configuration, and keeps an advanced automation/MCP video deferred until user evidence justifies it.

The July test profile found one duplicated integration boundary: `test_packaging.py` built and installed a wheel, then launched the complete pip install/reinstall/uninstall verifier that CI and release workflows already run independently. Removing only that nested lifecycle reduced the packaging test from 25.45s to 8.69s and the four-worker full suite from 37.04s to 20.26s, with all 450 tests passing. Six workers measured 17.78s locally but remain opt-in to avoid oversubscribing shared runners.

The latest external dev/mvp_0.5 review is evaluated in `docs/project/reviews/dev-mvp-0.5-latest-review-evaluation.md`. The numbered P0 backlog is replaced with the remaining release/adoption work: adoption-cut hierarchy, first public artifact, no-clone public verification, mandatory release-path CI, standardized trial evidence, a breadth freeze, and portable review provenance. The two unnumbered P0 completion gates remain open. Drift moves to the front of P1, and schema tightening is explicitly evidence-led.

Cross-platform install verification now uses an OS-neutral relative synthetic model ID for Tier-1 exports. It always checks tunnel planning without mutation, checks runtime-helper rejection on macOS/Windows, and checks tunnel-lifecycle rejection only on Windows. macOS is never asked to start an SSH tunnel during install verification. Focused verifier/contracts/platform/packaging coverage passes 41 tests, and a rebuilt-wheel pip install/verify/reinstall/uninstall lifecycle passes locally.
P0.1 is complete: the public demo hierarchy now has one seven-command adoption cut, while privacy/replay and remote-GPU flows are explicitly validation recordings. P0.2 publication automation is hardened but remains open until a complete public GitHub Release has verified wheel/source/checksum assets; the release workflow now runs the full gate, generates preview notes, requires complete artifacts, verifies checksums, and post-verifies the published attachments.

P0.3-P0.6 local implementation is complete: clean-wheel lifecycle verification has a canonical evidence format; `CI / Release gate` aggregates quality, compatibility, and cross-OS install jobs; repository protection requirements are explicit; trial records have a deterministic sanitizer/shape validator; and the preview scope freeze has an exception contract. Public-artifact evidence, hosted ruleset activation, and independent-user trials remain maintainer/external actions.

Post-merge no-clone candidates are now automated: a successful protected `main` push builds a wheel only after `CI / Release gate`, verifies its SHA-256 manifest, writes commit/run provenance, and uploads a 30-day artifact named with package version plus the short version-commit SHA. This is prerelease test evidence, not the immutable public P0 release.

CI-owned versioning now uses the narrowly scoped `aiplane-versioning` GitHub App token, trusts loop suppression only for that event actor, rejects PR edits and non-increasing direct versions, serializes patch mutation, and retries from latest `main`. Patch tags retain validated Actions artifacts without automatic public publication; intentional minor/major tags publish complete wheel/source/checksum releases, and successful publication dispatches the nine-job public verification matrix. App installation, secret storage, hosted app proof, and main/tag ruleset activation remain maintainer actions documented in `repository-protection.md`.

Release-path hardening now serializes and retries CI-owned version mutation from latest `main`, rejects version changes in PRs while preserving authorized direct-main minor/major values, fails closed when PR association cannot be queried, and suppresses redundant bot-commit matrices. Publication requires and post-verifies complete assets; a nine-job published-release workflow produces sanitized Linux/macOS/Windows × pip/pipx/uv evidence. Exact hosted branch/tag ruleset steps are documented but must be enabled by a maintainer.

The local evaluator workflow now has one explicit install-to-execution runbook in
README and the public demo plan. It covers profile creation, current-machine
hardware discovery, provider refresh, alias/native-id review, promotion, runtime
and model preparation, Codex/Copilot host-client exports, and endpoint-backed chat. Model listing
now defaults to adjacent `ALIAS` and provider-native `MODEL` columns and supports
`--identity alias|model|both`, reducing the risk of passing a native model id to
commands that require a profile alias. This improves demo usability but does not
close the remaining P0 external gates: verified public release assets, hosted
ruleset activation, independent-user trials, and the final post-trial docs sweep.

The approved host-client export scope exception is implemented: Codex, Copilot CLI, and Copilot-in-VS-Code are Tier-1 v1 print-only targets with explicit API/capability checks, canonical cross-platform Copilot JSON, named Codex profiles, VS Code Custom Endpoint JSON, and synchronized primary-demo commands. Client installation, file mutation, and launching remain out of scope. Release promotion still requires current-client smoke evidence on local Ollama and one authenticated Responses-compatible gateway.

## Integration Roadmap

See also: [Strategy](strategy.md) and [Project Roadmap](project-plan.md#roadmap).

The product is an environment doctor and configuration compiler first. Integrations should attach
to the same profile, provider, model, runtime, endpoint, policy, tool, approval, and audit layers
instead of each integration inventing its own configuration.

### Target Direction

Prioritize **VS Code + Continue** first because it has the simplest config export
path, but keep the integration layer generic. Add Cline, Zed, Aider, Cursor, and
JetBrains paths where they can consume OpenAI-compatible endpoints, MCP config,
or a small launch wrapper. Avoid spending too much effort on a custom always-on
chat UI before the provider/session contracts are stable.

### Recommended Order and Status

1. **Configuration exporters for existing tools - Implemented / ongoing**
   - Implemented: Continue, Cline, Zed, Aider, generic OpenAI-compatible, Codex, Copilot CLI, and Copilot-in-VS-Code endpoint exports.
   - Implemented: VS Code MCP, Continue MCP, Cline-style MCP, and generic MCP config exports.
   - Ongoing: validate more client-specific config shapes as tools evolve.

2. **CLI wrapper commands - Implemented / hardening**
   - Implemented: `aiplane chat`, which resolves a chat-capable profile alias and uses configured endpoints by default; `--native-ollama` delegates Ollama-runnable aliases to `ollama run <model>`.
   - Implemented: `aiplane launch --tool continue`, `aiplane launch --tool ollama`, and `aiplane launch --tool aider` wrappers for selected profile entries, provider/runtime constraints, and policy checks.
   - Implemented: `aiplane session start` for minimal session metadata/audit records, transcript path defaults, and handoff-friendly state.
   - Planned: wrappers for Codex/Cursor/Claude Code or other stable CLIs where support is explicit.

3. **Thin `aiplane session` layer - Implemented / hardening**
   - Implemented as minimal handoff state in `session start` records: selected model, launch command, transcript path, and local audit event.
   - Do not build a full Copilot/Codex clone.
   - Prefer delegating interactive chat to mature provider or IDE tools when they exist

4. **Patch proposal workflow - Planned**
   - Not implemented as a general workflow yet.
   - Intended behavior: generate diffs, validate/show patches, and apply only with approval.

5. **Local HTTP/API adapter - Planned**
   - Not implemented yet.
   - The MCP stdio server is implemented and should remain the first structured tool surface.
   - A local HTTP service should only be added if multiple clients need it.

6. **Agent-to-agent setup and export - Implemented configuration foundation / live validation ongoing**
   - Implemented today: orchestrator catalog/readiness, package/setup scaffolding, stack binding, schema-linked secret-free agent manifests, and framework-specific topology/readiness starter exports.
   - Role bindings describe model aliases/native ids, managed or self-managed endpoints, tool policies, approval modes, limits, audit labels, and credential references without secret values.
   - Export starter configuration for established orchestrator frameworks; live framework-version validation is ongoing, and autonomous agent execution remains outside `aiplane`.
   - Managed-service models are valid endpoint choices for this layer when the orchestrator can call them directly; they should not be treated as local runtime candidates.

### Integration Matrix

`aiplane` should integrate with mature tools at the lowest useful level. It
should generate config, run readiness checks, call official CLIs, and export
starter artifacts. It should not reimplement IDE agents, infrastructure
provisioners, model runtimes, or configuration-management engines.

| Tool / family | Planned use in `aiplane` | Integration level | Status |
| --- | --- | --- | --- |
| Continue | First VS Code coding assistant path; consume local or remote OpenAI-compatible endpoints and optional MCP tools. | Config export, setup plan, MCP config export. | Implemented / hardening. |
| VS Code MCP clients | Let IDEs query `aiplane` for models, hardware, recommendations, integration snippets, and guarded profile changes. | MCP stdio server plus client config export. | Implemented / hardening. |
| Cline / Roo-style clients | Alternative VS Code agent surfaces that can use endpoints and MCP tools. | Config export and MCP config export; wrappers only after stable CLI/API review. | Export implemented; wrappers planned. |
| Zed | Editor path for OpenAI-compatible endpoints and MCP-capable workflows. | Config export first. | Implemented / needs end-to-end validation. |
| Aider | CLI pair-programming path against selected model endpoints. | Config/export first; launch wrapper now implemented and hardening is underway. | Export implemented; launch/session wrapper implemented. |
| Cursor / Windsurf | Commercial IDE paths where custom endpoint or MCP support is available. | Research, config export where supported, no brittle plugin assumptions. | Research/planned. |
| Codex CLI / Claude Code / Copilot-style tools | Existing agentic CLI or IDE tools. | Possible launch wrappers and environment/config handoff only. | Planned/research. |
| Ollama | Local/self-managed runtime and optional native CLI chat. | Install/update/start/stop/status/pull helpers; endpoint-backed `aiplane chat` by default, with `--native-ollama` delegating to `ollama run`. | Implemented for core flow. |
| vLLM / llama.cpp / TGI / LocalAI / LM Studio | Self-managed model serving runtimes. | Runtime catalog, setup helpers where practical, endpoint export, stack lifecycle planning. | Partial/ongoing. |
| LangGraph / CrewAI / AutoGen / OpenHands / Semantic Kernel / LlamaIndex Workflows | Agent/workflow orchestration frameworks on top of model endpoints. | Catalog/readiness, role-aware stack binding, secret-free agent manifests, and framework-specific render-only starters; no custom agent runner. | Implemented configuration foundation / live validation ongoing. |
| Docker / Compose | Reproducible local or VM-hosted runtime stacks. | Tool doctor/install hints, stack artifacts, Compose export, and native Docker Model Runner same-host lifecycle with explicit confirmation. | Implemented foundation / live validation ongoing. |
| Azure CLI | Account, quota, SKU, VM/AKS discovery, and guarded Azure operations. | Tool doctor/install helper, CLI wrapper, profile-driven planning/apply for narrow VM flows. | Partial/ongoing. |
| OpenTofu / Terraform | Repeatable VM/AKS infrastructure provisioning without reinventing IaC. | Generate variables/modules or starter plans, call official CLI, keep apply guarded. | Planned. |
| kubectl / Helm | AKS/Kubernetes runtime deployment and inspection. | Tool doctor/install helper, generated manifests/charts or value files, guarded apply later. | Planned. |
| SSH / OpenSSH | Remote workstation/VM access and local endpoint tunnels. | Tunnel plan/start/status/stop and stack access policy. | Implemented / hardening. |
| Ansible | Optional host configuration over SSH when shell scripts become too fragile. | Tool doctor/install helper and generated playbook hooks only if needed. | Research/planned. |

### Candidate IDEs and Tools

Initial candidates:

- **VS Code**: highest priority. It is the broadest target and Ollama documents
  VS Code under its launchable integrations.
- **Continue**: first concrete IDE integration target. Continue provides a VS
  Code extension, CLI, and JetBrains plugin, and its docs identify it as an
  open-source coding agent. We should generate Continue config from our provider
  catalog rather than asking users to hand-copy model settings.
- **Cline**: strong candidate after Continue. It has VS Code, terminal, JetBrains,
  MCP, and broad editor positioning, so it fits both endpoint export and MCP
  configuration.
- **Cursor**: target after Continue. Cursor is worth supporting, but the first
  path should be config/export or MCP-style integration rather than assuming it
  can use every local provider directly. We should verify the supported custom
  model/provider surface before writing a deep adapter.
- **JetBrains IDEs**: secondary target after the config/session contracts are
  stable. Continue has a JetBrains plugin path, but Continue itself recommends
  its CLI over the JetBrains plugin.
- **Zed**: useful local-model-friendly editor path with provider, gateway, local
  model, and MCP surfaces.
- **Aider**: CLI-first pair-programming target. Useful because it can consume
  Ollama and OpenAI-compatible endpoints.
- **Roo Code**: watch-list only unless a maintained successor is selected; its
  docs currently say the extension was shut down on May 15, 2026.
- **Codex CLI-like interface**: prefer wrapper/delegation first, not a large
  custom chat implementation.

### CLI Session Strategy - Implemented baseline

A full custom active chat/session UI is medium effort and easy to overbuild. The
better first implementation is a thin command layer. Current status:

```bash
# Implemented: endpoint-backed chat for configured chat-capable aliases.
aiplane chat --prompt "Say hello"

# Implemented: optional Ollama-native chat for configured Ollama-runnable aliases.
aiplane chat --native-ollama

# Implemented: thin launch/session wrappers and session handoff metadata:
aiplane launch --tool continue --model MODEL_ALIAS --dry-run
aiplane launch --tool ollama --app vscode --model MODEL_ALIAS
aiplane launch --tool aider --model MODEL_ALIAS
aiplane session start --tool continue --model MODEL_ALIAS
```

Future wrappers should:

- Resolve model aliases from `models.yaml`.
- Check provider readiness with `doctor` before launch.
- Export the needed environment variables or config snippets.
- Start the provider-native CLI/tool when available.
- Record audit/session metadata locally.

### Ollama CLI Chat and Launch

Ollama provides a native CLI chat flow:

```bash
ollama run text-generation:0.5b
```

It also has `ollama launch`, which can configure and launch supported external
applications. Ollama docs list supported launch integrations including OpenCode,
Claude Code, Codex, VS Code, and Droid. That makes Ollama a good first provider
for wrapper commands because `aiplane` can select the configured model and then
delegate the interactive UX to Ollama.

### Decision and Current Status

Start with:

1. Continue config generation for VS Code. - **Implemented**
2. `aiplane chat` endpoint-backed smoke chat, plus `--native-ollama` for `ollama run`. - **Implemented for configured chat-capable aliases; native Ollama path is opt-in**
3. `aiplane launch` wrapper for supported tools (currently `continue`, `ollama`, `aider`). - **Implemented**
4. Cline/Zed/Aider exporter or wrapper research against their documented endpoint/MCP/config surfaces. - **Exporters implemented; wrappers still planned/research**
5. Minimal session metadata/audit around those launches. - **Implemented (thin session records + audit)**
6. Agent-to-agent role metadata and orchestrator config export for established frameworks. - **Partial scaffolding implemented; multi-role schema/export planned next**
7. Cursor research/config-export path after the generic endpoint/MCP exporters are stable. - **Research/planned**

Do **not** start by building a heavy custom chat UI. Use existing CLI/IDE tools
where they are good, and let `aiplane` own configuration, provider selection,
policy, setup, readiness, and audit.

### Non-Goals for the First Integration Milestone

- No direct file mutation by models without patch review.
- No IDE-specific hidden policy bypass.
- No separate provider/model configuration inside each IDE adapter.
- No direct autonomous agent-to-agent execution inside `aiplane`; use established orchestrator frameworks and export/review their config.
- No cloud escalation until policy, secret scanning, and audit behavior are
  explicit for that profile.

## Product Adoption Backlog

This backlog incorporates the original product/adoption review and the tracked [dev/mvp_0.5 latest-review evaluation](reviews/dev-mvp-0.5-latest-review-evaluation.md). It is the persistent priority list; do not rerun the whole analysis merely to recover decisions.

### Evaluation

The review identifies the right primary product: an AI environment doctor and configuration compiler for reproducible local and hybrid development. Its scope warning is well founded. The code already has disciplined boundaries, a decomposed CLI, atomic persistence, guarded MCP writes, sanitized errors, synthetic external-I/O tests, and explicit advanced-command categorization, so recommendations that assume those are absent are now stale.

Accepted recommendations:

- lead with discovery, doctor, recommendation, deterministic export, profiles, provenance, compatibility, and drift;
- freeze breadth until installation/onboarding and external beta evidence are credible;
- publish normal package installation, a platform matrix, profile schema/versioning, stable doctor/export contracts, adapter tiers, clean-machine demonstrations, and a threat model;
- keep advanced runtime, stack, agent, benchmark, orchestration, deployment, and MCP mutation surfaces subordinate and explicitly maintained;
- keep the useful individual/local core open and validate services before central software monetization.

Accepted with modification:

- do not delete advanced code merely to simplify marketing; retain it behind advanced/experimental status while it has tests and a clear owner, then remove only on evidence of maintenance cost without use;
- do not promise identical hardware discovery on every OS. Promise portable profile/doctor/export behavior and report platform-specific probe coverage explicitly;
- do not add telemetry by default. Use opt-in telemetry or structured beta reports with a documented privacy contract;
- profile migration/backward compatibility begins when the first public schema version is declared; the project is still pre-stable and should not preserve accidental interfaces.

Rejected or gated:

- a general AI control plane, hosted model gateway, inference resale, GPU marketplace, proprietary runtime, coding agent, broad infrastructure service, and secret store remain outside the product boundary;
- central registry, fleet inventory, organization policy, approvals, signed profiles, SSO/SCIM, SIEM, and long-retention audit are commercial discovery targets, not near-term implementation commitments;
- market-size and competitor claims in the review need current external validation before they drive engineering decisions.

### Prioritized Engineering and Adoption Backlog

#### P0 — Developer preview coherence

1. **Separate the primary adoption cut from validation workflows — completed.** Keep one public introduction under three minutes and limited to `quickstart --dry-run`, `discover`, `doctor`, `recommend`, and `export continue`. Retain local-only/replay and remote-GPU recordings as P0 validation workflows, not co-equal introductory product stories. Completion: the plan, recording titles, narration, and public links preserve that hierarchy; advanced commands do not enter the adoption cut.
2. **Publish the first complete developer-preview release artifact — selective publication automation implemented; hosted app proof and complete public assets pending.** A dedicated short-lived GitHub App token owns patch commits/tags, PR version edits and non-increasing versions are rejected, patches remain CI artifacts unless manually selected, and intentional minor/major versions publish automatically with complete wheel/source/checksum validation. Completion: a public immutable release URL contains exactly one wheel, one source distribution, `SHA256SUMS`, supported-platform/upgrade/rollback guidance, and metadata matching its tag.
3. **Verify the public no-clone path — cross-platform workflow implemented and automatically dispatched after publication; successful public run pending.** `Verify published release` downloads the actual named release on Linux, macOS, and Windows, verifies the portable manifest, exercises pip/pipx/uv independently, and uploads canonical sanitized evidence. Final evidence still requires a complete P0.2 release and a successful hosted run. Completion: the nine evidence records identify release URL, checksum, tag commit, commands, results, and platform limitations.
4. **Make CI mandatory on the release path — repository implementation and exact settings guide complete; hosted app proof and ruleset activation pending.** The PR UI shows `CI / Release gate` while the ruleset requires the exact job name `Release gate`; the guide covers reviews, main-only force/deletion protection, the narrow `aiplane-versioning` bypass, tag immutability, and audit commands. Completion still requires an active hosted ruleset and a blocked-merge test.
5. **Standardize external-trial evidence — standard implemented; trial adoption pending.** The canonical JSON template, recording guidance, sanitizer/shape validator, and regression tests cover one sanitized record format for commit/version, OS, installation channel, Python/runtime/model, start state, commands, elapsed time, first failure, assistance, written files, final outcome, and participant feedback. Completion: every P0 workflow trial uses the same record and distinguishes rehearsal from independent completion.
6. **Freeze public breadth through the preview gate — completed.** The tracked freeze defines the allowed core promise, permitted maintenance work, and a six-part exception decision. Add no new public integration, runner, orchestrator, stack, benchmark, deployment, or MCP-write promise before the P0 gates close. Fix blockers and contract defects; keep tested advanced surfaces subordinate. Completion: any exception requires an explicit scope decision in strategy, roadmap, and command coverage.
7. **Keep review provenance portable — completed.** The maintainer-local review path is replaced by a tracked [evaluation and decision record](reviews/dev-mvp-0.5-latest-review-evaluation.md) that states accepted, modified, stale, and deferred recommendations.

**P0 completion gate.** P0 closes only when both gate requirements pass:

- **Three reproducible demonstrations:** Local Ollama coding, laptop-to-remote-GPU, and local-only/privacy-policy workflows. Completion: independent users reproduce each from a clean environment.
- **Final README and documentation consistency sweep:** Re-read README, package metadata, top-level and core-command help, user documentation entrypoints, examples, strategy, launch review, and roadmap after all numbered P0 work is complete. Remove stale breadth, maturity drift, duplicated guidance, and any claim not backed by a tested workflow. Completion: one coherent product promise, command hierarchy, installation path, and maturity statement across every public entrypoint. Re-run public example, link, help, and contract checks after the sweep. This sweep was run once after the earlier implementation milestones and must be repeated after the user-testing demonstrations; the interim pass does not close this gate. Interim focused documentation/help/schema/export/packaging gate: 76 passed; full suite: 449 passed.

#### P1 — Prove repeated value

8. **Completed implementation — portable replay, multi-client verification, comparison, and drift.** Implement safe portable-profile backup/replay, aggregate verification of at least two distinct client-produced archives, profile comparison, and current-environment drift detection with deterministic provenance-aware explanations. Define an explicit inclusion/exclusion manifest; classify destinations as exact, capability-equivalent, materially incompatible, or unresolved based on reviewed model/runtime/policy requirements; and validate identical VMs, near-equivalent hardware, and an incompatible machine. Do not copy credentials, model weights, caches, audit/tunnel state, or runtime-owned data, and do not turn replay into broad host/cloud apply.
9. Run the six clean-environment trials defined by the public demo plan and record failures by stage.
10. Recruit external design partners, targeting ten unaided successful onboardings before public beta.
11. Measure opt-in activation and recurrence: first useful export, second integration, profile replay, seven/thirty-day return, and support points.
12. **Completed implementation — recommendation-critical schema hardening.** Tighten detailed profile-schema contracts from observed validation and ranking failure modes without making speculative fields rigid. Model aliases now require usable provider/native IDs; optional boolean, resource, and list fields have explicit types; recommendation thresholds are ordered; explicit null defaults remain valid; and every failure includes a canonical path and remediation. Continue using physical trial evidence for future compatible refinements.
13. **Completed implementation — secret-free draft import.** integrations import continue|aider PATH --as PROFILE previews by default, creates only a new unapproved profile with --yes, preserves environment-variable credential references, omits literal credentials, and never overwrites a profile.
14. **Completed implementation — versioned support declarations.** support list/show publishes provider, runtime, and client tiers, capabilities, limitations, ownership, and maintenance policy under contract version 1.0. Unverified upstream versions remain empty rather than becoming compatibility claims.
15. **Completed implementation — contributor adapter contract.** The versioned Python protocol, JSON Schema, reusable fixture, secret-field rejection, provenance requirements, and CLI validation command define a narrow catalog-result boundary without loading arbitrary contributor code.
16. **Completed implementation — pre-1.0 release hardening.** Tracked changelog notes render deterministically into each release; wheel and source distributions receive a verified SHA-256 manifest plus signed GitHub build-provenance attestation; pip, pipx, and uv lifecycle verification, upgrade guidance, and rollback instructions are maintained. Hosted publication evidence remains part of the separate P0 release gate.
17. **Completed implementation — shared evidence contract.** Discover, doctor, recommend, profile show, and integration export planning now use one versioned source-state, sample-count, evidence-state, and uncertainty shape. Configured catalog scores remain explicitly distinct from measured task-quality evidence.
18. Decide the public future of stacks through observed user tests; simplify, keep advanced, or remove from the public model based on evidence.

#### P2 — Differentiated core after adoption evidence

19. Build evidence-backed model placement after the P0 gate and initial P1 trial evidence. Define versioned model-variant, placement-evidence, YAML/canonical-JSON benchmark-suite, artifact-lock, and external-runner-launch schemas; resolve quantization, format, total/active parameters, configured context, KV-cache assumptions, memory pool, execution/offload mode, headroom, and usable context before ranking; standardize repeated throughput/TTFT/latency/token and stochastic task-quality measurements with decoding settings, robust summaries, uncertainty, runtime settings, and privacy-conscious environment fingerprints; calibrate only from comparable local evidence; keep task-quality, placement, performance, and policy separate; support evidence-backed role-routing comparisons with alternatives; expose source, confidence, sample count, uncertainty, and near-miss remedies; and preserve deterministic behavior when measurements are absent. Record separate go/no-go research decisions for node REST scheduling and community benchmark exchange. Do not promote this work into the primary onboarding cut until the breadth freeze closes.
20. **Completed implementation; cross-platform field evidence pending — Docker Model Runner and Kubernetes rendering.** Docker Model Runner is a first-class runtime/source/provider with its official host endpoint, JSON status/inventory, native OCI model ids, inspect/benchmark commands, and preview-first guarded lifecycle. stacks render-kubernetes deterministically emits ResourceClaim, Deployment, Service, and Helm values; it never writes or applies resources and requires explicit image/device-class inputs. This host lacks the Docker model command, so supported-platform live evidence remains open. Keep Kubernetes apply and node scheduling REST deferred pending reviewed design and demonstrated demand.
21. **Completed implementation — remote-workstation multi-client replay contract.** The documented workflow restores and validates the approved profile independently, runs client-local drift/doctor/export checks, re-archives each result, and uses read-only `profiles replay-check` to verify at least two distinct client archives together. Deterministic two-client tests prove exact replay and byte-stable supported exports; actual participant/machine recordings remain under the P1 field-evidence gate rather than being fabricated.
22. Keep policy local and small: allow, warn, approval-required, and block, consistently enforced across CLI, doctor, recommendation, export, and MCP.
23. Maintain a neutral, versioned compatibility knowledge base separable from shell execution.
24. Create a maintenance budget for advanced/experimental surfaces and archive those without use or ownership.
25. **Completed implementation — materialized model catalog and indexed queries.** Refresh generates an ignored, atomic, versioned enriched catalog derived from profile YAML, discovery data, and latest benchmark summaries. Queries cover aliases, provider-native IDs, providers, sources, runtimes/runners, roles, ownership, capabilities, parameter ranges, popularity, benchmark evidence, hardware requirements, and safe exact properties. Digest/version invalidation, corruption fallback, optional bypass/rebuild controls, indexed/full-scan equivalence tests, and opt-in synthetic 1k/10k/100k timing coverage are complete.

### Monetization Validation Track

#### M0 — Services now, without weakening open source

- Package a fixed-scope “Local and Hybrid AI Development Environment Standardisation” engagement: inventory, compatibility report, approved profiles, Continue/Aider exports, remote endpoint plan, repository privacy policy, CI doctor checks, team documentation, and up to two adapters.
- Validate pricing through real proposals and paid discovery, not generic SaaS benchmarks.
- Track whether customers pay for repeatability/governance or only installation help; this determines product direction.
- Keep discovery, profiles, validation, doctor, recommendation, deterministic exports, drift, basic local policy/audit, and community adapters fully useful in open source.

#### M1 — Paid team prototype, gated

Start only after two organizations replay approved profiles across at least three machines and request paid central governance. Candidate scope: central profile registry/history/promotion, shared templates/policy, approvals, fleet/drift reporting, central audit, signed profiles, and integration compatibility management.

Go gate: two paid pilots or signed intent, named budget owners, recurring governance need, and delivery without becoming a gateway or infrastructure platform.

#### M2 — Enterprise, later and evidence-led

Potential self-hosted registry/control service, SSO, SCIM, SIEM export, air-gapped updates, signed policy/profile bundles, retention, compliance evidence, private adapters, and support agreements. None is scheduled until M1 proves demand.

### Product Metrics and Decision Gates

North star: approved profiles successfully replayed on more than one machine and used by more than one external integration.

Developer-preview exit: standard install works; five unaided external users complete the main workflow; one integration is verified on Linux, macOS, and Windows; doctor/export contracts are stable; docs match behavior; no critical unsafe mutation or secret leak is open.

Team-product gate: two teams use the same approved setup across at least three machines, use drift in practice, and explicitly request shared policy, approval, registry, or audit.

Decision outcomes:

- activation plus replay/return supports the profile/compiler thesis;
- activation without return suggests a setup/service product unless drift and CI create recurrence;
- policy/audit demand supports a governance commercial wedge;
- consultancy-only demand supports a professional delivery accelerator;
- installation failures mean market conclusions are premature;
- no cross-tool value means narrow to diagnostics/compatibility or stop broad investment.

## Developer-Preview Scope Freeze

Until the P0 gates close, the public promise remains the profile-driven environment doctor and configuration compiler workflow: quickstart preview, discovery, doctor, recommendation, policy explanation, and deterministic Tier-1 export.

No new integration, runner, orchestrator, stack, benchmark, deployment, MCP-write capability, or other advanced command may be promoted into README onboarding, package metadata, the primary demo, or the Core command category during this freeze. Existing tested advanced and experimental surfaces may receive security, correctness, compatibility, maintainability, and contract fixes.

### Exception process

An exception requires one tracked decision before implementation or promotion. It must state:

1. the observed external-user blocker or release defect;
2. why the existing core workflow cannot solve it;
3. the precise new public promise and affected commands;
4. security, platform, maintenance, documentation, and test costs;
5. success and removal criteria;
6. synchronized changes to strategy, roadmap, command coverage, help, and public documentation.

Convenience, speculative market breadth, or the existence of advanced code is not evidence for an exception. Without the decision record, the feature remains subordinate and must not enter the public adoption story.

Approved exceptions:

- [Host-client model exports](host-client-export-scope-exception.md) - Codex, Copilot CLI, and Copilot-in-VS-Code deterministic print-only exports.

## P0 Maintainer Checklist

This checklist contains actions that require GitHub administration, public publication, or independent participants.

### 1. Install and prove the versioning identity

Follow [Repository Protection](repository-protection.md).

- [ ] Create and install the private `aiplane-versioning` GitHub App only on this repository.
- [ ] Grant only Contents read/write and Metadata read-only; disable webhooks.
- [ ] Store `AIPLANE_VERSIONING_APP_ID` as an Actions repository variable.
- [ ] Store the complete PEM as the `AIPLANE_VERSIONING_APP_PRIVATE_KEY` Actions repository secret.
- [ ] Merge the app-token workflow before activating protection.
- [ ] Confirm an ordinary merge is patched and tagged by `aiplane-versioning[bot]`.
- [ ] Confirm the patch tag runs the release workflow but does not create a public release.

### 2. Activate repository protection

- [ ] Activate the `main`-only branch ruleset.
- [ ] Require the exact status-check value `Release gate` and an up-to-date branch.
- [ ] Require PRs, conversation resolution, stale-review dismissal, and one approval when another reviewer exists.
- [ ] Restrict updates, force pushes, and deletion of `main`.
- [ ] Add only repository administrators and `aiplane-versioning` to bypass.
- [ ] Activate immutable `v*` tag rules with the same narrow bypass.
- [ ] Prove a pending/failing gate or missing review blocks a non-bypass merge.
- [ ] Save the ruleset URL or screenshot in private evidence.

Read-only confirmation:

```bash
gh api repos/ocagdas/aiplane/branches/main/protection
gh api repos/ocagdas/aiplane/rulesets --jq '.[] | {id, name, target, enforcement}'
```

### 3. Publish one complete developer-preview release

For an intentional minor or major release, follow [CI and Release Process](ci-and-release-process.md); publication should start automatically after the app creates the tag. A selected patch may instead be published through **Actions -> Release artifacts -> Run workflow**.

Confirm the release visibly contains:

- [ ] exactly one `aiplane-VERSION-py3-none-any.whl`;
- [ ] exactly one `aiplane-VERSION.tar.gz`;
- [ ] `SHA256SUMS`;
- [ ] metadata matching the immutable tag;
- [ ] platform, upgrade, uninstall, and rollback guidance.

Do not count an empty release page and never replace assets under an existing version.

### 4. Verify actual public assets

Publication dispatches **Verify published release** automatically; it may also be run manually.

- [ ] All nine Linux/macOS/Windows x pip/pipx/uv jobs passed.
- [ ] Every job downloaded public assets rather than rebuilding source.
- [ ] Every manifest and install/replacement/uninstall lifecycle passed.
- [ ] Evidence identifies the same URL, tag commit, version, and wheel digest.
- [ ] Evidence contains no private data and reflects documented platform limitations.

### 5. Run independent demonstrations

Give participants only the installed artifact and the relevant [Public Demo Plan](project-plan.md#public-demo-plan) section. Record first failures and assistance honestly, sanitize every record, and validate it:

```bash
python scripts/validate_trial_evidence.py PATH_TO_RECORD.json
```

Required outcomes:

- [ ] primary local adoption flow reproduced;
- [ ] local-only policy plus backup/restore replay reproduced;
- [ ] existing remote-GPU import/plan/export flow reproduced;
- [ ] participants understand written files and export boundaries.

### 6. Trigger the final documentation gate

Only after public verification and independent demonstrations:

- [ ] compare README, metadata, help, user docs, and demos;
- [ ] remove unsupported claims and maturity drift;
- [ ] run public example, link, help, contract, packaging, and full test gates;
- [ ] update the P0 backlog with evidence paths and final counts.

## External Trial Evidence

Use the [Field Evidence Collection Runbook](../user/evidence-collection.md) for the copy-paste capture procedure. Use one sanitized JSON record for every P0 workflow rehearsal and independent-user trial. Copy [`trial-evidence/template.json`](trial-evidence/template.json), fill every field, and validate it before sharing:

```bash
python scripts/validate_trial_evidence.py path/to/trial.json
```

The record separates `rehearsal` from `independent` evidence. A maintainer rehearsal can verify commands and timing, but it cannot close the independent-user gate.

### Recording rules

- Use a pseudonymous trial ID; never record names, email addresses, organizations, personal paths, private hosts, tenants, subscriptions, account IDs, credentials, or tokens.
- Identify the immutable release URL, package version, SHA-256, and full source commit. An unpublished rehearsal may use `null` for the URL, but cannot count as published-release evidence.
- Record OS/version/architecture, Python, installation owner, runtime/model, clean start state, and whether a checkout was present.
- Record commands in order with elapsed seconds, exit status, outcome, and relative written paths.
- Record the first failure once with its stage, command index, category, and sanitized summary. Use `null` when nothing failed.
- State whether assistance exceeded the written workflow, whether written files and non-mutating export were understood, and concise sanitized feedback.
- Set every sanitization assertion only after human review. Automated validation is an additional guard, not a substitute.

Allowed workflows are `primary-adoption`, `local-only-replay`, `remote-gpu`, and `no-clone-install`. A demonstration counts only when classification is `independent`, completion is true, clean-start facts are accurate, and the published immutable artifact is referenced. Keep failed and assisted trials: they are evidence, not discarded attempts.

Store records outside the repository until publication consent is established. Sanitized records approved for tracking belong under `docs/project/trial-evidence/records/`.

## Public Launch Review

This is the release-readiness checklist for the initial public version and later public updates.

### Scope

`aiplane` should present itself first as an environment doctor and configuration compiler for reproducible local and hybrid AI development environments. It should not claim to be a coding agent, model runtime, model proxy, marketplace, or production LLM gateway.

### Terminology

Use these terms consistently:

- **Provider / model source / catalog**: where model ids, files, or deployments come from. Examples: Ollama library, Hugging Face Hub, GGUF files, OpenAI, Anthropic, Azure OpenAI.
- **Runtime**: software that loads model weights or serves inference. Examples: Ollama, vLLM, TGI, llama.cpp server, LocalAI, Transformers, LM Studio.
- **Runtime endpoint**: the URL exposed by a runtime, often OpenAI-compatible `/v1`.
- **Model**: a profile-approved alias mapped to a source-native model id or deployment plus metadata.
- **Profile**: editable YAML configuration for one workflow or machine context.
- **Machine**: normalized hardware/OS/runtime capacity description.
- **Stack**: operational binding of machine, runtime, primary model, optional orchestrator, and access policy.
- **Target**: deployment/access target such as Azure VM, AKS, Docker host, or SSH tunnel plan.
- **Integration export**: generated config text for an IDE/CLI. It does not edit the target tool.
- **MCP adapter**: stdio tool surface for structured `aiplane` inspection and guarded mutations.
- **Doctor**: readiness check for profiles, tools, providers, runtimes, models, machines, or stacks.

### Public Quality Gate

Before calling a public release or beta ready, the visible project state should be internally consistent: code behavior, README claims, user docs, roadmap status, command coverage, session handoff, examples, and tests should describe the same product. New features should have focused tests or an explicit documented reason they are smoke-only, and broad future work should stay in roadmap sections rather than being implied as current capability.

### Pre-Release Checks

- Run `aiplane environment doctor` and confirm the setup summary is understandable; text is the default output and `--format json` is only for machine-readable checks.
- Run `aiplane profiles validate local-dev`.
- Run representative smoke commands for profiles, providers, runtimes, integrations, and stacks.
- Run the full test suite.
- Confirm `.aiplane/`, logs, PID files, caches, editor swap files, and generated runtime state are ignored or absent.
- Confirm `pyproject.toml` has a public-safe description, readme, license, build backend, package discovery, and a version matching the proposed `vVERSION` tag.
- Build the wheel and source distribution, then run `python scripts/verify_install_channels.py dist` before publishing artifacts.
- Confirm normal CI validates wheel lifecycles through `pip`, `pipx`, and `uv tool` on Linux, macOS, and Windows.
- Confirm `.aiplane/` and generated model caches are not tracked.
- Confirm `docs/user/tools.md` maps each external tool to the workflows it enables.
- Confirm `docs/project/agent-guidance.md` and tool-specific instruction files point to the current project guidance.
- Scan README and user docs for stale command examples and terminology drift.

### Known Public-Launch Caveats

- The project is developer-preview, pre-1.0 alpha quality and should be marked that way.
- Broad cloud and Kubernetes apply paths remain guarded or planned.
- Runtime helpers delegate to native runtimes and official CLIs where possible; deep runtime tuning remains runtime-native.
- MCP write tools must remain narrow, audited, and guarded.

## Public Demo Plan

This plan presents `aiplane` as it exists in the developer preview: it inventories AI development capabilities, diagnoses readiness, matches reviewed models to their purpose and available hardware, and compiles reproducible tool configuration. This read-only diagnosis is its environment doctor role.

The public story is deliberately narrow. `aiplane` turns environment facts and reviewed YAML profiles into readiness findings, hardware-aware recommendations, and deterministic configuration exports. It does not become a model runtime, coding agent, IDE extension, secret manager, or hidden cloud deployment system.

Terminology used throughout: the editable profile YAML is the backup/replay source of truth; `profiles render` prints a consistently ordered JSON snapshot for validation, comparison, CI, or archival evidence and cannot restore the YAML; `export` compiles profile choices into another tool's configuration syntax and prints it without editing that tool. A replay restores reviewed YAML and evaluates the destination before producing fresh exports.

### End-to-end local Ollama evaluator runbook

The three-minute adoption cut below intentionally starts from a prepared runtime so
it can demonstrate the read-only product promise. Before recording—or when an
evaluator wants to prove the runnable path—use this complete sequence. It separates
profile creation, live hardware inspection, online catalog discovery, alias
curation, runtime/model preparation, configuration export, and endpoint execution.
The example wheel version is illustrative.

```bash
# Install into an isolated application environment and enter a disposable workspace.
uv tool install ./aiplane-0.1.0-py3-none-any.whl
aiplane --version
mkdir aiplane-demo
cd aiplane-demo

# Create editable profile YAML without hiding hardware or catalog discovery inside bootstrap.
aiplane profiles bootstrap-local --no-overwrite --no-discovery --no-hardware-discovery
aiplane profiles validate local-dev
aiplane hardware discover

# Preview and populate the ignored discovery cache, then compare aliases with native model ids.
aiplane models refresh --provider ollama --query chat --limit 25 --dry-run
aiplane models refresh --provider ollama --query chat --limit 25
aiplane models list --provider ollama --runtime ollama --role chat --current-machine --sort-by role --limit 10 --format text
aiplane models list --provider ollama --runtime ollama --role chat --current-machine --sort-by role --limit 10 --identity alias

# Replace DISCOVERED_ALIAS with a reviewed ALIAS from the list and make it profile-owned.
aiplane models show DISCOVERED_ALIAS
aiplane models promote DISCOVERED_ALIAS --as local_chat --dry-run
aiplane models promote DISCOVERED_ALIAS --as local_chat
aiplane models use chat_model local_chat

# Preview and perform supported Ollama/model preparation, then verify runtime inventory.
aiplane integrations setup codex --model local_chat --runtime ollama --dry-run
aiplane integrations setup codex --model local_chat --runtime ollama
aiplane runtimes status ollama
aiplane runtimes list-runtime-models ollama

# Compile client configuration and run the small endpoint-backed chat smoke test.
aiplane export codex --model local_chat
aiplane export copilot-cli --model local_chat --format json --offline
aiplane export copilot-vscode --model local_chat
aiplane chat --model local_chat
```

The compact model table defaults to adjacent `ALIAS` and `MODEL` columns. Use
`--identity alias`, `--identity model`, or `--identity both` when a rehearsal needs
one identity or both explicitly. The three host-client exports print reviewed configuration, while `aiplane chat` talks to the prepared endpoint; none installs, launches, or edits Codex, Copilot CLI, or VS Code. This evaluator runbook is preparation evidence and
does not add commands to the bounded primary adoption cut.

### Recording hierarchy

#### Primary public adoption cut — one outcome in under three minutes

This is the one introductory product video. It contains exactly seven core commands—quickstart dry-run, discover, doctor, recommend, and three host-client exports—with no advanced command detours.

**Promise:** “Inspect this AI-development environment, understand readiness, choose a suitable configuration, and produce reviewed Codex, Copilot CLI, and Copilot-in-VS-Code configuration without hidden mutation.”

**Prepared state:** `aiplane` is installed from a release wheel in a clean workspace. Use a sanitized, rehearsed local Ollama profile so output is useful and deterministic; preparing the runtime/model is part of trial setup, not this public cut.

**Recording convention:** The quoted narration is the exact script to read. Do not read headings, command labels, or stage directions aloud. Type or paste the exact command, pause on the named output cue, then read the quotation at a normal pace. Keep terminal font and window size fixed so output does not reflow between rehearsals.

##### 0:00-0:25 — Preview without mutation

On screen: begin with an empty prompt, execute the command, let the `[quickstart]` status line show each phase, then hold on `next_action` and the dry-run/write metadata.

Exact command:

```bash
aiplane quickstart local-coding --dry-run
```

Narration:

> An AI coding setup must match model capabilities to the task, available RAM and VRAM, runtimes, endpoints, and development tools, then remain reproducible on another machine. Aiplane inventories those facts, diagnoses what is ready or missing—its doctor role—and compiles a reviewable profile and deterministic tool configuration. This dry-run previews the process without changing anything.

##### 0:25-0:55 — Inspect provenance

On screen: keep the summary visible and point once to detected, generated/discovered, user-supplied, and unresolved counts.

Exact command:

```bash
aiplane discover
```

Narration:

> Discovery inventories this environment and labels where configuration came from: detected machine facts, generated or discovered records, values supplied by my profile, and anything still unresolved.

##### 0:55-1:40 — Diagnose readiness

On screen: pause on one representative finding and its reason, impact, remediation, and mutation metadata.

Exact command:

```bash
aiplane doctor
```

Narration:

> Doctor turns that inventory into actionable findings. Each blocker or advisory identifies the affected resource, explains the impact, and gives a remediation while making any mutation or dry-run requirement explicit.

##### 1:40-2:10 — Choose a suitable configuration

On screen: hold on the recommended model/configuration and the hardware or policy reasons—not the full candidate list.

Exact command:

```bash
aiplane recommend
```

Narration:

> Recommendation combines reviewed profile policy with available hardware. This is a transparent compatibility recommendation, not a benchmark result or performance guarantee.

##### 2:10-2:50 — Compile host-client configuration

On screen: scroll only enough to show the model alias and endpoint fields, then return to the command prompt without saving the output.

Exact commands:

```bash
aiplane export codex --model local_chat
aiplane export copilot-cli --model local_chat --format json --offline
aiplane export copilot-vscode --model local_chat
```

Narration:

> Export compiles the same reviewed alias into host-specific Codex, Copilot CLI, and Copilot-in-VS-Code configuration. The alias remains visible beside the provider-native model id, and secret values are never printed. These commands do not install, launch, or edit the clients.

##### 2:50-3:00 — Close on the repeatable loop

On screen: leave the deterministic export visible and add a small overlay reading `profile → discover → doctor → recommend → export`.

Exact command: none; leave the export visible.

Narration:

> That is the repeatable loop: profile, discover, doctor, recommend, and export. Reviewable inputs produce reproducible configuration when the environment changes.

Do not show model pulls, chat/run/code commands, runtime lifecycle, MCP, stacks, orchestrators, deployment, benchmarks, or cloud discovery in this cut. Link advanced documentation below the video rather than adding another segment.

#### P0 workflow-validation recordings

These are evidence workflows for independent user testing, not co-equal introductory product videos.

| Recording | Validation outcome | Target |
| --- | --- | --- |
| Local-only replay | Enforce local-only policy, archive editable YAML, recover from damage, and prove deterministic replay. | 2:50 |
| Existing remote GPU | Capture/import a GPU workstation, rank placement, plan access, and export endpoint configuration. | 2:50 |

A successful internal rehearsal does not satisfy the P0 gate. Independent users must complete all three workflows: the local Ollama adoption flow above, local-only/privacy replay, and laptop-to-remote-GPU.

### Shared recording rules

- Start from an installed wheel, `pipx`, or `uv tool` installation; normal viewers should not need a repository clone.
- Use a disposable working directory and sanitized profile names, hosts, paths, endpoints, and model aliases.
- Rehearse every command from a fresh directory before recording.
- Run inspect, doctor, plan, export, or `--dry-run` before mutation.
- Never show credentials, environment-variable values, private hostnames, tenant/subscription IDs, personal paths, or raw audit logs.
- Explain which command writes files. Exports print text; they do not edit Continue, Aider, or IDE settings.
- Keep provider catalog access explicit. The default quickstart is offline-safe; `--discovery` opts into configured catalog communication.
- Use live model pulls or endpoint calls only on a prepared machine. Otherwise show the exact dry-run plan.
- Keep command output at default verbosity unless one field is the point of the shot.

Prepare a clean workspace:

```bash
mkdir aiplane-demo
cd aiplane-demo
aiplane --help
```

The installed CLI creates editable profiles relative to this workspace. Keep the demo workspace after each rehearsal until the recording has been reviewed.

### P0 validation recording 1 — Local-only policy, backup, restore, and deterministic replay

**Promise:** “Treat the setup as reviewable configuration: prove cloud use is blocked, archive it, recover it, and reproduce the same export.”

**Prepared state:** Start with the working `local-dev` profile from video 1. The profile and local config must contain no raw credentials. This video uses ordinary filesystem copies because `aiplane` does not claim to be a backup product.

#### 0:00-0:35 — Make policy visible

On screen: show the blocked cloud decision, allowed Ollama decision, and doctor summary; do not expose the policy file path.

Exact commands:

```bash
aiplane policy explain --action backend:cloud
aiplane policy explain --action provider:ollama
aiplane doctor
```

Use a rehearsed local-only repository policy whose output clearly blocks cloud escalation and allows the selected local provider.

Narration:

> Policy is profile-owned and inspectable. Doctor and policy explanation expose the decision before a model or endpoint is used.

#### 0:35-1:10 — Archive editable and canonical forms

On screen: paste commands one at a time and briefly show the backup filenames, not their potentially private contents.

Exact commands:

```bash
mkdir -p demo-backup
cp -a profiles/local-dev demo-backup/local-dev
aiplane profiles render local-dev > demo-backup/local-dev.profile.json
aiplane export continue > demo-backup/continue.before.yaml
```

Continue with these exact commands to include non-secret local CLI defaults:

```bash
aiplane config init --template local
aiplane config show
cp -a .aiplane/config.yaml demo-backup/config.yaml
```

Narration:

> The editable source is the directory of focused YAML files. Render produces one canonical, read-only JSON document for validation, comparison, or archival. Local CLI preferences are separate. Credentials and discovered caches are intentionally not part of this portable profile backup.

Before sharing any archive, review it for private endpoints, machine names, account aliases, or other operational metadata.

#### 1:10-1:45 — Demonstrate failure and template repair

On screen: hold on the missing-file validation error and the repair dry-run; make the `dry_run` state visible.

Exact commands; remove one file only after the backup exists:

```bash
mv profiles/local-dev/models.yaml profiles/local-dev/models.yaml.broken
aiplane profiles validate local-dev
aiplane profiles repair local-dev --file models.yaml --dry-run
```

Narration:

> Validation fails closed when a required profile file is missing. Repair can restore a missing structural file from the shipped template, but it cannot reconstruct user customizations. That is why the real profile backup matters.

Do not run repair without `--dry-run` in this sequence; restoring the blank template would not recover the reviewed model choices.

#### 1:45-2:30 — Restore and prove equivalence

On screen: keep both silent `cmp` commands and their zero exit status visible, followed by successful validation.

Exact commands:

```bash
cp demo-backup/local-dev/models.yaml profiles/local-dev/models.yaml
rm profiles/local-dev/models.yaml.broken
cp demo-backup/config.yaml .aiplane/config.yaml
aiplane profiles validate local-dev
aiplane profiles render local-dev > demo-backup/local-dev.restored.profile.json
aiplane export continue > demo-backup/continue.after.yaml
cmp demo-backup/local-dev.profile.json demo-backup/local-dev.restored.profile.json
cmp demo-backup/continue.before.yaml demo-backup/continue.after.yaml
```


Narration:

> Validation proves the references are coherent; byte-for-byte comparison proves the canonical profile and generated Continue configuration replay exactly. Runtime model weights and credentials remain machine-local and are restored through their owning tools, not copied in this YAML bundle.

#### 2:30-2:50 — Close with portability boundaries

On screen: show only the sanitized relative backup file list while the narration separates portable and machine-owned state.

Exact command:

```bash
find demo-backup -maxdepth 2 -type f -print
```

Narration:

> This backup contains the reviewed profile YAML, canonical render, optional non-secret local defaults, and generated integration text. Credentials, model weights, provider caches, audit logs, tunnel state, and machine-specific runtime data stay with the systems that own them.

This P0 recording proves lossless restoration and deterministic replay in one workspace. `profiles compare` and `profiles drift` now cover exact, capability-equivalent, materially incompatible, and unresolved destinations with deterministic synthetic fixtures; cross-machine field recordings remain an evidence task so hardware variance and material drift are demonstrated honestly.

### P0 validation recording 2 — Reuse the setup with an existing remote GPU workstation

**Promise:** “Describe a real GPU machine once, import that fact on a laptop, plan safe access, and compile client configuration without provisioning infrastructure.”

**Prepared state:** A sanitized existing GPU workstation is reachable through normal OpenSSH. Its runtime endpoint and model alias are already prepared. This demo does not create a VM, bypass SSH authentication, or copy credentials.

#### 0:00-0:40 — Capture the GPU machine

On screen: run on the workstation, then show the exported filename and successful profile validation—not raw private hardware identifiers.

Exact commands to run on the GPU workstation:

```bash
mkdir -p aiplane-machine-export
cd aiplane-machine-export
aiplane profiles bootstrap-local --no-discovery
aiplane hardware export-machine --name gpu-workstation --origin onprem > gpu-workstation.machine.yaml
aiplane profiles validate local-dev
```

Narration:

> Hardware export prints a normalized, reviewable machine description. It contains capacity facts, not runtime weights or SSH credentials. Review the file before transferring it.

Transfer `gpu-workstation.machine.yaml` through the team’s approved file-transfer path.

#### 0:40-1:20 — Import and rank on the laptop

On screen: switch clearly to the laptop terminal, show the imported machine summary, then hold on the ranked recommendation reasons.

Exact commands to run in the laptop demo workspace:

```bash
aiplane machines import gpu-workstation.machine.yaml
aiplane machines show gpu-workstation
aiplane machines recommend --workload inference_large --limit 3
```

Set the sanitized alias prepared in the laptop profile, then run the exact recommendation command:

```bash
REMOTE_MODEL="REHEARSED_REMOTE_ALIAS"
aiplane machines recommend --model "$REMOTE_MODEL" --limit 3
```

Narration:

> The machine, model alias, runtime, and endpoint remain separate facts. Recommendation explains placement; it does not start the remote service.

#### 1:20-2:05 — Plan access without opening it

On screen: emphasize `plan`, the local forwarded endpoint, and status. Do not run `tunnel start` during this segment.

Use a sanitized `ssh_tunnel` target already reviewed in `profiles/local-dev/targets.yaml`. Exact commands:

```bash
aiplane remote tunnel plan --target gpu_workstation_ssh
aiplane remote tunnel status --target gpu_workstation_ssh
```

Narration:

> Plan prints the OpenSSH local-forward command and resulting endpoint. It does not start a process. OpenSSH still owns host-key verification, authentication, and encryption; the remote service still owns application authentication.

If lifecycle support is unavailable on the recording platform, show the explicit `unsupported_platform` result and manage the planned command with the platform-native SSH client.

#### 2:05-2:40 — Compile endpoint configuration

On screen: hold on doctor readiness and sanitized endpoint/model fields in both exports; do not save or open an IDE.

Exact commands, with the tunnel or approved endpoint already running:

```bash
aiplane doctor
aiplane export openai-compatible --model "$REMOTE_MODEL" --endpoint http://127.0.0.1:8000/v1
aiplane export continue --chat "$REMOTE_MODEL"
```

Narration:

> The same laptop profile now compiles configuration for an existing remote runtime. Export still only prints reviewable text; it does not create the workstation, start the model server, edit the IDE, or weaken authentication.

#### 2:40-2:50 — Close

On screen: leave the sanitized Continue export visible and overlay `describe → diagnose → choose → plan → export`.

Exact command: none; leave the exported configuration visible.

Narration:

> Local or remote, the loop stays the same: describe, diagnose, choose, plan, and export deterministic configuration.

### Optional fourth video — hold until evidence supports it

Do not record this for the initial set. Candidate scope is “automation and integration contracts”:

- `aiplane profiles schema` and canonical JSON validation;
- Tier-1 Aider, OpenAI-compatible, and generic MCP exports;
- read-only MCP initialize/tools-list demonstration;
- JSON doctor output in CI;
- the security boundary: read-only defaults, explicit write enablement, per-call confirmation, and audit sensitivity.

The video should be approved only if user testing shows that it answers a recurring adoption question and can remain under three minutes without turning advanced features into the main product promise.

### Rehearsal checklist

Before each recording:

```bash
scripts/check.sh quick
aiplane profiles validate local-dev
aiplane doctor
```

For a wheel-installed recording workspace without a repository clone, omit `scripts/check.sh quick`; that command is for contributors.

Verify:

- each video completes in a normal-speed rehearsal under 2:50;
- every alias, target, host, endpoint, and output is sanitized and predetermined;
- every mutation is preceded by its dry-run or plan;
- commands use the installed CLI rather than `PYTHONPATH=src`;
- no command depends on live catalog/cloud communication unless the segment says so;
- expected nonzero validation output is rehearsed and explained;
- integration exports are compared before/after where repeatability is claimed;
- profile backup and template repair are described as different operations;
- platform limitations match `docs/user/platform-support.md`;
- no credentials, audit records, private paths, or account identifiers appear on screen.

### P0 demonstration evidence

Use the canonical [external-trial evidence record](project-plan.md#external-trial-evidence) and validate it before sharing. For each independent user, record:

- operating system and installation channel;
- start/end timestamps and whether the video stayed under three minutes;
- whether help was required beyond the video;
- first failed command and failure category;
- whether the user could explain what files were written;
- whether the user understood that export does not edit the target tool;
- whether backup/restore reproduced canonical render and export byte-for-byte;
- whether remote planning was understood as planning rather than provisioning.

The P0 demonstration gate closes only after independent users reproduce all three flows from clean environments and the final README/documentation sweep is repeated afterward.
