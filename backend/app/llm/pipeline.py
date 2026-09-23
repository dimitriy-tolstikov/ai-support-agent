"""демонстрирует: полный LLM-конвейер — tool loop (function calling), пословный стриминг в SSE,
structured output с pydantic-валидацией и 1 retry, логирование задержек (TTFT/total) в JSONB."""
import json
import logging
import re
import time
from typing import Any

from pydantic import ValidationError

from ..db import user_conn
from ..schemas import AgentReply
from ..sse import bus
from .client import stream_chat
from .tools import TOOL_SCHEMAS, execute_tool

log = logging.getLogger("llm.pipeline")

SYSTEM_DEFAULT = (
    "Ты — AI-оператор поддержки магазина. Помогай с заказами: используй инструменты "
    "get_order_status и create_support_ticket. Финальный ответ пользователю давай строго в JSON "
    'вида {"answer": "текст ответа", "resolved": true|false, "sentiment": "positive|neutral|negative"}.'
)

_ANSWER_START = re.compile(r'"answer"\s*:\s*"')
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}


class AnswerExtractor:
    """Инкрементально достаёт значение поля "answer" из стримящегося JSON, декодируя escapes."""

    def __init__(self) -> None:
        self.buf = ""
        self.i: int | None = None   # позиция разбора внутри значения answer
        self.done = False

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        if self.done:
            return ""
        if self.i is None:
            m = _ANSWER_START.search(self.buf)
            if not m:
                return ""
            self.i = m.end()
        out: list[str] = []
        while self.i < len(self.buf):
            ch = self.buf[self.i]
            if ch == '"':                       # неэкранированная кавычка — конец строки
                self.done = True
                break
            if ch == "\\":
                nxt = self.buf[self.i + 1] if self.i + 1 < len(self.buf) else None
                if nxt is None:
                    break                        # неполный escape в конце буфера — ждём
                if nxt == "u":
                    hex4 = self.buf[self.i + 2 : self.i + 6]
                    if len(hex4) < 4:
                        break
                    out.append(chr(int(hex4, 16)))
                    self.i += 6
                else:
                    out.append(_ESCAPES.get(nxt, nxt))
                    self.i += 2
                continue
            out.append(ch)
            self.i += 1
        return "".join(out)


async def generate(conversation_id: str, assistant_msg_id: int) -> dict[str, Any]:
    """Один ход агента: история → tool loop → structured output. Публикует события в SSE-шину."""
    started = time.monotonic()
    ttft_ms: float | None = None
    tool_calls_log: list[dict] = []
    usage: dict[str, Any] = {}

    def publish(event: dict) -> None:
        bus.publish(conversation_id, event)

    try:
        async with user_conn() as conn:
            conv = await conn.fetchrow("SELECT agent_settings FROM conversations WHERE id = $1", conversation_id)
            rows = await conn.fetch(
                "SELECT role, content FROM messages WHERE conversation_id = $1 AND id < $2 ORDER BY id",
                conversation_id, assistant_msg_id)
            settings = json.loads(conv["agent_settings"]) if conv else {}
            system = settings.get("system_prompt") or SYSTEM_DEFAULT
            temperature = settings.get("temperature", 0.7)
            messages: list[dict] = [{"role": "system", "content": system}]
            messages += [{"role": r["role"], "content": r["content"]} for r in rows if r["role"] != "tool"]

            reply: AgentReply | None = None
            raw = ""
            for retry in range(2):  # 1 автоматический retry при невалидном structured output
                round_msgs = list(messages)
                extractor = AnswerExtractor()
                while True:  # tool loop
                    raw = ""
                    calls: list[dict] | None = None
                    async for kind, data in stream_chat(
                        round_msgs, tools=TOOL_SCHEMAS, response_format={"type": "json_object"}
                    ):
                        if kind == "content":
                            if ttft_ms is None:
                                ttft_ms = (time.monotonic() - started) * 1000
                                publish({"type": "first_token", "ttft_ms": round(ttft_ms)})
                            raw += data
                            token = extractor.feed(data)
                            if token:
                                publish({"type": "token", "text": token})
                        elif kind == "tool_calls":
                            calls = data
                        elif kind == "usage":
                            usage = data
                    if not calls:
                        break
                    round_msgs.append({"role": "assistant", "content": None, "tool_calls": [
                        {"id": c["id"], "type": "function",
                         "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                        for c in calls]})
                    for c in calls:
                        result = await execute_tool(conn, conversation_id, c["name"], c["arguments"])
                        tool_calls_log.append({"name": c["name"], "arguments": c["arguments"]})
                        publish({"type": "tool_call", "name": c["name"], "arguments": c["arguments"]})
                        round_msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
                    extractor = AnswerExtractor()  # следующий раунд — финальный JSON

                try:
                    reply = AgentReply.model_validate(json.loads(raw))
                    break
                except (json.JSONDecodeError, ValidationError) as exc:
                    log.warning("invalid structured output (retry %d): %s", retry, exc)
                    if retry == 0:
                        messages.append({"role": "system", "content":
                            "Твой предыдущий ответ не прошёл валидацию. Верни строго JSON "
                            '{"answer": str, "resolved": bool, "sentiment": str}.'})
            if reply is None:
                reply = AgentReply(answer="Извините, произошла ошибка генерации. Попробуйте ещё раз.")

            total_ms = (time.monotonic() - started) * 1000
            metadata = {
                "tool_calls": tool_calls_log,
                "latency": {"ttft_ms": round(ttft_ms or 0), "total_ms": round(total_ms)},
                "usage": usage,
            }
            await conn.execute(
                "UPDATE messages SET content = $1, metadata = $2 WHERE id = $3",
                reply.answer, json.dumps(metadata, ensure_ascii=False), assistant_msg_id)
            publish({"type": "done", "message_id": assistant_msg_id, "metadata": metadata})
            log.info("turn done conv=%s ttft=%sms total=%sms", conversation_id, ttft_ms, round(total_ms))
            return {"answer": reply.answer, "tool_calls": tool_calls_log}
    except Exception as exc:  # noqa: BLE001 — ошибку показываем в чате
        log.exception("generation failed")
        publish({"type": "error", "message": str(exc)})
        async with user_conn() as conn:
            await conn.execute(
                "UPDATE messages SET content = $1, metadata = $2 WHERE id = $3",
                "Ошибка генерации ответа.", json.dumps({"error": str(exc)}), assistant_msg_id)
        return {"answer": "Ошибка генерации ответа.", "tool_calls": tool_calls_log}
