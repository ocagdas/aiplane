"""Documentation-backed harness identities, not an executable plugin registry."""

from __future__ import annotations

from copy import deepcopy

CATALOG_VERSION = "1"
CHECKED_ON = "2026-10-04"


def _entry(surfaces, protocols, auth, sources, *, native_provider=None, executable=None, discovery=""):
    return {
        "surfaces": surfaces,
        "protocols": protocols,
        "auth_modes": auth,
        "native_provider": native_provider,
        "executable": executable,
        "model_discovery": discovery,
        "sources": sources,
        "checked_on": CHECKED_ON,
        "tested_upstream_versions": [],
    }


HARNESS_CATALOG = {
    "codex": _entry(
        ["cli"],
        ["responses"],
        ["provider_env", "harness_login", "none"],
        ["https://developers.openai.com/codex/config-advanced/"],
        native_provider="openai",
        executable="codex",
        discovery="Use configured provider model IDs; for login use the installed Codex model picker. Custom providers must support the Responses wire API.",
    ),
    "claude-code": _entry(
        ["cli", "sdk"],
        ["anthropic_api"],
        ["provider_env", "harness_login"],
        ["https://code.claude.com/docs/en/third-party-integrations", "https://code.claude.com/docs/en/llm-gateway"],
        native_provider="anthropic",
        executable="claude",
        discovery="Use Claude Code's model configuration and the selected Claude hosting provider's catalog. Non-Claude models through a gateway are not supported.",
    ),
    "cursor": _entry(
        ["cli", "sdk"],
        [],
        ["harness_login", "product_env"],
        ["https://cursor.com/docs/sdk/typescript", "https://cursor.com/docs/cli/reference/parameters"],
        native_provider="cursor",
        executable="agent",
        discovery="Run agent models (or agent --list-models) yourself for account-specific native IDs. SDK local execution still uses Cursor-hosted inference. IDE BYOK is a different surface.",
    ),
    "opencode": _entry(
        ["cli"],
        ["openai_compatible", "ollama_api", "anthropic_api"],
        ["provider_env", "none"],
        ["https://opencode.ai/docs/providers/", "https://opencode.ai/docs/agents/"],
        executable="opencode",
        discovery="Use OpenCode's provider/model catalog and configured custom providers; select a profile alias pointing to the matching endpoint model ID.",
    ),
    "langgraph": _entry(
        ["python"],
        ["openai_compatible", "ollama_api", "anthropic_api"],
        ["provider_env", "none"],
        [
            "https://docs.langchain.com/oss/python/langgraph/overview",
            "https://docs.langchain.com/oss/python/integrations/providers/overview",
        ],
        discovery="Choose the appropriate LangChain model integration, then its provider's model ID. An adapter must construct the model and graph.",
    ),
    "deepagents": _entry(
        ["python"],
        ["openai_compatible", "ollama_api", "anthropic_api"],
        ["provider_env", "none"],
        ["https://docs.langchain.com/oss/python/deepagents/subagents"],
        discovery="Subagents accept model configurations/objects; choose a supported model integration and verify tool calling.",
    ),
    "crewai": _entry(
        ["python"],
        ["openai_compatible", "ollama_api", "anthropic_api"],
        ["provider_env", "none"],
        ["https://docs.crewai.com/en/learn/llm-connections"],
        discovery="Use CrewAI's LLM provider integrations and exact provider model IDs; local endpoints require the correct integration/base URL.",
    ),
    "openai-agents": _entry(
        ["python"],
        ["openai_compatible", "responses"],
        ["provider_env", "none"],
        ["https://developers.openai.com/api/docs/guides/agents/models"],
        discovery="Select a Responses or Chat Completions model adapter, or a separately qualified provider adapter. Model names come from the endpoint provider.",
    ),
}


def harness_catalog():
    return {"catalog_version": CATALOG_VERSION, "harnesses": deepcopy(HARNESS_CATALOG)}


def harness_record(name):
    if name not in HARNESS_CATALOG:
        raise ValueError("unknown harness; use aiplane harnesses list")
    return {"id": name, **deepcopy(HARNESS_CATALOG[name])}


def compatibility(harness, surface, *, protocol=None, provider=None, native=False, auth="provider_env"):
    record = harness_record(harness)
    status, reason = (
        "documented",
        "Documented integration family; model access and tool calling still require qualification.",
    )
    if surface not in record["surfaces"] or auth not in record["auth_modes"]:
        status, reason = (
            "unsupported",
            "Surface or authentication mode is outside this catalog's supported configuration.",
        )
    elif native:
        if not record["native_provider"] or auth not in {"harness_login", "product_env"}:
            status, reason = "unsupported", "This harness has no native-model binding for this authentication mode."
    elif harness == "cursor":
        status, reason = (
            "unsupported",
            "Cursor CLI/SDK uses its native hosted-model namespace; IDE BYOK does not imply custom endpoint support here.",
        )
    elif auth in {"harness_login", "product_env"}:
        status, reason = (
            "unsupported",
            "Login/product authentication requires a harness_model binding, not a direct model alias.",
        )
    elif harness == "claude-code" and provider != "anthropic":
        status, reason = (
            "unknown"
            if protocol == "anthropic_api" or provider in {"bedrock", "vertex", "foundry", "azure_anthropic"}
            else "unsupported",
            "Only direct Anthropic is mapped here; Bedrock/Vertex/Foundry Claude routing needs a qualified adapter. Non-Claude routing is unsupported upstream.",
        )
    elif protocol not in record["protocols"]:
        status, reason = (
            "unknown",
            "Protocol is not covered by the curated integration matrix; do not assume API equivalence.",
        )
    return {"status": status, "reason": reason, "sources": record["sources"]}
