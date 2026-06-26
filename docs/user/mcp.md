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

- `aiplane.profiles.list`
- `aiplane.providers.list`
- `aiplane.providers.models`
- `aiplane.models.defaults`
- `aiplane.models.list` with filters, sorting, and limits
- `aiplane.models.show`
- `aiplane.hardware.discover`
- `aiplane.hardware.recommend`
- `aiplane.integrations.export`
- `aiplane.runtimes.status`
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

The MCP write surface is intentionally narrow. These remain blocked until stronger approval, audit, and rollback behavior exist:

- pulling/downloading models;
- installing runtimes;
- running real benchmarks;
- applying cloud deployments;
- writing secrets;
- arbitrary shell execution.

Planned next phases:

1. Add audit events for every mutating MCP tool call.
2. Add guarded model pull/runtime lifecycle tools after provider helper approvals are clear.
3. Keep deployment apply blocked until cloud cost/risk controls are explicit.

The adapter must not bypass `aiplane` policy. Write-capable tools should call the same internal managers used by the CLI.
