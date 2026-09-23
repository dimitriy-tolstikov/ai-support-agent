"""демонстрирует: in-memory pub/sub шину для SSE-стриминга токенов по conversation_id."""
import asyncio
import contextlib
from collections.abc import AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def publish(self, conversation_id: str, event: dict) -> None:
        for q in self._subs.get(conversation_id, ()):
            q.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self, conversation_id: str) -> AsyncIterator[asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(conversation_id, set()).add(q)
        try:
            yield q
        finally:
            self._subs.get(conversation_id, set()).discard(q)


bus = EventBus()
