# Command Coverage

This table tracks the public CLI surface at a high level. Use it during release review to keep docs, tests, and status claims aligned.

| Area | Primary commands | Status | Notes |
| --- | --- | --- | --- |
| Local config | `config templates/init/show/get/set/default-profile` | Implemented | Local `.aiplane/config.yaml` is ignored by git. |
| Credentials | `credentials list/show` | Implemented / local-only | Reads ignored local credential refs; output is redacted and raw secrets are not printed. |
| Profiles | `profiles list/templates/create/show/validate` | Implemented | Profile templates are versioned; editable profiles can be local or external. |
| Environment/setup | `environment show/list/active/use/plan/doctor` | Implemented / growing | `environment doctor` defaults to a human text table; use `--format json` for scripts. Expand scope as new tools are integrated. |
| External tools | `tools list/doctor/plan/export/install` | Implemented / growing | Covers Azure CLI, OpenTofu/Terraform/Pulumi, Vagrant, Packer, Docker/Compose, Dev Container CLI, kubectl, Helm, SSH, Ansible, and benchmark helpers. Plan/export prints non-mutating starter workflow artifacts for VM/IaC/devcontainer/configuration tools. |
| Providers/sources | `providers list/show/models/add/enable/disable/remove/init-defaults/clear/doctor` | Implemented / partial discovery | Online adapters exist for selected sources, including Azure OpenAI deployments when endpoint/key configuration is present; broader managed-provider discovery still needs hardening. |
| Models | `models list/show/defaults/use/enable/disable/refresh/promote/clear-cache/pull/test/benchmark` | Implemented / ongoing | `promote` is the reviewed path from generated catalog entry to curated profile alias. |
| Runtimes | `runtimes map/list/sources/models/model/use/prerequisites/doctor/bundle/install/start/stop/...` | Implemented / helper-dependent | Lifecycle delegates to runtime helpers where supported. |
| Hardware | `hardware show/templates/schema/active/use/set/discover/doctor/recommend/export-machine` | Implemented / ongoing | Discovery is best-effort and platform-dependent. |
| Machines | `machines import/list/show/validate/recommend/discover/cache-list/cache-clear/azure-status/import-azure-sku/profile-remote-plan` | Implemented / remote execution planned | Azure discovery has live/offline/cache paths. |
| Orchestrators | `orchestrators list/show/doctor/setup` | Catalog/readiness implemented | Stacks remain the operational binding point. |
| Stacks | `stacks setup/list/show/plan/doctor/status/export/prepare/start/stop/restart` | Implemented / same-host execution first | Plan/doctor include preflight checks; remote/AKS execution remains guarded/planned. |
| Integrations | `integrations list/roles/plan/setup/export` | Implemented / hardening | Config/export first; no target tool files are edited. `export --from-plan` can reuse a saved plan decision. |
| Agents | `agents templates/plan/export` | Initial scaffold | Prints non-mutating starter agent application files that use selected model endpoints. |
| Remote | `remote doctor/tunnel-plan/tunnel-start/tunnel-status/tunnel-stop` | Implemented / guarded | SSH tunnel lifecycle is narrow and auditable. |
| Deploy | `deploy list/show/plan/doctor/apply` | Partial / guarded | Azure VM narrow apply exists; broad AKS/cloud apply remains planned. |
| MCP | `mcp manifest/serve` | Implemented / hardening | Read tools and narrow guarded writes exist; broad mutation remains out of scope. |
| Audit/policy | `audit tail`, `policy explain` | Implemented | Used for local governance and debugging. |
