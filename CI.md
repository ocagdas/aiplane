# Continuous integration

`ci.yml` (display name **CI**) checks pull requests, branch pushes, merge queues and manual runs. It is reusable for a release's exact commit. CI only grants version mutation to a successful push on the selected trunk. Trunk defaults to main; `REPOSITORY_TRUNK` is the optional repository-variable override.

## Local commands and hosted jobs

Run `make check` or `scripts/check.sh` from an environment installed with `python -m pip install -e '.[dev]'`. Formatting and Ruff cover source, tests and release scripts. Formatting is check-only; `make format` explicitly applies fixes. `scripts/check.sh quick` is a smaller developer check, not release qualification.

Required jobs:

- `checks`: checksum-pinned actionlint 1.7.12 workflow validation, formatting, Ruff, isolated-profile full pytest suite on Python 3.11, with JUnit evidence.
- `compatibility`: packaging and command contracts on Python 3.12 and 3.13.
- `install-channels`: real pip, pipx and uv installed-wheel lifecycle checks on Linux, macOS and Windows, using Python 3.13. These exercise installed resources, replacement and uninstall without starting providers, model runtimes, tunnels or IDE clients.

**Quality gate** requires every required job to succeed. Missing, failed, skipped or cancelled results block; additional failed dependencies also block. Its `go=true|false` output is also exposed by reusable CI. Consumers require both successful qualification and `go == 'true'` on the same commit.

The `quality-gate` artifact contains `ci-gate.json`:

```json
{"schema_version": 1, "go": true, "commit": "tested-sha", "run_id": "run-id", "checks": {"checks": "success", "compatibility": "success", "install-channels": "success"}}
```

Run `python scripts/ci_gate.py --results jobs.json --report /tmp/ci-gate.json` to evaluate dependency results locally. Each input job is an object with a `result` field; malformed input fails closed. Local reports do not authorize publication.

## Activation and protection

The hosted ruleset now requires **Quality gate**, replacing `Release gate`. The rule was updated through the GitHub API on 10 September 2026; prove a failing non-bypass PR cannot merge after the current workflow delta is pushed. Preserve branch-current, review, force-push/deletion, immutable-tag and GitHub App constraints in [repository protection](docs/project/repository-protection.md).

Release CI repeats the complete matrix on the resolved immutable tag commit, including manual patch publication. The version workflow cannot mutate versions during PR, manual or reusable release checks. Current local evidence is in [VALIDATION.md](VALIDATION.md); hosted work remains in [TODO.md](TODO.md).

See [version and release policy](VERSIONING.md), [development setup](docs/development/setup.md), and [published release verification](docs/user/release-verification.md).

Shared conformance is mandatory in the static/local gate. The canonical verify-release.yml
checks downloaded release identity before installation; see VERSIONING.md for each
product's publication/verification activation. All external Actions are pinned.

Follow [BRANCHING.md](BRANCHING.md) for the shared trunk/dev branch convention,
version/tag rules and REPOSITORY_VERSIONING_ENABLED activation setting.
