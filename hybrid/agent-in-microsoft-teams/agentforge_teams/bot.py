"""Bot Framework activity handler that bridges Teams <-> Agent Forge."""

from __future__ import annotations

import asyncio
import logging

from botbuilder.core import ActivityHandler, MessageFactory, TurnContext
from botbuilder.schema import Activity, ActivityTypes, ChannelAccount

from .config import Settings, settings
from .conversation import HistoryStore, InMemoryHistoryStore
from .forge_client import ForgeAgent, ForgeError

logger = logging.getLogger(__name__)

# Teams clears the typing indicator after a few seconds, so it has to be
# refreshed while a slow agent turn is in flight.
TYPING_REFRESH_SECONDS = 4.0

RESET_COMMANDS = {"/reset", "/clear", "/new"}


class ForgeTeamsBot(ActivityHandler):
    def __init__(
        self,
        agent: ForgeAgent,
        history: HistoryStore | None = None,
        config: Settings | None = None,
    ) -> None:
        self._agent = agent
        self._config = config or settings
        self._history = history or InMemoryHistoryStore(
            ttl_seconds=self._config.history_ttl_seconds
        )

    # ------------------------------------------------------------------ events

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ) -> None:
        """Greet on install.

        Teams signals installation by putting the *bot's own* id in
        `membersAdded` — in personal scope and when the app is added to a team or
        group chat alike. Greeting on any other member therefore means saying
        nothing when someone installs the app into a channel, then greeting every
        human who later joins that team. So the test is deliberately inverted
        relative to the obvious `member.id != bot_id`.
        """
        recipient = turn_context.activity.recipient
        bot_id = recipient.id if recipient else None
        if any(member.id == bot_id for member in members_added):
            await turn_context.send_activity(
                MessageFactory.text(self._config.welcome_message)
            )

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        prompt = self._clean_text(turn_context)
        conversation = turn_context.activity.conversation
        conversation_id = conversation.id

        # History is keyed on this id, and in a Teams channel it carries a
        # `;messageid=<thread-root>` suffix — so each thread gets its own
        # history. Logged so you can confirm that separation in a real channel
        # rather than taking it on trust.
        logger.info(
            "turn: conversation=%s is_group=%s threaded=%s",
            conversation_id,
            conversation.is_group,
            "messageid=" in (conversation_id or ""),
        )

        # In a channel or group chat the @mention is what addresses the turn to
        # the bot. Everything else is someone else's conversation — stay out of
        # it, silently, the way a person would.
        if conversation.is_group and not self._addressed_to_bot(turn_context.activity):
            logger.info("ignoring unaddressed group message in %s", conversation_id)
            return

        if not prompt:
            await turn_context.send_activity(
                MessageFactory.text("Send me some text and I'll pass it to the agent.")
            )
            return

        if prompt.casefold() in RESET_COMMANDS:
            await self._history.clear(conversation_id)
            await turn_context.send_activity(
                MessageFactory.text("Conversation history cleared. 🧹")
            )
            return

        messages = self._build_messages(
            await self._history.get(conversation_id), prompt
        )

        async with _typing(turn_context):
            try:
                reply = await self._agent.complete(messages)
            except ForgeError as exc:
                logger.exception("Agent Forge call failed")
                await turn_context.send_activity(
                    MessageFactory.text(
                        "⚠️ I couldn't reach the agent just now. "
                        f"Please try again.\n\n_Details: {exc}_"
                    )
                )
                return

        # Only record the turn once the agent actually answered, so a failed
        # call doesn't poison the history with a dangling user message.
        await self._history.append(
            conversation_id,
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": reply},
            max_messages=self._config.history_turns * 2,
        )

        await turn_context.send_activity(MessageFactory.text(reply))

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _addressed_to_bot(activity: Activity) -> bool:
        """Was the bot itself @mentioned in this message?

        Teams normally withholds unaddressed channel messages from a bot, so
        this only starts mattering once the app is granted
        `ChannelMessage.Read.Group` — at which point every line of the
        surrounding discussion arrives here, and answering all of it would be
        indistinguishable from a malfunction. Cheap to hold the line now rather
        than discover it after the permission is granted.

        The id lives in `additional_properties`: `get_mentions` returns raw
        `Entity` objects despite its `List[Mention]` annotation, so the obvious
        `mention.mentioned.id` raises `AttributeError`.
        """
        recipient = activity.recipient
        bot_id = recipient.id if recipient else None
        for mention in TurnContext.get_mentions(activity):
            mentioned = (mention.additional_properties or {}).get("mentioned") or {}
            if mentioned.get("id") == bot_id:
                return True
        return False

    @staticmethod
    def _clean_text(turn_context: TurnContext) -> str:
        """Strip the `<at>Bot</at>` mention Teams prepends in channels."""
        text = TurnContext.remove_recipient_mention(turn_context.activity) or ""
        return text.strip()

    def _build_messages(
        self, history: list[dict[str, str]], prompt: str
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self._config.system_prompt:
            messages.append({"role": "system", "content": self._config.system_prompt})
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages


class _typing:
    """Async context manager that keeps the Teams typing indicator alive."""

    def __init__(self, turn_context: TurnContext) -> None:
        self._turn_context = turn_context
        self._task: asyncio.Task | None = None

    async def __aenter__(self) -> "_typing":
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self._turn_context.send_activity(
                    Activity(type=ActivityTypes.typing)
                )
            except Exception:  # never let a cosmetic indicator break the turn
                logger.debug("typing indicator failed", exc_info=True)
                return
            await asyncio.sleep(TYPING_REFRESH_SECONDS)
