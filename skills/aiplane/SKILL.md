---
name: aiplane
description: Inspect and configure AI development environments with the aiplane CLI or MCP tools. Use for aiplane profiles, environment diagnosis, model recommendations, integration exports, or contributions to the aiplane repository.
---

# aiplane

Skill version: 0.2.0

This version tracks the playbook independently of the application version.

## Operating Boundary

Treat `aiplane` as an environment doctor and configuration compiler. It plans, checks, prepares, and exports configuration for AI development environments. It must not become a coding agent, model runtime, model proxy, IDE extension, hidden cloud deployment engine, or broad MCP shell executor.

## Installed CLI Use

Start with `aiplane quickstart local-coding --dry-run`. Use `aiplane --help` for available commands and `aiplane.docs.list` / `aiplane.docs.read` through MCP for bundled guides. Product help comes from the installation, independently of the selected profile workspace. Preview recommendations and exports before applying changes.

## Repository Contributions

These steps require a source checkout; they do not apply to ordinary installed CLI use.

1. Read `docs/project/agent-guidance.md` before changing files.
2. Check `git status --short --untracked-files=all` and avoid reverting user changes.
3. Read the relevant user docs, command coverage, roadmap, and backlog before changing behavior.
4. Prefer existing managers and CLI patterns over new parallel logic.

## Change Rules

- Keep behavior, docs, roadmap/backlog, command coverage, MCP surfaces, and tests aligned.
- Add or update tests for behavior changes unless there is a clear engineering reason not to; tests should prove real behavior, contracts, regressions, or failure modes rather than increase counts; still run focused tests.
- Keep tests deterministic and avoid live cloud/provider/runtime dependency unless mocked or explicitly requested.
- Use plan, doctor, dry-run, and export flows before mutation.
- Do not expose runtime installs, model pulls, cloud apply, secret writes, or arbitrary shell execution through MCP unless explicit guardrails exist.
- Keep credentials in ignored local files or environment variables; never add real secrets to tracked files.

## Common Validation

Run focused tests for the changed area, then run the full check before calling a milestone done:

```bash
python -m pytest tests/test_contracts.py -q
python -m pytest tests/test_quick_smoke.py -q
conda run -n aiplane scripts/check.sh
```

For docs-only contributor/security changes, also run a Markdown sanity check for local links and fenced code blocks if available.

## Preferred Read-Only Workflows

- Use `aiplane pick --intent chat` for one local choice; use `aiplane recommend` for the complete rationale.
- Use `aiplane runtimes inventory RUNTIME` to distinguish runner-reported installed/served IDs from profile aliases.
- Use `aiplane runtimes capacity-plan RUNTIME --model MODEL_ALIAS` before changing context, parallelism, cache, or offload settings.
- Use `aiplane benchmarks calibration-plan` and preview-first calibration export/import for repeatable measurement evidence.
- Use `aiplane models handoff-plan --role ROLE --model MODEL_ALIAS --runtime RUNTIME` to compose routing, calibration status, capacity, client, and optional agent handoffs without applying them; validate a saved artifact with `aiplane models handoff-validate PATH`.
- For external agent frameworks, export `guardrails.py`, follow the framework starter’s `guardrail_integration` guidance, and set `AIPLANE_GUARDRAILS_RECEIPT_PATH` only when a secret-free local receipt is wanted. Inspect it with `aiplane agents guardrails receipt PATH`.
- Use `aiplane models list --machine-file PATH` for a read-only named-machine simulation; do not mistake a fixture for target-host discovery.

## MCP Guidance

MCP should mirror useful inspection, planning, recommendation, and export surfaces by delegating to existing managers. Keep mutation narrow, audited, and guarded. When adding an MCP tool:

1. Add it to the advertised tool list.
2. Add an input schema.
3. Delegate to the existing manager method.
4. Add focused schema and behavior tests.
5. Update command coverage, backlog, skill guidance, and user docs when user-visible.

## Skill Versus MCP

Use MCP for structured tool calls into a live `aiplane` workspace. Use this skill for assistant workflow guidance: what to read, what boundaries to preserve, which commands to prefer, and how to keep docs/tests aligned. The skill should not duplicate every CLI reference; use repository docs as the source of truth.
