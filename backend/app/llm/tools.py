"""демонстрирует: function calling — JSON-схемы инструментов и их исполнение запросами к БД."""
import json
from typing import Any

import asyncpg

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Получить статус заказа по его номеру",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "Номер заказа, например 1001"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": "Создать тикет в поддержку, если проблема не решена в чате",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        },
    },
]


async def execute_tool(conn: asyncpg.Connection, conversation_id: str, name: str, arguments: dict[str, Any]) -> str:
    """Возвращает JSON-строку результата для сообщения роли tool."""
    if name == "get_order_status":
        row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", str(arguments.get("order_id", "")))
        if row is None:
            result = {"found": False, "order_id": arguments.get("order_id")}
        else:
            result = {
                "found": True,
                "order_id": row["id"],
                "status": row["status"],
                "items": row["items"],
                "total": float(row["total"]),
                "carrier": row["carrier"],
                "updated_at": row["updated_at"].isoformat(),
            }
    elif name == "create_support_ticket":
        row = await conn.fetchrow(
            "INSERT INTO support_tickets (conversation_id, title, description) VALUES ($1, $2, $3) RETURNING id",
            conversation_id, arguments.get("title", ""), arguments.get("description", ""),
        )
        result = {"ticket_id": row["id"], "status": "open"}
    else:
        result = {"error": f"unknown tool {name}"}
    return json.dumps(result, ensure_ascii=False, default=str)
