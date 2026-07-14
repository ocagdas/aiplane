# External Trial Evidence

Use one sanitized JSON record for every P0 workflow rehearsal and independent-user trial. Copy [`trial-evidence/template.json`](trial-evidence/template.json), fill every field, and validate it before sharing:

```bash
python scripts/validate_trial_evidence.py path/to/trial.json
```

The record separates `rehearsal` from `independent` evidence. A maintainer rehearsal can verify commands and timing, but it cannot close the independent-user gate.

## Recording rules

- Use a pseudonymous trial ID; never record names, email addresses, organizations, personal paths, private hosts, tenants, subscriptions, account IDs, credentials, or tokens.
- Identify the immutable release URL, package version, SHA-256, and full source commit. An unpublished rehearsal may use `null` for the URL, but cannot count as published-release evidence.
- Record OS/version/architecture, Python, installation owner, runtime/model, clean start state, and whether a checkout was present.
- Record commands in order with elapsed seconds, exit status, outcome, and relative written paths.
- Record the first failure once with its stage, command index, category, and sanitized summary. Use `null` when nothing failed.
- State whether assistance exceeded the written workflow, whether written files and non-mutating export were understood, and concise sanitized feedback.
- Set every sanitization assertion only after human review. Automated validation is an additional guard, not a substitute.

Allowed workflows are `primary-adoption`, `local-only-replay`, `remote-gpu`, and `no-clone-install`. A demonstration counts only when classification is `independent`, completion is true, clean-start facts are accurate, and the published immutable artifact is referenced. Keep failed and assisted trials: they are evidence, not discarded attempts.

Store records outside the repository until publication consent is established. Sanitized records approved for tracking belong under `docs/project/trial-evidence/records/`.
