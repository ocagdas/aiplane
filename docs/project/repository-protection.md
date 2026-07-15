# Repository Protection

The durable required check is **CI / Release gate**. It succeeds only after the full quality gate, supported-Python packaging checks, and Linux/macOS/Windows installed-wheel lifecycle jobs succeed.

## Current hosted-state gap

Source-controlled workflows cannot enable repository rules. Verify hosted state before release: `main` must be protected and the applicable ruleset must be active. A disabled ruleset does not satisfy P0.

## Configure in GitHub

Open **Settings → Rules → Rulesets → New ruleset → New branch ruleset**.

1. Name it `Protected main and CI release gate` and set enforcement to **Active**.
2. Target the default branch (`main`).
3. Add the GitHub Actions app to the bypass list with the narrowest available mode that permits the CI-owned version commit. Without this exception, “require pull request” will reject `github-actions[bot]` pushing the patch-version commit. Do not grant bypass to arbitrary users or third-party apps.
4. Enable **Restrict deletions** and **Block force pushes**.
5. Enable **Require a pull request before merging** for human changes. Require at least one approval when a second maintainer is available; dismiss stale approvals and require conversation resolution.
6. Enable **Require status checks to pass** and select `CI / Release gate`. Enable the option requiring the branch to be current before merge.
7. Enable linear history only if the selected merge strategy is squash/rebase; the version classifier supports merge and squash commits through associated-PR detection.
8. Save the ruleset, then use a disposable PR to prove a failing or pending gate blocks merge.

The Actions bypass is a deliberate trust boundary: repository workflows with `contents: write` can update `main` and create tags. Changes to `.github/workflows/ci.yml`, `.github/workflows/release.yml`, and `scripts/version.py` therefore require careful review and should use CODEOWNERS when a second maintainer is available.

## Protect version tags

Create a tag ruleset targeting `v*`:

- make it **Active**;
- restrict deletion and update so published versions cannot move;
- allow tag creation only to designated maintainers and the GitHub Actions app used by the version workflow;
- do not allow force updates;
- retain CI-created `[ci-artifact]` annotated tags even before public publication.

## Verify from the command line

Read-only audit commands:

```bash
gh api repos/ocagdas/aiplane/branches/main/protection
gh api repos/ocagdas/aiplane/rulesets --jq '.[] | {id, name, target, enforcement}'
gh api repos/ocagdas/aiplane/rulesets/RULESET_ID
```

Expected evidence:

- main protection returns HTTP 200 rather than `Branch not protected`;
- the selected branch ruleset reports `enforcement: active`;
- `CI / Release gate` is required;
- pull requests, deletion protection, and non-fast-forward protection are enabled;
- bypass actors are limited to the versioning workflow’s GitHub Actions app and named maintainers;
- the `v*` tag ruleset prevents deletion and update.

Save the ruleset URL or a dated screenshot in private maintainer evidence. Never store administration tokens or raw private repository output in this repository.
