"""Async client for the Agent Forge agent.

Agent Forge exposes an OpenAI-compatible surface — `POST /v1/chat/completions`,
bearer auth, and OpenAI-shaped error envelopes (`{"error": {"message", "type"}}`)
— so the `openai` client is the native fit here rather than an adapter. It gives
us a genuinely async client (no thread offload in front of a blocking HTTP call),
typed exceptions carrying the server's own message, and retry/backoff for free.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, AsyncOpenAI

from .config import Settings, settings

logger = logging.getLogger(__name__)

# Retries apply to connection errors, timeouts, 408/409/429 and 5xx — never to a
# 4xx like a bad key, which would only burn the Teams turn's latency budget.
MAX_RETRIES = 2


class ForgeError(RuntimeError):
    """Raised when the agent could not be reached or returned no usable text."""


class ForgeAgent:
    """Talks to one Agent Forge agent over the OpenAI-compatible chat endpoint."""

    def __init__(self, config: Settings | None = None) -> None:
        self._config = config or settings
        self._config.validate_forge()
        self._client = AsyncOpenAI(
            api_key=self._config.agent_api_key,
            base_url=self._config.forge_api_url,
            timeout=self._config.forge_timeout,
            max_retries=MAX_RETRIES,
        )
        logger.info(
            "Forge client ready (url=%s, model=%s)",
            self._config.forge_api_url,
            self._config.agent_id,
        )

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Send a message list to the agent and return its reply text."""
        try:
            response = await self._client.chat.completions.create(
                model=self._config.agent_id,
                messages=messages,  # type: ignore[arg-type]
            )
        except APITimeoutError as exc:
            raise ForgeError(
                f"The agent didn't respond within {self._config.forge_timeout:.0f}s."
            ) from exc
        except APIConnectionError as exc:
            raise ForgeError(f"Couldn't reach {self._config.forge_api_url}.") from exc
        except APIStatusError as exc:
            raise ForgeError(_describe_status_error(exc)) from exc
        except APIError as exc:
            raise ForgeError(str(exc)) from exc

        return self._extract_text(response)

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull assistant text out of an OpenAI-shaped response.

        Normalises the typed `ChatCompletion` to a plain dict first, so this stays
        tolerant of an agent runtime that returns a shape the model doesn't cover.
        """
        if hasattr(response, "model_dump"):
            response = response.model_dump()
        elif not isinstance(response, dict):
            response = getattr(response, "__dict__", {}) or {}

        choices = response.get("choices") or []
        if not choices:
            raise ForgeError(f"Agent returned no choices: {response!r}")

        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()

        if not text:
            # Some agent runtimes surface tool-only or reasoning-only turns.
            # Include the raw payload: an agent may nest its answer differently
            # than a plain model, and without the body there is nothing to debug.
            reason = choices[0].get("finish_reason", "unknown")
            raise ForgeError(
                f"Agent returned empty content (finish_reason={reason}): {response!r}"
            )
        return text


def _describe_status_error(exc: APIStatusError) -> str:
    """Turn an HTTP failure into something actionable in a Teams message."""
    hints = {
        401: "the AGENT_API_KEY is invalid",
        403: "this key isn't allowed to call that agent",
        404: f"no agent with id {settings.agent_id!r} was found",
        429: "the agent is rate limited or over quota",
    }
    hint = hints.get(exc.status_code)
    detail = getattr(exc, "message", None) or str(exc)
    return f"{detail} ({hint})" if hint else detail
