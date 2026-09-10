# Shared open-source repository structure and release contract

This is the agreed target convention for AI Content Factory, aiplane and repo_pilot.
It defines file ownership and automation interfaces, not identical product architectures.
Each repository must be updated and verified independently. Do not describe another repository as migrated before inspecting its code.

## Baselines and reuse

Use **repo_pilot** as the initial baseline for root documentation, a separate
`publish_version.py`, strict artifact verification and tests of atomic publication.
Use **aiplane** for mature install-channel qualification, version/release policy,
release notes and post-publication verification. ACF supplies configurable trunk
selection, externally stored project artifacts and the source-checkout release adapter.

The shared safety rule is to version only the exact tested trunk tip. Do not copy
refresh/rebase/retry logic that bumps newer code not qualified by that run. Include
trunk-filtered, paginated merged-PR detection for squash/rebase merges.

Once the sibling updates are complete, their reviewed code with appropriate reuse permission can
serve as reusable baselines. Preserve applicable licenses and notices, pin the imported
revision and rerun local tests. No installed tool or CI job may import `../aiplane`,
`../repo_pilot`, or another sibling checkout. If a common toolkit is extracted, version
it independently and consume a pinned dependency or vendored copy with provenance.
Until then, use matching interfaces and conformance tests around small local adapters;
do not claim separately copied implementations are already one shared library.

## Canonical layout

```text
README.md
PURPOSE.md
STATUS.md
VALIDATION.md
ROADMAP.md
TODO.md
CONTRIBUTING.md
CI.md
VERSIONING.md
REPOSITORY_STRUCTURE.md
AGENTS.md
LICENSE                       approved license before public OSS distribution
NOTICE.md                     when attribution/dependencies require it
SECURITY.md                    maintained reporting procedure for public distribution
CODE_OF_CONDUCT.md             when accepting a public contributor community
pyproject.toml
Makefile
src/<package>/
tests/
scripts/
  check.sh                    POSIX entrypoint; check.py may own cross-platform checks
  format.sh                   optional convenience wrapper around the pinned formatter
  version.py
  publish_version.py
  build_release.py
  ci_gate.py
configs/                      distributable defaults/templates; no private credentials
docs/
  index.md
  architecture.md
  user/
  development/
  project/                    focused domain/design material, not duplicate backlogs
.github/
  workflows/ci.yml
  workflows/version.yml
  workflows/release.yml
  workflows/verify-release.yml  optional separate post-publication matrix
```

Keep intentional architecture differences. ACF's `modules/` compatibility/runtime
package and repo_pilot's installed `project/` payload are valid additions. Do not move
runtime code merely to make directory trees identical. Test fixtures can live inside
the repo; production media, credentials, logs, caches and build outputs belong outside
it or in an explicitly ignored disposable directory. ACF release output is external.

## Documentation ownership and required content

| File | Sole responsibility |
|---|---|
| README.md | Product summary, supported quick start, installation boundary, links to authoritative guides |
| PURPOSE.md | Mission, audience, scope, operating principles and non-goals |
| STATUS.md | Current capabilities and known functional limits; links to evidence and tasks |
| VALIDATION.md | Latest tested revision/scope when available, commands, results, environment and unverified gates |
| ROADMAP.md | Milestone priorities, dependencies and acceptance; not a second task checklist |
| TODO.md | Open actionable work only; remove completed tasks and update STATUS/VALIDATION |
| CONTRIBUTING.md | Development setup, contribution/review expectations and links to CI/version policy |
| CI.md | Local commands, hosted jobs, supported matrix, required gate, evidence schema and activation |
| VERSIONING.md | Version sources/mirrors, CLI, automatic bump/tag rules, public-release policy, credentials, races/recovery |
| REPOSITORY_STRUCTURE.md | This common structural/interface contract and legitimate project adapters |
| AGENTS.md | Short instruction entrypoint pointing to agent guidance and current authoritative guides |
| docs/index.md | Navigation to maintained documents |
| docs/architecture.md | Components, dependencies, runtime boundaries and artifact/data ownership |
| LICENSE / NOTICE.md | Owner-approved licensing and preserved attribution; never invent approval or provenance |
| SECURITY.md | Actual private reporting channel and supported scope; do not invent an email or enabled platform feature |
| CODE_OF_CONDUCT.md | Chosen conduct policy and real enforcement route, where applicable |

