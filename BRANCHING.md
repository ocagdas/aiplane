# Shared branch, version and tag policy

Repo Pilot and aiplane use `main` as the integration and release trunk. ACF uses
`master` by owner choice. Work in short-lived `dev/<topic>` branches, then open a
PR to the repository's trunk. There is no separate
long-lived develop branch. Fork contributors use the same naming convention.
Dependabot's generated `dependabot/*` branches are the explicit automation exception.
CI checks branch names and PR targets; it also runs checks on all branch pushes.

`<topic>` is a short description of the change, not a prescribed project category:

| Example branch | Intended work |
| --- | --- |
| dev/fix-config-loading | Fix how project configuration is read |
| dev/add-sourcegraph-cache | Add or improve retrieval caching |
| dev/improve-video-subtitles | Improve ACF subtitle behavior |
| dev/unify-release-workflows | Change shared maintenance automation |
| dev/docs-installation | Improve installation instructions |
| dev/123-fix-path-handling | Include an issue number for traceability |

Prefer lowercase words separated by hyphens. Existing names such as dev/mvp_0.20
and dev/0.1 remain valid; descriptive topics are recommended. Create a branch from
an up-to-date trunk, keep the change focused, squash-merge its PR after Quality gate
and review pass, and delete the completed dev branch when appropriate.

## Versions and immutable tags

- Use numeric MAJOR.MINOR.PATCH versions, synchronized across the product's mirrors.
- Ordinary PRs do not edit versions. A successful merged-PR trunk run increments patch.
- Maintainers explicitly select a higher minor/major (or exact) version on the trunk;
  after successful CI the selected version receives an annotated vX.Y.Z tag.
- Direct code-only pushes do not increment versions. Feature branches and PR runs
  never publish version commits or tags. Only the exact tested trunk revision qualifies.
- Push the version commit and tag atomically. Exact-tag reruns do nothing; an advanced
  remote reports superseded; push rejection fails. Never rebase onto untested code,
  move/delete an existing tag, or replace published assets automatically.
- Tagging and release publication are distinct. Product artifact types, installation
  checks and public/private publication controls are documented in VERSIONING.md.

## Common GitHub settings

`REPOSITORY_TRUNK` is the common Actions variable: `main` for Repo Pilot/aiplane,
`master` for ACF. Workflows default to main when it is absent; retain ACF's explicit
master setting. Change it consistently with branch protection and the GitHub
default branch only for an intentional shared-policy change.

`REPOSITORY_VERSIONING_ENABLED=true` explicitly enables automatic version mutation.
Leave it false until a repository-scoped versioning App is installed, its existing
project-specific App ID/client ID and private-key settings are supplied, and rules
permit its narrowly scoped branch/tag updates. CI and classification remain usable
while setup is incomplete. Credentials are never copied between repositories.

Require Quality gate, current branches, reviewed PRs, resolved conversations, linear
history/squash merging, and prohibit trunk deletion and force pushes. Protect v* tags
against update/deletion. Restrict bypass to designated administrators and the installed
versioning App; bypass actors can bypass the whole ruleset. Never rely on a bypassed
merge as evidence of check enforcement. Dev branches can be rebased and removed.

Rulesets are hosted settings, not activated by committing these files. A private
repository whose plan lacks rulesets needs an owner-approved plan upgrade; until
then use a documented manual review/check procedure, without claiming enforced
protection or making the repository public.
