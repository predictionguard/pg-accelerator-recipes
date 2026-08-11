# Agent connected to a live API

A [Pydantic AI](https://ai.pydantic.dev/) agent with a tool that calls a live external API, using Prediction Guard as the model. Uses [Open-Meteo](https://open-meteo.com/) (free, no API key needed) as a stand-in for whatever live API your pod actually needs — swap the tool for a real one: inventory, pricing, a forecasting endpoint, anything with a URL.

## How it works

1. The agent has one tool, `get_current_weather` — it calls a live HTTP API and returns the result as plain text.
2. The agent decides when to call it, and is told in its system prompt to always call it rather than guess, since the underlying data changes.
3. If asked something the tool genuinely can't answer (a forecast, when the tool only returns current conditions), the agent says so instead of making something up — worth testing for, since it's easy for a model to fill that gap with a plausible-sounding guess instead.

## Files

- `weather_agent.py` — the agent and its one live-API tool
- `.env.example` — required environment variables

## Run it

```bash
cp .env.example .env      # fill in PG_BASE_URL, PG_API_KEY, and PG_CHAT_MODEL
pip install pydantic-ai requests
python weather_agent.py "What's the current wind speed near West Lafayette, Indiana (40.42, -86.91)?"
```

## Swap points

- Replace `get_current_weather` with your pod's actual API call — same shape: a plain Python function decorated with `@agent.tool`, calling `requests` (or your API's SDK), returning a string the agent can read.
- If your API needs auth, add the credential the same way `PG_API_KEY` is handled here — an env var, never hardcoded.
- Make sure the chat model you pick actually supports tool calling (check its `capabilities.tool_calling` flag via `GET {PG_BASE_URL}/v1/models`) — not every model handles Pydantic AI's tool-calling format correctly, even if it can answer plain questions fine.
