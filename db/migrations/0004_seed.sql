-- демонстрирует: seed-данные (3 заказа, 1 диалог с историей)
-- Демо-пользователь совпадает с DEMO_USER_ID из .env.example
BEGIN;

INSERT INTO orders (id, user_id, status, items, total, carrier) VALUES
    ('1001', '00000000-0000-0000-0000-000000000001', 'shipped',
     '[{"name": "Наушники SoundCore Q30", "qty": 1}]', 8990.00, 'СДЭК'),
    ('1002', '00000000-0000-0000-0000-000000000001', 'processing',
     '[{"name": "Клавиатура Keychron K2", "qty": 1}, {"name": "Коврик XL", "qty": 1}]', 12480.00, null),
    ('1003', '00000000-0000-0000-0000-000000000001', 'delivered',
     '[{"name": "Монитор LG 27UP600", "qty": 1}]', 32990.00, 'Boxberry')
ON CONFLICT (id) DO NOTHING;

INSERT INTO conversations (id, user_id, title) VALUES
    ('11111111-1111-1111-1111-111111111111',
     '00000000-0000-0000-0000-000000000001',
     'Вопрос о доставке заказа')
ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (conversation_id, role, content, metadata) VALUES
    ('11111111-1111-1111-1111-111111111111', 'user',
     'Здравствуйте! Подскажите, где мой заказ 1003?', '{}'),
    ('11111111-1111-1111-1111-111111111111', 'assistant',
     'Здравствуйте! Ваш заказ 1003 (Монитор LG 27UP600) доставлен. Перевозчик — Boxberry. Могу помочь чем-то ещё?',
     '{"tool_calls": [{"name": "get_order_status", "arguments": {"order_id": "1003"}}],
       "latency": {"ttft_ms": 320, "total_ms": 1450},
       "usage": {"prompt_tokens": 180, "completion_tokens": 42, "total_tokens": 222}}'::jsonb);

COMMIT;
