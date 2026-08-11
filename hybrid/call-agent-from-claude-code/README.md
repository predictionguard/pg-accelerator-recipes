# Calling an Agent Forge agent from Claude Code

Build the agent visually in Agent Forge, then call it as one step inside a larger Claude Code script or workflow — useful when a pod wants to combine several Agent-Forge-built agents (each owned by a different pod member) into one larger piece of code.

This pattern is new — treat it as something to validate together with the PG team this week, not a settled recipe.

## How it works

1. Build and test the agent in Agent Forge first, in chat, until it does what you want.
2. In your workspace's Settings, under the **API access** tab, click **Create API key** and pick this agent from the dropdown — no code needed for this step, Agent Forge hands you the key plus a ready-made example request. The key only ever calls that one agent.
3. Call it from your script exactly like you'd call any chat completions endpoint — the request/response shape is the same as talking to Prediction Guard directly.

## Files

- `call_agent.py` — minimal script that calls one Agent Forge agent via its scoped API key
- `.env.example` — required environment variables

## Run it

```bash
cp .env.example .env      # fill in AGENT_FORGE_BASE_URL, AGENT_API_KEY, AGENT_ID
pip install requests
python call_agent.py "What's our current stock for SKU 4471?"
```

## Swap points

- Wrap `call_agent.py`'s request in an MCP tool definition if you want Claude Code to decide *when* to call the agent, rather than always calling it — turns the agent into a tool Claude Code can reach for on its own.
- Before you attach an API key to an agent, check what tools it has and whether any of them are supposed to require approval — see [`agent-as-approval-gated-tool`](../agent-as-approval-gated-tool/) for why that gate doesn't carry over to API calls.
