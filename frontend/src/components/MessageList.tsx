// демонстрирует: рендер ленты сообщений + «живой» черновик стримящегося ответа
import type { Message } from "../api/client";
import MessageItem from "./MessageItem";

interface Props {
  messages: Message[];
  draft: string;
  draftToolCalls: { name: string; arguments: Record<string, unknown> }[];
  streaming: boolean;
}

export default function MessageList({ messages, draft, draftToolCalls, streaming }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {messages.map((m) => (
        <MessageItem key={m.id} message={m} />
      ))}
      {(streaming || draft) && (
        <MessageItem
          message={{
            id: 0,
            conversation_id: "",
            role: "assistant",
            content: draft,
            metadata: { tool_calls: draftToolCalls },
            created_at: new Date().toISOString(),
          }}
          live
        />
      )}
      {messages.length === 0 && !streaming && (
        <p className="py-6 text-center text-sm text-slate-400">
          Напишите первое сообщение — например, «где мой заказ 1001?»
        </p>
      )}
    </div>
  );
}
