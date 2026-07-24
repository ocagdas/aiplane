# CI and Release Process

This is the operational reference from pull-request validation through CI versioning, workflow artifacts, selective GitHub Release publication, verification, and rollback. GitHub Releases are the current no-clone distribution channel; a package index is not advertised until ownership and trusted publishing are verified.

## Lifecycle at a glance

```text
pull request
  -> quality, compatibility, install, and version-policy checks
  -> protected merge to main
  -> CI-owned version commit/tag using a short-lived GitHub App token
  -> validated 30-day wheel workflow artifact
  -> minor/major: automatic GitHub Release
     patch: no public release unless manually selected
  -> public cross-platform installation verification
```

The PR UI displays **CI / Release gate**. The ruleset check value is the job name, `Release gate`. Hosted setup and trust boundaries are documented in [Repository Protection](repository-protection.md).

## Pull-request validation

PRs run the quality gate, supported-Python packaging checks, and Linux/macOS/Windows installed-wheel lifecycle checks. On each hosted operating system, the matrix builds the wheel and invokes its installed `aiplane` executable through real `pip`, `pipx`, and `uv` lifecycles in isolated homes. Each channel performs one full clean-workspace behavior check, then a focused replacement smoke before uninstall; the smoke confirms the wheel identity, packaged templates, persisted profile, and MCP manifest without repeating the expensive exports and MCP stdio exchange. The jobs do not install model runtimes, open SSH tunnels, contact providers, or launch IDE clients. Those are deliberate field-evidence checks, not a claim made by packaging CI. They must not change package versions in `pyproject.toml` or `src/aiplane/__init__.py`; CI rejects those edits before merge.

Two PRs created from the same `main` version do not conflict solely because the first merge causes a patch bump. A second PR that did not modify the version lines retains the newer `main` value when merged. It needs updating only for a real conflict or because the branch-current rule requires it.

## Ordinary merges: automated patch versions

After an ordinary PR merges and `Release gate` succeeds, CI:

1. obtains a short-lived token for the private `aiplane-versioning` GitHub App;
2. refreshes from the latest `origin/main`;
3. increments the patch component in both version files;
4. pushes `chore(release): vVERSION [skip ci-version]`;
5. retries from the latest `main` up to three times if another merge wins the race;
6. creates the immutable annotated `vVERSION` tag;
7. builds and validates the exact tagged wheel; and
8. uploads the wheel, checksum, and provenance as a 30-day Actions artifact.

The mutation jobs share one concurrency group. They never force-push. Continued contention fails visibly and can be rerun safely.

The loop marker is trusted only when the event actor is `aiplane-versioning[bot]`; author text in a forged commit cannot bypass checks. The app tag push starts **Release artifacts**, where semantic classification recognizes a patch and intentionally skips public publication.

## Intentional minor, major, and explicit versions

Package versions are never changed on PR branches. An authorized administrator starts from clean, current `main`:

```bash
git switch main
git pull --ff-only
python scripts/version.py minor --dry-run
python scripts/version.py minor
# or: python scripts/version.py major
# or: python scripts/version.py set 1.0.0
python scripts/version.py check
git diff -- pyproject.toml src/aiplane/__init__.py
```

Commit only the synchronized version files and push through the documented administrator bypass. The local helper rejects equal or decreasing versions, and CI repeats that defense, preserves a valid selected value without adding a patch, and lets the app create the immutable tag.

The release workflow compares that version with its first parent:

- patch change: keep the tag and Actions artifact, but do not publish automatically;
- minor or major change: run the full release gate and publish automatically;
- invalid/equal/decreasing change: fail without publication.

## Publication and manual patch override

Automatic minor/major publication and manual selected-tag publication both:

1. verify tag, commit, and package-version agreement;
2. run the full quality gate;
3. build one wheel and one source distribution;
4. generate and verify `SHA256SUMS`;
5. create and locally verify signed build-provenance attestations for both distributions;
6. render release notes from tracked `CHANGELOG.md`;
7. validate pip, pipx, and uv installation;
8. reject an incomplete artifact set;
9. create the GitHub Release;
10. confirm exactly one wheel, one source distribution, and `SHA256SUMS`; and
11. dispatch the public cross-platform checksum, attestation, and installation verification workflow.

To deliberately publish an existing patch tag, open **Actions -> Release artifacts -> Run workflow**, enter the exact tag, and run it from trusted `main`. Manual selection changes publication intent, not validation strength.

A workflow artifact is not a GitHub Release, and a release page without its required assets is not complete. Never move a tag or replace assets under a published version; correct a fault with a new version.

## Expected edge cases and recovery

- **Two PRs merge close together:** serialized versioning refreshes from latest `main`, producing successive patch versions.
- **A stale PR changes no version field:** it remains valid unless it conflicts or the current-branch rule requires an update.
- **A PR changes a version field:** the PR guard fails; remove the edit.
- **`main` moves during the push:** CI retries three times, then stops without force-pushing.
- **App configuration is absent or invalid:** the mutation job fails with a named variable/secret error before checkout or push.
- **The app patch commit starts CI:** actor-plus-marker checks prevent a second bump and duplicate expensive jobs.
- **A patch tag starts the release workflow:** classification succeeds but public publication is skipped.
- **A minor/major publication fails:** no complete release is claimed; fix through review and issue a new version.
- **A tag already identifies the commit:** tagging is idempotent and never moves the tag.

## Local rehearsal

```bash
scripts/check.sh
python scripts/build_local_wheel.py --clean --validate-pip
```

Local snapshots under ignored `.aiplane/wheelhouse` use PEP 440 local metadata and are not official release wheels.

## Verify and consume a published release

Successful publication dispatches **Verify published release** automatically. Each matrix job verifies both the SHA-256 manifest and GitHub build-provenance attestation before installation. Maintainers may also run it manually with the same tag. Its nine Linux/macOS/Windows x pip/pipx/uv jobs download the public assets, verify the manifest, exercise install/replacement/uninstall, and upload sanitized evidence.

Manual smoke after downloading the wheel and manifest:

```bash
python scripts/verify_release_manifest.py .
gh attestation verify aiplane-* --repo ocagdas/aiplane
python -m pip install ./aiplane-VERSION-py3-none-any.whl
python -m pip show aiplane
aiplane --version
aiplane quickstart local-coding --dry-run
```

Use the same installation owner for upgrade and uninstall. Preserve reviewed profile YAML; credentials, caches, logs, tunnel state, and runtime weights remain owned by their respective systems.

## Integrity and rollback

Linux can run `sha256sum --check SHA256SUMS`; macOS can run `shasum -a 256 --check SHA256SUMS`. The portable verifier avoids shell-specific checksum behavior on Windows. `gh attestation verify aiplane-* --repo ocagdas/aiplane` independently verifies that GitHub Actions built the files from this repository; checksum and attestation checks serve different purposes and both are required by the hosted workflow.

For rollback, uninstall with the original installation owner, verify a previously downloaded immutable wheel, and reinstall it. Published tags and assets must never be moved or silently replaced.