Runtime prompts/contracts remain where their loaders expect them; link to them rather
than duplicating prose. Product-specific setup, quick starts and operations can remain
under `docs/user/`. Move root INSTALLATION/QUICKSTART documents only when links and
consumer references can be updated; avoid two authoritative installation instructions.
Optional detailed implementation plans must describe design, not duplicate TODO/ROADMAP.

Do not maintain dated merge reports or delivery histories as current guidance. Git and
immutable release notes retain history. If a CHANGELOG is required by a distribution,
generate it from release evidence rather than updating a second manual status ledger.
ACF uses generated release notes. These conventions do not authorize changing a
repository's license or deleting unique research, contractual or customer material.

## Version and tag contract

- Numeric `MAJOR.MINOR.PATCH`; reject prerelease forms, leading zeros, equal/decreasing
  requested versions and inconsistent mirrors. Tags are annotated `vMAJOR.MINOR.PATCH`.
- `pyproject.toml [project].version` is the package source of truth. Mirrors are explicit
  adapters: package `__init__.__version__` for ACF/aiplane; `upstream.lock.json`'s
  `package_version` for repo_pilot. Never bump upstream tools/preset/extension versions
  merely because the package changes.
- Ordinary PRs cannot change package version values. CI performs patch bumps after
  qualifying trunk PR merges. A maintainer may select a higher version directly on
  authorized trunk; CI tags that value without another bump. Direct code-only pushes
  run checks but do not automatically bump versions.
- Trunk defaults to the repository default branch with a documented override. No fixed
  branch-name pattern is required for checks; mutation is restricted to the selected trunk.
- A matching existing tag means no-op. A tag at a different commit is a conflict; never
  force-push, move or delete it as recovery. Atomic branch/tag push prevents half-publication.
- If trunk advances, report `superseded` without moving onto untested code. Rapid merges
  can coalesce; a later direct code-only push is not an automatic catch-up bump.

## Standard command interfaces

```bash
python scripts/version.py check
python scripts/version.py current --plain       # shell-friendly version
python scripts/version.py current --json        # also the default format
python scripts/version.py patch --dry-run
python scripts/version.py minor                 # major, patch, set X.Y.Z also supported
python scripts/version.py tag --dry-run
python scripts/version.py check-pr --base-ref REF
python scripts/version.py classify-ci --merged --github-output
python scripts/version.py classify-release --tag vX.Y.Z --github-output
python scripts/publish_version.py --source SHA --trunk BRANCH --merged --github-output
python scripts/build_release.py --tag vX.Y.Z --output /external/artifacts
python scripts/build_release.py --verify-only --output /external/artifacts
python scripts/ci_gate.py --results /external/jobs.json --report /external/ci-gate.json
```

`--merged` is supplied only after the workflow verifies PR association; merge commits
can also be detected from history. `classify-ci` emits schema version 1 with
`mode=patch|tag|none`, target `version`, `tag` and `source_commit`. Classifiers do not
publish. `--github-output` explicitly requests step outputs. `publish_version.py`
emits schema version 1 and `status=published|unchanged|superseded`, source commit and,
when published, version, tag and version commit. It requires matching HEAD/GITHUB_SHA,
a clean disposable checkout and current remote trunk. CLI errors exit nonzero.

The workflow, not a fabricated local JSON flag, authorizes mutations. Supply credentials
only after required quality jobs succeed. Local bump/tag helpers do not commit or push.
For projects with no public publication policy, `classify-release` validates identity
but emits `publish=false`; it must not silently enable publication.

## CI and machine-readable evidence

