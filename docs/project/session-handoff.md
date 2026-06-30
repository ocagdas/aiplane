# Session Handoff

This file is the short resume point for future `aiplane` development sessions. Use it together with [Agent Guidance](agent-guidance.md), [Project Roadmap](roadmap.md), [Strategy](strategy.md), and [Command Coverage](command-coverage.md).

## Current Milestone

**Early beta release hardening** is the active milestone.

The immediate task is repository coherence after sensitive-history cleanup: keep the README, user docs, project strategy, roadmap, command coverage, implemented CLI surface, and tests aligned without restoring private/local-only planning content to tracked files.

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
- environment planning/doctor checks for system Python, `venv`, Conda, and Docker;
- provider/model catalogs, provider-only shipped profile config, ignored generated cache review, runtime/source mapping, local model defaults, and benchmark smoke checks;
- hardware discovery, machine inventory, Azure SKU discovery/import, and stack planning;
- tool doctors/plans/exports for infrastructure, quality, and automation tools;
- integration exports for Continue, Cline, Zed, Aider, OpenAI-compatible clients, and MCP client snippets;
- starter agent app planning/export;
- MCP stdio server with read tools and narrow audited writes;
- policy, approvals, secret redaction, and audit foundations.

Known in-progress areas:

- richer managed-provider discovery and provider-specific live credential tests;
- managed-service endpoint binding for stacks/orchestrator exports without mixing those models into self-managed runtime-fit checks;
- agent-to-agent role metadata and config export for established orchestrator frameworks;
- remote execution and Docker-aware stack lifecycle;
- provider-specific IaC/playbook/template hardening;
- broader deployment apply paths;
- endpoint authentication/gateway planning;
- benchmark metrics, comparisons, and repeated-run summaries.

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
```

Results:

- Profile validation passed with `ok: true`.
- `environment doctor --required-only` passed with `2/2` mandatory tools installed; runtime prerequisite checks now come from provider/runtime config rather than shipped model defaults.
- JSON environment doctor passed with mandatory tools installed and runtime prerequisite rows for Ollama and vLLM.
- Full test suite passed: `169 passed in 125.69s`.
- `tools matrix` passed and reported `16` tools, `2` mandatory, `14` optional, `11` installable by `aiplane`, `7` exports available, and `9` workflow categories: `4` complete, `1` partial, and `4` needing setup on this machine.
- `tools plan opentofu` passed and reported OpenTofu as optional/manual with non-mutating IaC plan guidance.
- `models list` returned an empty list for the checked-in provider-only profile.
- `models clear-cache --dry-run` passed with `include_curated: true` and zero removals on the clean cache.
- Hugging Face `text-to-video` refresh dry-run contacted the source API, reported `profile_models_before_refresh: 0`, and mapped returned candidates to `video_generation` on the `diffusers` runtime.
- Continue integration planning is now documented as a discovery-first demo step: refresh provider catalogs into the ignored generated cache, derive chat/autocomplete/embedding aliases, then pass explicit role aliases to plan/export.
- Focused provider-kind, managed-service runtime separation, and Ollama Docker-substrate dry-run tests passed. The Docker dry-run path prints `docker pull ollama/ollama:latest` and `docker run ... ollama/ollama:latest` without starting containers.
- Agent template listing passed with `langgraph` and `simple-openai` templates.
- Stack listing passed and returned an empty configured stack list.

## Current Follow-Up Work

The **Tool/task matrix and setup doctor expansion** milestone started with workflow-level readiness summaries in `tools matrix`. The current local matrix reports cloud, configuration, remote, and VM workflows as complete; container as partial; and benchmark, IaC, image-build, and Kubernetes as needing setup.

The next roadmap milestone, **Provider discovery and model import**, is now in progress. Work now includes provider-only shipped profiles, ignored provider override YAML, discovery-derived media roles, ElevenLabs managed TTS voice discovery, generated cache clearing by default, and `next_steps` guidance from provider discovery to generated aliases to reviewed local promotion.

Checked-in profiles now contain provider definitions without model aliases or defaults. Ollama runtime helpers now support both the default native path and `--substrate docker` using the official `ollama/ollama` image. `models refresh` repopulates ignored `models.generated.yaml` from configured providers, user provider extensions live in ignored `model-providers.user.yaml`, and `models clear-cache` includes curated/template aliases by default; use `--keep-curated` to preserve curated aliases and clear only generated or legacy refresh-imported entries. `models list --group-by provider-kind` now nests aliases by ownership and provider/source, while runtime grouping places managed-service aliases under `no_runtime` and ignores runtime-fit fields on those aliases instead of treating provider names or `preferred_runtime` values as local runtime candidates. Managed-service endpoint metadata should still remain available to stacks, orchestrator exports, and future agent-to-agent role plans where the framework calls a hosted endpoint directly.

The **Cloud, VM, and workstation tool integrations** milestone is now in progress from a public-demo angle. `docs/project/public-demo-plan.md` captures the intro narration, three-minute outline, discovery-first command flow, repeatability points, Azure redaction warning, and readiness gates for showcasing local, endpoint, MCP, stack, and Azure discovery workflows. The plan now uses a disposable `/tmp` profile, writes generated aliases only outside the repo, derives aliases from `models list` JSON, and avoids undefined model placeholders in the demo path.

## Next Useful Work

1. Review and commit the restored public `strategy.md`, `roadmap.md`, and `session-handoff.md` files after human inspection.
2. Keep scanning changed tracked files for secret-like content and private/local-only planning terms before publication.
3. Continue tightening README, user docs, command coverage, and roadmap around current behavior rather than future claims.
4. Expand `environment doctor` only where it improves setup clarity without turning optional workflows into mandatory prerequisites.
5. Public demo planning is appropriate once the beta-hardening docs are committed and the tool matrix/doctor checks remain green.
6. Add stack/orchestrator schema support for managed endpoint bindings and future agent-to-agent role graphs before exposing deeper autonomous workflows.

The media demo segment is now planned as discovery-first AI media selection: use online provider refresh into ignored generated aliases, filter by role/runtime/target hardware, show the Azure/GPU resource command path, fast-forward the generation job, and play the generated clip at the end.
