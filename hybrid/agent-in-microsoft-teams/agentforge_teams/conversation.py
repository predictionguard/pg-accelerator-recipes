"""Per-conversation chat history.

`/v1/chat/completions` is stateless: it only knows what you resend each call.
Teams, meanwhile, hands the bot one activity at a time. Without replaying prior
turns the agent has no memory and feels broken to the user, so we keep a short
rolling window keyed on the Teams conversation id.

The default store is in-process. On a scaled-out Azure Functions plan each
instance therefore has its own view of history — fine for a demo, but see
`HistoryStore` for the seam to swap in Azure Table Storage / Redis when it
matters.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Protocol

Message = dict[str, str]


class HistoryStore(Protocol):
    """Swap-in point for a durable backing store."""

    async def get(self, conversation_id: str) -> list[Message]: ...

    async def append(
        self, conversation_id: str, *messages: Message, max_messages: int
    ) -> None: ...

    async def clear(self, conversation_id: str) -> None: ...


class InMemoryHistoryStore:
    """Bounded, TTL-expiring history held in process memory."""

    def __init__(self, ttl_seconds: int = 3600, max_conversations: int = 500) -> None:
        self._ttl = ttl_seconds
        self._max_conversations = max_conversations
        # conversation_id -> (last_touched_monotonic, messages)
        self._store: OrderedDict[str, tuple[float, list[Message]]] = OrderedDict()

    def _evict(self) -> None:
        now = time.monotonic()
        stale = [
            key
            for key, (touched, _) in self._store.items()
            if now - touched > self._ttl
        ]
        for key in stale:
            del self._store[key]
        while len(self._store) > self._max_conversations:
            self._store.popitem(last=False)  # drop least-recently-used

    async def get(self, conversation_id: str) -> list[Message]:
        self._evict()
        entry = self._store.get(conversation_id)
        if entry is None:
            return []
        self._store.move_to_end(conversation_id)
        return list(entry[1])

    async def append(
        self, conversation_id: str, *messages: Message, max_messages: int
    ) -> None:
        self._evict()
        _, existing = self._store.get(conversation_id, (0.0, []))
        combined = [*existing, *messages][-max_messages:]
        self._store[conversation_id] = (time.monotonic(), combined)
        self._store.move_to_end(conversation_id)

    async def clear(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)
