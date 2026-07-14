# Session Handoff

This file is the short resume point for future `aiplane` development sessions. Use it together with [Agent Guidance](agent-guidance.md), [Project Roadmap](roadmap.md), [Strategy](strategy.md), and [Command Coverage](command-coverage.md).


## Current Milestone

**Current target: Milestone 1 (External Beta Readiness)**

P0.5 quickstart sufficiency is complete: provider discovery is opt-in, repeat runs preserve profile edits, empty profiles receive at most two no-YAML setup paths plus a no-runtime dry-run plan, and configured profiles receive one exact Continue export action. Validation: focused quickstart suite 6 passed; quick gate 19 passed; full suite 436 passed; required profile and environment doctor checks passed.

P0.6 stable doctor contract v1 is complete: all findings expose stable IDs, severity, reason, impact, affected resources, and uniform remediation/mutation/dry-run metadata; blocker actions are deterministic and payload exit semantics are authoritative. Validation: focused doctor/contract suite 29 passed; focused doctor suite 14 passed; quick gate 19 passed; full suite 438 passed; required profile and environment doctor checks passed.

P0.7 Tier-1 deterministic exports are implemented: four v1 golden contracts define the release boundary, advanced exporters are explicitly unversioned, and installed-wheel CI performs real MCP stdio verification on every supported OS.

P0.8 public profile schema v1 is complete: packaged JSON Schema, canonical read-only rendering, deterministic merge semantics, validation paths/remedies, and a no-silent-migration pre-1.0 policy.

Must

1. Completed: top-level `aiplane discover` coverage and execution for the public onboarding flow.
2. Completed: `aiplane quickstart local-coding` now carries discovery provenance and prints the public core command sequence.
3. Completed: discovery/bootstrap output now distinguishes detected, built-in, provider-discovered cache, profile-configured, and unresolved provenance records.
4. Completed: blocking/advisory doctor findings now include structured remediation command metadata, impact, mutability, and dry-run support fields.
5. Add deterministic, reproducible exports for Continue, Aider, Cline, Zed, OpenAI-compatible, and MCP clients.
6. Implement recommendation test matrix and deterministic ranking.
7. Completed: public onboarding has top-level `discover`, `doctor`, `recommend`, and `export` commands with help text and tests.
8. Validate clean onboarding on multiple environments and classify failures.

Should

1. Completed for current behavior: policy decisions now expose stable `allowed`, `approval_required`, and `blocked` outcomes; temporary approvals and audited overrides remain future governance work.
2. Completed: user docs are split by maturity with Start here, Common workflows, and Advanced concepts sections, and command examples call out mutating-state behavior and verifiable outcomes.

Scope freeze until sprint targets complete:

- No new orchestrators, cloud providers, benchmark frameworks, or runtime types.
- Priority remains onboarding determinism, actionability, provenance, deterministic exports, and clean-machine evidence.

## Current Public Status

High-level implemented areas:

- profiles, local config, ignored credential references, provider credential tests, and validation;
- environment planning/doctor checks for system Python, `venv`, Conda, and Docker, with setup helpers that bootstrap ignored `profiles/local-dev` before profile-aware checks;
- provider/model catalogs including NVIDIA Hugging Face-scoped open model discovery, OpenAI-compatible `/v1/models` discovery, structural shipped profile config, ignored discovery cache review, direct profile-owned model add/clone, runtime/source mapping, local model defaults, local AI quickstart with opt-in model pull preview/execution plus doctor summaries, protocol-backed single-prompt execution for Ollama/OpenAI-compatible/Azure OpenAI/Anthropic, and benchmark smoke checks;
- hardware discovery, machine inventory, Azure SKU discovery/import, and stack planning;
- tool doctors/plans/exports for infrastructure, quality, and automation tools;
- integration role inspection, setup, and exports for Continue, Cline, Zed, Aider, OpenAI-compatible clients, and MCP client snippets, with setup planning supported helper install/start/pull actions and skipping unsupported source/runtime pull combinations;
- starter agent app planning/export plus a versioned `skills/aiplane/SKILL.md` assistant workflow package;
- MCP stdio server with read tools, provider ownership/status grouping, machine recommendation, stack list/show/plan/doctor, integration role/plan inspection, orchestrator list/show inspection, and narrow audited writes;
- policy, approvals, secret redaction, and audit foundations.

Known in-progress areas:

