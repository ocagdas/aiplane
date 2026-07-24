# Public profile schema v1

An editable Aiplane profile remains a directory of nine focused YAML files. `aiplane profiles render` combines those files into one canonical, read-only JSON document for external validation, comparison, and archival.

```bash
aiplane profiles render local-dev > local-dev.profile.json
aiplane profiles schema > aiplane-profile-v1.schema.json
```

The rendered document contains `$schema`, `schema_version: "1.0"`, the profile name, and one object for each source file: hardware, backends, repository, tools, approvals, environment, models, targets, and orchestrators. Rendering is deterministic and never rewrites the YAML source.

The repository schema is [`schemas/aiplane-profile-v1.schema.json`](../../schemas/aiplane-profile-v1.schema.json). It is packaged with wheels and printed by `profiles schema`, so validators do not need to import Aiplane or install a Python validation library.

## Validation

`aiplane profiles validate PROFILE` applies Aiplane's built-in v1 structural and cross-reference contract. The public JSON Schema remains the portable external-validation contract for rendered documents; CI validates canonical instances against it. Every CLI result includes a canonical JSON path and a remediation. Validation does not modify the profile.

```bash
aiplane profiles validate local-dev
```

## Recommendation-critical model contracts

The built-in v1 contract validates the model fields already consumed by fit checks, runtime selection, and recommendations; the public schema expresses the matching portable structural requirements. Every configured model alias must have a non-empty provider and provider-native model ID. When present, `enabled` and `local` must be booleans; RAM, VRAM, and parameter values must be finite non-negative numbers; role/runtime/accelerator lists must contain unique non-empty strings; and recommended RAM/VRAM cannot be lower than the corresponding minimum.

A default role may be explicitly set to `null` to mean “not selected.” A non-null default must resolve to a configured alias. These checks prevent strings such as `"yes"` from silently behaving as true and prevent contradictory thresholds from influencing fit or ranking.

Validation findings identify the canonical JSON path, observed value, and remediation:

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

## YAML parser subset limits

Aiplane keeps profile loading dependency-free with a built-in YAML subset parser. Supported inputs are nested mappings, scalars, and inline lists (`[a, b]`). Inline-list values containing commas, quotes, or backslashes must be quoted; standard YAML single quotes use doubled apostrophes (`its`), and Aiplane emits JSON-style double quotes whenever it writes such values. Profile names are simple directory names and cannot contain path separators or traversal segments. A profile directory must be a real child of the configured profiles root; profile symlinks are rejected.

Unsupported YAML constructs are rejected with line-specific errors:

- dash-list syntax (`- item`);
- document markers (`---`, `...`);
- block scalars (`|`, `>`);
- anchors, aliases, and tags.

When you need those constructs, rewrite the profile files using the supported subset before running `profiles validate`, `profiles archive`, or import workflows.

## Backup, recovery, and cross-machine replay

The editable YAML directory remains the restorable and transferable source of truth. `profiles render` only reads the nine canonical YAML files and prints one consistently ordered JSON snapshot for validation, comparison, CI, or archival evidence; the rendered JSON is not currently accepted as restore input and is not configuration for an IDE or runtime.

`profiles archive` creates a separate deterministic JSON transfer artifact. It includes the nine canonical YAML files plus profile-owned `model-providers.yaml` when present, records byte sizes and SHA-256 checksums, and carries a versioned inclusion/exclusion manifest. It rejects raw credential values and symlinked portable files. It excludes ignored discovery caches and provider overrides, local CLI/credential/audit/session/tunnel state, model weights, runtime caches, and generated exports.

```bash
# Validate and inspect what would be included without writing.
aiplane profiles archive local-dev --output local-dev.aiplane-profile.json --dry-run

# Write the archive. Existing archive files require explicit --overwrite.
aiplane profiles archive local-dev --output local-dev.aiplane-profile.json

# Compare the editable source with the validated archive without restoring it.
aiplane profiles compare local-dev local-dev.aiplane-profile.json --right-source archive

# On the destination, preview first; preview is the default.
aiplane profiles restore local-dev.aiplane-profile.json --as restored-local

# Create a new profile only after review.
aiplane profiles restore local-dev.aiplane-profile.json --as restored-local --yes
aiplane profiles validate restored-local
aiplane profiles compare local-dev restored-local
aiplane profiles drift restored-local
aiplane doctor --profile restored-local

# After at least two clients replay and re-archive the profile:
aiplane profiles replay-check local-dev.aiplane-profile.json \
  --source archive \
  --client-archive laptop-replayed.json \
  --client-archive desktop-replayed.json
```

Restore revalidates the archive kind/version, duplicate JSON keys, supported filenames, required files, YAML mappings, size limits, checksums, and credential safety before writing. It materializes a complete temporary profile directory and renames it into place; existing profile directories are never overwritten, even with `--yes`. Choose a new name with `--as` when a destination already exists.

`profiles repair` copies missing structure from a shipped template. It does not reconstruct user model choices, endpoints, policies, or other customizations and therefore does not replace an archive. Aiplane creates and validates the transfer artifact but does not store, synchronize, encrypt, or publish it. Review archives before sharing because paths, hostnames, endpoints, account aliases, and other operational metadata may be sensitive.

After restoration, run `profiles compare`, `profiles drift`, `doctor`, `recommend`, and the required exports on the destination. `compare` accepts profile operands by default and explicit archive operands with `--left-source archive` or `--right-source archive`; `drift` accepts an archive with `--source archive`. Canonically identical portable evidence is `exact`. Hardware-only variance is `capability_equivalent` only when every selected local model meets its configured minimum RAM, VRAM, GPU-vendor, and accelerator-API requirements on both sides. A minimum failure is `materially_incompatible`; missing selected-model or machine evidence is `unresolved`; other portable configuration changes are conservatively material. Results identify every evidence source. These commands are read-only, and tested archive/restore replay preserves byte-stable supported Continue exports. Credentials, weights, caches, audit/tunnel state, and runtime data must be restored through their owning systems.

For multi-client replay, each destination re-archives its restored profile and returns that artifact through an approved transfer channel. `profiles replay-check` compares one approved source with at least two distinct client archives in a single read-only result. It summarizes classifications and exits nonzero when any client is unresolved or materially incompatible. This is portable configuration evidence, not proof of live endpoint reachability; run `doctor`, `profiles drift`, and the relevant endpoint/runtime checks on every actual client.

## Pre-1.0 migration policy

Schema v1 is the only public canonical profile schema in the developer preview. Compatible clarifications may retain v1; any structural breaking change requires a new schema identifier and version. Aiplane does not silently rewrite profiles or canonical documents. Before a future v2 is accepted, the CLI must provide an explicit previewable migration command, document lossy changes, preserve the original, and keep v1 validation available for the announced transition window.

The multi-file YAML profile is still the editable source of truth. The canonical JSON document is an interchange and validation representation, not a second file that Aiplane keeps synchronized.
