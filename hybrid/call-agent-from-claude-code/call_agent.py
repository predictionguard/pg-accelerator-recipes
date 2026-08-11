"""
Call one Agent Forge agent via its scoped API key.

Usage:
    python call_agent.py "your question here"

Fill in .env first (copy from .env.example). The API key must be scoped
to AGENT_ID — using a different agent ID in the request will fail.
"""

import os
import sys
import requests

BASE_URL = os.environ["AGENT_FORGE_BASE_URL"].rstrip("/")
API_KEY = os.environ["AGENT_API_KEY"]
AGENT_ID = os.environ["AGENT_ID"]


def call_agent(question):
    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": AGENT_ID,
            "messages": [{"role": "user", "content": question}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "Hello, what can you help with?"
    print(call_agent(question))


if __name__ == "__main__":
    main()
