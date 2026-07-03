# Session Handoff

This file is the short resume point for future `aiplane` development sessions. Use it together with [Agent Guidance](agent-guidance.md), [Project Roadmap](roadmap.md), [Strategy](strategy.md), and [Command Coverage](command-coverage.md).

## Current Milestone

**Post-merge architecture and integration hardening** is the active milestone.

The PR has merged, so the immediate work moves from demo/merge readiness to making the merged MVP surface easier to maintain and extend. Priorities are: modularize the largest code hotspots, bring MCP into deliberate parity with useful CLI inspection/planning/export features, add a versioned `aiplane` agent skill package, and deepen orchestrator support for multi-agent workflow metadata without turning `aiplane` into the agent runner.

## Product Boundary

`aiplane` is a control-plane CLI for self-managed and managed LLM development environments. It configures and checks profiles, providers, models, runtimes, machines, stacks, tools, credentials references, IDE/MCP snippets, and supporting workflows.

It should not become a coding agent, model runtime, general model proxy, IDE extension, or hidden cloud deployment engine.

## Local Direction Notes

If `docs/project/.strategy/` exists, read it before roadmap, strategy, release-readiness, or positioning changes. It is intentionally gitignored local context and should not be copied into tracked public docs unless the human owner explicitly asks.

## Recent Repository Event

The GitHub history was rewritten to remove sensitive tracked planning files from earlier history. As part of the beta-hardening milestone, clean public versions of the core project planning docs were restored in the current working tree:

- `docs/project/strategy.md`
- `docs/project/roadmap.md`
- `docs/project/session-handoff.md`

These restored docs are public-facing contributor context and intentionally avoid private business/financial positioning.

## Current Public Status

High-level implemented areas:

- profiles, local config, ignored credential references, provider credential tests, and validation;
- environment planning/doctor checks for system Python, `venv`, Conda, and Docker, with setup helpers that bootstrap ignored `profiles/local-dev` before profile-aware checks;
- provider/model catalogs including NVIDIA Hugging Face-scoped open model discovery, structural shipped profile config, ignored discovery cache review, direct profile-owned model add/clone, runtime/source mapping, local model defaults, and benchmark smoke checks;
- hardware discovery, machine inventory, Azure SKU discovery/import, and stack planning;
- tool doctors/plans/exports for infrastructure, quality, and automation tools;
- integration role inspection, setup, and exports for Continue, Cline, Zed, Aider, OpenAI-compatible clients, and MCP client snippets, with setup planning supported helper install/start/pull actions and skipping unsupported source/runtime pull combinations;
- starter agent app planning/export plus a versioned `skills/aiplane/SKILL.md` assistant workflow package;
- MCP stdio server with read tools, provider ownership/status grouping, machine recommendation, stack list/show/plan/doctor, integration role/plan inspection, orchestrator list/show inspection, and narrow audited writes;
- policy, approvals, secret redaction, and audit foundations.

Known in-progress areas:

- richer managed-provider discovery and provider-specific live credential tests;
- managed-service endpoint binding for stacks/orchestrator exports without mixing those models into self-managed runtime-fit checks;
- agent-to-agent role metadata and config export for established orchestrator frameworks; the first `aiplane` agent skill package now documents safe assistant workflows and MCP usage;
- remote execution and Docker-aware stack lifecycle;
- provider-specific IaC/playbook/template hardening;
- broader deployment apply paths;
- endpoint authentication/gateway planning;
- benchmark metrics, comparisons, and repeated-run summaries;
- continued test-suite performance/isolation hardening after the first focused contract-test split.

## Validation Baseline

Latest checks from this session:

```bash
PYTHONPATH=src python -m aiplane profiles validate local-dev
PYTHONPATH=src python -m aiplane environment doctor --required-only
PYTHONPATH=src python -m aiplane environment doctor --required-only --format json
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m aiplane tools matrix
PYTHONPATH=src python -m aiplane tools plan opentofu
PYTHONPATH=src python -m aiplane agents templates
PYTHONPATH=src python -m aiplane stacks list
PYTHONPATH=src python -m aiplane models list
PYTHONPATH=src python -m aiplane models clear-cache --dry-run
PYTHONPATH=src python -m aiplane models refresh --provider huggingface --query text-to-video --dry-run --verbose --limit 2
PYTHONPATH=src python -m pytest -q tests/test_mvp.py -k "models_list_and_defaults_support_grouping or managed_service_models_do_not_mix_into_runtime_groups or model_catalog_cloud_doctor_checks_env_var or runtime_catalog_maps_sources_and_models or integrations_export_continue_uses_planner_constraints"
PYTHONPATH=src python -m aiplane models list --profile local-dev --group-by provider-kind
PYTHONPATH=src python -m aiplane models list --profile local-dev --group-by runtime
PYTHONPATH=src python -m pytest tests/test_mvp.py -q -k "models_add or models_clone or models_promote"
conda run -n aiplane scripts/check.sh
```

