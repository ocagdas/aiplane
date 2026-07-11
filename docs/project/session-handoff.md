# Session Handoff

This file is the short resume point for future `aiplane` development sessions. Use it together with [Agent Guidance](agent-guidance.md), [Project Roadmap](roadmap.md), [Strategy](strategy.md), and [Command Coverage](command-coverage.md).


## Current Milestone

**Current target: Milestone 1 (External Beta Readiness)**

Must

1. Completed: top-level `aiplane discover` coverage and execution for the public onboarding flow.
2. Completed: `aiplane quickstart local-coding` now carries discovery provenance and prints the public core command sequence.
3. Completed: discovery/bootstrap output now reports detected, generated, user-supplied, and unresolved provenance records.
4. Completed: blocking/advisory doctor findings now include structured remediation command metadata, impact, mutability, and dry-run support fields.
5. Add deterministic, reproducible exports for Continue, Aider, Cline, Zed, OpenAI-compatible, and MCP clients.
6. Implement recommendation test matrix and deterministic ranking.
7. Completed: public onboarding has top-level `discover`, `doctor`, `recommend`, and `export` commands with help text and tests.
8. Validate clean onboarding on multiple environments and classify failures.

Should

1. formalize policy-state outcomes (Allowed/Allowed-with-warning/Approval required/Temporarily approved/Blocked/Overridden with audit)
2. split docs by maturity and add command examples with mutating-state flags.

Scope freeze until sprint targets complete:

- No new orchestrators, cloud providers, benchmark frameworks, or runtime types.
- Priority remains onboarding determinism, actionability, provenance, deterministic exports, and clean-machine evidence.

