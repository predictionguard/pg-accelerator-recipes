"""
A Pydantic AI agent that retrieves from your own documents before answering,
using Prediction Guard for both embeddings and chat.

Usage:
    python embed_and_query.py "your question here"

Fill in .env first (copy from .env.example).
"""

import os
import sys
import glob
import requests
import numpy as np
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

PG_BASE_URL = os.environ["PG_BASE_URL"].rstrip("/")
PG_API_KEY = os.environ["PG_API_KEY"]
CHAT_MODEL = os.environ["PG_CHAT_MODEL"]
EMBED_MODEL = os.environ["PG_EMBED_MODEL"]

DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
CHUNK_SIZE = 800


def load_chunks():
    chunks = []
    for path in glob.glob(os.path.join(DOCS_DIR, "*.txt")):
        text = open(path, encoding="utf-8").read()
        for i in range(0, len(text), CHUNK_SIZE):
            chunks.append(text[i : i + CHUNK_SIZE])
    return chunks


def embed(texts):
    resp = requests.post(
        f"{PG_BASE_URL}/v1/embeddings",
        headers={"Authorization": f"Bearer {PG_API_KEY}"},
        json={"model": EMBED_MODEL, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    return np.array([row["embedding"] for row in resp.json()["data"]])


def top_matches(question_vec, chunk_vecs, chunks, k=4):
    # Some BLAS backends (e.g. macOS Accelerate) emit spurious FP warnings on
    # matmul that don't reflect an actual invalid result — suppress locally.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        sims = chunk_vecs @ question_vec / (
            np.linalg.norm(chunk_vecs, axis=1) * np.linalg.norm(question_vec)
        )
    k = min(k, len(chunks))
    order = np.argsort(-sims)[:k]
    return [chunks[i] for i in order]


model = OpenAIChatModel(
    CHAT_MODEL,
    provider=OpenAIProvider(base_url=f"{PG_BASE_URL}/v1", api_key=PG_API_KEY),
)

agent = Agent(
    model,
    system_prompt=(
        "Answer questions using the search_documents tool. Only answer from "
        "what the tool returns — say so plainly if it doesn't cover the question."
    ),
)


@agent.tool
def search_documents(ctx: RunContext[None], query: str) -> str:
    """Search the loaded documents for passages relevant to the query."""
    chunks = load_chunks()
    if not chunks:
        return "No documents are loaded."
    chunk_vecs = embed(chunks)
    query_vec = embed([query])[0]
    matches = top_matches(query_vec, chunk_vecs, chunks)
    return "\n\n---\n\n".join(matches)


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "What is this document about?"
    if not glob.glob(os.path.join(DOCS_DIR, "*.txt")):
        print(f"No .txt files found in {DOCS_DIR} — add some source documents first.")
        return
    result = agent.run_sync(question)
    print(result.output)


if __name__ == "__main__":
    main()
