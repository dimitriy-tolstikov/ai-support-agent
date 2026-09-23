// демонстрирует: типобезопасный API-клиент с zod-валидацией ответов
import { z } from "zod";

export const ConversationSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.enum(["open", "closed"]),
  agent_settings: z.object({
    system_prompt: z.string().nullable().optional(),
    temperature: z.number().optional(),
  }),
  stats: z.record(z.any()).nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Conversation = z.infer<typeof ConversationSchema>;

export const MessageSchema = z.object({
  id: z.number(),
  conversation_id: z.string(),
  role: z.enum(["user", "assistant", "tool"]),
  content: z.string(),
  metadata: z.object({
    tool_calls: z.array(z.object({ name: z.string(), arguments: z.record(z.any()) })).optional(),
    latency: z.object({ ttft_ms: z.number(), total_ms: z.number() }).optional(),
    usage: z.record(z.any()).optional(),
  }).passthrough(),
  created_at: z.string(),
});
export type Message = z.infer<typeof MessageSchema>;

async function req<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api/v1${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return schema.parse(await resp.json());
}

export const api = {
  listConversations: () => req("/conversations", z.array(ConversationSchema)),
  createConversation: (title: string) =>
    req("/conversations", ConversationSchema, { method: "POST", body: JSON.stringify({ title }) }),
  listMessages: (id: string) => req(`/conversations/${id}/messages`, z.array(MessageSchema)),
  postMessage: (id: string, content: string) =>
    req(
      `/conversations/${id}/messages`,
      z.object({ user_message: MessageSchema, assistant_message: MessageSchema }),
      { method: "POST", body: JSON.stringify({ content }) },
    ),
  putSettings: (id: string, settings: { system_prompt: string | null; temperature: number }) =>
    req(`/conversations/${id}/settings`, ConversationSchema, {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  closeConversation: (id: string) =>
    req(`/conversations/${id}/close`, ConversationSchema, { method: "POST" }),
};
