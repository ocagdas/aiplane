# Cloud Deployment

Cloud deployment starts with Azure. The first target is Azure CLI (`az`) from the
local machine, followed by `kubectl` for AKS cluster operations.

The goal is not to replace Azure CLI, AWS CLI, SSH, Docker, Helm, or Kubernetes.
`aiplane` keeps the target configuration in a profile, shows the plan, checks
the local/cloud prerequisites, and then calls the existing tools.

## Commands

```bash
aiplane deploy list
aiplane deploy show --target aks_gpu_pool
aiplane deploy plan --target aks_gpu_pool
aiplane deploy doctor --target aks_gpu_pool
aiplane deploy plan --target azure_gpu_vm
aiplane deploy doctor --target azure_gpu_vm
```

`apply` is guarded:

```bash
aiplane deploy apply --target aks_gpu_pool
aiplane deploy apply --target azure_gpu_vm
```

Run `plan` first. `apply` only runs the narrow mutating steps shown in the plan.
For AKS this currently means bootstrap steps such as loading cluster credentials
and creating the target namespace. For Azure VM targets this means Azure CLI
resource creation steps such as resource group creation, VM creation, and
optional SSH port opening. Runtime manifests for Ollama/vLLM model serving are a
later step.

## Machine Import Is Not Provisioning

`aiplane machines import` and `aiplane machines import-azure-sku` only register machine profiles for planning and recommendation. They do not create Azure resources.

Use `aiplane deploy plan` and `aiplane deploy doctor` to render and check provisioning steps. Guarded Azure VM apply is available for the narrow create path shown in the plan. AKS apply is currently limited to narrow bootstrap steps. Stack deployment is automatic only for same-host/local runtime lifecycle steps.

## Target Configuration

Targets live in `profiles/<profile>/targets.yaml`. The default profile includes
`aks_gpu_pool`:

```yaml
default: aks_gpu_pool
targets:
  aks_gpu_pool:
    type: azure_aks
    control_cli: az
    resource_group: rg-ai-coding
    cluster: ai-coding-aks
    namespace: aiplane-models
    runtime: ollama
    image: ollama/ollama:latest
```

Before using it, set real values for your Azure subscription, resource group,
cluster, namespace, runtime, image, and endpoint policy.

The default profile also includes `azure_gpu_vm`, a plan-only Azure VM target for
single-machine cloud GPU or CPU-heavy setups. It includes resource classes for:

- `inference_small`: lower-cost LLM inference and simple coding models.
- `inference_large`: high-VRAM inference for larger code/reasoning models.
- `training_finetune`: fine-tuning, training, and heavier experiments.
- `cpu_compile`: compilation, builds, package creation, and indexing.
- `memory_indexing`: embeddings preprocessing and memory-heavy analysis.

Render the VM plan before provisioning anything:

```bash
aiplane deploy plan --target azure_gpu_vm
aiplane deploy doctor --target azure_gpu_vm
```

Create the VM only after reviewing the plan:

```bash
aiplane deploy apply --target azure_gpu_vm
```

Azure SKU names and GPU availability change by region and subscription quota.
Treat the profile sizes as starting points and validate with `az vm list-skus`,
Azure quota checks, and your target region before creating resources.

## Roadmap

Order of work:

1. Azure CLI checks and AKS target planning.
2. AKS bootstrap through `az`, `kubectl`, and later `helm`.
3. Azure GPU VM target over `az` and SSH. - Plan/doctor implemented.
4. Model-serving manifests for Ollama/vLLM.
5. Export local IDE/CLI configuration pointing at the deployed endpoint.
6. AWS CLI and generic SSH targets after Azure is stable.

## Remote Endpoint Access and Authentication

For shared workstations and cloud deployments, do not expose the raw model server port directly to a team or the internet. Put a controlled endpoint in front of it.

Recommended patterns:

- **Local-only workstation**: bind the model server to `127.0.0.1` and let only the local user connect.
- **Shared workstation on a trusted network**: bind to a private network interface, require authentication, and restrict firewall/VPN access.
- **Cloud VM**: expose through a reverse proxy or gateway with TLS and auth; keep the model runtime itself private.
- **AKS/shared cluster**: expose through Kubernetes Service plus Ingress/Gateway/API gateway, with TLS, auth, quota, and audit.

Useful connection options:

- SSH tunnel for individual users or early testing:

```bash
ssh -L 11434:127.0.0.1:11434 user@gpu-workstation
```

