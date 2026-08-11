# RAG over your own documents

A [Pydantic AI](https://ai.pydantic.dev/) agent that retrieves from your own documents before answering, using Prediction Guard for both embeddings and chat. Good starting point for any pod whose use case is "ask questions about our own material."

## How it works

1. The agent has one tool, `search_documents` — it embeds the query, compares it against pre-embedded document chunks, and returns the closest matches.
2. Pydantic AI handles the tool-calling loop: the agent decides when to call `search_documents`, gets the results back, and answers from them.
3. The system prompt tells it to only answer from what the tool returns, and say so plainly if the documents don't cover the question.

## Files

- `embed_and_query.py` — the agent: loads docs, defines the retrieval tool, runs the query
- `.env.example` — required environment variables

## Run it

```bash
cp .env.example .env      # fill in PG_BASE_URL, PG_API_KEY, and both model names
pip install pydantic-ai requests numpy
python embed_and_query.py "What does the Q2 report say about grain yields?"
```

## Swap points

- Replace the naive in-memory cosine search with a real vector store (pgvector, Chroma, etc.) once your document set is larger than a few hundred chunks.
- The embedding and chat models are named as placeholders in `.env.example` — confirm the exact model names available on your cluster via `GET {PG_BASE_URL}/v1/models`, and make sure the chat model you pick actually supports tool calling (check its `capabilities.tool_calling` flag) — not every model handles Pydantic AI's tool-calling format correctly, even if it can answer plain questions fine.
