# Changelog

This file records user-visible changes for the current pre-1.0 development line. Until 1.0, minor releases may include compatibility changes; migration notes must call them out here.

## Unreleased

### Added

- A shared, versioned provenance and uncertainty contract for discovery, doctor, recommendation, profile display, and integration planning.
- Signed build-provenance attestations for release distributions, alongside the portable SHA-256 manifest.
- An optional, versioned materialized model catalog with exact-match indexes and on-demand 1k/10k/100k query benchmarks.
- Cross-platform per-device accelerator discovery, runtime-aware placement assessment, context/KV-cache estimates, and versioned placement-readiness scoring with safe data-only extensions.

### Changed

- CLI parser construction now has a dedicated owner, leaving the composition root focused on command dispatch and process error handling.
- Release notes are rendered from this tracked changelog and include verification, upgrade, and rollback guidance.
- Model queries can select aliases, provider-native IDs, runtimes/runners, parameter ranges, benchmark scores, and exact catalog properties without repeatedly enriching the source catalog.

### Fixed

- Evidence output now uses the same configured, detected, discovered, generated, measured, and unresolved source vocabulary across public planning surfaces.
