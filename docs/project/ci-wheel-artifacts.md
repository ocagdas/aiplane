# CI Wheel Artifacts

Every successful push to protected `main`—normally a merged pull request—creates a GitHub Actions artifact named:

```text
aiplane-wheel-v<VERSION>-<SHORT_VERSION_COMMIT_SHA>
```

The artifact contains the wheel, `SHA256SUMS`, and `provenance.json`. Provenance records the package version, release tag, source commit, exact versioned commit, short versioned commit, branch ref, and workflow run ID. The producing job depends on **CI / Release gate**, so it cannot run unless the full quality, compatibility, and Linux/macOS/Windows installation matrix succeeds.

Download the artifact from the successful CI workflow run, extract it into a clean directory, verify `SHA256SUMS`, and install the wheel through `pipx`, `uv tool`, or an explicitly active Python environment. This supports pre-release no-clone testing without requiring a source checkout.

CI artifacts are retained for 30 days, require repository/workflow access, and are not immutable public releases. They must not be advertised as the P0 release URL. The versioned GitHub Release remains the durable public artifact and rebuilds its own wheel and source distribution through the release workflow.

The artifact name intentionally includes the version only once, for example `aiplane-wheel-v0.1.1-5dab675`. The official wheel filename and metadata carry the package version as `0.1.1`; the artifact suffix is a 7-character commit identifier for traceability, not part of the Python package version.
