-- откат 0002: удаление триггеров и функций
BEGIN;
DROP TRIGGER IF EXISTS trg_conversations_audit ON conversations;
DROP TRIGGER IF EXISTS trg_conversations_updated_at ON conversations;
DROP FUNCTION IF EXISTS audit_conversation_status();
DROP FUNCTION IF EXISTS set_updated_at();
DROP FUNCTION IF EXISTS close_conversation(uuid);
COMMIT;
