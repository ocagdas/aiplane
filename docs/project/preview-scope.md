# Developer-Preview Scope Freeze


Until the P0 gates close, the public promise remains the profile-driven environment doctor and configuration compiler workflow: quickstart preview, discovery, doctor, recommendation, policy explanation, and deterministic Tier-1 export.

No new integration, runner, orchestrator, stack, benchmark, deployment, MCP-write capability, or other advanced command may be promoted into README onboarding, package metadata, the primary demo, or the Core command category during this freeze. Existing tested advanced and experimental surfaces may receive security, correctness, compatibility, maintainability, and contract fixes.

### Exception process

An exception requires one tracked decision before implementation or promotion. It must state:

1. the observed external-user blocker or release defect;
2. why the existing core workflow cannot solve it;
3. the precise new public promise and affected commands;
4. security, platform, maintenance, documentation, and test costs;
5. success and removal criteria;
6. synchronized changes to strategy, roadmap, command coverage, help, and public documentation.

Convenience, speculative market breadth, or the existence of advanced code is not evidence for an exception. Without the decision record, the feature remains subordinate and must not enter the public adoption story.

Approved exceptions:

- [Host-client model exports](host-client-export-scope-exception.md) - Codex, Copilot CLI, and Copilot-in-VS-Code deterministic print-only exports.


### Bounded selection/evaluation development — revised 2026-10-18

[AP0–AP6](../../ROADMAP.md#current-development-plan--2026-10-17) owns the engineering sequence. AP0/AP1 are complete locally. The owner removed AP2 to avoid a custom wrapper protocol and external process manager. Preserve the existing standard model API paths, smoke/custom suites, command graders and data-only measurement import/comparison.

AP3 is narrowed to useful external results and manual task review. Run benchmark tools through their own CLI/API. Add a format converter only when an actual native result file demonstrates a need; no generic wrapper framework or mandatory pair of maintained launch adapters. Optional llmfit candidate input remains AP4. This is workflow/learning work, not a promotion into README onboarding, package metadata or the Core category.

Account for producer format/version maintenance and private prompt/output handling. Keep raw results and source/version identity. Do not install all evaluation dependencies into the base package or add a hidden executor through MCP.

Success/removal: apply AP0–AP6 exits. If an adapter cannot preserve native measurement semantics or supplies no useful result beyond import-only conversion, narrow it to conversion or remove it from the supported path; keep an optional learning fixture where useful. More adapters, a TUI, load-engine rewrite and benchmark services are outside this exception.
