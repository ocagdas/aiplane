# dev/mvp_0.5 Latest Review — Evaluation

This decision record evaluates the July 2026 external report titled “Aiplane dev/mvp_0.5 Latest Review” against the repository after the demo-plan and test-performance updates. It preserves the useful conclusions without depending on a maintainer-local Downloads path.

## Accepted

- External user evidence, not more internal feature breadth, is the principal developer-preview blocker.
- The first published release and installation from its public artifacts remain maintainer-controlled release gates.
- Checks must be mandatory for changes reaching the release path.
- Trial evidence should identify commit, platform, installation channel, runtime, commands, failures, assistance, and outcome.
- Profile comparison and current-environment drift are the strongest candidates for recurring P1 value.
- The v1 schema should become more specific using real profiles and failure evidence rather than speculative constraints.
- Advanced surfaces must remain subordinate until user evidence justifies their public cost.

## Accepted with modification

- The old broad engineering demo criticism was valid, but the current plan has already removed the stale MVP-version, agent, orchestration, Azure, deployment, and broad MCP walkthrough. The remaining correction is hierarchy: one primary public adoption cut should show only quickstart, discover, doctor, recommend, and Continue export. Privacy/replay and remote-GPU recordings remain P0 workflow-validation videos, not co-equal introductory product stories.
- Do not add `dev/mvp_0.5` permanently to CI triggers. Require protected checks for pull requests reaching `main` and for release publication; feature-branch CI may be added temporarily by maintainer policy but is not the durable contract.
- Checksums and signing are desirable for the first preview, but signing must use a maintainable trusted identity and must not be simulated merely to satisfy wording.

## Already addressed or stale

- README/package positioning, stable doctor/export contracts, platform behavior, the initial profile schema, security documentation, and offline-safe quickstart are implemented and tested.
- The public demo plan no longer contains the broad legacy engineering walkthrough described by the report.
- The review-source provenance problem is resolved by this tracked decision record and the backlog link to it.

## Deferred deliberately

- Drift, profile comparison, evidence-based schema tightening, adapter contracts, and support-tier publication remain P1 because they improve repeated value but are not prerequisites for learning from the first developer-preview users.
- Central governance, registry, fleet, signing infrastructure, and enterprise controls remain evidence-gated monetization targets.
