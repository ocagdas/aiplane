# Offline demo fixtures

These reviewed, synthetic fixtures support no-network demonstrations and CI-style
planning. They contain no local paths, endpoints, credentials, model weights, or
claims that a runtime is installed.

```bash
aiplane models list --offline-catalog examples/offline-demo/models.catalog.yaml --machine-file examples/offline-demo/laptop-32gb.machine.yaml --runtime ollama --role chat
# Or import the machine deliberately when you want it persisted in the profile:
aiplane machines import examples/offline-demo/laptop-32gb.machine.yaml
```

The first command is the explicit read-only simulation loader; do not combine
`--machine-file` with `--current-machine`. The fallback catalog is versioned and
reviewed fixture data, not a claim about a provider's current catalog. Use profile-owned model aliases or the existing materialized catalog for model
selection. A fixture is planning evidence only; run `hardware discover` on the
target machine before pulling or serving a model.
