# Adoption decisions

### Evaluation

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

