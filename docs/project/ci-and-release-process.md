# CI and Release Process

GitHub Releases are the current no-clone distribution channel. PyPI or another package index is not advertised until ownership, trusted publishing, and the first publication have been verified.

This document is the operational reference from pull-request validation through a validated CI artifact, optional GitHub Release publication, verification, and rollback.

## Lifecycle at a glance

```text
pull request
  -> quality, compatibility, install, and version-policy checks
  -> protected merge to main
  -> CI patch commit and immutable version tag
  -> validated wheel workflow artifact
  -> optional GitHub Release publication
  -> public cross-platform installation verification
```

The durable required check is **CI / Release gate**. The hosted rules and narrow permissions required by the versioning workflow are documented in [Repository Protection](repository-protection.md).

## Pull-request validation

Pull requests run the quality gate, supported-Python packaging checks, and Linux, macOS, and Windows installed-wheel lifecycle checks. They must not change package versions in `pyproject.toml` or `src/aiplane/__init__.py`; CI rejects such changes before merge. This keeps version ownership on `main` and prevents parallel branches from choosing the same release number.

Two PRs created from the same `main` version do not conflict solely because the first merge causes a version bump. If the second PR did not modify the version lines, merging it against current `main` retains the newer version. It needs updating only for a real content conflict or when the repository rule requiring the branch to be current blocks its merge.

## Ordinary merges: CI-owned patch versions and tags

After an ordinary pull request merges to `main` and **CI / Release gate** succeeds, CI refreshes from the latest `origin/main`, increments the patch component in both tracked version files, pushes a `[skip ci-version]` commit, creates an annotated immutable `vVERSION` tag marked `[ci-artifact]`, validates the exact tagged wheel, and uploads checksum- and provenance-bound workflow artifacts.

Version-mutation jobs share one concurrency group. If another merge moves `main` during the patch push, CI starts again from the latest tip and retries up to three times. Continued contention fails visibly instead of force-pushing or tagging the wrong commit; rerunning the failed workflow is then safe.

`[skip ci-version]` prevents another version mutation and skips the expensive matrix on the CI-owned commit. The skip applies only when the actor is `github-actions[bot]` and its commit contains the marker; contributor-authored marker text cannot bypass checks.

## Agreed minor, major, or explicit versions

For an agreed minor, major, or explicit version, an authorized maintainer uses the script in a clean, current `main` checkout and pushes that direct version commit through the configured maintainer bypass:

```bash
git switch main
git pull --ff-only
python scripts/version.py minor --dry-run
python scripts/version.py minor
# or: python scripts/version.py major
# or: python scripts/version.py set 1.0.0
python scripts/version.py check
```

CI preserves that authorized direct-main value and tags it without adding a patch. Ordinary PR merges never carry version edits and receive the automatic patch increment. Do not edit only one version file and do not create or move the tag manually.

## Expected edge cases and recovery

- **Two PRs merge close together:** serialized versioning refreshes from the latest `main`, so successive merges receive successive patch versions.
- **A stale PR changes no version field:** it remains valid unless it has a real merge conflict or the branch-current rule requires an update.
- **A PR changes a version field:** the version guard fails. Remove the edit and use the authorized direct-`main` flow for an agreed release.
- **`main` moves during the CI push:** CI retries from the new tip. After three failed races it stops without force-pushing; rerun it when activity settles.
- **The bot patch commit starts CI again:** the bot-and-marker guard prevents a second bump and duplicate expensive checks.
- **A tag already identifies the commit:** CI treats it idempotently; it must not create another version or move the tag.
- **Validation or publication fails:** do not claim or repair that release in place. Fix the cause through review and produce a new version.

## Rehearse locally

```bash
scripts/check.sh
python scripts/build_local_wheel.py --clean --validate-pip
```

Local snapshots are written under ignored `.aiplane/wheelhouse` with PEP 440 local metadata, checksum, and provenance. They are developer test artifacts, not public releases.

## Publish an existing CI tag

CI artifact tags do not publish automatically. In GitHub, open **Actions → Release artifacts → Run workflow**, enter the exact tag such as `v0.1.2`, and run it from trusted `main`.

The release workflow:

1. checks out the immutable tag and verifies tag/package agreement;
2. runs the full quality gate;
3. builds one wheel and one source distribution;
4. generates and verifies `SHA256SUMS`;
5. validates all installation owners;
6. refuses an incomplete artifact set;
7. creates the GitHub Release; and
8. confirms the published release has exactly one wheel, one source distribution, and `SHA256SUMS`.

A workflow run is not a successful release if the GitHub Release has no attached assets. Do not retag or silently replace a published version; correct it with a new version.

## Verify the published artifact

After publication, run **Actions → Verify published release → Run workflow** with the same tag. Its nine Linux/macOS/Windows × pip/pipx/uv jobs download the actual public assets, verify the portable checksum manifest, exercise install/replacement/uninstall, and upload canonical sanitized evidence.

Manual consumer smoke:

```bash
# Download the wheel and SHA256SUMS into one clean directory first.
python scripts/verify_release_manifest.py .
python -m pip install ./aiplane-VERSION-py3-none-any.whl
python -m pip show aiplane
aiplane --version
aiplane quickstart local-coding --dry-run
```

Use the same installation owner for upgrade and uninstall. Preserve reviewed profile YAML before changing versions. Credentials, caches, audit logs, tunnel state, and runtime weights remain owned by their respective systems.

## Integrity and rollback

Linux users may also run `sha256sum --check SHA256SUMS`; macOS users may run `shasum -a 256 --check SHA256SUMS`. On Windows, the project’s portable verifier avoids shell-specific checksum behavior; PowerShell users can independently compare `Get-FileHash -Algorithm SHA256 FILE` with the manifest.

For rollback, uninstall with the original installation owner, verify the previously downloaded immutable wheel, and reinstall it. Published tags and assets must never be moved or silently replaced.
