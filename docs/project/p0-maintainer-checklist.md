# P0 Maintainer Checklist

This checklist contains actions that require GitHub administration, public publication, or independent participants.

## 1. Install and prove the versioning identity

Follow [Repository Protection](repository-protection.md).

- [ ] Create and install the private `aiplane-versioning` GitHub App only on this repository.
- [ ] Grant only Contents read/write and Metadata read-only; disable webhooks.
- [ ] Store `AIPLANE_VERSIONING_APP_ID` as an Actions repository variable.
- [ ] Store the complete PEM as the `AIPLANE_VERSIONING_APP_PRIVATE_KEY` Actions repository secret.
- [ ] Merge the app-token workflow before activating protection.
- [ ] Confirm an ordinary merge is patched and tagged by `aiplane-versioning[bot]`.
- [ ] Confirm the patch tag runs the release workflow but does not create a public release.

## 2. Activate repository protection

- [ ] Activate the `main`-only branch ruleset.
- [ ] Require the exact status-check value `Release gate` and an up-to-date branch.
- [ ] Require PRs, conversation resolution, stale-review dismissal, and one approval when another reviewer exists.
- [ ] Restrict updates, force pushes, and deletion of `main`.
- [ ] Add only repository administrators and `aiplane-versioning` to bypass.
- [ ] Activate immutable `v*` tag rules with the same narrow bypass.
- [ ] Prove a pending/failing gate or missing review blocks a non-bypass merge.
- [ ] Save the ruleset URL or screenshot in private evidence.

Read-only confirmation:

```bash
gh api repos/ocagdas/aiplane/branches/main/protection
gh api repos/ocagdas/aiplane/rulesets --jq '.[] | {id, name, target, enforcement}'
```

## 3. Publish one complete developer-preview release

For an intentional minor or major release, follow [CI and Release Process](ci-and-release-process.md); publication should start automatically after the app creates the tag. A selected patch may instead be published through **Actions -> Release artifacts -> Run workflow**.

Confirm the release visibly contains:

- [ ] exactly one `aiplane-VERSION-py3-none-any.whl`;
- [ ] exactly one `aiplane-VERSION.tar.gz`;
- [ ] `SHA256SUMS`;
- [ ] metadata matching the immutable tag;
- [ ] platform, upgrade, uninstall, and rollback guidance.

Do not count an empty release page and never replace assets under an existing version.

## 4. Verify actual public assets

Publication dispatches **Verify published release** automatically; it may also be run manually.

- [ ] All nine Linux/macOS/Windows x pip/pipx/uv jobs passed.
- [ ] Every job downloaded public assets rather than rebuilding source.
- [ ] Every manifest and install/replacement/uninstall lifecycle passed.
- [ ] Evidence identifies the same URL, tag commit, version, and wheel digest.
- [ ] Evidence contains no private data and reflects documented platform limitations.

## 5. Run independent demonstrations

Give participants only the installed artifact and the relevant [Public Demo Plan](public-demo-plan.md) section. Record first failures and assistance honestly, sanitize every record, and validate it:

```bash
python scripts/validate_trial_evidence.py PATH_TO_RECORD.json
```

Required outcomes:

- [ ] primary local adoption flow reproduced;
- [ ] local-only policy plus backup/restore replay reproduced;
- [ ] existing remote-GPU import/plan/export flow reproduced;
- [ ] participants understand written files and export boundaries.

## 6. Trigger the final documentation gate

Only after public verification and independent demonstrations:

- [ ] compare README, metadata, help, user docs, and demos;
- [ ] remove unsupported claims and maturity drift;
- [ ] run public example, link, help, contract, packaging, and full test gates;
- [ ] update the P0 backlog with evidence paths and final counts.
