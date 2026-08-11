"""
A Pydantic AI agent that calls a live external API as a tool, using
Prediction Guard as the model. Uses Open-Meteo (free, no API key needed)
as a stand-in for whatever live API your pod actually needs — swap the
tool function for a real one (inventory, pricing, weather risk, etc.).

Usage:
    python weather_agent.py "your question here"

Fill in .env first (copy from .env.example).
"""

import os
import sys
import requests
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

PG_BASE_URL = os.environ["PG_BASE_URL"].rstrip("/")
PG_API_KEY = os.environ["PG_API_KEY"]
CHAT_MODEL = os.environ["PG_CHAT_MODEL"]

model = OpenAIChatModel(
    CHAT_MODEL,
    provider=OpenAIProvider(base_url=f"{PG_BASE_URL}/v1", api_key=PG_API_KEY),
)

agent = Agent(
    model,
    system_prompt=(
        "You answer questions about current weather conditions using the "
        "get_current_weather tool. Always call it rather than guessing — "
        "conditions change, so there's no way to know without checking."
    ),
)


@agent.tool
def get_current_weather(ctx: RunContext[None], latitude: float, longitude: float) -> str:
    """Get current temperature (C) and wind speed (km/h) for a location."""
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m",
        },
        timeout=10,
    )
    resp.raise_for_status()
    current = resp.json()["current"]
    return (
        f"Temperature: {current['temperature_2m']}C, "
        f"Wind speed: {current['wind_speed_10m']} km/h"
    )


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else (
        "What's the current wind speed near West Lafayette, Indiana (40.42, -86.91)?"
    )
    result = agent.run_sync(question)
    print(result.output)


if __name__ == "__main__":
    main()