## Current Public Status

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
PYTHONPATH=src python -m aiplane profiles validate local-dev
PYTHONPATH=src python -m aiplane environment doctor --required-only
PYTHONPATH=src python -m aiplane environment doctor --required-only --format json
PYTHONPATH=src python -m aiplane quickstart local-coding --dry-run --no-discovery
PYTHONPATH=src python -m aiplane quickstart local-coding --dry-run --no-discovery --format json
PYTHONPATH=src python -m aiplane quickstart local-coding --dry-run --no-discovery --pull-model MODEL_ALIAS
PYTHONPATH=src python -m aiplane doctor --profile local-dev
PYTHONPATH=src python -m aiplane doctor --profile local-dev --format json
PYTHONPATH=src python -m aiplane config format
PYTHONPATH=src python -m aiplane hardware show --list-types
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m aiplane tools matrix
PYTHONPATH=src python -m aiplane tools plan opentofu
PYTHONPATH=src python -m aiplane agents templates
PYTHONPATH=src python -m aiplane stacks list
PYTHONPATH=src python -m aiplane models list
PYTHONPATH=src python -m aiplane models clear-cache --dry-run
PYTHONPATH=src python -m aiplane deploy workflow-plan --target azure_gpu_vm
PYTHONPATH=src python -m aiplane deploy apply --target azure_gpu_vm
PYTHONPATH=src python -m aiplane models refresh --provider huggingface --query text-to-video --dry-run --verbosity 2 --limit 2
PYTHONPATH=src python -m pytest -q tests/test_models_providers.py tests/test_runtimes_execution.py tests/test_integrations_chat.py -k "models_list_and_defaults_support_grouping or managed_service_models_do_not_mix_into_runtime_groups or model_catalog_cloud_doctor_checks_env_var or runtime_catalog_maps_sources_and_models or integrations_export_continue_uses_planner_constraints"
PYTHONPATH=src python -m aiplane models list --profile local-dev --group-by provider-kind
PYTHONPATH=src python -m aiplane models list --profile local-dev --group-by runtime
PYTHONPATH=src python -m pytest tests/test_models_providers.py -q -k "models_add or models_clone or models_promote"
conda run -n aiplane scripts/check.sh
```

Results:

- Profile validation passed with `ok: true`.
- `environment doctor --required-only` passed with `2/2` mandatory tools installed; runtime prerequisite checks now come from provider/runtime config rather than shipped model defaults.
- JSON environment doctor passed with mandatory tools installed and runtime prerequisite rows for Ollama and vLLM.
- `aiplane quickstart local-coding --dry-run --no-discovery` passed in JSON and text modes, previewing the local profile bootstrap and printing the doctor/export/MCP command sequence without writing profile files; quickstart model pulls are opt-in with `--pull-model MODEL_ALIAS` once a profile-owned or discovered alias exists, and `--dry-run --pull-model MODEL_ALIAS` previews without pulling model weights.
- Top-level `aiplane doctor --profile local-dev` passed in text and JSON modes. It is read-only and summarizes profile status, required/optional environment checks, configured model defaults with provider/endpoint details, selected role-default endpoint readiness, active hardware and role-model fit, provider readiness, Continue/Aider role capability readiness, MCP manifest and local AI read-surface readiness, and next safe steps.
- Latest local gate passed after explicit test imports, focused fixture split, and local doctor coverage: `scripts/check.sh` completed with formatter check, Ruff lint, and `306 passed, 3 subtests passed in 64.55s`. Runtime helper subprocesses now receive `AIPLANE_PROFILES_DIR` for custom profile roots. The original `tests/test_mvp.py` monolith is now a legacy pointer; MVP coverage lives in focused domain modules with shared setup in `tests/support.py`, `tests/profile_fixtures.py`, and `tests/http_fixtures.py`. Earlier full-gate baselines reported `253 passed` before the chat/task behavior tests and split.
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

## Current Follow-Up Work

Provider discovery and model import now has an implemented foundation: structural shipped model templates, discovery-backed add/promote/clone flows, refresh next-step guidance, machine-derived `models list` filtering, OpenAI-compatible `/v1/models` discovery, Azure OpenAI deployment discovery, ElevenLabs voice discovery, and structured managed-provider refresh failures for missing live catalog configuration. Remaining work in that area is richer provider-specific live discovery and credential tests where provider APIs justify dedicated adapters.

The roadmap milestones are now grouped into three bands:

- **Post-Merge Foundation**: architecture/codebase cleanup, MCP and agent skill hardening, and orchestrator-backed multi-agent workflow metadata.
- **Product Hardening**: provider discovery/import, runtime/stack endpoint hardening, cloud/VM/workstation workflows, and tool doctor expansion.
- **Later Expansion**: runtime packaging, IDE launch/session integrations, benchmark quality, and test-suite isolation.

The architecture cleanup slice now centralizes integration role contracts, model list grouping, model resource estimates, runtime pull compatibility, runtime/source/provider definitions, shared CLI parse/progress helpers, and the integration/model CLI command families. Continue splitting `src/aiplane/cli.py` by command family where it reduces real ownership pressure, not just to move code around.

MCP is implemented and tested, but it is still a hand-maintained adapter. It now includes model filters with named-machine/current-machine fit selectors, machine recommendations, stack list/show/plan/doctor checks, integration role/plan, and orchestrator list/show read surfaces. Future MCP sync should focus on safe gaps only, while leaving model pulls, installs, cloud apply, secret writes, and arbitrary shell execution blocked or CLI-only.

The first versioned `aiplane` skill package exists at `skills/aiplane/SKILL.md`. It documents safe workflows for coding assistants: read the guidance docs, inspect profiles/providers/models/runtimes separately, prefer doctor/plan/dry-run/export, use MCP when a structured read/planning tool exists, keep docs/tests aligned, and run focused checks before proposing PRs.

Orchestrator support now has stack role metadata over reviewed model aliases and endpoints: planner/coder/reviewer/researcher/tool-runner roles, tool policies, approval modes, limits, audit labels, managed-service endpoint bindings, doctor checks, and starter exports for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands. Runtime/stack hardening now adds endpoint auth/TLS/gateway planning and clearer same-host lifecycle result metadata. `aiplane` should keep configuring and validating those workflows, not execute autonomous agent conversations directly.

## Next Useful Work

1. Must: finish the remote-workstation onboarding documentation pass and align it with the public demo workflow sequence.
2. Must: keep policy/risk behavior regressions visible: expand blocked cloud-policy and disallowed-provider coverage beyond current stack tests.
3. Should: keep docs/tests/command-coverage synchronized before feature-freeze gates.
4. Should: add a reproducibility check for Continue/Aider/Cline/MCP exports from saved plan IDs for regression stability.