- richer managed-provider discovery and provider-specific live credential tests;
- managed-service endpoint binding for stacks/orchestrator exports without mixing those models into self-managed runtime-fit checks;
- stack role metadata is implemented for planner/coder/reviewer-style model bindings, including managed-service role endpoint binding and warning-level doctor checks for risky tool-policy/approval combinations; framework starter exports and MCP stack export read parity now exist, with deeper framework-specific templates still next; the first `aiplane` agent skill package documents safe assistant workflows and MCP usage;
- remote execution and Docker-aware stack lifecycle;
- deploy workflow classification now separates local install, local VM, remote workstation/VM, cloud VM, and cloud Kubernetes boundaries with non-mutating `deploy workflow-plan`;
- `deploy apply` now requires explicit `--yes`, and broad cloud apply remains intentionally out of scope until provider-specific guardrails are ready;
- provider-specific IaC/playbook/template hardening;
- broader deployment apply paths;
- endpoint authentication/gateway planning now exists at stack level through endpoint auth/TLS/gateway metadata and `stacks endpoint-plan`; top-level `aiplane doctor` now gives a read-only local AI workflow stack readiness summary with selected endpoint readiness, capability, and hardware-fit details; richer runtime-agnostic chat/task UX beyond single-prompt execution remains planned;
- benchmark metrics, comparisons, and repeated-run summaries;
- continued test-suite performance/isolation hardening. Default tests should use synthetic fixture profiles, temp roots, mocked subprocess/network boundaries, and controlled generated caches; real disk/cache/tool dependencies should be explicit and isolated in dev setup.

