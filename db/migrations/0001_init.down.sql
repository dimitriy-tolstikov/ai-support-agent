-- откат 0001: удаление всех таблиц домена
BEGIN;
DROP TABLE IF EXISTS conversation_events;
DROP TABLE IF EXISTS dlq_tasks;
DROP TABLE IF EXISTS webhook_events;
DROP TABLE IF EXISTS support_tickets;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS conversations;
COMMIT;
