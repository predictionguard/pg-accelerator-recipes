# Sensitive tools and API keys don't mix — here's why

If an agent has a tool set to **"Ask"** (require approval) on the org Tools page, that only applies when a person is chatting with the agent directly in Agent Forge. It does not apply when the agent is called through a scoped API key.

Confirmed directly: a tool set to "Ask" was called through an agent's API key and ran immediately, with no pause and nothing to approve — exactly what Agent Forge's own API access page warns about:

> API calls do not show tool approval prompts. Enabled tools using shared service credentials run automatically, so anyone with the key can trigger them. Tools requiring a user to sign in, or disabled on the agent or connector, are unavailable through API keys.

So there's no "pending approval" state to catch in code — a hybrid integration cannot insert a human-in-the-loop step for a tool call the way it can in the chat UI. This may change as the Agent API comes out of preview; check back before assuming otherwise.

## What this means for your pod

**Don't give an API key to an agent that has a tool you wouldn't want running unattended.** If a tool needs a human to sign off before it runs — anything that sends something, spends something, or changes real data — that agent should stay chat-only. Anyone with the key can trigger any "Allow" or "Ask" tool the agent has, with no gate in between.

If you need both — some questions answered via API, and a specific sensitive action gated behind a person — split it into two agents: one with only the safe, read-only tools attached, scoped API key and all; a separate one with the sensitive tool, chat-only, no key ever issued for it.

## Swap points

- If your pod's hybrid workflow was planning to rely on approval gating over the API, stop and re-scope now, not after something runs.
- Ask the PG team whether approval-over-API is on the roadmap if your use case genuinely needs it — this is a preview feature, so it may show up.
