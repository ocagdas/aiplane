# Shared repository standard 1.0.0

## Objective and authority

Make repo_pilot, aiplane and AI Content Factory interoperable at their maintenance interfaces while preserving product behavior, installed resources, legal rights and publication policy. This is the implementation design and migration specification. TODO.md owns remaining repo_pilot work; each sibling owns its own acceptance record. The parent handoff is a replaceable delivery instruction, not the contract authority.

The canonical local baseline is `standards/repository/v1/contract.json`, its JSON schemas and fixtures, plus the small portable check helpers. The contract version is independent of each product version. Wire payloads use integer schema_version 1. Incompatible fields/semantics require a new major contract directory; additive optional fields can be a compatible minor version. Freeze and checksum a reviewed bundle before copying it. Do not depend on sibling directories at runtime or in CI.

## Ownership and repository adapters

| Shared, copied unchanged | Repository-owned; adapt and test |
| --- | --- |
| standards/repository/v1 schemas, contract fixtures, bundle manifest and MIT notice | repository-standard.json: project, required jobs, mirror, trunk variable, publication and licensing profile |
| scripts/check_repository_standard.py | scripts/version.py: version mirror reads/writes and package identity |
| scripts/repository_release.py, repository_provenance.py, verify_release.py and verify_quality_evidence.py | scripts/publish_version.py: exact-tip atomic publication through the local version adapter |
| Schema field names and public CLI contracts | scripts/build_release.py: resources, distribution types, install channels and licensing checks |
| Quality success/identity and immutable-tag rules | scripts/ci_gate.py: repository's required job set |
| Documentation roles | Actual docs, licensing, contacts, App variables/secrets, triggers and supported platform matrix |

Never copy repo_pilot's LICENSE over ACF's proprietary license. Never replace aiplane's install-channel/attestation/rollback coverage or ACF's media exclusions with the smaller repo_pilot payload adapter. Templates can provide structure, never claims of approval or completed qualification.

## Documentation contract

REPOSITORY_STRUCTURE.md maps roles: purpose, status, validation, roadmap, open tasks, contribution, CI, versioning, agent handoff and docs navigation/architecture each have one owner. Root quickstart/installation can remain when external/package references need them. Consumer-installed guidance stays at loader-defined paths. A changelog is acceptable as release-note input, not a second current-state/backlog document.

Private repositories also need an explicit license/rights notice. ACF now uses LicenseRef-Proprietary; its contributor/security/conduct routes are for authorized private collaborators. Open-source preparation is not an open-source license. A public transition requires an owner decision, third-party review and actual contact routes. GitHub visibility is independent of license choice.

## Version and publication semantics

- current defaults to JSON; --json is explicit JSON and --plain is the shell interface.
- classify-ci is a read-only classification of the selected checkout. --merged records independently verified PR association; multi-parent merge commits count too. It does not require GitHub event variables. Workflow guards own authorization/trunk selection.
- classify-ci emits mode patch/tag/none, target version/tag and source_commit under schema 1. Reject PR version changes and non-increasing manual changes. Version mirrors must agree. A matching existing tag produces none.
- classify-release emits schema_version, version, tag, source_commit and publish. It validates exact tag/HEAD/version identity. Repo Pilot always returns false. aiplane retains minor/major automatic, deliberate manual patch publication. ACF retains this version selection for private internal GitHub Releases; its proprietary policy blocks public publication.
- publisher requires a clean disposable checkout and exact HEAD/GITHUB_SHA/source agreement. Validate the selected trunk ref and remote tip before mutation. Only mirror files may enter the automatic patch commit. Push branch and annotated tag atomically without force.
- status unchanged means the requested source remains the remote tip and needs no mutation. Any advanced remote, including a previously created patch child, means superseded. Neither status is an error or permission to rebase. Push rejection exits nonzero; a fresh retry rechecks remote state. This deliberately replaces aiplane's special patch-child/race classification.
- A same-tag/different-commit conflict is always an error. Do not delete/move tags to recover. A missing publication response may mean the atomic push succeeded; inspect through a fresh checkout, never repeat mutations in the dirty failed checkout.

