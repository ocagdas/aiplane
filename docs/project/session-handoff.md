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

- profiles, local config, ignored credential references, and validation;
- environment planning/doctor checks for system Python, `venv`, Conda, and Docker;
- provider/model catalogs, generated cache review, runtime/source mapping, model defaults, and benchmark smoke checks;
- hardware discovery, machine inventory, Azure SKU discovery/import, and stack planning;
- tool doctors/plans/exports for infrastructure and automation tools;
- integration exports for Continue, Cline, Zed, Aider, OpenAI-compatible clients, and MCP client snippets;
- starter agent app planning/export;
- MCP stdio server with read tools and narrow audited writes;
- policy, approvals, secret redaction, and audit foundations.

Known in-progress areas:

- richer managed-provider discovery;
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
PYTHONPATH=src python -m aiplane integrations plan continue --select-best --runtime ollama
PYTHONPATH=src python -m aiplane agents templates
PYTHONPATH=src python -m aiplane stacks list
PYTHONPATH=src python -m aiplane models refresh --provider ollama --dry-run --limit 3
```

Results:

- Profile validation passed with `ok: true`.
- `environment doctor --required-only` passed: `2/2` mandatory tools installed and `0` runtime prerequisites missing.
- JSON environment doctor passed with `tools_checked: 2`, `tools_installed: 2`, and `runtime_prerequisites_missing: 0`.
- Full test suite passed: `165 passed in 15.15s`.
- `tools matrix` passed and reported `16` tools, `2` mandatory, `14` optional, `11` installable by `aiplane`, `7` exports available, and `9` workflow categories: `4` complete, `1` partial, and `4` needing setup on this machine.
- `tools plan opentofu` passed and reported OpenTofu as optional/manual with non-mutating IaC plan guidance.
- Continue integration planning passed with selected Ollama-backed chat, autocomplete, and embedding aliases.
- Agent template listing passed with `langgraph` and `simple-openai` templates.
- Stack listing passed and returned an empty configured stack list.

## Current Follow-Up Work

The **Tool/task matrix and setup doctor expansion** milestone started with workflow-level readiness summaries in `tools matrix`. The current local matrix reports cloud, configuration, remote, and VM workflows as complete; container as partial; and benchmark, IaC, image-build, and Kubernetes as needing setup.

The next roadmap milestone, **Provider discovery and model import**, is now in progress. Work started by adding `next_steps` guidance to `models refresh` and `models promote` output so demos and release review can show the safe path from provider discovery, to generated aliases, to curated profile aliases without relying on separate documentation. Focused refresh/promote tests passed, and `aiplane models refresh --provider ollama --dry-run --limit 3` showed the expected guidance.

The **Cloud, VM, and workstation tool integrations** milestone is now in progress from a public-demo angle. `docs/project/public-demo-plan.md` captures the intro narration, three-minute outline, command flow, repeatability points, Azure redaction warning, and readiness gates for showcasing local, endpoint, MCP, stack, and Azure discovery workflows.

## Next Useful Work

1. Review and commit the restored public `strategy.md`, `roadmap.md`, and `session-handoff.md` files after human inspection.
2. Keep scanning changed tracked files for secret-like content and private/local-only planning terms before publication.
3. Continue tightening README, user docs, command coverage, and roadmap around current behavior rather than future claims.
4. Expand `environment doctor` only where it improves setup clarity without turning optional workflows into mandatory prerequisites.
5. Public demo planning is appropriate once the beta-hardening docs are committed and the tool matrix/doctor checks remain green.
