# Versioning and releases

`pyproject.toml [project].version` is authoritative; `src/aiplane/__init__.py` mirrors it. Versions are numeric `MAJOR.MINOR.PATCH`, with no leading zeros or prerelease suffixes. Equal/decreasing changes and inconsistent mirrors fail. GitHub Releases remain the no-clone distribution channel; package-index publication is not enabled by this change.

## Commands

```bash
python scripts/version.py check
python scripts/version.py current --plain
python scripts/version.py current --json
python scripts/version.py patch --dry-run
python scripts/version.py minor --dry-run
python scripts/version.py major --dry-run
python scripts/version.py set 1.0.0 --dry-run
python scripts/version.py tag --dry-run
python scripts/version.py check-pr --base-ref origin/main
python scripts/version.py classify-ci --merged --github-output
python scripts/version.py classify-release --tag v0.2.18 --github-output
```

`current` defaults to JSON. Bump/set commands without `--dry-run` modify only the two version files; tag creates an annotated tag on a clean tree and never commits or pushes. Coding assistants must not execute git publication operations in this repository; the owner performs them.

## Ordinary merges and intentional version selection

PRs must not change version values. The PR guard compares against the merge base, so an unchanged version on a stale branch passes. Merged code is checked again against its first parent. A maintainer may select a higher version directly on authorized trunk; CI preserves that value and tags it. Ordinary PR merges get a patch increment after **Quality gate** succeeds. Direct code-only pushes get checks without an automatic bump.

`classify-ci` emits integer `schema_version: 1`, `mode=patch|tag|none`, target `version`, `tag`, and `source_commit`. `--merged` is supplied only after paginated GitHub API results confirm a merged PR targeting this repository's selected trunk. Merge commits are also detected from history. Classifiers never publish.

Trunk defaults to main. REPOSITORY_TRUNK is the common override for intentional policy changes. Development PRs use dev/<topic> and target main; see BRANCHING.md.

## Exact tested publication and recovery

`version.yml` is called only by a successful trunk-push CI with `go == 'true'`. It uses the existing repository variable `AIPLANE_VERSIONING_APP_ID` and secret `AIPLANE_VERSIONING_APP_PRIVATE_KEY`; neither was renamed. The repository-scoped `aiplane-versioning` App requires contents-write permission and the narrowly configured ruleset bypass described in [repository protection](docs/project/repository-protection.md).

The disposable CI checkout runs:

```bash
python scripts/publish_version.py --source TESTED_SHA --trunk main --merged --github-output
```

The helper requires a clean checkout and exact agreement between HEAD, GITHUB_SHA and the tested source. It fetches and checks remote trunk before mutation, commits only version mirrors for a patch, creates the immutable annotated tag, and pushes branch plus tag together with `git push --atomic`. It never refreshes onto newer code, rebases, retries a bump or force-pushes.

Output is schema version 1, `status=published|unchanged|superseded`, and `source_commit`; published results also include `version`, `tag`, and `version_commit`.

- Two PRs merge close together: a stale run reports `superseded`; the latest qualifying merge can coalesce changes into one patch.
- A later direct code-only push is not an automatic catch-up bump.
- A stale PR changes no version field: merge-base comparison accepts it; normal conflicts/current-branch rules still apply.
- Trunk advances during publication: the atomic push prevents a partial update, and the push fails; a fresh run rechecks the remote tip.
- A conflicting tag fails without moving or deleting it. Resolve through a new authorized version.
- A matching tag on the current remote tip is an unchanged rerun; an advanced patch child is superseded.
- App-generated version commits still receive checks. The existing exact tag prevents another bump.

## Build and publication policy

```bash
python scripts/build_release.py --tag v0.2.18 --output /tmp/aiplane-release
python scripts/build_release.py --verify-only --output /tmp/aiplane-release
```

Build requires a clean annotated-tag checkout and empty output directory. It produces one matching wheel/source pair, checksummed `provenance.json` and `SHA256SUMS`; verification rejects corruption, missing/unlisted artifacts, unsafe paths and mismatched versions. The helper never publishes. `verify_install_channels.py`, `verify_release_manifest.py`, and `write_release_evidence.py` retain their specialized installation, checksum and evidence responsibilities.

Successful version publication builds and pip-validates the exact tagged wheel/source set, then uploads a 30-day workflow artifact with source/version commit provenance. These are prerelease candidates, not public release evidence.

`classify-release --tag` validates tag/version/HEAD identity and compares against the first parent. Minor/major changes emit `publish=true` and publish automatically. Patch versions emit `publish=false`; a maintainer may deliberately select a patch through **Actions → Release artifacts → Run workflow**. Both paths qualify the exact tag commit through reusable CI's complete OS/Python/install-channel matrix, require success and `go == 'true'`, verify checksums and build-provenance attestations, and render notes from the maintained release-note input `CHANGELOG.md`.

Publication downloads the actual public assets and compares them with the validated checksums before dispatching the nine OS/channel post-publication checks. No PyPI publication is added. Never replace published assets or move an immutable tag. See [verification and rollback](docs/user/release-verification.md) for the single owner of post-publication instructions.

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

`verify-release.yml` retains Linux/macOS/Windows × pip/pipx/uv qualification,
attestations and sanitized lifecycle evidence. It now downloads checksummed provenance
and records the same bound artifact evidence as the other repositories.

Follow [BRANCHING.md](BRANCHING.md) for the shared trunk/dev branch convention,
version/tag rules and REPOSITORY_VERSIONING_ENABLED activation setting.

Automatic mutation additionally requires REPOSITORY_VERSIONING_ENABLED=true. This
is true for aiplane, whose App settings already exist, and false for Repo Pilot and
ACF until their repository-scoped App installation/key setup is complete. Disabled
versioning does not fail ordinary CI and does not create commits/tags. It does not
change the requirement for maintainer review before enabling automation.

Downloaded-release verification checks checksums and the selected tag/commit identity.
The published-release workflow separately verifies GitHub artifact attestations before
installation. It does not compare a fresh cross-platform rebuild byte-for-byte with
release archives. Local snapshot wheels use `scripts/build_local_wheel.py`; this
project's release builder requires a clean annotated tag.
