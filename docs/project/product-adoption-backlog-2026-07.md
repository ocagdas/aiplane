# Product, Adoption, and Monetization Backlog — July 2026

This backlog evaluates `/home/ocagdas/Downloads/aiplane_mvp_0_5_product_review_and_adoption_plan.md` against the current repository and test suite. It is the persistent follow-up list for that review; do not rerun the whole analysis merely to recover priorities.

## Evaluation

The review identifies the right primary product: an AI environment doctor and configuration compiler for reproducible local and hybrid development. Its scope warning is well founded. The code already has disciplined boundaries, a decomposed CLI, atomic persistence, guarded MCP writes, sanitized errors, synthetic external-I/O tests, and explicit advanced-command categorization, so recommendations that assume those are absent are now stale.

Accepted recommendations:

- lead with discovery, doctor, recommendation, deterministic export, profiles, provenance, compatibility, and drift;
- freeze breadth until installation/onboarding and external beta evidence are credible;
- publish normal package installation, a platform matrix, profile schema/versioning, stable doctor/export contracts, adapter tiers, clean-machine demonstrations, and a threat model;
- keep advanced runtime, stack, agent, benchmark, orchestration, deployment, and MCP mutation surfaces subordinate and explicitly maintained;
- keep the useful individual/local core open and validate services before central software monetization.

Accepted with modification:

- do not delete advanced code merely to simplify marketing; retain it behind advanced/experimental status while it has tests and a clear owner, then remove only on evidence of maintenance cost without use;
- do not promise identical hardware discovery on every OS. Promise portable profile/doctor/export behavior and report platform-specific probe coverage explicitly;
- do not add telemetry by default. Use opt-in telemetry or structured beta reports with a documented privacy contract;
- profile migration/backward compatibility begins when the first public schema version is declared; the project is still pre-stable and should not preserve accidental interfaces.

Rejected or gated:

- a general AI control plane, hosted model gateway, inference resale, GPU marketplace, proprietary runtime, coding agent, broad infrastructure service, and secret store remain outside the product boundary;
- central registry, fleet inventory, organization policy, approvals, signed profiles, SSO/SCIM, SIEM, and long-retention audit are commercial discovery targets, not near-term implementation commitments;
- market-size and competitor claims in the review need current external validation before they drive engineering decisions.

## Prioritized Engineering and Adoption Backlog

### P0 — Developer preview coherence

1. **DOC-1: repair public documentation contracts — completed.** Remove/fill the empty README workflow heading, correct workflow numbering, replace invalid bare export examples, align maturity language, and add command/link/code-block checks. Completion: public examples execute in CI where safe and README, package metadata, help, strategy, and launch review agree.
2. **Positioning and default-help pass — completed.** Lead with “environment doctor and configuration compiler”; visually separate core, advanced, and experimental commands without removing tested functionality. Completion: first-screen README/help explains one outcome and one next command. Validation: focused suite 30 passed; quick gate 18 passed; full suite 426 passed.
3. **Standard installation and release channel — implementation completed; first release tag is maintainer-controlled.** Validate `pipx`, `uv tool`, and normal `pip` installation from a built wheel on Linux, macOS, and Windows; document upgrade/uninstall. Completion: evaluation requires no repository clone. GitHub Release wheels are the declared no-clone channel; CI validates `pip`, `pipx`, and `uv tool` lifecycle on Linux, macOS, and Windows, and tag publication is gated on version agreement plus artifact validation. Validation: focused packaging/contract suite 16 passed; real final-wheel pip, pipx, and uv lifecycles passed; quick gate 19 passed; full suite 427 passed.
4. **Platform CI matrix — implementation completed; cross-OS runner execution occurs in CI.** Enforce [platform-support.md](../user/platform-support.md) with synthetic unit tests plus Linux/macOS/Windows package smoke jobs. Completion: promised portable commands run and unsupported mutations return `unsupported_platform` before executing host commands. The installed-wheel smoke runs from clean temporary workspaces through pip, pipx, and uv on Ubuntu, macOS, and Windows; synthetic platform tests cover Ubuntu, Debian, Fedora, WSL, macOS, and Windows. Validation: focused platform/remote suite 79 passed; real Linux final-wheel lifecycle passed through all three installers; quick gate 19 passed; full suite 434 passed.
5. **Quickstart sufficiency and idempotence — completed.** No manual YAML for first success, at most two choices, preserve manual edits, and provide a useful no-runtime plan. Completion: clean-machine fixtures reach one exact action, configured profiles reach one exact export/verification action, provider discovery is explicit, and reruns preserve profile edits byte-for-byte. External trials remain tracked under P1 item 10. Validation: focused quickstart suite 6 passed; quick gate 19 passed; full suite 436 passed.
6. **Stable doctor contract — completed.** Version findings with severity, reason, impact, remediation, affected resource, mutation/dry-run status, and exit-code semantics. Completion: every blocker has a deterministic non-placeholder next action; every finding follows contract v1; the payload is authoritative for exit behavior; focused contract and CLI tests enforce the schema. Validation: focused doctor/contract suite 29 passed; focused doctor/help suite 19 passed; quick gate 19 passed; full suite 438 passed.
7. **Tier-1 deterministic exports — implementation completed; cross-OS execution occurs in CI.** Release-blocking support is limited to Continue, Aider, generic OpenAI-compatible, and generic MCP. Completion: v1 golden files freeze all four outputs; the installed-wheel Linux/macOS/Windows matrix validates each format and performs a real MCP initialize and tools-list exchange. Advanced exporters remain available but unversioned. Validation: focused export/contract/packaging suite 51 passed; installed-wheel pip lifecycle passed locally; full suite 449 passed.
8. **Public profile schema v1 — completed.** Canonical `profiles render` output carries schema version 1.0; `profiles schema` exposes the packaged dependency-free JSON Schema; deterministic merge semantics, validation paths/remedies, and the explicit pre-1.0 migration policy are documented and tested. External validators can check rendered profiles without importing Aiplane. Validation: focused schema/profile/packaging suite 27 passed; full suite 449 passed.
9. **Practical threat model — completed.** Credential references, redaction limits, generated-config leakage, shell helpers, MCP guards, tunnel ownership, profile trust, and audit sensitivity are mapped to deterministic tests and explicit residual limitations in [the threat model](threat-model.md). Validation: focused security suite 62 passed; full suite 449 passed.