Use `ci.yml` with display name **CI**, plus the stable required job **Quality gate**.
Run on PRs, branch pushes, merge queues and manual dispatch; allow reuse for exact
release commits. Avoid path filters that leave required checks missing. Missing,
failed, skipped or cancelled required jobs are no-go; additional failing dependencies
also block. The required job set and platform matrix are project-specific.

The workflow/job output is only `go=true|false`; an absent output is never permission.
The `quality-gate` artifact contains `ci-gate.json`:

```json
{
  "schema_version": 1,
  "go": true,
  "commit": "tested-commit-sha",
  "run_id": "workflow-run-id",
  "checks": {"unit": "success", "integration": "success"}
}
```

Keep reports outside source files; upload scoped results as workflow artifacts.
Consumers require job/workflow success AND `go == 'true'` for the same revision.
Retain JUnit or equivalent machine-readable test evidence. Separate quick developer
checks from full integration and release qualification; report unsupported platforms.

`version.yml` may be a reusable dependent workflow or a trusted completed-CI listener.
ACF uses a completed-CI listener that checks event, repository, trunk and tested SHA.
A listener must track the CI display name and live on the default branch. Reusable
or manual release checks cannot accidentally invoke version mutation. Prefer pinned
reviewed action revisions and checksum-verified workflow validators; actionlint should
validate expressions and wiring, not just YAML parsing.

Use a repository-scoped GitHub App for automatic commit/tag pushes, documenting its
client/App ID, secret and branch/tag permissions. Prefix credentials per repository;
do not rename working secrets silently or embed them in configuration. Configure actual
branch protection separately; workflow files cannot enforce repository administration.

## Build, release and distribution adapters

`build_release.py` builds and verifies artifacts, never publishes. Required types,
resource checks, install channels and license notices remain project-specific:

- ACF: source-checkout archive, `provenance.json`, `SHA256SUMS`; real installation from
  the exact archive. Wheels remain unqualified.
- aiplane: wheel/source, checksums, install-channel and post-publication qualification.
- repo_pilot: wheel/source, checksums, installed payload/licensing checks; public release
  remains disabled until separately selected by that repository's owner.

Versioning, tagging, artifact readiness and public publication are distinct gates.
Every public asset must match the tested immutable tag. Compare published downloads
with validated artifacts. Minor/major automatic publication and manual patch publication
remain ACF/aiplane policy, not a mandate to change repo_pilot policy. No PyPI upload,
new provider spending or video publication follows from standardization.

## Migration acceptance

Update workflow references/listeners, docs, installed payload references, script imports,
archive resource lists and contributor commands together. ACF is undeployed and keeps
no obsolete script wrappers or command aliases. Other repos should remove obsolete
names when safe; retain an explicit migration period only if real consumers require it.

Test synchronized versions, PR/stale-branch guards, all bump kinds, tag collisions,
clean-tree checks, exact tested SHA, stale remote tips, atomic push failure, same-commit
reruns, paginated/trunk-filtered PR detection, fail-closed quality decisions, corrupt or
incomplete manifests and actual distribution installation. Run formatting, analysis,
deterministic tests, real integration, workflow validation and local link checks.
Hosted app/ruleset and public release qualification require actual hosted evidence.

## aiplane adapter

Version mirrors are pyproject.toml and src/aiplane/__init__.py. Required CI jobs are checks, compatibility and install-channels; all three OS runners and pip/pipx/uv remain required. The package has no runtime dependencies. Existing config-templates, profile-templates, schemas, skills and specialized verification helpers retain their ownership. CHANGELOG.md is release-note input, not a current status/backlog. See CI.md and VERSIONING.md for local implementation and hosted activation requirements.

Repository handoff notes are not stored in aiplane. Maintained agent instructions live in `docs/project/agent-guidance.md`; the project plan links the current status, validation, roadmap and backlog.

Follow [BRANCHING.md](BRANCHING.md) for the shared trunk/dev branch convention,
version/tag rules and REPOSITORY_VERSIONING_ENABLED activation setting.
