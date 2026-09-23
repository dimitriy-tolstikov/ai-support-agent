"""демонстрирует: версионируемый REST API диалогов + SSE-стриминг генерации."""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..db import user_conn
from ..llm.pipeline import generate
from ..schemas import (AgentSettingsIn, AgentTurnIn, AgentTurnOut, ConversationOut,
                       CreateConversationIn, CreateMessageIn, CreateMessageOut, MessageOut)
from ..sse import bus

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


def _conv_out(r) -> ConversationOut:
    return ConversationOut(id=str(r["id"]), title=r["title"], status=r["status"],
                           agent_settings=json.loads(r["agent_settings"]),
                           stats=json.loads(r["stats"]) if r["stats"] else None,
                           created_at=r["created_at"].isoformat(), updated_at=r["updated_at"].isoformat())


def _msg_out(r) -> MessageOut:
    return MessageOut(id=r["id"], conversation_id=str(r["conversation_id"]), role=r["role"],
                      content=r["content"], metadata=json.loads(r["metadata"]),
                      created_at=r["created_at"].isoformat())


@router.get("", response_model=list[ConversationOut])
async def list_conversations() -> list[ConversationOut]:
    async with user_conn() as conn:
        rows = await conn.fetch("SELECT * FROM conversations ORDER BY updated_at DESC")
    return [_conv_out(r) for r in rows]


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: CreateConversationIn) -> ConversationOut:
    async with user_conn() as conn:
        row = await conn.fetchrow(
            "INSERT INTO conversations (user_id, title) VALUES (current_setting('app.user_id')::uuid, $1) RETURNING *",
            body.title)
    return _conv_out(row)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(conversation_id: str) -> list[MessageOut]:
    async with user_conn() as conn:
        rows = await conn.fetch(
            "SELECT * FROM messages WHERE conversation_id = $1 ORDER BY id", conversation_id)
    return [_msg_out(r) for r in rows]


@router.post("/{conversation_id}/messages", response_model=CreateMessageOut, status_code=201)
async def post_message(conversation_id: str, body: CreateMessageIn) -> CreateMessageOut:
    """Создаёт сообщение пользователя + placeholder ассистента и запускает генерацию в фоне."""
    async with user_conn() as conn:
        conv = await conn.fetchrow("SELECT id, status FROM conversations WHERE id = $1", conversation_id)
        if conv is None:
            raise HTTPException(404, "conversation not found")
        if conv["status"] == "closed":
            raise HTTPException(409, "conversation is closed")
        user_row = await conn.fetchrow(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'user', $2) RETURNING *",
            conversation_id, body.content)
        asst_row = await conn.fetchrow(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'assistant', '') RETURNING *",
            conversation_id)
        await conn.execute("UPDATE conversations SET updated_at = now() WHERE id = $1", conversation_id)
    asyncio.create_task(generate(conversation_id, asst_row["id"]))
    return CreateMessageOut(user_message=_msg_out(user_row), assistant_message=_msg_out(asst_row))


@router.get("/{conversation_id}/stream")
async def stream(conversation_id: str) -> StreamingResponse:
    """SSE-поток событий генерации: token / tool_call / first_token / done / error."""
    async def events():
        async with bus.subscribe(conversation_id) as q:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] in ("done", "error"):
                    break

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.put("/{conversation_id}/settings", response_model=ConversationOut)
async def put_settings(conversation_id: str, body: AgentSettingsIn) -> ConversationOut:
    async with user_conn() as conn:
        row = await conn.fetchrow(
            """UPDATE conversations
               SET agent_settings = agent_settings || $1::jsonb
               WHERE id = $2 RETURNING *""",
            json.dumps(body.model_dump()), conversation_id)
        if row is None:
            raise HTTPException(404, "conversation not found")
    return _conv_out(row)


@router.post("/{conversation_id}/close", response_model=ConversationOut)
async def close_conversation(conversation_id: str) -> ConversationOut:
    """RPC close_conversation: транзакционно закрывает диалог и пишет статистику в stats (JSONB)."""
    from ..queue import enqueue

    async with user_conn() as conn:
        try:
            await conn.fetchval("SELECT close_conversation($1::uuid)", conversation_id)
        except Exception as exc:
            raise HTTPException(404, str(exc)) from exc
        row = await conn.fetchrow("SELECT * FROM conversations WHERE id = $1", conversation_id)
    await enqueue("postprocess_conversation", {"conversation_id": conversation_id})
    return _conv_out(row)


@router.post("/internal/agent-turn", response_model=AgentTurnOut, tags=["internal"])
async def agent_turn(body: AgentTurnIn) -> AgentTurnOut:
    """Внутренний endpoint для телефонии: синхронный ход агента по тому же конвейеру, что и чат."""
    async with user_conn() as conn:
        await conn.fetchrow(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'user', $2) RETURNING id",
            body.conversation_id, body.text)
        asst = await conn.fetchrow(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'assistant', '') RETURNING id",
            body.conversation_id)
    result = await generate(body.conversation_id, asst["id"])
    return AgentTurnOut(answer=result["answer"], tool_calls=result["tool_calls"])
