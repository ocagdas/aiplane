# Activate the shared GitHub policy

BRANCHING.md owns the trunk/dev branch and numeric-version rules. CI cannot create a
GitHub App installation, retrieve a stored private key, grant administrator access,
or upgrade a billing plan. Read the final readiness record before enabling mutation.

## Current hosted state

- aiplane: main default branch, common branch/tag rules active, Quality gate required,
  corrected v* target, squash-only merges. Existing App settings retained; automatic
  versioning enabled through REPOSITORY_VERSIONING_ENABLED=true.
- repo_pilot: main default branch, equivalent branch/tag rules active, squash-only
  merges. Automatic versioning disabled until its App/key setup is complete.
- AI_Content_Factory: remains private; default branch stays master by owner choice. The available
  login lacks administrator access to change repository settings, and
  GitHub reports that private rulesets require a plan upgrade. REPOSITORY_TRUNK=master
  and REPOSITORY_VERSIONING_ENABLED=false are configured. No branch rename is needed.

These settings were inspected/applied on 10 September 2026. The workflow/code delta
is still uncommitted. A successful current-candidate hosted CI run remains required.

## ACF owner: complete trunk and protection setup

Use an account with repository administrator access. Keep the repository private.
An owner-approved plan supporting private rulesets is required for enforced parity;
a written manual process is not equivalent to GitHub-enforced protection.

ACF retains master. An administrator can align its repository merge options with:

```bash
gh api --method PATCH repos/zcagdas85-commits/AI_Content_Factory -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false
```

After the plan supports rulesets, create the prepared common rules (or update the
existing matching rules by ID; do not create duplicate active rules):

```bash
python -c 'import json; from pathlib import Path; x=json.loads(Path("standards/repository/v1/github-branch-ruleset.json").read_text()); x["conditions"]["ref_name"]["include"]=["refs/heads/master"]; x["name"]="Protected master and quality gate"; Path("/tmp/acf-branch-ruleset.json").write_text(json.dumps(x))'
gh api --method POST repos/zcagdas85-commits/AI_Content_Factory/rulesets --input /tmp/acf-branch-ruleset.json
gh api --method POST repos/zcagdas85-commits/AI_Content_Factory/rulesets --input standards/repository/v1/github-tag-ruleset.json
```

The templates allow administrator bypass only. Add the repository-installed
versioning App as a narrowly scoped bypass actor after its setup. No unrelated
App or broad write role should receive that exception. Branch rules require one
review approval; an administrator bypass must remain an explicit reviewed action.

Existing local dev branches and the master trunk remain intact.

## Repo Pilot and ACF: configure the versioning App

Create/install a repository-scoped GitHub App with Contents read/write and Metadata
read-only, webhooks disabled. Store the private PEM only as an Actions secret.
Settings names are intentionally preserved for each application's identity:

| Repository | Actions variable | Actions secret |
| --- | --- | --- |
| repo_pilot | REPO_PILOT_VERSIONING_APP_ID | REPO_PILOT_VERSIONING_APP_PRIVATE_KEY |
| AI_Content_Factory | ACF_VERSIONING_APP_CLIENT_ID | ACF_VERSIONING_APP_PRIVATE_KEY |
| aiplane (already configured) | AIPLANE_VERSIONING_APP_ID | AIPLANE_VERSIONING_APP_PRIVATE_KEY |

Configure its allowed trunk/tag updates, then set REPOSITORY_VERSIONING_ENABLED=true.
Repo Pilot/aiplane use REPOSITORY_TRUNK=main; ACF uses master. Do not copy credentials from another
repository or enable version mutation before App access is actually working.

## Hosted acceptance

Push a review branch containing the complete intended delta (including new shared
files), open its PR to the configured trunk, and wait for Quality gate on that exact commit. Prove
that a failing non-bypass PR cannot merge. Verify an authorized merged PR creates
one patch commit and annotated tag, reruns do not duplicate publication, and stale
runs never publish untested code. Applicable released assets must pass the new
per-artifact attestation/download/install workflow before release qualification.
The local shell fixtures do not establish live GitHub attestation success.
