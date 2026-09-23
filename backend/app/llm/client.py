"""демонстрирует: async-клиент OpenAI-совместимого chat.completions API со стримингом и tools,
а также встроенный mock-провайдер (LLM_PROVIDER=mock) для работы без ключа.

События генератора: ("content", str) — дельта текста; ("tool_calls", [...]) — модель вызвала
инструменты; ("usage", {...}) — статистика токенов в конце.
"""
import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..config import settings

Event = tuple[str, Any]

_ORDER_RE = re.compile(r"\b(\d{4})\b")


async def _drain_text(text: str, chunk: int = 6, delay: float = 0.015) -> AsyncIterator[Event]:
    """Эмуляция пословного стриминга: выдаём текст кусочками с задержкой."""
    for i in range(0, len(text), chunk):
        yield ("content", text[i : i + chunk])
        await asyncio.sleep(delay)


async def _mock_stream(messages: list[dict], tools: list[dict] | None) -> AsyncIterator[Event]:
    last = messages[-1]
    if last["role"] == "tool":
        # После результата инструмента — финальный structured output.
        tool_result = json.loads(last["content"])
        if "status" in tool_result and "order_id" in tool_result and tool_result.get("found"):
            answer = (f"Заказ {tool_result['order_id']}: статус «{tool_result['status']}», "
                      f"сумма {tool_result['total']} ₽"
                      + (f", перевозчик {tool_result['carrier']}." if tool_result.get("carrier") else "."))
        elif tool_result.get("found") is False:
            answer = f"К сожалению, заказ {tool_result.get('order_id')} не найден. Проверьте номер, пожалуйста."
        elif "ticket_id" in tool_result:
            answer = f"Я создал тикет №{tool_result['ticket_id']}, специалисты свяжутся с вами. Чем-то ещё помочь?"
        else:
            answer = "Готово. Чем-то ещё помочь?"
        payload = json.dumps({"answer": answer, "resolved": True, "sentiment": "neutral"},
                             ensure_ascii=False)
        async for ev in _drain_text(payload):
            yield ev
        yield ("usage", {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160})
        return

    user_text = last.get("content") or ""
    m = _ORDER_RE.search(user_text)
    if tools and m:
        yield ("tool_calls", [{"id": "call_mock_1", "name": "get_order_status",
                               "arguments": {"order_id": m.group(1)}}])
        return
    if tools and any(w in user_text.lower() for w in ("тикет", "жалоба", "пожаловаться")):
        yield ("tool_calls", [{"id": "call_mock_2", "name": "create_support_ticket",
                               "arguments": {"title": user_text[:60], "description": user_text}}])
        return

    payload = json.dumps(
        {"answer": "Я AI-оператор поддержки. Спросите о статусе заказа (например, «где мой заказ 1001?») "
                   "или попросите создать тикет.",
         "resolved": False, "sentiment": "neutral"},
        ensure_ascii=False)
    async for ev in _drain_text(payload):
        yield ev
    yield ("usage", {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130})


async def _openai_stream(messages: list[dict], tools: list[dict] | None,
                         response_format: dict | None, temperature: float | None) -> AsyncIterator[Event]:
    body: dict[str, Any] = {"model": settings.llm_model, "messages": messages, "stream": True,
                            "stream_options": {"include_usage": True}}
    if temperature is not None:
        body["temperature"] = temperature
    if tools:
        body["tools"] = tools
    if response_format:
        body["response_format"] = response_format
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    tool_calls: dict[int, dict] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", f"{settings.llm_base_url}/chat/completions",
                                 json=body, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage"):
                    yield ("usage", chunk["usage"])
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    if delta.get("content"):
                        yield ("content", delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        slot = tool_calls.setdefault(tc["index"], {"id": "", "name": "", "arguments": ""})
                        slot["id"] += tc.get("id") or ""
                        slot["name"] += (tc.get("function") or {}).get("name") or ""
                        slot["arguments"] += (tc.get("function") or {}).get("arguments") or ""
    if tool_calls:
        yield ("tool_calls", [
            {"id": tc["id"], "name": tc["name"], "arguments": json.loads(tc["arguments"] or "{}")}
            for tc in (tool_calls[i] for i in sorted(tool_calls))
        ])


async def stream_chat(messages: list[dict], tools: list[dict] | None = None,
                      response_format: dict | None = None,
                      temperature: float | None = None) -> AsyncIterator[Event]:
    if settings.llm_provider == "mock":
        async for ev in _mock_stream(messages, tools):
            yield ev
    else:
        async for ev in _openai_stream(messages, tools, response_format, temperature):
            yield ev
