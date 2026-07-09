---
name: aiplane
description: Work safely in the aiplane repository and CLI. Use when Codex is asked to modify, review, test, document, or plan aiplane features involving profiles, providers, models, runtimes, machines, stacks, MCP tools, integrations, security/contributor docs, or roadmap/handoff updates.
---

# aiplane

Version: 0.1.0

## Operating Boundary

Treat `aiplane` as a control-plane CLI. It plans, checks, prepares, and exports configuration for AI development environments. It must not become a coding agent, model runtime, model proxy, IDE extension, hidden cloud deployment engine, or broad MCP shell executor.

## First Steps

1. Read `docs/project/agent-guidance.md` before changing files.
2. Check `git status --short --untracked-files=all` and avoid reverting user changes.
3. Read the relevant user docs, command coverage, roadmap, and handoff before changing behavior.
4. Prefer existing managers and CLI patterns over new parallel logic.

## Change Rules

- Keep behavior, docs, roadmap/handoff, command coverage, MCP surfaces, and tests aligned.
- Add or update tests for behavior changes unless there is a clear engineering reason not to; tests should prove real behavior, contracts, regressions, or failure modes rather than increase counts; still run focused tests.
- Keep tests deterministic and avoid live cloud/provider/runtime dependency unless mocked or explicitly requested.
- Use plan, doctor, dry-run, and export flows before mutation.
- Do not expose runtime installs, model pulls, cloud apply, secret writes, or arbitrary shell execution through MCP unless explicit guardrails exist.
- Keep credentials in ignored local files or environment variables; never add real secrets to tracked files.

## Common Validation

Run focused tests for the changed area, then run the full check before calling a milestone done:

```bash
conda run -n aiplane python -m pytest tests/test_contracts.py -q
conda run -n aiplane python -m pytest tests/test_mvp.py -k "keyword_for_change" -q
conda run -n aiplane scripts/check.sh
```

For docs-only contributor/security changes, also run a Markdown sanity check for local links and fenced code blocks if available.

## MCP Guidance

MCP should mirror useful inspection, planning, recommendation, and export surfaces by delegating to existing managers. Keep mutation narrow, audited, and guarded. When adding an MCP tool:

1. Add it to the advertised tool list.
2. Add an input schema.
3. Delegate to the existing manager method.
4. Add focused schema and behavior tests.
5. Update command coverage, handoff, and user docs when user-visible.

## Skill Versus MCP

Use MCP for structured tool calls into a live `aiplane` workspace. Use this skill for assistant workflow guidance: what to read, what boundaries to preserve, which commands to prefer, and how to keep docs/tests aligned. The skill should not duplicate every CLI reference; use repository docs as the source of truth.
