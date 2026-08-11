# Claude Code calling an MCP tool server

Give Claude Code itself an MCP server, so it can call live tools (inventory lookups, a forecasting function, etc.) as part of a normal coding session — useful when you want Claude to look something up while it's helping you build, not just when the finished agent runs.

This is a different thing from the [`live-tool-agent`](../live-tool-agent/) recipe: that one is a Pydantic AI agent your code builds and runs later, calling a live API on its own. This one is Claude Code, right now, while you're coding with it, reaching for a tool.

## How it works

1. Register your MCP server with Claude Code (`claude mcp add ...` or `.claude/settings.json`).
2. Ask Claude Code questions that require the tool — it decides when to call it.

Optionally, you can also point Claude Code's own API traffic at Prediction Guard instead of the public Anthropic API — see `settings.example.json`. That's a nice-to-have, not the point of this recipe: what matters is that whatever Claude *builds* for you ends up calling Prediction Guard, not whether Claude Code itself does while you're working.

## Files

- `settings.example.json` — Claude Code settings shape for registering an MCP server (and optionally pointing Claude Code at PG)
- `example_mcp_server.py` — a minimal MCP server exposing one tool (`lookup_sku`), to use as a template for your pod's real tools

## Set it up

```bash
cp settings.example.json ~/.claude/settings.json   # or merge into your existing one, fill in values
pip install mcp
python example_mcp_server.py   # runs the example tool server locally for testing
```

Then in Claude Code: `claude mcp add inventory-tools -- python example_mcp_server.py`

## Swap points

- Replace `lookup_sku` in `example_mcp_server.py` with your pod's actual tool functions.
- If your MCP server needs to be reachable from a shared cluster (not just your laptop), it needs network access to that cluster — flagged on the Aug 10 call as the main setup item for pods bringing their own MCP servers. Loop in the PG team for that networking step.
