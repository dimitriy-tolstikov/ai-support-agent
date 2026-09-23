"""демонстрирует: asyncio-очередь фоновых задач с ретраями (3 попытки, backoff) и DLQ-таблицей."""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .db import pool

log = logging.getLogger("queue")

MAX_ATTEMPTS = 3
Handler = Callable[[dict[str, Any]], Awaitable[None]]

_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
_handlers: dict[str, Handler] = {}


def register(task_type: str, handler: Handler) -> None:
    _handlers[task_type] = handler


async def enqueue(task_type: str, payload: dict[str, Any]) -> None:
    await _queue.put({"type": task_type, "payload": payload, "attempts": 0})


async def _to_dlq(task: dict[str, Any], error: str) -> None:
    # dlq_tasks без RLS — пишем напрямую из пула
    async with pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO dlq_tasks (task_type, payload, error, attempts) VALUES ($1, $2, $3, $4)",
            task["type"], json.dumps(task["payload"]), error, task["attempts"],
        )
    log.error("task moved to DLQ: %s (%s)", task["type"], error)


async def worker() -> None:
    """Единственный воркер; backoff 1s, 2s, 4s между попытками."""
    while True:
        task = await _queue.get()
        handler = _handlers.get(task["type"])
        try:
            if handler is None:
                raise ValueError(f"no handler for task type {task['type']!r}")
            await handler(task["payload"])
        except Exception as exc:  # noqa: BLE001 — любая ошибка задачи идёт в ретрай/DLQ
            task["attempts"] += 1
            if task["attempts"] >= MAX_ATTEMPTS:
                await _to_dlq(task, f"{type(exc).__name__}: {exc}")
            else:
                delay = 2 ** (task["attempts"] - 1)
                log.warning("task %s failed (attempt %d), retry in %ds: %s",
                            task["type"], task["attempts"], delay, exc)
                await asyncio.sleep(delay)
                await _queue.put(task)
        finally:
            _queue.task_done()
