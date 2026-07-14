# Public profile schema v1

An editable Aiplane profile remains a directory of nine focused YAML files. `aiplane profiles render` combines those files into one canonical, read-only JSON document for external validation, comparison, and archival.

```bash
aiplane profiles render local-dev > local-dev.profile.json
aiplane profiles schema > aiplane-profile-v1.schema.json
```

The rendered document contains `$schema`, `schema_version: "1.0"`, the profile name, and one object for each source file: hardware, backends, repository, tools, approvals, environment, models, targets, and orchestrators. Rendering is deterministic and never rewrites the YAML source.

The repository schema is [`schemas/aiplane-profile-v1.schema.json`](../../schemas/aiplane-profile-v1.schema.json). It is packaged with wheels and printed by `profiles schema`, so validators do not need to import Aiplane or install a Python validation library.

## Validation

`aiplane profiles validate PROFILE` checks the v1 structure plus profile cross-references. Every result includes a canonical JSON path and a remediation. Validation does not modify the profile.

```bash
aiplane profiles validate local-dev
```

## Merge semantics

Canonical profile document merges follow these rules:

1. mappings merge recursively by key;
2. lists replace the complete earlier list;
3. scalar values replace the earlier value;
4. explicit `null` replaces the earlier value;
5. inputs are not mutated.

There is no implicit merge of editable profile directories today. These rules define deterministic behavior for comparison/import tooling and prevent surprising list concatenation or silent null deletion.

## Pre-1.0 migration policy

Schema v1 is the only public canonical profile schema in the developer preview. Compatible clarifications may retain v1; any structural breaking change requires a new schema identifier and version. Aiplane does not silently rewrite profiles or canonical documents. Before a future v2 is accepted, the CLI must provide an explicit previewable migration command, document lossy changes, preserve the original, and keep v1 validation available for the announced transition window.

The multi-file YAML profile is still the editable source of truth. The canonical JSON document is an interchange and validation representation, not a second file that Aiplane keeps synchronized.
