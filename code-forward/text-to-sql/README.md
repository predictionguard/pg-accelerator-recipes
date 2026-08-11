# Text-to-SQL

A [Pydantic AI](https://ai.pydantic.dev/) agent that answers plain-English questions against a real database. Good fit for pods with structured transactional/historical data (inventory levels, weight/grade records, etc.).

## How it works

1. The agent has one tool, `run_sql_query` — it takes a SQL string, refuses anything that looks like a write or schema change, and runs everything else against your database.
2. The agent decides what SQL to write based on the schema in its system prompt, calls the tool, and answers in plain English from the results.
3. Ask follow-up questions in the same way — the agent can run more than one query per conversation if it needs to.

## Files

- `ask.py` — the agent: schema-aware system prompt, the `run_sql_query` tool, and the safety check
- `schema.sql` — example schema (swap for your pod's actual tables)
- `.env.example` — required environment variables

## Run it

```bash
cp .env.example .env      # fill in PG_BASE_URL, PG_API_KEY, PG_CHAT_MODEL, and DB_URL
pip install pydantic-ai sqlalchemy
python ask.py "How many units of SKU 4471 shipped last week?"
```

## Safety note

Use a database credential that only has `SELECT` access. The tool itself blocks anything containing `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `DROP`, or `TRUNCATE` before it reaches your database — but a read-only DB credential is a second layer that doesn't depend on that check catching everything.

## Swap points

- `schema.sql` is a placeholder — replace with your pod's real schema (or generate it with `SHOW CREATE TABLE` / your DB's equivalent) so the model has accurate column names to work from.
- Make sure the chat model you pick actually supports tool calling (check its `capabilities.tool_calling` flag via `GET {PG_BASE_URL}/v1/models`) — not every model handles Pydantic AI's tool-calling format correctly, even if it can answer plain questions fine.