## Quality authorization and workflow boundaries

CI runs on PRs, all branch pushes, merge queues and manual dispatch, with reusable exact-commit qualification. Quality gate requires all required jobs and every supplied additional dependency to succeed. Emit boolean GO, commit, run_id and checks; local null identities are not hosted authorization.

A reusable version workflow must be reachable only from a successful top-level CI push of the selected trunk and exact tested SHA. In aiplane the CI workflow calls `version.yml` directly through `workflow_call`, and the callee must still require `github.event_name == 'push'`, `github.workflow == 'CI'`, `github.ref_name == inputs.trunk`, `github.sha == inputs.source`, and `inputs.go == 'true'` before mutation. Manual/reusable release qualification must not invoke mutation; do not rely on a user-supplied go string alone. Restrict credentials to that exact dependency path.

Merged-PR detection must paginate and filter merged status, target repository and selected trunk; malformed/API failures must fail rather than guess. Serialize per trunk, avoid cancelling an active mutation, and never refresh onto a newer untested revision.

Pin external Actions to reviewed immutable SHAs. Pin/checksum a validator version supporting every used permission/action syntax; the baseline is actionlint 1.7.12 (Linux amd64 SHA-256 8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8). It supports aiplane's artifact-metadata scope. Pin App actions to their actual reviewed SHA; the validator's mutable v3 metadata can lag current client-id inputs. Record validator/action upgrades before propagating them. Keep existing secret names; document any unavoidable migration. Hosted rules and App permission checks remain separate activation evidence.

## Build and provenance contract

Shared repositories may define a product-owned candidate-build path, but aiplane does not expose `scripts/build_release.py --candidate`. Local snapshot wheels come from `scripts/build_local_wheel.py`, while `scripts/build_release.py --tag` remains the clean annotated-tag release path. Candidate/local snapshot outputs are never public-release evidence.

--tag builds require a clean exact annotated tag matching package mirrors. Provenance records build_kind release, dirty false, matching tag/version and version_commit equal to the checkout SHA. source_commit in a build record means the checkout used to build; in a publication result it means the pre-bump tested source. These are separate record types; do not silently equate them.

Each artifact directory contains the adapter's complete payload set, provenance.json and SHA256SUMS. Provenance includes schema_version, distribution, version, tag, source_commit, version_commit, run_id, dirty/build_kind and payload SHA-256 digests. SHA256SUMS covers payloads plus provenance; it does not checksum itself. Verify exact membership, regular files, portable names, digest format, data identity and bytes. Additional attestation files must be explicitly included by the adapter, not exempted as unchecked extras.

Checksums are integrity evidence, not publisher authentication. aiplane retains signed attestations and public-download verification. Shared provenance does not require repo_pilot to enable public releases or ACF to qualify standalone wheels.

## Conformance and local acceptance

The portable runner uses repository-standard.json and shared schemas. It checks document/helper/workflow presence, current output modes, fail-closed quality cases and identity, merged classification, monotonic versions, release schema, tag reruns and atomic publication in a temporary non-main-trunk Git fixture. It never mutates target checkout refs. It requires the maintenance interpreter's jsonschema dependency.

Run `python scripts/check_repository_standard.py --report .quality/repository-standard.json`. The full local/hosted gate must also retain each repository's integration/platform tests. Unit tests cover evidence rejection for stale run/SHA, string booleans, missing/failed dependencies and schema mismatch. Product publisher tests additionally cover collision/rejected atomic push. Build and install exact artifacts; verify required docs/resources and corrupt/incomplete downloads. Static schema compliance alone is not hosted workflow qualification.

## Delivery and migration sequence

