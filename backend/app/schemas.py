"""демонстрирует: pydantic v2-модели API и схему structured output ответа агента."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: str
    title: str
    status: str
    agent_settings: dict[str, Any]
    stats: dict[str, Any] | None
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    metadata: dict[str, Any]
    created_at: str


class CreateConversationIn(BaseModel):
    title: str = "Новый диалог"


class CreateMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class CreateMessageOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut


class AgentSettingsIn(BaseModel):
    system_prompt: str | None = Field(default=None, max_length=2000)
    temperature: float = Field(ge=0.0, le=2.0, default=0.7)


class AgentReply(BaseModel):
    """Structured output: финальное сообщение агента валидируется этой схемой."""

    answer: str
    resolved: bool = False
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"


class AgentTurnIn(BaseModel):
    """Внутренний вызов от телефонии: один ход диалога текстом."""

    conversation_id: str
    text: str = Field(min_length=1, max_length=4000)


class AgentTurnOut(BaseModel):
    answer: str
    tool_calls: list[dict[str, Any]]


class WebhookOut(BaseModel):
    status: str  # accepted | duplicate
