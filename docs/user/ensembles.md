# Role-based agent ensembles

Aiplane describes and checks an ensemble, then exports a neutral handoff manifest. An external runner must translate that manifest into its own configuration and execute the collaboration. These commands do not create a working multi-agent runtime by themselves. Here, an agent cluster means a logical team; workers may ultimately run as local processes, containers or remote services chosen by the runner.

The three responsibilities are:

| Component | Responsibility |
| --- | --- |
| CAS | Repository guidance, skills, conventions and setup. |
| Aiplane | Harness/model bindings, endpoint/auth references, dependency validation, policy checks and configuration export. |
| Runner/orchestrator | Agent processes, task assignment, messages, artifacts, isolation, retries, budgets and lifecycle. |

A fleet manager owns running workers: starting and stopping them, distributing tasks, monitoring health and recovering failures. That remains the runner's responsibility. Aiplane can describe those workers without becoming the service that operates them. CAS remains responsible for instructions used inside their workspaces.

## Profiles directory and workspace

These paths have separate purposes:

| Option | Meaning | Example |
| --- | --- | --- |
| `--profiles-dir` | Parent directory containing named configuration profiles. | `/tmp/aiplane-ensemble-demo/profiles` |
| `--profile` | Name of one subdirectory inside that parent. | `demo` selects `profiles/demo/` |
| `--workspace` | Project root to which the configuration applies. Relative guidance and artifact paths are resolved within it. | The aiplane checkout, or another project you want agents to work on. |

A profile holds model aliases/providers/endpoints, hardware, repository policy, tools, approvals and other environment settings. A workspace holds the project source and guidance. The same profile can be used with different workspaces; it is not automatically regenerated to match each project's policy, so review its repository/tool settings before using it elsewhere.

The temporary example has this layout:

```text
/tmp/aiplane-ensemble-demo/
  ensemble.yaml                 # Role/harness/model bindings
  profiles/                     # --profiles-dir
    demo/                       # --profile demo
      models.yaml               # Providers and model aliases
      repository.yaml           # Repository/cloud policy
      tools.yaml                # Tool permissions
      ...                       # Other required profile files
```

`--workspace` defaults to the current directory. Profile-directory precedence is the explicit option, `AIPLANE_PROFILES_DIR`, local configuration's `profiles_dir`, then the checkout's `profiles/` (for a source checkout). The ensemble specification is a separately selected file; its location does not determine the workspace. Global path options go before `ensembles` in the command.

To test configuration **for the aiplane folder itself**, keep the demo settings under `/tmp` and select the checkout as the workspace:

```sh
# Run from the aiplane repository root with Python 3.11+.
PYTHONPATH=src python -m aiplane \
  --profiles-dir /tmp/aiplane-ensemble-demo/profiles \
  --workspace "$PWD" \
  ensembles plan /tmp/aiplane-ensemble-demo/ensemble.yaml --profile demo
```

The `/tmp` profile/spec are disposable session examples, not installed package resources. Its model ID is synthetic; this command validates configuration without calling that model. The tracked examples below are templates for your own profile aliases. Selecting a workspace does not start agents or change the project.

## Where the names come from

There are three independent namespaces. Do not interchange them.

1. **Harness IDs** are stable aiplane catalog keys: `codex`, `claude-code`, `cursor`, `opencode`, `langgraph`, `deepagents`, `crewai`, `openai-agents`. `harnesses show` returns source links, supported surfaces/authentication families, discovery guidance and the documentation review date. These are curated claims, not installed adapters or verified upstream versions.
2. **Profile aliases** such as `local_coder` are your names in `models.yaml`. They refer to an exact provider model ID and endpoint. Use aiplane's existing discovery and promotion workflow to choose durable entries. Discovery caches alone cannot be ensemble bindings.
3. **Harness-native model IDs** come from the installed tool/account. For Cursor CLI, run `agent models` or `agent --list-models`; use that result with `harness_model`. Claude Code's `default` is a dynamic native selection, not a pinned model. Provider API names and harness-native names can differ. OpenCode exposes `opencode models [provider]` to list its configured provider/model catalog; see its [CLI reference](https://opencode.ai/docs/cli/).

```sh
aiplane harnesses list
aiplane harnesses show cursor
aiplane harnesses show codex
aiplane models refresh --provider ollama --dry-run
aiplane models refresh --provider ollama
aiplane models promote SELECTED_DISCOVERED_ALIAS --as local_coder
aiplane harnesses models opencode --surface cli --auth none --profile local-dev
```

Run discovery deliberately: provider discovery can access endpoints and requires the provider's configuration/credentials. The new harness/ensemble commands perform no live discovery. A model list is an inventory, not proof of account entitlement, tool calling, context limits or reliable collaboration. Names are not guessed from ChatGPT/Claude subscription labels.

## Compatibility and BYOK

The matrix covers **harness + surface + authentication + protocol/provider family**. Its `documented` status means upstream documents the integration family, not that this model or installed version was exercised. `unknown` means a separately qualified adapter is needed. `unsupported` means the selection is outside the catalog's configured scope. Native model access is always unverified locally.

| Harness | Scope in this catalog | Cloud/local considerations |
| --- | --- | --- |
| Codex | CLI; native login or Responses endpoint | Custom endpoint must advertise Responses, not merely Chat Completions. Local use also requires a suitable model/server. |
| Claude Code | CLI/SDK; native login or direct Anthropic | Bedrock/Vertex/Foundry routes require a separately qualified adapter here. Upstream's gateway guidance does not support arbitrary non-Claude models. |
| Cursor | CLI/SDK; native login or Cursor product key | Cursor SDK uses hosted inference even when execution is local. IDE BYOK is a separate feature and is not generalized to CLI/SDK. |
| OpenCode | CLI; configured model endpoints | Documents custom providers and Ollama; native provider naming/configuration needs an adapter. |
| LangGraph / Deep Agents | Python; model integration per role | Application code constructs graph/subagents and provider adapters. |
| CrewAI | Python; LLM integration per agent | Application code constructs agents/tasks/crew and correct provider integration. |
| OpenAI Agents SDK | Python; Responses or Chat Completions adapter | Other provider adapters need separate qualification; this catalog does not assume all APIs are interchangeable. |

