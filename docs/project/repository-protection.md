# Repository Protection

The pull-request UI displays the durable aggregate check as **CI / Release gate**. GitHub rulesets identify a normal workflow check by its job name, so the required-check value to select is **`Release gate`**. It succeeds only after the full quality gate, supported-Python packaging checks, and Linux/macOS/Windows installed-wheel lifecycle jobs succeed.

## Current hosted-state gap

Source-controlled workflows cannot install a GitHub App, store its private key, or activate repository rules. Complete the app-token test below before activating protection; otherwise the automated version push will be rejected.

## Install the narrow versioning identity

Create the private `aiplane-versioning` GitHub App under the repository owner's account with:

- webhooks disabled;
- repository **Contents: read and write**;
- **Metadata: read-only**;
- no other permissions;
- installation limited to this repository.

Under **Settings -> Secrets and variables -> Actions**, store:

- repository variable `AIPLANE_VERSIONING_APP_ID`: the numeric App ID;
- repository secret `AIPLANE_VERSIONING_APP_PRIVATE_KEY`: the complete generated PEM, including boundary lines.

Never commit or print the PEM. CI exchanges it for a short-lived, repository-scoped installation token. Azure Pipelines and Dependabot are unrelated identities and must not receive this bypass.

Before activating rules, merge the app-token workflow change and prove that an ordinary merge lets `aiplane-versioning[bot]` push the patch commit and `v*` tag. The patch tag must run **Release artifacts**, skip public publication, and retain the CI wheel artifact.

## Configure the main ruleset

Open **Settings -> Rules -> Rulesets -> New ruleset -> New branch ruleset**.

1. Name it `Protected main and CI release gate`.
2. Initially use **Evaluate** while testing; switch to **Active** only after the app-token proof succeeds.
3. Target only the default branch, `main`.
4. Add **Repository administrators** and the `aiplane-versioning` GitHub App to the bypass list as **Always allow**. Do not add write/maintain roles, Azure Pipelines, Dependabot, or unrelated apps.
5. Enable **Restrict updates**, so only bypass actors can make the final update to `main`; contributors may still open PRs and an administrator merges them.
6. Enable **Restrict deletions** and **Block force pushes**. These rules target `main` only; ordinary development branches may still be rebased, force-pushed, and deleted.
7. Enable **Require a pull request before merging**. Set one required approval when another eligible reviewer exists, dismiss stale approvals, require approval of the most recent reviewable push, and require conversation resolution. A PR author cannot approve their own PR. If this is still a single-maintainer repository, use zero approvals temporarily rather than creating an impossible gate.
8. Enable **Require status checks to pass** and add `Release gate`. Enable the option requiring the branch to be current before merge. GitHub offers a check only after it has completed successfully in this repository during the preceding seven days.
9. Enable linear history only if the selected merge strategy is squash or rebase.
10. Save, activate, and use a disposable PR to prove that pending/failing checks, missing approval, and unresolved conversations block non-bypass merging.

Administrator bypass is intentionally broad: GitHub rulesets cannot exempt an actor from only the approval rule. Use it for agreed direct-`main` version commits; ordinary administrator code and documentation changes should still use PR review. Review bypasses under **Rules -> Insights**.

## Protect version tags

Create a separate active tag ruleset targeting `v*`:

- grant bypass only to repository administrators and `aiplane-versioning`;
- restrict updates and deletion so version tags cannot move;
- block force updates;
- permit the app to create new CI-owned tags.

Keep patch tags even when they are not public releases. Minor and major tags publish automatically after validation; a selected patch tag can be published only through manual **Release artifacts** dispatch.

## Verify from the command line

Read-only audit commands:

```bash
gh api repos/ocagdas/aiplane/branches/main/protection
gh api repos/ocagdas/aiplane/rulesets --jq '.[] | {id, name, target, enforcement}'
gh api repos/ocagdas/aiplane/rulesets/RULESET_ID
```

Expected evidence:

- the branch ruleset is active and targets only `main`;
- `Release gate` is required and the branch must be current;
- pull requests, the configured review policy, update/deletion restriction, and force-push protection are enabled;
- bypass actors are limited to repository administrators and `aiplane-versioning`;
- the `v*` tag ruleset prevents update and deletion;
- a patch merge is versioned by the app without a public release;
- an intentional minor/major version creates a complete GitHub Release.

Save the ruleset URL or a dated screenshot in private maintainer evidence. Never store administration tokens, private keys, or raw private repository output here.
