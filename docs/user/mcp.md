# MCP Adapter

The MCP adapter lets an IDE or agent call `aiplane` as a structured tool instead of shelling out manually. It can inspect profiles, providers, provider model availability, approved model details, hardware, recommendations, integration exports, and SSH tunnel plans. It also exposes a small guarded write surface for profile-level changes and SSH tunnel lifecycle operations.

## Commands

Show the exposed surface:

```bash
aiplane mcp manifest
```

Start the stdio MCP server:

```bash
aiplane mcp serve
```

`--profile` is optional. Use it only when the MCP server should default to a specific non-default profile for calls that omit a profile argument.

## Exposed Tools

The current read tools are:

- `aiplane.docs.list` and `aiplane.docs.read` for project docs/help text
- `aiplane.profiles.list`
- `aiplane.providers.list` with `status`, `runtime`, and `group_by` filters for ownership/runtime grouping
- `aiplane.providers.models` and `aiplane.providers.diagnose`
- `aiplane.models.defaults`
- `aiplane.models.list` with filters, named-machine/current-machine fit filtering, sorting, and limits
- `aiplane.models.show`
- `aiplane.hardware.discover`
- `aiplane.hardware.recommend`
- `aiplane.machines.list`, `aiplane.machines.show`, and `aiplane.machines.recommend`
- `aiplane.stacks.list`, `aiplane.stacks.show`, `aiplane.stacks.plan`, and `aiplane.stacks.doctor`
- `aiplane.integrations.export`
- `aiplane.integrations.roles` and `aiplane.integrations.plan`
- `aiplane.orchestrators.list` and `aiplane.orchestrators.show`
- `aiplane.runtimes.status` and render-only `aiplane.runtimes.bundle`
- render-only `aiplane.agents.manifest`
- `aiplane.remote.tunnel.plan`
- `aiplane.remote.tunnel.status`

Write tools execute through the same managers as the CLI. Where a tool supports preview, use its `dry_run` argument.

- `aiplane.models.refresh`: import provider-discovered models into the profile catalog; use `dry_run: true` to preview.
- `aiplane.models.use`: set a default model role to an approved model alias.
- `aiplane.hardware.use`: select a hardware template and optional overrides.
- `aiplane.runtimes.use`: set a preferred runtime for a configured model.
- `aiplane.remote.tunnel.start`: start a configured SSH tunnel in the background.
- `aiplane.remote.tunnel.stop`: stop a helper-started SSH tunnel.

All tools return JSON as both text content and structured MCP content where supported by the client. Mutating tools call the same internal managers as the CLI; they do not bypass profile validation, policy boundaries, or filesystem scoping.

New CLI features are not automatically MCP tools. MCP coverage is reviewed during pre-PR cleanup and recurring synchronization checkpoints, not continuously after every feature and not at every regular milestone. Useful inspection, planning, recommendation, and config export features can be mirrored into MCP, while host mutation, downloads, installs, cloud apply, secret writes, and broad shell execution stay CLI-only or deferred until they have explicit guardrails and audit behavior.

## MCP And Agent Skills

MCP and agent skills solve different problems. MCP is a live protocol surface: an IDE or agent calls `aiplane` tools over stdio and receives structured results. An agent skill is an instruction/playbook package for a coding assistant: it tells the assistant how to approach an `aiplane` task, which commands to prefer, which safety boundaries matter, and when to use MCP.

The repository ships a versioned starter skill at `skills/aiplane/SKILL.md`. A useful `aiplane` skill can reference the MCP server, but it should not duplicate MCP. The skill should teach workflow and judgment; MCP should expose current structured state and guarded operations.

## Generate Client Config

You can print client config snippets instead of hand-writing them:

```bash
aiplane integrations export vscode-mcp
aiplane integrations export continue-mcp
aiplane integrations export cline-mcp
aiplane integrations export generic-mcp
```

These exporters only print configuration. They do not install IDE extensions or edit settings files.

## VS Code MCP Config

Use this when your VS Code setup or extension can launch MCP servers directly. Example `.vscode/mcp.json`:

```json
{
  "servers": {
    "aiplane": {
      "type": "stdio",
      "command": "aiplane",
      "args": ["mcp", "serve"]
    }
  }
}
```

## Continue MCP Config

Use this when Continue is the MCP client. Continue has its own config file shape, so this is separate from the VS Code-level MCP config:

```yaml
name: aiplane
version: 0.1.0
schema: v1
mcpServers:
  - name: aiplane
    type: stdio
    command: aiplane
    args:
      - mcp
      - serve
```

You do not need both configs for the same client. Use the VS Code config for a VS Code MCP client, or the Continue config for Continue.

## Scope

The MCP server is read-only by default. Starting it with `--allow-writes` is an explicit operator decision that enables only the listed narrow write tools; each mutating tool call must additionally include `confirm=true`. Either missing guard blocks the request before manager dispatch and writes a metadata-only `blocked` audit event. A `models.refresh` call with `dry_run=true` is non-mutating and remains available on a read-only server.

To opt in for a controlled session:

```yaml
args:
  - mcp
  - serve
  - --allow-writes
```

Do not add this flag to routine client configuration unless that client is intended to modify the selected profile. These broader operations remain blocked regardless of the flag:

- pulling/downloading models;
- installing runtimes;
- running real benchmarks;
- applying cloud deployments;
- writing secrets;
- arbitrary shell execution.

Planned next phases:

1. Add guarded model pull/runtime lifecycle tools only after provider helper approvals are clear.
2. Keep deployment apply blocked until cloud cost/risk controls are explicit.

The adapter must not bypass `aiplane` policy. Write-capable tools should call the same internal managers used by the CLI.

## Write Tools

Mutating MCP calls are audited through the same local JSONL audit log used by CLI tool execution. Missing server or per-call authorization records `blocked`; successful writes record `allowed`; manager failures record `failed` with a sanitized exception type. Raw arguments, output, and exception messages are not stored.
