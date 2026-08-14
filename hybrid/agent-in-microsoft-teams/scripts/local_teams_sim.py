"""Chat with the bot locally, with no Teams and no Azure.

Teams talks to a bot in two directions: it POSTs activities *to* the bot, and the
bot POSTs replies *back* to the Bot Connector at whatever `serviceUrl` the
activity carried. This script plays both halves — it runs a tiny fake connector
and points `serviceUrl` at it — so the whole turn (mention stripping, history,
the agent call, the reply) executes exactly as it will in production.

Run the bot first, in another terminal:

    uv run uvicorn agentforge_teams.app:app --port 3978

then:

    uv run python scripts/local_teams_sim.py
    uv run python scripts/local_teams_sim.py --channel   # simulate a channel

`--channel` puts the conversation in a channel (`isGroup`), where whether the bot
is addressed is decided per *message*, not per run: prefix your text with
`@Agent Forge` and the activity carries the mention the way Teams sends it, which
exercises the mention-stripping path. Type anything else and it goes out as a
plain channel message with no mention — the shape Teams withholds from the bot
unless the app is granted `ChannelMessage.Read.Group`.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

from aiohttp import ClientSession, web

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BOT_PORT = int(os.environ.get("BOT_PORT", "3978"))
BOT_URL = f"http://127.0.0.1:{BOT_PORT}/api/messages"

# The fake connector takes whatever port the OS hands out. Hard-coding one only
# invites a collision — with the bot itself, or with a previous run of this
# script — and the resulting bind error looks nothing like its cause.
SERVICE_URL = ""  # set in main() once the real port is known

BOT_ID = "28:local-bot"
BOT_NAME = "Agent Forge"
USER_ID = "29:local-user"
CONVERSATION_ID = "local-conversation-1"

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"


async def handle_reply(request: web.Request) -> web.Response:
    """Stand in for `POST /v3/conversations/{id}/activities`."""
    activity = await request.json()
    kind = activity.get("type")

    if kind == "typing":
        print(f"{DIM}  … typing{RESET}")
    elif kind == "message":
        print(f"\n{BOLD}agent:{RESET} {activity.get('text', '')}\n")
    else:
        print(f"{DIM}  [{kind}]{RESET}")

    return web.json_response({"id": str(uuid.uuid4())})


def split_mention(text: str) -> tuple[bool, str]:
    """Decide whether the typed text addresses the bot, and return the remainder.

    In Teams the `@` a human types never reaches the bot as text — the client
    turns it into a `mention` entity and rewrites the body. So the sim has to
    make that call here, at the point where a person would have clicked the
    autocomplete, rather than assuming every message in a channel is addressed
    to the bot.
    """
    if not text.startswith("@"):
        return False, text
    body = text[1:]
    if body.casefold().startswith(BOT_NAME.casefold()):
        return True, body[len(BOT_NAME) :].lstrip()
    # `@anyone-else` — Teams would address that mention elsewhere, but the sim
    # has only one bot to talk to, so treat it as addressing us.
    _, _, rest = body.partition(" ")
    return True, rest.lstrip()


def build_activity(text: str, *, channel: bool) -> dict:
    """Construct what Teams would send for a message."""
    mentioned, body = split_mention(text) if channel else (False, text)

    activity: dict = {
        "type": "message",
        "id": str(uuid.uuid4()),
        "channelId": "msteams",
        "serviceUrl": SERVICE_URL,
        "conversation": {"id": CONVERSATION_ID, "isGroup": channel},
        "from": {"id": USER_ID, "name": "Local Tester"},
        "recipient": {"id": BOT_ID, "name": BOT_NAME},
        "text": body,
        "textFormat": "plain",
        "locale": "en-US",
    }
    if mentioned:
        # Exactly the shape Teams uses for an @mention in a channel. The entity
        # is what does the work — `remove_recipient_mention` matches entities
        # against `recipient.id` and ignores the text — so the two have to be
        # set together or the prompt reaches the agent with the markup intact.
        mention = f"<at>{BOT_NAME}</at>"
        activity["text"] = f"{mention} {body}".strip()
        activity["entities"] = [
            {
                "type": "mention",
                "text": mention,
                "mentioned": {"id": BOT_ID, "name": BOT_NAME},
            }
        ]
    return activity


async def send(session: ClientSession, activity: dict) -> None:
    try:
        async with session.post(BOT_URL, json=activity) as response:
            if response.status >= 400:
                body = await response.text()
                print(f"\n✗ bot returned {response.status}: {body}\n")
    except Exception as exc:
        print(f"\n✗ couldn't reach the bot at {BOT_URL}: {exc}")
        print("  Is it running?  uv run uvicorn agentforge_teams.app:app --port 3978\n")


async def preflight(session: ClientSession) -> bool:
    """Confirm the bot on the far end is healthy and holds the expected key.

    A bot left over from an earlier run — different key, different config — looks
    identical from here once it has the port, and every message just fails with a
    confusing upstream error. Comparing key fingerprints makes that obvious
    before you start typing.
    """
    health_url = BOT_URL.replace("/api/messages", "/healthz")
    try:
        async with session.get(health_url) as response:
            health = await response.json()
    except Exception as exc:
        print(f"✗ No bot answering at {health_url}: {exc}")
        print("  Start it:  uv run uvicorn agentforge_teams.app:app --port 3978\n")
        return False

    print(f"{DIM}  bot status : {health.get('status')}{RESET}")
    print(f"{DIM}  model      : {health.get('agent_id')}{RESET}")

    if health.get("status") != "ok":
        print(f"✗ Bot reports misconfigured: {health.get('error')}\n")
        return False

    from agentforge_teams.config import settings

    theirs, mine = health.get("agent_key_fingerprint"), settings.key_fingerprint
    if theirs != mine:
        print(
            f"\n✗ Key mismatch — the bot is using key {theirs}, your .env has {mine}.\n"
            f"  That bot was started with a different key. Most likely a stale\n"
            f"  process is holding the port. Find and stop it:\n"
            f"    lsof -nP -iTCP:3978 -sTCP:LISTEN\n"
        )
        return False

    print(f"{DIM}  key        : {mine} (matches your .env){RESET}")
    return True


async def main() -> int:
    channel = "--channel" in sys.argv

    app = web.Application()
    app.router.add_post("/v3/conversations/{conversation_id}/activities", handle_reply)
    # The connector also accepts replies addressed to a specific activity id.
    app.router.add_post(
        "/v3/conversations/{conversation_id}/activities/{activity_id}", handle_reply
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)  # 0 = let the OS choose
    await site.start()

    global SERVICE_URL
    port = runner.addresses[0][1]
    SERVICE_URL = f"http://127.0.0.1:{port}"

    mode = "channel" if channel else "personal chat"
    print(f"{BOLD}Local Teams simulator{RESET} — {mode}")
    print(f"{DIM}fake connector on {SERVICE_URL} → bot at {BOT_URL}{RESET}")

    async with ClientSession() as session:
        if not await preflight(session):
            await runner.cleanup()
            return 1

        print(f"\n{DIM}type a message, or 'quit'. Try /reset to clear history.{RESET}")
        if channel:
            print(
                f"{DIM}prefix with '@{BOT_NAME}' to send it as a mention; "
                f"anything else goes out unaddressed.{RESET}"
            )
        print()

        # Send the install event first, so you see the welcome message.
        await send(
            session,
            {
                "type": "conversationUpdate",
                "id": str(uuid.uuid4()),
                "channelId": "msteams",
                "serviceUrl": SERVICE_URL,
                "conversation": {"id": CONVERSATION_ID},
                "from": {"id": USER_ID},
                "recipient": {"id": BOT_ID, "name": BOT_NAME},
                "membersAdded": [{"id": BOT_ID, "name": BOT_NAME}],
            },
        )
        await asyncio.sleep(0.5)

        loop = asyncio.get_running_loop()
        while True:
            try:
                text = await loop.run_in_executor(None, input, f"{BOLD}you:{RESET} ")
            except (EOFError, KeyboardInterrupt):
                break
            text = text.strip()
            if not text:
                continue
            if text in {"quit", "exit"}:
                break
            activity = build_activity(text, channel=channel)
            if channel and "entities" not in activity:
                # The bot drops unaddressed group messages without replying, and
                # silence here looks exactly like a crashed bot. Say which it is.
                print(f"{DIM}  … sent unaddressed — the bot should stay silent{RESET}")
            await send(session, activity)

    await runner.cleanup()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
