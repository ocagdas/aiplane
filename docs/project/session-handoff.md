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
- environment planning/doctor checks for system Python, `venv`, Conda, and Docker, with setup helpers that bootstrap ignored `profiles/local-dev` before profile-aware checks;
- provider/model catalogs, structural shipped profile config, ignored discovery cache review, direct profile-owned model add/clone, runtime/source mapping, local model defaults, and benchmark smoke checks;
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
- benchmark metrics, comparisons, and repeated-run summaries;
- test-suite performance/isolation hardening beyond the current hot-path fixes.

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
scripts/check.sh
```

Results:

- Profile validation passed with `ok: true`.
- `environment doctor --required-only` passed with `2/2` mandatory tools installed; runtime prerequisite checks now come from provider/runtime config rather than shipped model defaults.
- JSON environment doctor passed with mandatory tools installed and runtime prerequisite rows for Ollama and vLLM.
- Full local check passed: `scripts/check.sh` completed with `179 passed in 39.99s`.
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

- **Demo / PR Merge Readiness**: manual demo validation plus release hygiene/CI gates.
- **Next Hardening**: provider discovery/import, tool doctors, stack/endpoint hardening, and cloud/VM/workstation workflows.
- **Later Expansion**: runtime packaging, IDE/MCP/agent-tool expansion, benchmark quality, and test-suite isolation.

The immediate pre-merge activity is manual demo validation. Rehearse the disposable-profile demo path from clean setup through provider discovery, filtered model selection, Continue export, MCP export, stack dry-runs, and Azure discovery. Keep the run inspect-first and verify that output is concise and free of secrets, raw account identifiers, subscription IDs, tenant IDs, and private local notes.

Provider discovery and model import remain the first hardening milestone after the demo-readiness pass. Work now includes structural shipped profile templates, ignored provider/source override YAML, built-in runtime/provider endpoint defaults, discovery-derived media roles, ElevenLabs managed TTS voice discovery, discovery cache clearing by default, direct `models add`/`models clone`, and `next_steps` guidance from provider discovery to discovered entries to reviewed local promotion.

Shipped profile templates now keep `models.yaml` limited to structural defaults and profile-owned model entries; provider/source definitions live in model-provider config and runtime/provider endpoints come from conventional built-in defaults unless locally overridden. Ollama runtime helpers now support both the default native path and `--substrate docker` using the official `ollama/ollama` image. `profiles bootstrap-local` can create/validate the default editable profile and optionally populate ignored `models.discovered.yaml`. `models refresh` repopulates ignored `models.discovered.yaml` from configured providers, user provider extensions live in ignored `model-providers.user.yaml`, `models add` writes deliberate local entries to `models.yaml` from discovered aliases or discovered provider/model matches, `models clone` writes second local entries, and `models clear-cache` includes profile-owned review entries by default; use `--keep-curated` to preserve profile-owned entries and clear only discovered refresh/import entries. `models list --group-by provider-kind` now nests aliases by ownership and provider/source, while runtime grouping places managed-service aliases under `no_runtime` and ignores runtime-fit fields on those aliases instead of treating provider names or `preferred_runtime` values as local runtime candidates. Managed-service endpoint metadata should still remain available to stacks, orchestrator exports, and future agent-to-agent role plans where the framework calls a hosted endpoint directly.

`docs/project/public-demo-plan.md` captures the intro narration, three-minute outline, discovery-first command flow, repeatability points, Azure redaction warning, and readiness gates for showcasing local, endpoint, MCP, stack, and Azure discovery workflows. The plan uses a disposable `/tmp` profile, writes discovered entries only outside the repo, derives selected model entry names from `models list` JSON, and avoids undefined model placeholders in the demo path.

## Next Useful Work

1. Run manual validation against the demo targets using the disposable-profile flow in `docs/project/public-demo-plan.md`.
2. Confirm CI format, lint, and test jobs stay green after the final branch push.
3. Keep scanning changed tracked files for secret-like content and private/local-only planning terms before publication.
4. Treat any demo command that errors, prints unsafe identifiers, or implies mutation without explicit apply as a pre-merge fix.
5. Do not add new feature scope before the demo merge unless manual validation exposes a real blocker.
6. Park further test-suite optimization as a planned roadmap milestone. Current local `scripts/check.sh` timing is about 40 seconds for 179 tests; next work should focus on fixture isolation, splitting `tests/test_mvp.py`, and safe single-pass catalog helpers.

The media demo segment is now planned as discovery-first AI media selection: use online provider refresh into ignored discovered entries, filter by role/runtime/target hardware, show the Azure/GPU resource command path, fast-forward the generation job, and play the generated clip at the end.
