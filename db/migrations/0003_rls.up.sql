-- демонстрирует: Row-Level Security через роль приложения и current_setting('app.user_id')
-- Запускается суперпользователем (postgres) при миграции.
BEGIN;

-- Роль приложения (пароль подставляет migrate.py из POSTGRES_APP_PASSWORD вместо __APP_PASSWORD__)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        EXECUTE format('CREATE ROLE app_user LOGIN PASSWORD %L', '__APP_PASSWORD__');
    ELSE
        EXECUTE format('ALTER ROLE app_user LOGIN PASSWORD %L', '__APP_PASSWORD__');
    END IF;
END $$;

GRANT CONNECT ON DATABASE ai_support TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    conversations, messages, orders, support_tickets, webhook_events, dlq_tasks, conversation_events
TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
GRANT EXECUTE ON FUNCTION close_conversation(uuid) TO app_user;

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages      ENABLE ROW LEVEL SECURITY;

-- Пользователь видит только свои диалоги.
DROP POLICY IF EXISTS conversations_owner ON conversations;
CREATE POLICY conversations_owner ON conversations
    USING (user_id = current_setting('app.user_id', true)::uuid)
    WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);

-- Сообщения — только в своих диалогах.
DROP POLICY IF EXISTS messages_owner ON messages;
CREATE POLICY messages_owner ON messages
    USING (EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = messages.conversation_id
          AND c.user_id = current_setting('app.user_id', true)::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = messages.conversation_id
          AND c.user_id = current_setting('app.user_id', true)::uuid
    ));

-- Пример ручной проверки (см. README):
--   SET ROLE app_user;
--   SET app.user_id = '00000000-0000-0000-0000-000000000001';
--   SELECT * FROM conversations;          -- только свои
--   SET app.user_id = '00000000-0000-0000-0000-000000000099';
--   SELECT * FROM conversations;          -- 0 строк
--   RESET ROLE;

COMMIT;
