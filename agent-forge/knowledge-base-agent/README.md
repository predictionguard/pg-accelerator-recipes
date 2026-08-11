# Knowledge-base agent (no code)

Build a chat agent grounded in your own documents — no code, no MCP, just upload and configure. This is the pattern for something like AI Susanna: a knowledge agent that answers questions from a fixed set of source material.

For the click-by-click version of every step below (where to click in Agent Forge itself), see the [Agent Forge walkthrough](#) — this README is about the *configuration*, the walkthrough is about the *clicking*.

## What you'll need

- A workspace in Agent Forge (ask your pod's workspace admin if you don't have one yet)
- The source documents you want the agent grounded in (PDFs, docs — whatever format your material is in)

## The pattern

1. Create a knowledge base and upload your documents to it. This is separate from any one agent — a knowledge base can be reused across multiple agents.
2. Create an agent, and attach that knowledge base to it.
3. Write a system prompt that tells the agent what it is and how to use its knowledge base — see `system-prompt-example.txt`.
4. Test it with a few real questions your pod actually cares about, not generic ones.

## Files

- `system-prompt-example.txt` — a starting system prompt, written for a knowledge agent specifically (tell it to say "I don't know" rather than guessing when the knowledge base doesn't cover something)

## Swap points

- If your material changes often, re-upload to the knowledge base rather than editing the system prompt — keep source material and instructions separate.
- If more than one pod wants to ask this agent questions, use cross-workspace sharing with chat-only permissions rather than duplicating the agent.
