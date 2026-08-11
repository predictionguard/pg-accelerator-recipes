# MCP-connected agent (no code)

Connect a live tool — an inventory lookup, a forecasting function, anything with an API — to an Agent Forge agent, so it can pull live data instead of only answering from static documents.

For where to actually click, see the [Agent Forge walkthrough](#) — this README covers the pattern, the walkthrough covers the clicking.

## What you'll need

- An MCP server already running and reachable from the cluster Agent Forge runs on (see [`code-forward/mcp-tool-agent`](../../code-forward/mcp-tool-agent/) if your pod needs to stand one up)
- A bearer token or other credential for that server, if it requires auth
- A teammate with **org admin** access — registering the server is org-wide, not something a workspace admin or an individual agent builder can do

## The pattern

Tool connections in Agent Forge are org-level, not per-agent, and not even per-workspace. There are two roles in this flow:

1. **Once, org-wide (org admin only):** register the MCP server under **Organization settings → Access & tools → Tools**. This is a distinct settings area from any individual workspace — don't look for it inside a workspace's own settings. The registration form asks for a display name, the server URL, and an authentication method (either a shared bearer token, or session-based OAuth 2.0 if the server supports it), plus an "allow anonymous visitors" option. This makes the tool available to be picked by any agent in any workspace in the org; it doesn't attach it to anything by itself.
2. **Per agent (anyone building an agent):** in the agent builder, find the **Tools** field and click **Add tools**. Check just the tools this specific agent needs from everything registered org-wide.
3. Test with a question that specifically requires the tool, so you can confirm the agent actually calls it rather than guessing an answer.

There's no separate "streaming mode" or similar toggle to turn on first — the Tools field is always available in the agent builder.

## Files

- `tool-registration-example.json` — a rough shape for what a registration needs (display name, server URL, auth method). The real form doesn't have a separate description field or an explicit `type`, so treat the file as a planning reference, not a literal payload to paste in.

## Swap points

- If your MCP server exposes its own OAuth authorization server (rather than a static bearer token), choose "Session (OAuth 2.0)" as the authentication method instead of a shared token — ask the PG team if you're unsure which your server needs.
- Only check the specific tools an agent needs on the picker — not everything registered org-wide. Easier to reason about, easier to trust.
- Per-tool approval behavior (Allow / Ask / Deny) is also set on the org-wide Tools page, per tool — not in the agent builder. See [`hybrid/agent-as-approval-gated-tool`](../../hybrid/agent-as-approval-gated-tool/) before relying on "Ask" for anything called through a scoped API key.
