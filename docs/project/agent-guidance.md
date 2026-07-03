# Agent Guidance

This is the master project guidance file for coding agents and IDE assistants working on `aiplane`. Tool-specific instruction files should point here instead of duplicating policy.

## Product Boundary

`aiplane` is an AI control-plane CLI for self-managed and managed LLM development environments. It configures, checks, plans, and exports profiles, providers, models, runtimes, machines, stacks, IDE/MCP snippets, and supporting tools.

It must not become a coding agent, model runtime, model proxy, IDE extension, or hidden cloud deployment engine.

## Open Source Quality Bar

Treat `aiplane` as a public open-source project that should be worthy of trust, adoption, and contribution. Keep code, documentation, roadmap, implemented features, command coverage, handoff notes, examples, and tests aligned and held to a high standard. Do not let the project drift into a collection of impressive but undocumented, untested, or overstated capabilities.

## Local Direction Notes

If `docs/project/.strategy/` exists in the working tree, read its notes before making roadmap, positioning, release-readiness, or strategy changes. That folder is intentionally gitignored local context; use it for alignment, but do not copy private/local-only positioning details into tracked public docs unless the human owner explicitly asks.

## Required Maintenance Habit

When changing behavior, update these together in the same change whenever relevant:

- user docs under `docs/user/`;
- project docs under `docs/project/`;
- `docs/project/roadmap.md` for implemented/planned status;
- `docs/project/session-handoff.md` for current handoff state;
- `docs/project/command-coverage.md` for public CLI coverage;
- tests in `tests/test_mvp.py` or a focused new test file.

Behavior changes should normally land with matching test updates in the same change. If a behavior change genuinely does not need a new or changed test, make that an explicit engineering decision and still run the relevant focused tests. Do not leave roadmap, handoff, command coverage, or tests stale after adding commands, changing defaults, or moving a feature between planned/in-progress/implemented.

## Compatibility Policy

`aiplane` has not been deployed or released as a stable public interface yet. Until the human owner says otherwise, do not add backward-compatibility shims, deprecated aliases, or legacy behavior solely to preserve older local commands. Prefer the clean current interface, and keep README, user docs, command coverage, roadmap/handoff notes, and tests aligned with that interface.

## Implementation Rules

- Coding tools and assistants must never commit, push, tag, publish releases, or open PRs from this repository. They may inspect `git status`/`git diff` and prepare changes; the human owner performs all git write/publish operations.
- Treat secret sanitation as a release blocker: before finalizing, scan changed files for API keys, tokens, passwords, private keys, personal data, and tenant/account identifiers. Never add real secrets to tracked files; use ignored local credentials and env-var references instead.
- Prefer plan, doctor, dry-run, and export flows before mutating hosts, runtimes, or cloud accounts.
- If `apply_patch` fails with the sandbox loopback error (`bwrap: loopback: Failed RTM_NEWADDR`), do not retry it repeatedly. Use a narrow scripted edit for the specific file/block instead, document what changed, and keep the edit scoped to the intended conflict or behavior change.
- Keep generated/cache/local files out of git: `.aiplane/`, generated model caches, PID/log files, and runtime state must remain ignored.
- Test thoroughly but realistically. Add tests for behavior, contracts, regressions, and realistic failure modes; do not add tests merely to increase counts. Keep tests deterministic, isolated from the developer machine where possible, and mindful of suite runtime.
- Preserve the distinction between provider/model source, runtime, runtime endpoint, profile model alias, machine, stack, integration export, MCP tool surface, and agent skill guidance.
- During pre-PR merge cleanup, tidy-up, release review, or a recurring MCP/skills synchronization checkpoint, audit the public CLI/options against docs, command coverage, MCP tools, planned/implemented agent skills, and tests. These checkpoints should happen periodically, not continuously after every feature and not at every regular milestone. Bring MCP and skills into sync where appropriate, explicitly leave risky operations out of MCP/skills when guardrails are not ready, and run or add focused tests for the synced surface.
- Managed providers such as OpenAI, Anthropic, Azure OpenAI, and Ollama Cloud are sources/endpoints; they become useful to tools through profile-owned model entries in `models.yaml`.
- Do not make broad cloud apply, arbitrary shell execution through MCP, secret writes, or IDE file edits implicit.
- Use official external tools instead of reimplementing their domain: Docker/Compose, OpenSSH, Azure CLI, OpenTofu/Terraform/Pulumi, Vagrant, Packer, Dev Container CLI, Ansible, kubectl, and Helm.
- OpenTofu is the default provider-agnostic IaC direction; Terraform is supported for teams standardized on it; Pulumi is optional for language-native IaC.
- Packer builds images; Vagrant runs local dev VMs from boxes/images. They complement each other.

## Validation Expectations

Before claiming a release-ready or beta-ready state, run the focused smoke checks that match the change plus the full test suite:

```bash
PYTHONPATH=src python -m aiplane profiles validate local-dev
PYTHONPATH=src python -m aiplane environment doctor --required-only
PYTHONPATH=src python -m aiplane environment doctor --required-only --format json
PYTHONPATH=src python -m pytest
```

For tool, provider, integration, or stack work, also run representative CLI commands and update the handoff with the latest successful validation summary.

## Documentation Tone

Docs should be practical and explicit: what the command does, what it does not do, which files it reads/writes, and what users should run next. Avoid implying that exports install tools, edit IDE settings, start cloud resources, or bypass runtime/provider authentication.
