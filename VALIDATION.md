# Validation

## Follow-up review fixes — 11 September 2026

On the pending delta over a1d7f41, `credentials list` now redacts URL credentials and
notes while preserving useful account metadata. Disk catalog rows are validated for
numeric, capability, benchmark and collection shape before reuse; malformed values,
NaN/infinity and oversized numeric values trigger rebuilding from authoritative sources.

Actual full `make check`: **901 passed, 9 opt-in skips**, including formatting, lint,
shared conformance and public CLI/cache regressions. Log: /tmp/followup-aiplane-full.log.
Synthetic credentials and isolated profiles only; changed files contain no matched
credential signatures. Hosted qualification of the pending revision remains outstanding;
no commits, pushes, tags or publication were performed.

## Review fixes — 11 September 2026

The pending delta on a1d7f41 fixes option injection in read-only search, URL and
subscription-key credential handling, malformed derived catalog indexes, and direct
release-script imports. Tests exercise public import/archive paths before writes,
option-like search expressions and rebuilding corrupted indexes from source data.

- Actual `make check`: **890 passed, 9 opt-in skips**; formatting, lint and shared
  conformance passed. Log: /tmp/review-fixes-aiplane-full2.log.
- The first run found the versioning test loading a script outside its package
  context; the fixture now loads it as a scripts submodule from its own file root.
- No live credentials or providers were used. Synthetic credential values remain in
  fixtures only. Changed files were scanned for credential signatures; none found.

Existing hosted success for a1d7f41 does not qualify this pending delta. The owner
must perform real commits/pushes and obtain candidate CI under repository guidance.

All three pass shared managed-file hashes, actionlint and patch whitespace checks.
Shared bundle SHA-256: `f907247d239cad6cb98efda366a5ba8e9c409d1d56621e8ebf7abb693a17220b`. No commits, pushes, tags, releases or hosted
settings changes were made during this fix task.

## Final branch and consolidation review — 10 September 2026

Full make check passed: 878 tests, 9 opt-in skips. The subsequent focused contracts and shell regressions passed 46 tests, including all eight clean-runner/workflow shell cases. Logs: /tmp/unified-policy-aiplane-full.log and /tmp/unified-policy-final-contracts.log.

Final shared conformance, including master trunk selection and wrong-target rejection,
passed in all three repositories. Workflow actionlint and git diff whitespace checks
passed. The shared bundle is byte-identical; digest: `ad0044680cd3883efef6b358b8aa294554aa95a74f8016d4154d9339a9a28279`.
Aiplane's clean runner preserves real profiles and cleans temporary directories;
workflow regression tests cover failed PR lookup and per-artifact attestation loops.

GitHub readback confirms main/main/master trunks, active Quality gate and immutable
version-tag rules plus squash-only merges in Repo Pilot/aiplane. ACF remains private
on master; its plan denies private rulesets and repository-settings changes require
owner/admin access. Versioning is enabled only for aiplane; Repo Pilot/ACF need App
setup before enabling it. This supersedes earlier statements that no hosted settings
were changed. No real commits, pushes, branch renames, tags, secrets or releases were
created by this work. Current-candidate hosted CI, live App publication and hosted
attestation qualification remain outstanding. See docs/development/github-policy-setup.md.

## Current release consolidation evidence — 10 September 2026

Pending local working-tree delta. Real repository versions and refs were unchanged;
commits/tags/pushes in tests targeted disposable local fixtures only. Shared code,
provenance, conformance and post-publication verification are now integrated in all
three repositories; this supersedes earlier statements about pending adapter migration.

- Full pytest with /tmp/aiplane-consolidation-env/bin/python: **875 passed, 9 skipped**.
  Skips are opt-in external-validator/performance tests; they are not qualification.
  Log: /tmp/aiplane-release-full2.log. An initial run lacked jsonschema; the final
  disposable environment includes the declared dependency.
- Tagged wheel/source build, complete checksummed provenance and bound downloaded-
  artifact verification passed. Actual Linux pip, pipx and uv install, replacement
  and uninstall lifecycles passed with the built assets. Logs:
  /tmp/aiplane-release-artifacts.log and /tmp/aiplane-release-install.log. The first
  installation attempt lacked uv; the provisioned rerun passed all three channels.

All three pass shared conformance (including immutable bundle hashes, failed/skipped/
missing gate cases, classification, reruns and advanced-tip publication), actionlint
1.7.12 workflow structure/expression checks, and scoped formatting/lint. Documentation
and final gate wiring were checked after the artifact builds. Installed release assets
were local fixtures; no actual hosted download, attestation, App mutation, ruleset,
Windows/macOS run or release publication occurred. Hosted qualification remains open.

Earlier evidence below retains its original scope and does not supersede this entry.

## Community alignment validation — 10 September 2026

This is scoped evidence for the pending shared-documentation delta. Canonical root
document presence and exact common GitHub template/conduct parity passed across all
three repositories. actionlint 1.7.12 structure/expression checks and git diff --check
passed. Existing product evidence below retains its original scope.

The affected documentation contracts passed: `python -m pytest -q tests/test_contracts.py`
with /tmp/aiplane-release-env/bin/python: **38 passed**. This did not rerun the full
product suite or hosted release qualification.

Validated on Linux with Python 3.13.14, against the uncommitted standardization changes based on `ac0e02c60520e55ae1e58ae74923b526e10bf906`. The working tree has no committed revision yet. No repository commits, tags, pushes or publications were performed; Git publication tests used disposable synthetic repositories under `/tmp`.

- `PYTHONPATH=/tmp/aiplane-test-tools:src scripts/check.sh`: formatting and Ruff passed for source, tests and scripts; **875 passed, 9 opt-in skips**. The host lacked the declared `jsonschema==4.26.0` test dependency, so it was installed in a temporary dependency directory. An earlier full run's JUnit report is `/tmp/aiplane-standardization-junit.xml`; the final gate result is the count above.
- Focused version, publication, build, gate and documentation checks: **103 passed** after the final workflow edits. Coverage includes mirror synchronization, all bump kinds, invalid versions, stale-PR merge bases, tag collision, clean trees, exact source SHA, stale remote tips, atomic tag-race rejection and same-source reruns. Gate tests cover missing, failed, skipped, cancelled, malformed and additional failed dependencies. Artifact tests cover corruption, missing/unlisted files and portable path rejection.
- Checksum-verified **actionlint 1.7.11** passed all four workflows. ShellCheck integration was disabled; workflow expressions and reusable wiring were validated. The same pinned validator now runs in CI.
- `PYTHONPATH=src python -m aiplane profiles validate local-dev` and required-only environment doctor in text and JSON formats: passed.
- A disposable clean, tagged snapshot built the wheel and source through `scripts/build_release.py`. Canonical documentation and helpers were present in the source archive; private strategy notes were excluded. The real wheel passed Linux **pip, pipx and uv** install, replacement and uninstall verification, including packaged resources and MCP checks. Artifacts and logs are under the temporary directory recorded in `/tmp/aiplane-release-rehearsal-path`. Later changes affected helper hardening, checks and documentation, not packaged runtime behavior.
- Local documentation file/anchor checks and `git diff --check` passed. Changed-file secret sanitation found no credential values.

macOS/Windows hosted matrices, GitHub App operation, ruleset migration, immutable public assets/attestations and independent-user trials remain unverified. The nine skipped tests are opt-in performance or external-tool checks. These local results do not claim release-ready or beta-ready status. Remaining actions are maintained in [TODO.md](TODO.md).
