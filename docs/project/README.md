# Project Notes

This folder contains contributor-facing and planning material. End-user docs live
under `docs/user/`.

- [Strategy](strategy.md): product boundary, architecture scope, and strategic direction.
- [Project Roadmap](roadmap.md): implemented, in-progress, planned, and deferred work.
- [Command Coverage](command-coverage.md): public CLI surface, status, and release-review notes.
- [Public Launch Review](public-launch-review.md): release-readiness checklist and terminology guardrails.
- [Public Demo Plan](public-demo-plan.md): three-minute demo narrative, command flow, readiness gates, and immediate next steps.
- [Integration Roadmap](integrations-roadmap.md): IDE/CLI/MCP integration direction and status.
- [Release Process](release-process.md): versioning, artifact validation, GitHub Release publication, and package-index gate.
- [Development Guide](development.md): contributor setup, tests, and output conventions.
- [Agent Guidance](agent-guidance.md): master instructions for Codex, Copilot, Claude, Cursor, and other coding assistants.
- [Practical Threat Model](threat-model.md): tested security controls, trust boundaries, and explicit residual limitations.

The product boundary is intentionally narrow: `aiplane` is an environment doctor and configuration compiler, not another coding agent or IDE assistant.
