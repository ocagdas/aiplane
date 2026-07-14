# Product, Adoption, and Monetization Backlog — July 2026

This backlog incorporates the original product/adoption review and the tracked [dev/mvp_0.5 latest-review evaluation](reviews/dev-mvp-0.5-latest-review-evaluation.md). It is the persistent priority list; do not rerun the whole analysis merely to recover decisions.

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

1. **Separate the primary adoption cut from validation workflows — completed.** Keep one public introduction under three minutes and limited to `quickstart --dry-run`, `discover`, `doctor`, `recommend`, and `export continue`. Retain local-only/replay and remote-GPU recordings as P0 validation workflows, not co-equal introductory product stories. Completion: the plan, recording titles, narration, and public links preserve that hierarchy; advanced commands do not enter the adoption cut.
2. **Publish the first developer-preview release artifact — repository-ready; maintainer publication pending.** The repository now builds and validates the wheel/source distribution, emits and verifies SHA-256 checksums, uses versioned release notes, documents supported platforms and rollback, and gates release creation on the full quality suite. Create the maintainer-approved version tag and GitHub Release only after version agreement and release workflow success. Attach wheel and source distribution, SHA-256 checksums, release notes, supported-platform statement, upgrade/uninstall instructions, and rollback guidance. Signing is required only when backed by a maintainable trusted identity. Completion: a public immutable release URL exists and matches package metadata.
3. **Verify the public no-clone path — verifier ready; published cross-OS evidence pending.** The built-wheel lifecycle and canonical evidence format are implemented, but final evidence requires the published P0.2 artifact and hosted Linux/macOS/Windows runs. From clean machines with no repository checkout, install the published artifact through `pipx` and `uv tool` and exercise help, bootstrap, validate, discover, doctor, recommend, Tier-1 export, upgrade/replacement, and uninstall. Completion: Linux, macOS, and Windows evidence records the release URL, checksum, command results, and platform limitations.
4. **Make CI mandatory on the release path — repository implementation complete; hosted rule pending.** `CI / Release gate` aggregates the full quality, compatibility, and cross-OS install jobs, and exact protection requirements are documented. A maintainer must enable and verify the hosted ruleset. Protect changes reaching `main` and release tags with the full quality gate plus supported-OS installation jobs. Do not rely on a temporary feature-branch name as the durable policy. Completion: repository settings or an equivalent documented maintainer process names the required checks, and releases cannot publish before they pass.
5. **Standardize external-trial evidence — standard implemented; trial adoption pending.** The canonical JSON template, recording guidance, sanitizer/shape validator, and regression tests cover one sanitized record format for commit/version, OS, installation channel, Python/runtime/model, start state, commands, elapsed time, first failure, assistance, written files, final outcome, and participant feedback. Completion: every P0 workflow trial uses the same record and distinguishes rehearsal from independent completion.
6. **Freeze public breadth through the preview gate — completed.** The tracked freeze defines the allowed core promise, permitted maintenance work, and a six-part exception decision. Add no new public integration, runner, orchestrator, stack, benchmark, deployment, or MCP-write promise before the P0 gates close. Fix blockers and contract defects; keep tested advanced surfaces subordinate. Completion: any exception requires an explicit scope decision in strategy, roadmap, and command coverage.
7. **Keep review provenance portable — completed.** The maintainer-local review path is replaced by a tracked [evaluation and decision record](reviews/dev-mvp-0.5-latest-review-evaluation.md) that states accepted, modified, stale, and deferred recommendations.

**P0 completion gate.** P0 closes only when both gate requirements pass:

- **Three reproducible demonstrations:** Local Ollama coding, laptop-to-remote-GPU, and local-only/privacy-policy workflows. Completion: independent users reproduce each from a clean environment.
- **Final README and documentation consistency sweep:** Re-read README, package metadata, top-level and core-command help, user documentation entrypoints, examples, strategy, launch review, and roadmap after all numbered P0 work is complete. Remove stale breadth, maturity drift, duplicated guidance, and any claim not backed by a tested workflow. Completion: one coherent product promise, command hierarchy, installation path, and maturity statement across every public entrypoint. Re-run public example, link, help, and contract checks after the sweep. This sweep was run once after the earlier implementation milestones and must be repeated after the user-testing demonstrations; the interim pass does not close this gate. Interim focused documentation/help/schema/export/packaging gate: 76 passed; full suite: 449 passed.

### P1 — Prove repeated value

8. Implement profile comparison and current-environment drift detection with deterministic provenance-aware explanations.
9. Run the six clean-environment trials defined by the public demo plan and record failures by stage.
10. Recruit external design partners, targeting ten unaided successful onboardings before public beta.
11. Measure opt-in activation and recurrence: first useful export, second integration, profile replay, seven/thirty-day return, and support points.
12. Tighten detailed profile-schema contracts using real trial profiles and observed failures; do not make speculative fields rigid.
13. Import a narrow subset of Continue/Aider configuration into an unapproved draft profile without copying secrets.
14. Publish provider/runtime/client support tiers, upstream versions, owners, and maintenance expectations.
15. Define a contributor adapter protocol with reusable fixtures and contract tests.
16. Maintain pre-1.0 release notes, checksums/signing where practical, upgrade guidance, and rollback instructions.
17. Make provenance and recommendation uncertainty consistent across discover, doctor, recommend, profile show, and export planning.
18. Decide the public future of stacks through observed user tests; simplify, keep advanced, or remove from the public model based on evidence.

### P2 — Differentiated core after adoption evidence

19. Calibrate compatibility/recommendation rules against measured runs and clearly separate hard constraints, provider metadata, estimates, user scores, benchmarks, and policy.
20. Complete remote-workstation replay from two client machines, including drift and policy checks.
21. Keep policy local and small: allow, warn, approval-required, and block, consistently enforced across CLI, doctor, recommendation, export, and MCP.
22. Maintain a neutral, versioned compatibility knowledge base separable from shell execution.
23. Create a maintenance budget for advanced/experimental surfaces and archive those without use or ownership.

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
