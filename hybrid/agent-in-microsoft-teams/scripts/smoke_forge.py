"""Talk to the Agent Forge agent from the terminal, with no Teams in the loop.

Run this first when something is broken: it isolates "is the agent reachable and
is my key right?" from "is my Teams/Bot Service wiring right?".

    uv run python scripts/smoke_forge.py
    uv run python scripts/smoke_forge.py "What can you help me with?"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentforge_teams.config import ConfigError, settings  # noqa: E402
from agentforge_teams.forge_client import ForgeAgent, ForgeError

async def main() -> int:
    try:
        agent = ForgeAgent()
    except ConfigError as exc:
        print(f"✗ Config error: {exc}", file=sys.stderr)
        return 2

    print(f"→ url   : {settings.forge_api_url}")
    print(f"→ model : {settings.agent_id}\n")

    if len(sys.argv) > 1:
        prompts = [" ".join(sys.argv[1:])]
        interactive = False
    else:
        prompts = ["Hello! What can you help me with?"]
        interactive = True

    history: list[dict[str, str]] = []
    while True:
        for prompt in prompts:
            print(f"\033[1myou:\033[0m {prompt}")
            try:
                reply = await agent.complete([*history, {"role": "user", "content": prompt}])
            except ForgeError as exc:
                print(f"✗ Agent error: {exc}", file=sys.stderr)
                return 1
            print(f"\033[1magent:\033[0m {reply}\n")
            history += [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": reply},
            ]

        if not interactive:
            return 0
        try:
            nxt = input("you (blank to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if not nxt:
            return 0
        prompts = [nxt]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
