-- демонстрирует: схему одного домена «поддержка заказов», JSONB + GIN-индексы
BEGIN;

CREATE TABLE IF NOT EXISTS conversations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL,
    title       text NOT NULL DEFAULT 'Новый диалог',
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    agent_settings jsonb NOT NULL DEFAULT '{"system_prompt": null, "temperature": 0.7}',
    stats       jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              bigserial PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            text NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content         text NOT NULL DEFAULT '',
    -- metadata: {"tool_calls": [...], "latency": {"ttft_ms": .., "total_ms": ..}, "usage": {"total_tokens": ..}}
    metadata        jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id          text PRIMARY KEY,          -- '1001'
    user_id     uuid NOT NULL,
    status      text NOT NULL,             -- processing / shipped / delivered
    items       jsonb NOT NULL DEFAULT '[]',
    total       numeric(10,2) NOT NULL DEFAULT 0,
    carrier     text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id              bigserial PRIMARY KEY,
    conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
    title           text NOT NULL,
    description     text NOT NULL DEFAULT '',
    status          text NOT NULL DEFAULT 'open',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id           bigserial PRIMARY KEY,
    event_id     text NOT NULL UNIQUE,     -- дедупликация: unique constraint
    event_type   text NOT NULL,
    payload      jsonb NOT NULL,           -- сырой payload
    processed_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dlq_tasks (
    id         bigserial PRIMARY KEY,
    task_type  text NOT NULL,
    payload    jsonb NOT NULL,
    error      text NOT NULL,
    attempts   int NOT NULL,
    failed_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversation_events (
    id              bigserial PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    event_type      text NOT NULL,          -- 'status_changed'
    old_status      text,
    new_status      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
-- GIN-индексы под запросы по JSONB (@>):
CREATE INDEX IF NOT EXISTS idx_messages_metadata_gin ON messages USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_webhook_payload_gin  ON webhook_events USING gin (payload);

-- Пример запроса с оператором @> (использует idx_messages_metadata_gin):
--   SELECT id, content FROM messages
--   WHERE metadata @> '{"tool_calls": [{"name": "get_order_status"}]}';
-- Пример по сырому payload webhook'а:
--   SELECT event_id FROM webhook_events WHERE payload @> '{"order_id": "1001"}';

COMMIT;
