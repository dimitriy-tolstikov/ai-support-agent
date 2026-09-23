-- демонстрирует: бизнес-логику внутри PL/pgSQL (RPC) и audit-триггер
BEGIN;

-- RPC: транзакционно закрывает диалог, считает статистику и пишет её в conversations.stats (JSONB).
CREATE OR REPLACE FUNCTION close_conversation(p_conversation_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_stats jsonb;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM conversations WHERE id = p_conversation_id) THEN
        RAISE EXCEPTION 'conversation % not found', p_conversation_id;
    END IF;

    SELECT jsonb_build_object(
        'message_count', count(*),
        'user_messages', count(*) FILTER (WHERE role = 'user'),
        'assistant_messages', count(*) FILTER (WHERE role = 'assistant'),
        'total_tokens', coalesce(sum((metadata #>> '{usage,total_tokens}')::int), 0),
        'closed_at', now()
    )
    INTO v_stats
    FROM messages
    WHERE conversation_id = p_conversation_id;

    UPDATE conversations
    SET status = 'closed', stats = v_stats
    WHERE id = p_conversation_id;

    RETURN v_stats;
END;
$$;

-- Триггер 1: автообновление updated_at.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_conversations_updated_at ON conversations;
CREATE TRIGGER trg_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Триггер 2: audit-запись при смене статуса диалога.
CREATE OR REPLACE FUNCTION audit_conversation_status() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO conversation_events (conversation_id, event_type, old_status, new_status)
        VALUES (NEW.id, 'status_changed', OLD.status, NEW.status);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_conversations_audit ON conversations;
CREATE TRIGGER trg_conversations_audit
    AFTER UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION audit_conversation_status();

COMMIT;
