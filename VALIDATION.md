# Current validation

[CI.md](CI.md) owns check commands; [STATUS.md](STATUS.md) owns capabilities.

## Current working-tree validation

On 12 September 2026, the review changes based on `9b25137362e079c35371c7aff98998e5acb98bd8` passed local Linux validation:

- `make check`: formatting, Ruff, shared repository conformance, and **927 passed, 9 opt-in skips**, using four file-scheduled workers. Log: `/tmp/aiplane-review-check.log`; JUnit: `/tmp/aiplane-review-tests.xml`.
- Packaging regression builds an sdist, builds its wheel, and installs into an isolated environment. Every published documentation path is listed and readable through MCP from an unrelated workspace; complete skill files are present and private strategy files excluded.
- Real pip, pipx, and uv installation, replacement, and uninstall checks passed, including MCP stdio documentation reads and matching CLI/server versions. Log: `/tmp/aiplane-review-channels.log`; built artifacts: `/tmp/aiplane-review-dist`.
- Profile validation and required-only environment doctor passed in text and JSON with temporary shipped profiles. Logs: `/tmp/aiplane-review-profile.log`, `/tmp/aiplane-review-doctor.log`, `/tmp/aiplane-review-doctor-json.log`.
- Skill validation, changed-document local links, patch whitespace checks, and a credential-pattern scan passed. HTTP metadata tests use synthetic transports; no live provider requests were required.

These are uncommitted working-tree results. Windows/macOS and hosted publication checks have not run on this patch. The existing OS/channel workflow will exercise the expanded installed-help checks when the owner publishes the branch. The earlier hosted results below remain baseline evidence only.

## Earlier qualified revision

On 11 September 2026, commit `b843589b331716fbc7e2f799ebc3c7a40db257f6`
passed local and hosted validation. The working tree was clean when testing began;
the only subsequent changes from this task update validation evidence and the backlog.

- Local Linux/Python 3.13.14: `make check` passed formatting, Ruff, shared conformance
  and the isolated-profile suite: **918 passed, 9 opt-in skips**. Tests used four
  file-scheduled workers. Log: `/tmp/aiplane-current-check.log`; JUnit:
  `/tmp/aiplane-current-tests.xml`. Declared dependencies were installed in the
  disposable `/tmp/aiplane-validation-env` environment. An initial missing Ruff
  executable in that environment was corrected before the successful run.
- [Branch-push CI](https://github.com/ocagdas/aiplane/actions/runs/34653187556)
  and [pull-request CI](https://github.com/ocagdas/aiplane/actions/runs/34653190347)
  both succeeded. The push run's `quality-gate/ci-gate.json` reports `go=true` for
  the exact commit and run ID; `scripts/verify_quality_evidence.py` verified it.
- Hosted Linux/Python 3.11: **917 passed, 10 skipped**, plus formatting, Ruff,
  shared conformance, workflow-pin validation and checksum-pinned actionlint 1.7.12.
  The additional skip requires ripgrep, which was unavailable on that runner;
  that test passed locally. Hosted Python 3.12 and 3.13 compatibility checks each
  passed **40 tests**, including actual wheel packaging checks.
- All **nine OS/channel combinations** passed real wheel installation, replacement
  and uninstall: Linux, macOS and Windows, each using pip, pipx and uv. These are
  CI-built wheel checks, not verification of published release downloads.
- Opt-in synthetic catalog benchmarks at 1k, 10k and 100k entries: **3 passed**.
  Log: `/tmp/aiplane-current-performance.log`; JUnit:
  `/tmp/aiplane-current-performance.xml`.
- Opt-in installed external validators: **1 passed, 5 skipped**. Ansible inventory
  and playbook syntax validation passed. OpenTofu, Terraform, Packer and Pulumi
  were unavailable; VirtualBox's kernel module was not loaded. Log:
  `/tmp/aiplane-external-validators.log`.
- Profile validation and required-only environment doctor in text and JSON formats
  passed with temporary shipped profiles. No live credentials or provider requests
  were needed. Local smoke logs: `/tmp/aiplane-current-profile.log`,
  `/tmp/aiplane-current-doctor.log`, `/tmp/aiplane-current-doctor-json.log`.

## Earlier public baseline

The public [v0.2.0 release](https://github.com/ocagdas/aiplane/releases/tag/v0.2.0) has a wheel, source archive, and checksum manifest. An earlier [published-release verification run](https://github.com/ocagdas/aiplane/actions/runs/29414203549) passed all nine OS/channel jobs. This establishes earlier public-path evidence, not qualification of the current publication implementation or this working tree.

## Unverified scope

Exact-tag reusable release qualification, App version publication, live providers,
published asset attestations and independent-user trials remain separate gates.
The version job was intentionally skipped on the development branch and PR; these
successful runs do not establish publication readiness. The five unavailable external
validators remain unqualified. See [TODO.md](TODO.md) and
[hosted setup](docs/development/github-policy-setup.md).

No commits, pushes, tags or releases were performed by this task.
