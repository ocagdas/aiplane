# Repository Protection

The durable release-path check is **CI / Release gate**. It succeeds only after the full quality gate, supported-Python packaging checks, and Linux/macOS/Windows installed-wheel lifecycle jobs all succeed.

Maintainers must configure the default branch or an equivalent repository ruleset to:

- require pull requests before changes reach `main`;
- require **CI / Release gate** and require the branch to be current before merging;
- block force pushes and branch deletion;
- restrict bypass permission to designated maintainers;
- require release tags matching `v*` to come from a commit already present on protected `main`.

The release workflow independently reruns the full quality gate, validates the tag/package version, builds and verifies checksummed artifacts, exercises installation channels, and requires versioned release notes before publication. Repository settings are hosted state and cannot be enabled by a source change; a maintainer must verify the active rule after merging this implementation.

## Maintainer verification

Record the ruleset URL or a dated screenshot in private maintainer evidence. Confirm that a test pull request cannot merge while **CI / Release gate** is pending or failing, and that a release tag cannot be published from an unprotected side branch. Do not store access tokens or private repository-administration output here.
