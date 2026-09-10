# Published release verification

## Verify and consume a published release

Successful publication dispatches **Verify published release** automatically. Each matrix job verifies both the SHA-256 manifest and GitHub build-provenance attestation before installation. Maintainers may also run it manually with the same tag. Its nine Linux/macOS/Windows x pip/pipx/uv jobs download the public assets, verify the manifest, exercise install/replacement/uninstall, and upload sanitized evidence.

Manual smoke after downloading the wheel, source archive, `provenance.json` and `SHA256SUMS` into one clean directory:

```bash
python scripts/verify_release_manifest.py .
for artifact in ./*.whl ./*.tar.gz ./provenance.json; do
  gh attestation verify "$artifact" --repo ocagdas/aiplane
done
python -m pip install ./aiplane-VERSION-py3-none-any.whl
python -m pip show aiplane
aiplane --version
aiplane quickstart local-coding --dry-run
```

Use the same installation owner for upgrade and uninstall. Preserve reviewed profile YAML; credentials, caches, logs, tunnel state, and runtime weights remain owned by their respective systems.

## Integrity and rollback

Linux can run `sha256sum --check SHA256SUMS`; macOS can run `shasum -a 256 --check SHA256SUMS`. The portable verifier avoids shell-specific checksum behavior on Windows. `gh attestation verify "$artifact" --repo ocagdas/aiplane`, once for each payload and provenance file, independently verifies that GitHub Actions built the files from this repository; checksum and attestation checks serve different purposes and both are required by the hosted workflow.

For rollback, uninstall with the original installation owner, verify a previously downloaded immutable wheel, and reinstall it. Published tags and assets must never be moved or silently replaced.
