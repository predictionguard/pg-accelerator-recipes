"""FastAPI (ASGI) surface for the bot.

Deliberately framework-light: `BotFrameworkAdapter.process_activity()` accepts a
deserialised `Activity` plus the raw `Authorization` header, so nothing here is
tied to a particular web server. That is what lets the same app run under
`uvicorn` locally and under the Azure Functions ASGI bridge in the cloud.
"""

from __future__ import annotations

import logging
import sys
from http import HTTPStatus

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    MessageFactory,
    TurnContext,
)
from botbuilder.schema import Activity
from fastapi import FastAPI, Request, Response

from .bot import ForgeTeamsBot
from .config import ConfigError, settings
from .forge_client import ForgeAgent

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

def _build_adapter() -> BotFrameworkAdapter:
    adapter_settings = BotFrameworkAdapterSettings(
        app_id=settings.app_id,
        app_password=settings.app_password,
        # Single-tenant bots must validate against their own tenant authority.
        channel_auth_tenant=settings.app_tenant_id if settings.is_single_tenant else None,
    )
    adapter = BotFrameworkAdapter(adapter_settings)

    async def on_error(turn_context: TurnContext, error: Exception) -> None:
        logger.error("Unhandled error in turn: %s", error, exc_info=error)
        try:
            await turn_context.send_activity(
                MessageFactory.text(
                    "😵 Something went wrong handling that message. "
                    "The error has been logged."
                )
            )
        except Exception:
            logger.exception("Failed to send error message to the user")

    adapter.on_turn_error = on_error
    return adapter


app = FastAPI(title="Agent Forge → Microsoft Teams", version="0.1.0")

adapter = _build_adapter()

# Built once per process so the underlying requests.Session (and its connection
# pool) is reused across warm invocations.
try:
    _agent: ForgeAgent | None = ForgeAgent()
    _startup_error: str | None = None
except ConfigError as exc:
    _agent, _startup_error = None, str(exc)
    logger.error("Agent Forge client not initialised: %s", exc)

bot = ForgeTeamsBot(_agent) if _agent else None


# Registered on both paths: the Azure Functions ASGI bridge forwards the full
# request path, so behind the host's default `api` route prefix the probe arrives
# as `/api/healthz`, whereas local uvicorn serves it at `/healthz`.
@app.get("/healthz")
@app.get("/api/healthz")
async def healthz() -> dict[str, object]:
    """Liveness probe. Reports config readiness without leaking secrets."""
    return {
        "status": "ok" if bot else "misconfigured",
        "forge_base_url": settings.forge_base_url,
        "agent_id": settings.agent_id or None,
        # Truncated SHA-256, not the key. Lets a client confirm this process
        # holds the key it expects rather than a stale one.
        "agent_key_fingerprint": settings.key_fingerprint,
        "bot_auth_configured": settings.auth_configured,
        "error": _startup_error,
    }


@app.post("/api/messages")
async def messages(request: Request) -> Response:
    """The single endpoint the Azure Bot Service calls for every activity."""
    if bot is None:
        logger.error("Rejecting activity: %s", _startup_error)
        return Response(
            content=_startup_error or "Bot not configured",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    if not request.headers.get("content-type", "").startswith("application/json"):
        return Response(status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    activity = Activity().deserialize(await request.json())
    auth_header = request.headers.get("authorization", "")

    invoke_response = await adapter.process_activity(
        activity, auth_header, bot.on_turn
    )

    # Non-message activities (e.g. Teams invokes) can return a payload; plain
    # messages return None and want a bare 202.
    if invoke_response:
        return Response(
            content=invoke_response.body, status_code=invoke_response.status
        )
    return Response(status_code=HTTPStatus.ACCEPTED)
