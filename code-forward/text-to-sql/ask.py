"""
A Pydantic AI agent that answers questions against a real database,
using Prediction Guard as the model.

Usage:
    python ask.py "your question here"

Fill in .env first (copy from .env.example). Use a read-only DB credential.
"""

import os
import re
import sys
from sqlalchemy import create_engine, text
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

PG_BASE_URL = os.environ["PG_BASE_URL"].rstrip("/")
PG_API_KEY = os.environ["PG_API_KEY"]
CHAT_MODEL = os.environ["PG_CHAT_MODEL"]
DB_URL = os.environ["DB_URL"]

SCHEMA = open(os.path.join(os.path.dirname(__file__), "schema.sql")).read()
BLOCKED = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b", re.IGNORECASE)
ENGINE = create_engine(DB_URL)

model = OpenAIChatModel(
    CHAT_MODEL,
    provider=OpenAIProvider(base_url=f"{PG_BASE_URL}/v1", api_key=PG_API_KEY),
)

agent = Agent(
    model,
    system_prompt=(
        "You answer questions about a database using the run_sql_query tool. "
        f"Here is the schema:\n{SCHEMA}\n"
        "Write PostgreSQL SELECT queries only — you cannot modify data. "
        "Answer the user's question in plain English based on the query results."
    ),
)


@agent.tool
def run_sql_query(ctx: RunContext[None], sql: str) -> str:
    """Run a read-only SQL SELECT query against the database and return the rows."""
    if BLOCKED.search(sql):
        return "Refused: this tool only runs SELECT queries, no writes or schema changes."
    with ENGINE.connect() as conn:
        rows = [dict(row._mapping) for row in conn.execute(text(sql))]
    return str(rows)


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "How many SKUs are in inventory?"
    result = agent.run_sync(question)
    print(result.output)


if __name__ == "__main__":
    main()
