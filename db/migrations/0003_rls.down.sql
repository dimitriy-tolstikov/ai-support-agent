-- откат 0003: снятие RLS и удаление роли приложения
BEGIN;
DROP POLICY IF EXISTS messages_owner ON messages;
DROP POLICY IF EXISTS conversations_owner ON conversations;
ALTER TABLE messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE conversations DISABLE ROW LEVEL SECURITY;
REVOKE EXECUTE ON FUNCTION close_conversation(uuid) FROM app_user;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM app_user;
REVOKE ALL ON conversations, messages, orders, support_tickets, webhook_events, dlq_tasks, conversation_events FROM app_user;
REVOKE USAGE ON SCHEMA public FROM app_user;
REVOKE CONNECT ON DATABASE ai_support FROM app_user;
DROP ROLE IF EXISTS app_user;
COMMIT;
