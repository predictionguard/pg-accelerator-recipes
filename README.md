# Prediction Guard Accelerator Recipes

Working examples for the three ways to build on Prediction Guard, referenced from the accelerator overview guide. Each recipe is a small, self-contained folder: a README explaining the pattern, and starter code/config shaped correctly for Prediction Guard's APIs.

Starting a new Claude Code project to build on Prediction Guard? Copy [`CLAUDE.md.example`](CLAUDE.md.example) into your project as `CLAUDE.md` first — it tells Claude how to connect, how to discover available models and tools instead of guessing, and points at the recipes below as reference.

## Which folder do I want?

| I want to... | Go to |
|---|---|
| Write actual application code that calls Prediction Guard | [`code-forward/`](code-forward/) |
| Build an agent without writing code | [`agent-forge/`](agent-forge/) |
| Call an Agent Forge agent from a Claude Code script or tool | [`hybrid/`](hybrid/) |

## Recipes

**Code Forward** — [Pydantic AI](https://ai.pydantic.dev/) agents running on Prediction Guard
- [`rag-over-docs`](code-forward/rag-over-docs/) — retrieval-augmented answers over your own documents
- [`text-to-sql`](code-forward/text-to-sql/) — natural-language questions answered against a real database
- [`live-tool-agent`](code-forward/live-tool-agent/) — an agent with a tool that calls a live external API
- [`mcp-tool-agent`](code-forward/mcp-tool-agent/) — Claude Code itself, not a Python agent, calling out to an MCP tool server as part of a coding session

**Agent Forge**
- [`knowledge-base-agent`](agent-forge/knowledge-base-agent/) — upload documents, get a grounded chat agent, no code
- [`mcp-connected-agent`](agent-forge/mcp-connected-agent/) — connect a live tool (e.g. inventory lookup) to an Agent Forge agent

**Hybrid**
- [`call-agent-from-claude-code`](hybrid/call-agent-from-claude-code/) — treat an Agent Forge agent as one callable step in a larger script
- [`agent-as-approval-gated-tool`](hybrid/agent-as-approval-gated-tool/) — why "Ask" tool approval doesn't carry over to API calls, and what to do instead

## Conventions across every recipe

- `PG_BASE_URL` — your Prediction Guard control-plane endpoint (`https://ai-api.solentraglobal.com`)
- `PG_API_KEY` — a standard bearer key for the gateway (Code Forward recipes)
- `AGENT_API_KEY` — a scoped `sk-agentstudio-...` key bound to one Agent Forge agent (Hybrid recipes), called against `https://agents.solentraglobal.com`
- The gateway accepts both OpenAI (`/v1/chat/completions`) and Anthropic (`/v1/messages`) request shapes — recipes below use the OpenAI shape for brevity, but either works.
- Not every model that answers plain questions correctly also handles a tool-calling agent framework's format correctly. Check a model's `capabilities.tool_calling` flag via `GET {PG_BASE_URL}/v1/models` before picking one for a Pydantic AI recipe, and test it — the flag being true doesn't guarantee framework compatibility.

Nothing here needs credentials checked in. Copy `.env.example` → `.env` in each recipe and fill in your own.
