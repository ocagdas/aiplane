# Current validation

[CI.md](CI.md) owns check commands; [STATUS.md](STATUS.md) owns capabilities.

## Qualified scope

The consolidation fixes over `eb97320da765de2cbadd19839871e5234545e2db` passed
`make check` on Linux/Python 3.13.14: **918 passed, 9 opt-in skips**, formatting,
Ruff and shared conformance. Log: `/tmp/aiplane-divergence-final.log`.

The hardcoded runner path and formatting failures are fixed. Release tests now run
real checksum/provenance validation through subprocesses, accepting matching identity
and rejecting wrong identity, corruption and unlisted files. Generated/manual release
instructions extract source separately from the strict download directory.

Shared files and bundle manifests are byte-identical across Repo Pilot, aiplane and
ACF. Aiplane's conformance runner also passed against both sibling adapters. Path
containment and trunk-specific tracking improvements were retained and shared; product
classifier extensions are tested locally without imposing them on other adapters.
Workflow linting, documentation contracts and changed-file credential-signature scans
passed. Tests used synthetic credentials and isolated profiles.

## Unverified scope

These changes are uncommitted and require fresh hosted CI. The failed hosted run for
`eb97320` remains failed; local results do not qualify macOS/Windows or publication.
External-validator/performance skips, live providers, App publication and actual public
artifact attestations were not exercised. Hosted release verification still requires
GitHub attestations before installation; local checksum/identity checks are not a
replacement for that authorization. See [TODO.md](TODO.md) and
[hosted setup](docs/development/github-policy-setup.md).

No commits, pushes, tags or releases were performed by this task.