Results:

- Profile validation passed with `ok: true`.
- `environment doctor --required-only` passed with `2/2` mandatory tools installed; runtime prerequisite checks now come from provider/runtime config rather than shipped model defaults.
- JSON environment doctor passed with mandatory tools installed and runtime prerequisite rows for Ollama and vLLM.
- Full local MCP/skill-hardening check passed: `conda run -n aiplane scripts/check.sh` completed with formatter check, Ruff lint, and `238 passed in 141.41s`.
- `tools matrix` passed and reported `16` tools, `2` mandatory, `14` optional, `11` installable by `aiplane`, `7` exports available, and `9` workflow categories: `4` complete, `1` partial, and `4` needing setup on this machine.
- `tools plan opentofu` passed and reported OpenTofu as optional/manual with non-mutating IaC plan guidance.
- `models list` returned an empty list for the clean structural profile template until discovery or local model entries are added.
- `models clear-cache --dry-run` passed with `include_curated: true` and zero removals on the clean cache.
- Hugging Face `text-to-video` refresh dry-run contacted the source API, reported `profile_models_before_refresh: 0`, and mapped returned candidates to `video_generation` on the `diffusers` runtime.
- Continue integration planning is now documented as a discovery-first demo step: refresh provider catalogs into the ignored discovery cache, derive chat/autocomplete/embedding aliases, then pass explicit role aliases to plan/export.
- Focused provider-kind, managed-service runtime separation, and Ollama Docker-substrate dry-run tests passed. The Docker dry-run path prints `docker pull ollama/ollama:latest` and `docker run ... ollama/ollama:latest` without starting containers.
- Agent template listing passed with `langgraph` and `simple-openai` templates.
- Stack listing passed and returned an empty configured stack list.

## Current Follow-Up Work

The roadmap milestones are now grouped into three bands:

- **Post-Merge Foundation**: architecture/codebase cleanup, MCP and agent skill hardening, and orchestrator-backed multi-agent workflow metadata.
- **Product Hardening**: provider discovery/import, runtime/stack endpoint hardening, cloud/VM/workstation workflows, and tool doctor expansion.
- **Later Expansion**: runtime packaging, IDE launch/session integrations, benchmark quality, and test-suite isolation.

The first architecture cleanup slice now centralizes integration role contracts, model list grouping, model resource estimates, runtime pull compatibility, runtime/source/provider definitions, and part of the integration CLI command family. Continue splitting `src/aiplane/cli.py` by command family and keep moving shared definitions into small modules where they prevent real drift.

MCP is implemented and tested, but it is still a hand-maintained adapter. It now includes model filters, machine recommendations, stack list/show/plan/doctor checks, integration role/plan, and orchestrator list/show read surfaces. Future MCP sync should focus on safe gaps only, while leaving model pulls, installs, cloud apply, secret writes, and arbitrary shell execution blocked or CLI-only.

The first versioned `aiplane` skill package exists at `skills/aiplane/SKILL.md`. It documents safe workflows for coding assistants: read the guidance docs, inspect profiles/providers/models/runtimes separately, prefer doctor/plan/dry-run/export, use MCP when a structured read/planning tool exists, keep docs/tests aligned, and run focused checks before proposing PRs.

Orchestrator support is catalog/setup oriented today. The next design step is a multi-role workflow schema over reviewed model aliases and endpoints: planner/coder/reviewer/researcher/tool-runner roles, tool policies, approval modes, limits, and audit labels, with exports for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands. `aiplane` should configure and validate those workflows, not execute autonomous agent conversations directly.

## Next Useful Work

1. Design the multi-role orchestrator/stack schema before adding deeper exports or setup commands.
2. Continue splitting the large CLI implementation by command family while preserving the current `aiplane` entrypoint and tests.
3. Continue splitting `tests/test_mvp.py` into focused files and keep the full `scripts/check.sh` suite green during the split.
4. Keep provider/model/runtime docs aligned as discovery, runtime pulls, hardware fit, and managed-service endpoint behavior continue to harden.
