"""демонстрирует: идемпотентный webhook-приёмник — HMAC-верификация, немедленный 200,
дедупликация по event_id (unique constraint + ON CONFLICT), обработка в фоновой очереди."""
import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from ..config import settings
from ..db import pool, user_conn
from ..queue import enqueue, register
from ..schemas import WebhookOut

log = logging.getLogger("webhooks")
router = APIRouter(prefix="/api/v1", tags=["webhooks"])


def _verify_signature(body: bytes, signature: str | None) -> None:
    expected = "sha256=" + hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "invalid webhook signature")


@router.post("/webhooks/crm", response_model=WebhookOut)
async def crm_webhook(request: Request, x_signature: str | None = Header(default=None)) -> WebhookOut:
    body = await request.body()
    _verify_signature(body, x_signature)
    event: dict[str, Any] = json.loads(body)
    event_id = event.get("event_id")
    if not event_id:
        raise HTTPException(422, "event_id is required")

    async with pool().acquire() as conn:  # webhook_events без RLS
        row = await conn.fetchrow(
            """INSERT INTO webhook_events (event_id, event_type, payload)
               VALUES ($1, $2, $3)
               ON CONFLICT (event_id) DO NOTHING
               RETURNING id""",
            event_id, event.get("type", "unknown"), json.dumps(event))
    if row is None:
        return WebhookOut(status="duplicate")   # повторная доставка — дублей нет
    await enqueue("process_webhook_event", {"event_id": event_id})
    return WebhookOut(status="accepted")


@router.get("/admin/dlq")
async def list_dlq() -> list[dict[str, Any]]:
    async with pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM dlq_tasks ORDER BY id DESC LIMIT 100")
    return [{"id": r["id"], "task_type": r["task_type"], "payload": json.loads(r["payload"]),
             "error": r["error"], "attempts": r["attempts"], "failed_at": r["failed_at"].isoformat()}
            for r in rows]


async def process_webhook_event(payload: dict[str, Any]) -> None:
    """Обработчик очереди: применяет событие 'order.updated' к таблице orders (upsert)."""
    event_id = payload["event_id"]
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT event_type, payload FROM webhook_events WHERE event_id = $1", event_id)
        event = json.loads(row["payload"])
        if row["event_type"] != "order.updated":
            raise ValueError(f"unsupported event type {row['event_type']!r}")  # уйдёт в DLQ после ретраев
        data = event.get("data", {})
        await conn.execute(
            """INSERT INTO orders (id, user_id, status, updated_at)
               VALUES ($1, $2, $3, now())
               ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, updated_at = now()""",
            str(data["order_id"]), event.get("user_id") or "00000000-0000-0000-0000-000000000001",
            data["status"])
        await conn.execute("UPDATE webhook_events SET processed_at = now() WHERE event_id = $1", event_id)
    log.info("webhook event %s processed", event_id)


async def postprocess_conversation(payload: dict[str, Any]) -> None:
    """Post-processing закрытого диалога: здесь — лог статистики (место для summary/экспорта в CRM)."""
    async with user_conn() as conn:
        stats = await conn.fetchval("SELECT stats FROM conversations WHERE id = $1", payload["conversation_id"])
    log.info("post-processed conversation %s, stats=%s", payload["conversation_id"], stats)


register("process_webhook_event", process_webhook_event)
register("postprocess_conversation", postprocess_conversation)
