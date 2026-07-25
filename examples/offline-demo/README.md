# Offline demo fixtures

These reviewed, synthetic fixtures support no-network demonstrations and CI-style
planning. They contain no local paths, endpoints, credentials, model weights, or
claims that a runtime is installed.

```bash
aiplane machines import examples/offline-demo/laptop-32gb.machine.yaml
aiplane machines recommend --model MODEL_ALIAS --runtime ollama
```

Use profile-owned model aliases or the existing materialized catalog for model
selection. A fixture is planning evidence only; run `hardware discover` on the
target machine before pulling or serving a model.
