# Maintaining aiplane safely

Read [README.md](README.md), [PURPOSE.md](PURPOSE.md), [STATUS.md](STATUS.md),
[TODO.md](TODO.md) and [VALIDATION.md](VALIDATION.md). Inspect Git status and preserve
unrelated changes before editing. This file owns resumption conventions, not a backlog.

For the current development phase, read [AP0–AP6](ROADMAP.md#current-development-plan--2026-10-17) and the [task checklist](TODO.md#current-development-checklist). AP0/AP1 are complete locally; AP3 is complete locally with fixed-output review and the 20-case grading example (see VALIDATION for checks). AP2 is removed by owner direction; AP3 is narrowed to external result use and task review through existing interfaces. Do not recreate a generic runner framework. Start at the first incomplete milestone; do not substitute the older adoption/expansion lists for this execution order. Keep benchmark protocol work advanced/experimental and preserve the independent CAS/CIK boundaries.

[AGENTS.md](AGENTS.md) points to the authoritative
[agent guidance](docs/project/agent-guidance.md). Follow its prohibition on assistant
commits, pushes, tags, release publication and PR creation. The owner performs them.
Keep private strategy notes private and use isolated fixtures without real credentials.

[CI.md](CI.md) owns checks; [VERSIONING.md](VERSIONING.md) owns release policy;
[REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) owns shared interfaces.
Update the owning docs with behavior changes and record actual validation scope.
Local Linux evidence does not qualify hosted CI or other operating systems.
No runtime or CI job may depend on a sibling checkout.
