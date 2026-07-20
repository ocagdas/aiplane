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

## Backup, recovery, and cross-machine replay

The editable YAML directory is the restorable and transferable source of truth. `profiles render` only reads those YAML files and prints one consistently ordered JSON snapshot for validation, comparison, CI, or archival evidence; the rendered JSON is not currently accepted as restore input and is not configuration for an IDE or runtime. Aiplane is not a backup service, so use normal reviewed filesystem or version-control procedures for profile YAML that is safe to store. Keep credentials, discovered caches, audit logs, tunnel state, and runtime model data out of that bundle.

```bash
mkdir -p demo-backup
cp -a profiles/local-dev demo-backup/local-dev
aiplane profiles render local-dev > demo-backup/local-dev.profile.json

# Restore the reviewed YAML, then prove it is coherent and equivalent.
cp -a demo-backup/local-dev profiles/local-dev-restored
AIPLANE_PROFILES_DIR=profiles aiplane profiles validate local-dev-restored
AIPLANE_PROFILES_DIR=profiles aiplane profiles render local-dev-restored > demo-backup/local-dev-restored.profile.json
```

`profiles repair` copies missing structure from a shipped template. It does not reconstruct user model choices, endpoints, policies, or other customizations and therefore does not replace a backup. Review profile archives before sharing because paths, hostnames, endpoints, account aliases, and other operational metadata may be sensitive.

To replay on another machine, copy the reviewed YAML directory, validate it, and then run `discover`, `doctor`, `recommend`, and the required exports on the destination. Identical machines with equivalent resolved inputs should reproduce byte-stable supported exports. Small hardware differences are acceptable when the destination remains capability-equivalent for the reviewed model/runtime/policy requirements; those differences should be reported, not silently erased. Material incompatibility may correctly change recommendations or block an export. Credentials, weights, caches, audit/tunnel state, and runtime data must be restored through their owning systems. First-class archive/restore, comparison, and provenance-aware drift workflows are planned after the P0 evidence gate.

## Pre-1.0 migration policy

Schema v1 is the only public canonical profile schema in the developer preview. Compatible clarifications may retain v1; any structural breaking change requires a new schema identifier and version. Aiplane does not silently rewrite profiles or canonical documents. Before a future v2 is accepted, the CLI must provide an explicit previewable migration command, document lossy changes, preserve the original, and keep v1 validation available for the announced transition window.

The multi-file YAML profile is still the editable source of truth. The canonical JSON document is an interchange and validation representation, not a second file that Aiplane keeps synchronized.
