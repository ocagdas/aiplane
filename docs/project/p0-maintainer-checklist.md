# P0 Maintainer Checklist

This checklist contains only actions that require GitHub administration, public publication, or independent participants. Repository-side automation and tests are handled elsewhere.

## 1. Activate repository protection

Follow [Repository Protection](repository-protection.md).

- [ ] Activate the `main` branch ruleset.
- [ ] Require `CI / Release gate` and an up-to-date branch.
- [ ] Require pull requests for human changes.
- [ ] Restrict force pushes and deletion.
- [ ] Add only the GitHub Actions app and designated maintainers to bypass; the Actions exception is required for the CI-owned version commit/tag.
- [ ] Activate immutable `v*` tag rules.
- [ ] Open a disposable PR, make its gate fail, and confirm merge is blocked.
- [ ] Save the ruleset URL or screenshot in private evidence.

Read-only confirmation:

```bash
gh api repos/ocagdas/aiplane/branches/main/protection
gh api repos/ocagdas/aiplane/rulesets --jq '.[] | {id, name, target, enforcement}'
```

## 2. Publish one complete developer-preview release

Choose the CI-created tag whose source you reviewed. In GitHub:

1. Open **Actions → Release artifacts → Run workflow**.
2. Enter the exact tag, for example `v0.1.2`.
3. Run from trusted `main`.
4. Open the resulting release and confirm it is not a draft.

The release must visibly contain:

- [ ] exactly one `aiplane-VERSION-py3-none-any.whl`;
- [ ] exactly one `aiplane-VERSION.tar.gz`;
- [ ] `SHA256SUMS`;
- [ ] a tag matching wheel metadata;
- [ ] install, platform, upgrade, uninstall, and rollback links or notes.

Do not count an empty release page as completion and do not replace assets under an existing published tag. Publish a new patch when correction is needed.

## 3. Verify the actual public assets

1. Open **Actions → Verify published release → Run workflow**.
2. Enter the published tag.
3. Wait for all nine Linux/macOS/Windows × pip/pipx/uv jobs.
4. Download the nine `release-evidence-*` artifacts.
5. Review records for private data and retain the approved copies with P0 evidence.

- [ ] Every job downloaded public release assets rather than rebuilding source.
- [ ] Every manifest verification passed.
- [ ] Every install/replacement/uninstall lifecycle passed.
- [ ] Evidence identifies the same URL, tag commit, version, and wheel digest.
- [ ] Platform limitations are consistent with `docs/user/platform-support.md`.

## 4. Run independent demonstrations

Give participants only the installed artifact and the relevant section of [Public Demo Plan](public-demo-plan.md). Do not coach beyond the written script unless the record marks assistance.

For each participant and workflow:

1. Copy [the canonical template](trial-evidence/template.json) outside the repository.
2. Set `classification` to `independent` only for a genuinely independent participant.
3. Record the first failure rather than restarting silently.
4. Sanitize and human-review the record.
5. Validate it:

```bash
python scripts/validate_trial_evidence.py PATH_TO_RECORD.json
```

Required outcomes:

- [ ] primary local adoption flow reproduced from a clean environment;
- [ ] local-only policy plus backup/restore replay reproduced;
- [ ] existing remote-GPU import/plan/export flow reproduced;
- [ ] participant understands which files were written;
- [ ] participant understands that export does not edit the target tool;
- [ ] every assisted or failed attempt remains in the evidence set.

## 5. Trigger the final documentation gate

Only after the published-release verification and independent demonstrations:

- [ ] re-read README and package metadata;
- [ ] compare top-level/core help with user docs and demo commands;
- [ ] re-check product maturity and narrow scope wording;
- [ ] remove claims not demonstrated by evidence;
- [ ] run public example, link, help, contract, packaging, and full test gates;
- [ ] update the P0 backlog with evidence paths and final counts.