1. Implement/freeze the contract, schemas, portable checks and repo_pilot adapter; validate and build its candidate and clean-tag fixtures.
2. Apply ACF private licensing/metadata and internal-only publication guard; verify metadata and included legal files. Leave media/runtime behavior untouched.
3. Replace the parent handoff completely with the tested source bundle, hash/copy procedure, per-repository adapter changes and exact qualification commands.
4. Sibling agents preserve their existing changes, copy only managed common files, adapt local code/policies, then run conformance plus their complete product gates. Record baseline commit and dirty delta explicitly.
5. After all three pass independently, review/pin the baseline commit and perform authorized hosted qualification: passing/failing PR, merge version/tag, stale/collision/rerun, tag readiness, ruleset behavior and applicable public/internal download checks.
6. Consider extracting a shared library only after stable conformance; copying reviewed MIT helpers is currently the distribution mechanism. No sibling runtime imports or automatic cross-repository publication.

## Community files and documentation parity

All three repositories use the same root document names declared in contract.json,
including HANDOFF.md, NOTICE.md and SUPPORT.md. Shared community scaffolding is
byte-identical and covered by bundle.json: issue forms, PR template, CODEOWNERS,
Dependabot and CODE_OF_CONDUCT.md. Reporting routes are owned by SECURITY.md;
templates do not assume private vulnerability reporting has been enabled.

Use docs/index.md, docs/user/index.md and docs/development/index.md for navigation.
Long guides keep topic-specific names; aiplane's contributor guide is now
 docs/development/setup.md and project navigation is docs/project/index.md.
Product instructions and tests stay local. Do not copy a source product's runtime,
release, credentials or licensing policy merely to obtain textual similarity.

The filenames ci.yml, version.yml, release.yml and verify-release.yml are shared. Workflow job bodies
remain adapters for each product's tests, distribution and authorization model.
aiplane additionally owns copilot-instructions.md. Its
existing user/README.md is a product onboarding guide covered by product contracts;
user/index.md remains the canonical navigation entry. CHANGELOG.md remains its
release-note input. Repo Pilot retains root QUICKSTART.md and INSTALLATION.md because
installed metadata and setup output refer to them. ACF keeps private/proprietary
LICENSE, private reporting routes, media exclusions and internal-release guard.

README, PURPOSE, STATUS, VALIDATION, ROADMAP, TODO, CONTRIBUTING, CI, VERSIONING,
REPOSITORY_STRUCTURE and HANDOFF share document roles rather than duplicated prose.
Security support windows, contact routes, product threat models and legal notices
must retain their actual project-specific content. SUPPORT and conduct use common
wording with the private-access qualification in ACF SUPPORT.

## Shared release implementation

All three repositories vendor the same checksum-pinned repository standard under
standards/repository/v1. scripts/repository_release.py owns version decisions and
atomic publication; scripts/repository_provenance.py owns artifact identity;
scripts/verify_release.py binds downloaded assets to the selected tag and commit.
Product adapters retain mirror paths, build resources and publication policy.
Run scripts/check_repository_standard.py to detect drift and exercise the interfaces
against disposable Git fixtures. Never import a sibling checkout at runtime or in CI.

Classification is independent of GitHub event variables; workflow guards authorize
only the selected, successfully tested trunk push. An exact existing tag means no
mutation. Any advanced remote, including an already published patch child, means
superseded. A rejected push is an error; a new run rechecks the remote tip. Commit
messages and actor names are not loop-breaking authority. Tags and assets are never
moved or overwritten automatically.

Every tagged build requires a clean checkout and annotated tag. SHA256SUMS covers
both payloads and provenance.json. The metadata identifies the build commit/version,
release or candidate status and payload digests. Published verification checks the
selected tag/commit, then runs the product's installation checks. Artifact evidence
uses schema 1 with tag, source_commit, checks and artifact digests; installation
success is recorded by the workflow job, with additional product evidence where supplied.
Failed verification fails the workflow for maintainer review; it never repairs or
replaces published assets automatically. Hosted qualification remains necessary.


## Branch and activation policy

The common BRANCHING.md defines main (master for ACF), dev/<topic>, squash PR integration and
version/tag semantics. Every CI validates PR sources and targets with the shared
check_branch_policy.py. REPOSITORY_TRUNK defaults to main, with master explicitly configured for ACF; version mutation requires
REPOSITORY_VERSIONING_ENABLED=true and configured App credentials. Missing setup
leaves version automation disabled without weakening the quality gate.
