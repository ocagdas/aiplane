# Doctor output contract v1

`aiplane doctor` is a read-only readiness check. Its JSON output is a public, versioned contract intended for CI, scripts, and support tooling. The current `contract_version` is `1.0`.

Every finding lives in `sections[].checks[]` and has:

- `id`: stable `<section>.<check-name>` identity;
- `severity`: `blocking`, `advisory`, or `pass`;
- `reason`: what was observed;
- `impact`: why the finding matters;
- `affected_resource`: profile, resource type, and resource name;
- `remediation.command`: the deterministic next CLI action, or `null` for a passing finding;
- `remediation.mutation`: `none`, `read_only`, or `mutating`;
- `remediation.mutates`: machine-readable boolean equivalent;
- `remediation.dry_run_supported` and `dry_run_command`: whether and how a mutation can be previewed.

The top-level `outcome` and `exit_code` are authoritative:

| Outcome | Exit code | Meaning |
| --- | ---: | --- |
| `healthy` | 0 | All findings pass. |
| `advisory` | 1 | There are advisory findings but no blockers. |
| `blocking` | 2 | At least one blocking finding exists. |

`ok` means there are no blockers; an advisory-only result therefore has `ok: true` and exit code 1. The complete mapping is also embedded in `exit_codes`, so consumers do not need to infer semantics from counts.

```bash
aiplane doctor --profile local-dev --format json
```

Doctor never applies remediation. Review the reported command and, when `dry_run_supported` is true, run `dry_run_command` before approving a mutation.
