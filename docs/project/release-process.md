# Release Process

GitHub Releases are the current no-clone distribution channel. PyPI or another package index is not an advertised channel until its ownership, trusted publishing configuration, and first publication have been verified explicitly.

## Prepare

1. Complete the public launch checklist and update release notes.
2. Set `[project].version` in `pyproject.toml`; pre-1.0 tags use the matching `vVERSION` form.
3. Run `scripts/check.sh`, the required profile/environment doctors, and the install-channel validator against a freshly built wheel.
4. Review the wheel and source distribution for secrets, generated state, and unexpected files.

Local artifact rehearsal:

```bash
python -m pip install build pipx
python -m build
python scripts/verify_install_channels.py dist
```

The validator uses temporary isolated homes. For each of `pip`, `pipx`, and `uv tool`, it installs the wheel, verifies CLI help and packaged templates, rehearses the channel-appropriate upgrade or artifact replacement, uninstalls it, and checks that the executable is removed.

## Publish

The human maintainer creates and pushes a signed or annotated version tag after reviewing the commit:

```bash
git tag -a v0.1.0 -m "aiplane v0.1.0"
git push origin v0.1.0
```

`.github/workflows/release.yml` rejects a tag that does not match `pyproject.toml`, builds both wheel and source distribution, validates the wheel through all three install channels, and creates the GitHub Release with those artifacts. Normal pull-request and main-branch CI separately exercises the wheel lifecycle on Linux, macOS, and Windows.

Do not retag or silently replace a published version. Correct a bad release with a new version and release notes. Enabling a Python package index is a separate release decision; use trusted publishing and add index-install validation before documenting bare package-name install commands as available.

## Consumer verification

Follow the commands in [Setup](../user/setup.md#standard-wheel-install-no-repository-clone). Confirm the installed version and first safe outcome:

```bash
python -m pip show aiplane
aiplane profiles templates
aiplane quickstart local-coding --dry-run
```