- HTTPS reverse proxy such as Nginx, Caddy, Traefik, or an API gateway.
- Kubernetes Ingress/Gateway for AKS or other Kubernetes targets.
- VPN/private network access for team-only endpoints.

Authentication options, from simplest to stronger:

- Per-user bearer/API keys at the gateway.
- Basic auth only for quick internal testing, preferably over TLS.
- OAuth/OIDC through a gateway for teams.
- Azure Entra ID, managed identity, or API Management for Azure-hosted endpoints.
- mTLS for high-control internal environments.

`aiplane` should store endpoint URL, auth mode, and API key environment-variable names in profile config. It should not store real secrets in YAML. IDE/CLI export should then point tools such as Continue, Cursor-compatible clients, or generic OpenAI-compatible clients at the controlled endpoint.

Example target endpoint shape:

```yaml
targets:
  shared_gpu_endpoint:
    type: shared_workstation
    endpoint: https://llm-workstation.example.com/v1
    auth:
      mode: bearer
      api_key_env: AIPLANE_SHARED_LLM_KEY
```

For production shared use, add rate limits, per-user keys, logging, and model access policy before enabling remote write-heavy agent workflows.

## Focused Access Patterns

The first supported remote-access patterns should be deliberately narrow:

1. SSH tunnel for individual users and early testing.
2. Private LAN/VPN access for shared workstations.
3. Azure API Management for Azure-hosted shared endpoints, especially AKS or Azure GPU VM targets.

### SSH Tunnel

Use SSH tunneling when one user needs secure access to a model server without exposing the service on the network.

Example with Ollama listening on the remote host:

```bash
ssh -L 11434:127.0.0.1:11434 user@gpu-workstation
```

Then configure local tools to use:

```text
http://localhost:11434/v1
```

Pros:

- Simple.
- Uses SSH authentication and encryption.
- No public endpoint required.
- Good for testing and one-user workflows.

Limits:

- Not ideal for teams.
- No central quota/rate limiting.
- No shared endpoint identity unless wrapped separately.

### Private LAN or VPN Access

Use private LAN/VPN when a shared workstation or internal VM should serve multiple trusted users.

Recommended shape:

- Model server binds to a private interface, not public internet.
- Firewall allows only VPN/private subnet clients.
- A reverse proxy handles TLS and authentication.
- Use per-user API keys where possible.

Basic auth can be used for quick internal tests, but prefer bearer tokens or OIDC for real shared use.

Example profile shape:

```yaml
targets:
  lab_gpu_workstation:
    type: shared_workstation
    endpoint: https://gpu-workstation.internal.example.com/v1
    network: vpn
    auth:
      mode: bearer
      api_key_env: AIPLANE_LAB_LLM_KEY
```

### Azure API Management

Azure API Management is the preferred Azure-facing gateway when the endpoint is used by multiple people or teams. It can front model-serving APIs hosted on Azure GPU VMs, AKS, or other reachable backends.

For AKS, APIM can be used in a few ways:

- **Managed APIM gateway to AKS ingress/service**: expose the AKS model service through an internal or external ingress, then configure APIM with that backend URL. Best when APIM can reach the cluster network safely.
- **APIM in a VNet with private AKS access**: keep AKS private and let APIM reach it through private networking. Best for enterprise/internal deployments.
- **APIM self-hosted gateway in AKS**: run the APIM gateway component inside the cluster, close to the model service. The gateway is managed from Azure APIM but traffic can stay near the backend. This is useful for hybrid, private, or latency-sensitive deployments.

APIM gives us:

- TLS/custom domains.
- Subscription keys or OAuth/OIDC policies.
- Azure Entra ID integration.
- Rate limiting and quotas.
- Request/response policies.
- Central telemetry and access logs.
- A stable endpoint for IDE/CLI tools.

For `aiplane`, APIM should be represented as an access layer on a target, not as the model provider itself:

```yaml
targets:
  aks_gpu_pool:
    type: azure_aks
    endpoint: https://ai-models.example.com/v1
    access:
      mode: azure_api_management
      auth: entra_or_subscription_key
      api_key_env: AIPLANE_APIM_KEY
```

The model provider remains `ollama`, `vllm`, or another OpenAI-compatible runtime behind that gateway.

### SSH Tunnel Target Commands

The default profile includes an example `gpu_workstation_ssh` target. Edit `profiles/<profile>/targets.yaml` and replace the host/user before use.

Render the tunnel command:

```bash
aiplane remote tunnel plan --target gpu_workstation_ssh
```

This prints an `ssh -N -L ...` command and the local endpoint to use in IDE config exports. It does not start the tunnel yet.