**P0 completion gate.** P0 closes only when both gate requirements pass:

- **Three reproducible demonstrations:** Local Ollama coding, laptop-to-remote-GPU, and local-only/privacy-policy workflows. Completion: independent users reproduce each from a clean environment.
- **Final README and documentation consistency sweep:** Re-read README, package metadata, top-level and core-command help, user documentation entrypoints, examples, strategy, launch review, and roadmap after P0 items 4-9 are complete. Remove stale breadth, maturity drift, duplicated guidance, and any claim not backed by a tested workflow. Completion: one coherent product promise, command hierarchy, installation path, and maturity statement across every public entrypoint. Re-run public example, link, help, and contract checks after the sweep. This sweep is run once after items 8-9 and must be repeated after the user-testing demonstrations; the interim pass does not close this gate. Interim focused documentation/help/schema/export/packaging gate: 76 passed; full suite: 449 passed.

### P1 — Prove repeated value

10. Run the six clean-environment trials already defined in the public demo plan and record failures by stage.
11. Recruit external design partners, targeting ten unaided successful onboardings before public beta.
12. Measure opt-in activation and recurrence: first useful export, second integration, profile replay, seven/thirty-day return, and support points.
13. Implement profile comparison and current-environment drift detection with deterministic provenance-aware explanations.
14. Import a narrow subset of Continue/Aider configuration into an unapproved draft profile without copying secrets.
15. Publish provider/runtime/client support tiers, upstream versions, owners, and maintenance expectations.
16. Define a contributor adapter protocol with reusable fixtures and contract tests.
17. Establish pre-1.0 releases, changelog/upgrade notes, signed artifacts where practical, and rollback instructions.
18. Make provenance and recommendation uncertainty consistent across discover, doctor, recommend, profile show, and export planning.
19. Decide the public future of stacks through observed user tests; simplify, keep advanced, or remove from the public model based on evidence.

### P2 — Differentiated core after adoption evidence

20. Calibrate compatibility/recommendation rules against measured runs and clearly separate hard constraints, provider metadata, estimates, user scores, benchmarks, and policy.
21. Complete remote-workstation replay from two client machines, including drift and policy checks.
22. Keep policy local and small: allow, warn, approval-required, and block, consistently enforced across CLI, doctor, recommendation, export, and MCP.
23. Maintain a neutral, versioned compatibility knowledge base separable from shell execution.
24. Create a maintenance budget for advanced/experimental surfaces and archive those without use or ownership.

## Monetization Validation Track

### M0 — Services now, without weakening open source

- Package a fixed-scope “Local and Hybrid AI Development Environment Standardisation” engagement: inventory, compatibility report, approved profiles, Continue/Aider exports, remote endpoint plan, repository privacy policy, CI doctor checks, team documentation, and up to two adapters.
- Validate pricing through real proposals and paid discovery, not generic SaaS benchmarks.
- Track whether customers pay for repeatability/governance or only installation help; this determines product direction.
- Keep discovery, profiles, validation, doctor, recommendation, deterministic exports, drift, basic local policy/audit, and community adapters fully useful in open source.

### M1 — Paid team prototype, gated

Start only after two organizations replay approved profiles across at least three machines and request paid central governance. Candidate scope: central profile registry/history/promotion, shared templates/policy, approvals, fleet/drift reporting, central audit, signed profiles, and integration compatibility management.

Go gate: two paid pilots or signed intent, named budget owners, recurring governance need, and delivery without becoming a gateway or infrastructure platform.

### M2 — Enterprise, later and evidence-led

Potential self-hosted registry/control service, SSO, SCIM, SIEM export, air-gapped updates, signed policy/profile bundles, retention, compliance evidence, private adapters, and support agreements. None is scheduled until M1 proves demand.

## Product Metrics and Decision Gates

North star: approved profiles successfully replayed on more than one machine and used by more than one external integration.

Developer-preview exit: standard install works; five unaided external users complete the main workflow; one integration is verified on Linux, macOS, and Windows; doctor/export contracts are stable; docs match behavior; no critical unsafe mutation or secret leak is open.

Team-product gate: two teams use the same approved setup across at least three machines, use drift in practice, and explicitly request shared policy, approval, registry, or audit.

Decision outcomes:

- activation plus replay/return supports the profile/compiler thesis;
- activation without return suggests a setup/service product unless drift and CI create recurrence;
- policy/audit demand supports a governance commercial wedge;
- consultancy-only demand supports a professional delivery accelerator;
- installation failures mean market conclusions are premature;
- no cross-tool value means narrow to diagnostics/compatibility or stop broad investment.
