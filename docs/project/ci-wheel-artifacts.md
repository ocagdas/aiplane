# CI Wheel Artifacts

Every successful push to protected `main`—normally a merged pull request—creates a GitHub Actions artifact named:

```text
aiplane-wheel-v<VERSION>-<FULL_MERGE_COMMIT_SHA>
```

The artifact contains the wheel, `SHA256SUMS`, and `provenance.json`. Provenance records the package version, exact merged commit, branch ref, and workflow run ID. The producing job depends on **CI / Release gate**, so it cannot run unless the full quality, compatibility, and Linux/macOS/Windows installation matrix succeeds.

Download the artifact from the successful CI workflow run, extract it into a clean directory, verify `SHA256SUMS`, and install the wheel through `pipx`, `uv tool`, or an explicitly active Python environment. This supports pre-release no-clone testing without requiring a source checkout.

CI artifacts are retained for 30 days, require repository/workflow access, and are not immutable public releases. They must not be advertised as the P0 release URL. The versioned GitHub Release remains the durable public artifact and rebuilds its own wheel and source distribution through the release workflow.