`provider_env` references your provider API credential (BYOK); `product_env` references a harness product credential (`CURSOR_API_KEY` for Cursor). Those are different credential types. `harness_login` uses the harness's existing login; `none` is restricted to explicitly local models with loopback endpoints. No key values are accepted or exported.

For official source detail, use [Codex provider configuration](https://developers.openai.com/codex/config-advanced/), [Claude gateway constraints](https://code.claude.com/docs/en/llm-gateway), [Cursor SDK inference](https://cursor.com/docs/sdk/typescript), [Cursor CLI model discovery](https://cursor.com/docs/cli/reference/parameters), and [OpenCode providers](https://opencode.ai/docs/providers/).

## Configuration examples

Ensemble specifications are standalone restricted YAML or JSON files. Roles are a mapping because aiplane's restricted YAML does not accept block sequences. Use inline arrays for dependencies. Specifications are not automatically included in portable profile archives; distribute the specification and exported handoff separately from the secret-free profile.

Generate a starting example:

```sh
aiplane ensembles template > ensemble.yaml
```

**Single harness, mixed models:** configure `cloud_planner` and `local_coder` as reviewed aliases in the selected profile. Enable their providers and permit cloud access in profile policy. LangGraph is a suitable application layer when you want explicit graph control.

```yaml
schema_version: 1
name: shared-harness
artifact_directory: .aiplane/ensemble-artifacts
roles:
  planner:
    harness: langgraph
    surface: python
    model_alias: cloud_planner
    auth: provider_env
    credential_env: OPENAI_API_KEY
    depends_on: []
  implementer:
    harness: langgraph
    surface: python
    model_alias: local_coder
    auth: none
    depends_on: [planner]
  reviewer:
    harness: langgraph
    surface: python
    model_alias: cloud_reviewer
    auth: provider_env
    credential_env: ANTHROPIC_API_KEY
    depends_on: [implementer]
```

For an ensemble from one provider, use three different aliases from that provider, or the same alias for all roles. Roles express responsibilities; using different model IDs is optional. Cloud API aliases require API credentials even if you also have a chat subscription.

**Mixed harnesses:** keep the planner in your graph application, use OpenCode with a local model for implementation, and add Claude Code/Cursor through runner wrappers. This is configuration for a custom runner, not a ready-made graph import.

```yaml
schema_version: 1
name: mixed-harness
roles:
  planner:
    harness: langgraph
    surface: python
    model_alias: cloud_planner
    auth: provider_env
    depends_on: []
  implementer:
    harness: opencode
    surface: cli
    model_alias: local_coder
    auth: none
    depends_on: [planner]
  reviewer:
    harness: claude-code
    surface: cli
    harness_model: default
    auth: harness_login
    depends_on: [implementer]
  cursor-reviewer:
    harness: cursor
    surface: sdk
    harness_model: REPLACE_WITH_ACCOUNT_MODEL_ID
    auth: product_env
    credential_env: CURSOR_API_KEY
    depends_on: [implementer]
```

Replace the Cursor placeholder from its account catalog. `default` and other native selections can change upstream; the manifest's hash does not pin their underlying model version. Optionally attach a workspace-relative `guidance: AI_CONTEXT.md` reference to each role. The runner decides how to load it. Paths may not escape the workspace, including through symlinks.

```sh
aiplane ensembles plan ensemble.yaml --profile local-dev
aiplane ensembles doctor ensemble.yaml --profile local-dev
aiplane ensembles export ensemble.yaml --profile local-dev > /tmp/ensemble-handoff.json
```

`plan` reports resolved endpoint per role, authentication references, compatibility, policy and deterministic hashes. `doctor` only checks executable presence on PATH, credential environment-variable presence, and optional guidance-file presence. It does not verify binary identity, SDK installation, login state, model access, endpoint health or tool calling. Exit codes: `0` for a reviewable plan/export; `1` for invalid/blocked configuration; `2` for a doctor report that still needs runtime qualification. All exports have `execution_ready: false`. Blocked configurations cannot be exported; unknown integrations may be exported for review.

The output is **aiplane's versioned handoff JSON**, not native LangGraph, CrewAI, Codex or Cursor configuration. No runner adapter is shipped in this increment. It includes the spec, binding and catalog hashes, source links, dependency order and qualification requirements. Model/provider policy decisions are included. The runner must separately load and enforce repository/tool policy and required approvals. Aiplane does not grant approval through export.

## How the collaboration should actually run

Start with one graph-based runner and two roles (planner and implementer). Build its adapter to map each manifest binding into the appropriate model client, check the exported hashes/configuration immediately before use, qualify a small tool-calling task, and enforce profile policy and required approvals. Give writing agents isolated workspaces/worktrees and exchange reviewed artifacts through the declared directory. The directory and dependency graph are declarations; aiplane does not create them or enforce execution order.

Then add an independent reviewer. Add separate Codex, Claude Code or Cursor wrappers only when useful: each has its own session, tool loop, permissions and output format. The runner must normalize results and own retries, messaging, cost/time limits, shutdown and audit. Re-export when any spec, model binding or catalog changes. A hash detects changed configuration; it does not verify live entitlement or upstream model behavior.
