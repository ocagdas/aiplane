# Current validation

[CI.md](CI.md) owns check commands; [STATUS.md](STATUS.md) owns capabilities.

## Qualified scope

On 11 September 2026, the uncommitted changes over
`ba626dbacd168dfe17d7344779d14fbad2dc9bae` passed `make check` on Linux with
Python 3.13.14: **909 passed, 9 opt-in skips**, formatting, Ruff and shared conformance.
Log: `/tmp/yaml-pins-aiplane-full.log` (temporary local evidence).

Credential listing preserves boolean presence flags while sanitizing display fields;
regressions use synthetic credentials and isolated profiles. Workflow conformance
requires consistent commit pins and exact version comments. Shared structural policy
now links to its owners instead of repeating their rules.

## Unverified scope

The changed revision still needs hosted CI, including macOS/Windows installation
qualification. Earlier hosted success for the baseline does not qualify these changes.
Skipped external-validator/performance tests, live providers, App publication and
published-asset attestation were not exercised by this local run. See [TODO.md](TODO.md)
and [hosted setup](docs/development/github-policy-setup.md) for remaining activation.
No commits, pushes, tags or releases were performed.

The shared workflow-pin fix was validated through real YAML parsing: the original
inline unpinned action now exits nonzero. Regression coverage includes quoted keys,
flow mappings, aliases, reusable workflows, duplicate keys and shell text. All current
workflow pins and managed bundle hashes pass. This changed revision still requires
hosted CI; earlier hosted success does not qualify the new validator.