## Validation Baseline

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
python -m aiplane tools plan opentofu
python -m aiplane agents templates
python -m aiplane stacks list
python -m aiplane models list
python -m aiplane models clear-cache --dry-run
python -m aiplane deploy workflow-plan --target azure_gpu_vm
python -m aiplane deploy apply --target azure_gpu_vm
python -m aiplane models refresh --provider huggingface --query text-to-video --dry-run --verbosity 2 --limit 2
python -m pytest -q tests/test_models_providers.py tests/test_runtimes_execution.py tests/test_integrations_chat.py -k "models_list_and_defaults_support_grouping or managed_service_models_do_not_mix_into_runtime_groups or model_catalog_cloud_doctor_checks_env_var or runtime_catalog_maps_sources_and_models or integrations_export_continue_uses_planner_constraints"
python -m aiplane models list --profile local-dev --group-by provider-kind
python -m aiplane models list --profile local-dev --group-by runtime
python -m pytest tests/test_models_providers.py -q -k "models_add or models_clone or models_promote"
conda run --no-capture-output -n aiplane scripts/check.sh
```

Results:

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

## Current Follow-Up Work

Provider discovery and model import now has an implemented foundation: structural shipped model templates, discovery-backed add/promote/clone flows, refresh next-step guidance, machine-derived `models list` filtering, OpenAI-compatible `/v1/models` discovery, Azure OpenAI deployment discovery, ElevenLabs voice discovery, and structured managed-provider refresh failures for missing live catalog configuration. Remaining work in that area is richer provider-specific live discovery and credential tests where provider APIs justify dedicated adapters.

The roadmap milestones are now grouped into three bands:

- **Post-Merge Foundation**: architecture/codebase cleanup, MCP and agent skill hardening, and orchestrator-backed multi-agent workflow metadata.
- **Product Hardening**: provider discovery/import, runtime/stack endpoint hardening, cloud/VM/workstation workflows, and tool doctor expansion.
- **Later Expansion**: runtime packaging, IDE launch/session integrations, benchmark quality, and test-suite isolation.

The architecture cleanup slice now centralizes integration role contracts, model list grouping, model resource estimates, runtime pull compatibility, runtime/source/provider definitions, shared CLI parse/progress helpers, and focused CLI modules for config, profiles, governance, deployment/remote, setup/tooling, hardware/machines, orchestrators/stacks, integrations, and models. Continue splitting `src/aiplane/cli.py` by command family where it reduces real ownership pressure, not just to move code around.

MCP is implemented and tested, but it is still a hand-maintained adapter. It now includes model filters with named-machine/current-machine fit selectors, machine recommendations, stack list/show/plan/doctor checks, integration role/plan, and orchestrator list/show read surfaces. Future MCP sync should focus on safe gaps only, while leaving model pulls, installs, cloud apply, secret writes, and arbitrary shell execution blocked or CLI-only.

The first versioned `aiplane` skill package exists at `skills/aiplane/SKILL.md`. It documents safe workflows for coding assistants: read the guidance docs, inspect profiles/providers/models/runtimes separately, prefer doctor/plan/dry-run/export, use MCP when a structured read/planning tool exists, keep docs/tests aligned, and run focused checks before proposing PRs.

Orchestrator support now has stack role metadata over reviewed model aliases and endpoints: planner/coder/reviewer/researcher/tool-runner roles, tool policies, approval modes, limits, audit labels, managed-service endpoint bindings, doctor checks, and starter exports for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands. Runtime/stack hardening now adds endpoint auth/TLS/gateway planning and clearer same-host lifecycle result metadata. `aiplane` should keep configuring and validating those workflows, not execute autonomous agent conversations directly.

## Next Useful Work

1. Must: run the clean-machine onboarding trial commands from `docs/project/public-demo-plan.md` across the six Priority 9 environments and classify each failure.
2. Must: finish the remote-workstation onboarding documentation pass and align it with the public demo workflow sequence.
3. Must: keep policy/risk behavior regressions visible: expand blocked cloud-policy and disallowed-provider coverage beyond current stack tests.
4. Should: keep docs/tests/command-coverage synchronized before feature-freeze gates.


## July 2026 Safety and Structure Review

The persistent prioritized register is
[Code Quality and Safety Review — July 2026](code-quality-review-2026-07.md).
SEC-1 and ARCH-1 are complete. SEC-1 focused tests cover non-TTY denial without mutation, explicit per-invocation `--yes`, read-only execution, passthrough arguments, and audit denial. ARCH-1 reduces `cli.py` from 1,570 to 456 lines with dedicated launch, profile, presenter, and public-workflow modules plus structural drift tests. Validation: focused suite 89 passed, quick gate 14 passed, full suite 349 passed. REL-2 is also complete: audit-tail recovery skips malformed and likely truncated final records while keeping stdout valid JSONL and warnings metadata-only; focused recovery/audit/tool coverage passes 24 tests; quick gate 14 passed; full suite 353 passed. SAFE-1 is complete: SSH tunnel state is versioned, atomic, collision-resistant, and identity-verified before signalling; stale or reused PIDs are never killed. Focused remote/boundary coverage passes 23 tests, expanded integration coverage passes 70 tests, the production Linux inspector check passed, quick gate 14 passed, and full suite 357 passed. COMPAT-1 was added to the prioritized register to inventory and gate Linux-, Ubuntu/Debian-, systemd-, procfs-, Bash-, package-manager-, and GPU-tool-specific operations, with explicit help/doctor/documentation and synthetic cross-platform tests.
 REL-1 and SEC-3 are complete: production text persistence is atomic and serialized across threads/processes with bounded, non-nestable IPC locking and transactional YAML updates; audit writes are durable, secret redaction covers command-aware and structured inputs, and tool/MCP audit failures omit raw outputs, arguments, and exception messages. Focused persistence/redaction coverage passes 10 tests, expanded relevant coverage passes 96 tests, quick gate 14 passed, and full suite 367 passed.
 SEC-4 is complete: tunnel and remote-profile planning share strict host, username, port, and HTTP(S) endpoint validation; option-like destinations fail before command construction, IPv6 forwarding is bracketed, and remote shell values are quoted. Focused remote/validation coverage passes 49 tests, quick gate 14 passed, full suite 396 passed, and representative CLI valid/rejection checks passed.
 SEC-2 and REL-3 are complete: MCP is read-only by default and requires both operator `--allow-writes` and per-call `confirm=true` before manager dispatch; blocked attempts are audited. The CLI redacts expected errors, sanitizes unexpected failures unless debug is explicitly enabled, handles broken pipes quietly, and returns 130 on interruption. Focused MCP contracts pass 37 tests; focused CLI boundary/governance smoke coverage passes 26 tests; the combined suite passes 63 tests; the real pipefail check, quick gate (14 tests), and full suite (409 tests) pass.
 COMPAT-1 and ARCH-2 are complete. Platform capabilities centralize distro/WSL behavior, block unsupported runtime mutations, and skip non-Linux probes; focused compatibility coverage passes 78 tests. Model persistence/reconciliation and Azure pricing/CLI boundaries are decomposed with structural drift tests; focused architecture coverage passes 64 tests. The combined suite passes 117 tests; the final full suite passes 422 tests. The evaluated external product/adoption/monetization backlog is `docs/project/product-adoption-backlog-2026-07.md`.

 DOC-1 is complete. README and user onboarding now use `aiplane export continue`, the empty workflow heading is removed, and documentation contracts prevent ambiguous exports, empty adjacent sections, and workflow-number drift. Focused contract suite: 13 passed; quick gate: 17 passed; full suite: 425 passed.

 The product positioning/default-help backlog item is complete. Public entrypoints consistently lead with “environment doctor and configuration compiler,” developer-preview maturity is aligned with package alpha metadata, and top-level help groups every command into explicit core, advanced/supporting, or experimental tiers with one dry-run next action. Focused positioning/help suite: 30 passed; quick gate: 18 passed; full suite: 426 passed; required profile and environment-doctor checks passed in text and JSON modes.

 The standard installation/release-channel implementation is complete, with first tag publication intentionally left to the maintainer. GitHub Release wheels require no clone; `scripts/verify_install_channels.py` validates pip, pipx, and uv tool lifecycles in isolated homes; CI covers Ubuntu, macOS, and Windows; release tags must match `pyproject.toml` before validated wheel/sdist publication. Local focused packaging contracts passed 16 tests, all three real final-wheel installer lifecycles passed, quick gate passed 19 tests, full suite passed 427 tests, and required profile/environment doctor checks passed.

 README and package metadata breadth cleanup is complete: detailed agentic/provisioning/benchmark/stack/MCP marketing lists are removed, advanced commands are described only as a subordinate maturity surface, contribution and documentation links lead the narrow workflow, and package keywords now target diagnostics/configuration/reproducibility. Regression contracts prevent the stale broad headings and keywords returning. Focused contracts/packaging: 16 passed; quick gate: 19 passed; full suite: 427 passed. The final overall documentation consistency sweep is tracked at the bottom of P0, after all numbered P0 work and the user demonstrations.

 P0.4 platform CI is implementation-complete. The Ubuntu/macOS/Windows matrix runs 15 synthetic platform tests plus clean installed-wheel portable workflow smoke through pip, pipx, and uv. Windows SSH lifecycle is now gated before process/state access with explicit help and `unsupported_platform`; runtime mutation gates cover Fedora, WSL, macOS, and Windows before helper dispatch. Focused platform/remote suite: 79 passed; local real final-wheel lifecycles: all three passed; quick gate: 19 passed; full suite: 434 passed; required doctors passed. Cross-OS runner results will be produced when CI runs on push.

 P0.9 is complete: docs/project/threat-model.md maps all eight required security areas to deterministic tests and explicit residual limitations; SECURITY.md links it and uses the current product boundary. Focused security validation: 62 passed; full suite: 449 passed.

 The interim README/documentation consistency sweep after the earlier implementation milestones corrected stale quickstart outcome text, positive control-plane positioning, top-level help breadth, and obsolete P0 item-number references. Contract tests preserve those corrections. The unnumbered P0 completion gate remains open: run the three independent-user demonstrations, then repeat the final README/documentation sweep before closing P0. Focused consistency gate: 76 passed; full suite: 449 passed.

 The public demo plan has been replaced with three newbie-focused videos capped below three minutes: local Ollama onboarding, local-only policy with honest YAML/config backup and byte-identical restore proof, and existing remote-GPU machine import/access planning/export. A fourth automation/MCP video remains deferred pending user evidence. The plan explicitly separates canonical archival, filesystem restoration, template repair, credentials, caches, audit/tunnel state, and runtime-owned weights.

 Test profiling and one safe optimization are complete. Baseline four-worker suite: 450 passed in 36.46s / 37.04s wall; packaging lifecycle test 25.45s. The packaging test no longer reruns the independent install/reinstall/uninstall verifier already owned by OS-matrix and release gates. After: 450 passed in 19.71s / 20.26s wall; packaging test 8.69s. Six workers passed in 17.21s / 17.78s wall and remain an opt-in local setting; the portable default stays at four.

 The latest external review has a tracked evaluation at `docs/project/reviews/dev-mvp-0.5-latest-review-evaluation.md`. Numbered P0 now contains only current release/adoption actions; the independent-user and final-documentation gates remain unnumbered and open. The durable CI recommendation is protected checks on the main/release path, not a permanent feature-branch trigger.

 The macOS/Windows install-channel CI regressions are fixed. Tier-1 verification uses the stable relative model ID `portable-smoke.gguf`; all OSes exercise read-only tunnel planning; macOS/Windows assert unsupported runtime-helper mutation; only Windows asserts unsupported tunnel lifecycle. The verifier cannot start a tunnel on Linux or macOS in its platform contract. Behavioral synthetic tests cover Linux, Darwin, and Windows. Focused suite: 41 passed; rebuilt-wheel real pip lifecycle passed.
P0.1 is complete with a contract-enforced five-command primary adoption cut and two subordinate validation recordings. P0.2 repository implementation is ready: versioned notes, changelog, checksum generation/verification, full-gate release automation, supported-platform guidance, and rollback guidance are present; a rebuilt wheel passed the clean pip install/replace/uninstall lifecycle. P0.2 remains open until the maintainer publishes the approved immutable tag and public release URL.

P0.3-P0.6 local implementation is complete: clean-wheel lifecycle verification has a canonical evidence format; `CI / Release gate` aggregates quality, compatibility, and cross-OS install jobs; repository protection requirements are explicit; trial records have a deterministic sanitizer/shape validator; and the preview scope freeze has an exception contract. Public-artifact evidence, hosted ruleset activation, and independent-user trials remain maintainer/external actions.

Post-merge no-clone candidates are now automated: a successful protected `main` push builds a wheel only after `CI / Release gate`, verifies its SHA-256 manifest, writes commit/run provenance, and uploads a 30-day artifact named with package version plus the full merge SHA. This is prerelease test evidence, not the immutable public P0 release.
