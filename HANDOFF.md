# Maintaining aiplane safely

Read [README.md](README.md), [PURPOSE.md](PURPOSE.md), [STATUS.md](STATUS.md),
[TODO.md](TODO.md) and [VALIDATION.md](VALIDATION.md). Inspect Git status and preserve
unrelated changes before editing. This file owns resumption conventions, not a backlog.

[AGENTS.md](AGENTS.md) points to the authoritative
[agent guidance](docs/project/agent-guidance.md). Follow its prohibition on assistant
commits, pushes, tags, release publication and PR creation. The owner performs them.
Keep private strategy notes private and use isolated fixtures without real credentials.

[CI.md](CI.md) owns checks; [VERSIONING.md](VERSIONING.md) owns release policy;
[REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) owns shared interfaces.
Update the owning docs with behavior changes and record actual validation scope.
Local Linux evidence does not qualify hosted CI or other operating systems.
No runtime or CI job may depend on a sibling checkout.
