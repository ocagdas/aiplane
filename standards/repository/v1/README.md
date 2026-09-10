# Repository contract 1.0.0

This bundle is the reviewed-copy interface baseline, not a shared runtime dependency.
Its MIT license applies to these common schemas/fixtures/check helpers, not to the
receiving product or its data. Product licenses and publication policies are adapters.

`bundle.json` lists root-relative managed files and SHA-256 digests. Copy only those
files plus bundle.json, preserving paths. Review every destination diff. Run:

```bash
python -m pip install jsonschema==4.26.0
python scripts/check_repository_standard.py --verify-bundle-only
python scripts/check_repository_standard.py --report .quality/repository-standard.json
```

Use a maintenance environment. No network calls or real target Git mutations occur
in the conformance runner; Git commits/tags/pushes target temporary local fixtures.
Run only a trusted/reviewed helper, never executable code from arbitrary CI artifacts.

Create a repository-owned `repository-standard.json` with contract_version 1.0.0,
project, required_jobs, version_mirror, trunk_variable, publication and license_profile.
Repo Pilot's file is an example, not something to overwrite onto another product.
The design at docs/development/repository-standard-design.md defines exact semantics,
including superseded status for any advanced remote and explicit candidate builds.

Do not copy version.py, publish_version.py, build_release.py, ci_gate.py, full workflows,
LICENSE, product docs or credentials wholesale. Adapt those interfaces locally and
retain product integration/platform tests. The common evidence verifier is suitable
for an authenticated same-run artifact, not a replacement for workflow authorization.

Before freezing a new release, update contract_version for semantic changes, review
fixtures and regenerate bundle.json digests over exactly its existing managed list.
Commit/review the source bundle before pinning it for team reuse. Until then record
base commit plus working-tree delta; a checksum is integrity, not release approval.

The managed set also includes identical `.github` issue forms, PR template, CODEOWNERS,
Dependabot configuration and CODE_OF_CONDUCT.md. Workflows remain local adapters.
Review ownership and dependency ecosystems when adopting outside these three repositories.

The shared bundle now includes repository_release.py, repository_provenance.py,
merged_pr.py and verify_release.py. These are identical implementations used by
all three products, with local wrappers for mirrors, packaging and release policy.
Vendored formatting is canonical; a product may exclude these paths from its own
formatter but must keep bundle integrity and lint checks mandatory.

BRANCHING.md and check_branch_policy.py are managed shared files. main is the default trunk (master for ACF);
dev/<topic> is the development convention, with a Dependabot automation exception.
REPOSITORY_TRUNK and REPOSITORY_VERSIONING_ENABLED are common Actions settings.
