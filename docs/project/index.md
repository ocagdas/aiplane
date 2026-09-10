# Project Notes

This folder contains contributor-facing and planning material. End-user docs live
under `docs/user/`.

- [Strategy](../../PURPOSE.md): product boundary, architecture scope, and strategic direction.
- [Unified Project Plan](project-plan.md): navigation to the authoritative status, validation, roadmap, backlog, domain design, trial evidence, demo and agent guidance.
- [dev/mvp_0.5 Latest Review Evaluation](reviews/dev-mvp-0.5-latest-review-evaluation.md): accepted, modified, stale, and deferred findings from the external review.
- [CI](../../CI.md) and [Versioning](../../VERSIONING.md): required jobs, automated versioning, artifacts and publication.
- [Published Release Verification](../../.github/workflows/verify-release.yml): hosted Linux/macOS/Windows no-clone evidence workflow.
- [Repository Protection](repository-protection.md): stable required check and hosted ruleset requirements.
- [CI Wheel Artifacts](ci-wheel-artifacts.md): versioned post-merge wheels for no-clone prerelease testing.
- [Development Guide](../development/setup.md): contributor setup, tests, and output conventions.
- [Agent Guidance](agent-guidance.md): master instructions for Codex, Copilot, Claude, Cursor, and other coding assistants.
- [Practical Threat Model](threat-model.md): tested security controls, trust boundaries, and explicit residual limitations.

The product boundary is intentionally narrow: `aiplane` is an environment doctor and configuration compiler, not another coding agent or IDE assistant.
