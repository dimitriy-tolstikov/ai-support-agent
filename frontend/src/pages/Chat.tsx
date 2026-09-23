// демонстрирует: чат со стримингом — optimistic update, SSE-подписка, «Стоп», индикаторы состояния
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type Message } from "../api/client";
import { useToast } from "../components/Toaster";
import { useSSE, MAX_ATTEMPTS, type SSEEvent } from "../hooks/useSSE";
import MessageList from "../components/MessageList";
import Composer from "../components/Composer";
import AgentSettingsForm from "../components/AgentSettingsForm";

interface ToolCall { name: string; arguments: Record<string, unknown> }

export default function Chat() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const [streamActive, setStreamActive] = useState(false);
  const [draft, setDraft] = useState("");
  const [draftToolCalls, setDraftToolCalls] = useState<ToolCall[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: conversations } = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const conversation = conversations?.find((c) => c.id === id);

  const { data: messages, isLoading } = useQuery({
    queryKey: ["messages", id],
    queryFn: () => api.listMessages(id),
  });

  const onEvent = useCallback(
    (e: SSEEvent) => {
      if (e.type === "token") setDraft((d) => d + (e.text as string));
      if (e.type === "tool_call")
        setDraftToolCalls((t) => [...t, { name: e.name as string, arguments: e.arguments as Record<string, unknown> }]);
      if (e.type === "done") {
        setStreamActive(false);
        setDraft("");
        setDraftToolCalls([]);
        qc.invalidateQueries({ queryKey: ["messages", id] });
      }
      if (e.type === "error") {
        setStreamActive(false);
        toast(`Ошибка генерации: ${e.message}`, "error");
        qc.invalidateQueries({ queryKey: ["messages", id] });
      }
    },
    [id, qc, toast],
  );

  const { status, attempt, stop } = useSSE(id, streamActive, onEvent);

  const sendMut = useMutation({
    mutationFn: (content: string) => api.postMessage(id, content),
    onMutate: async (content) => {
      // optimistic update: сообщение появляется сразу, до ответа сервера
      await qc.cancelQueries({ queryKey: ["messages", id] });
      const prev = qc.getQueryData<Message[]>(["messages", id]);
      const optimistic: Message = {
        id: -Date.now(), conversation_id: id, role: "user", content,
        metadata: {}, created_at: new Date().toISOString(),
      };
      qc.setQueryData<Message[]>(["messages", id], [...(prev ?? []), optimistic]);
      return { prev };
    },
    onSuccess: (data) => {
      qc.setQueryData<Message[]>(["messages", id], (old = []) => [
        ...old.filter((m) => m.id > 0),
        data.user_message,
      ]);
      setDraft("");
      setDraftToolCalls([]);
      setStreamActive(true);
    },
    onError: (e, _v, ctx) => {
      qc.setQueryData(["messages", id], ctx?.prev);
      toast(`Не удалось отправить: ${e.message}`);
    },
  });

  const closeMut = useMutation({
    mutationFn: () => api.closeConversation(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      toast("Диалог закрыт, статистика посчитана", "info");
    },
    onError: (e) => toast(e.message),
  });

  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, draft]);

  const handleStop = () => {
    stop();
    setStreamActive(false);
    // backend досохранит ответ — подтянем финальное состояние
    setTimeout(() => qc.invalidateQueries({ queryKey: ["messages", id] }), 1500);
  };

  const streaming = status === "connecting" || status === "streaming" || status === "reconnecting";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/" className="text-sm text-blue-600 hover:underline">← к списку</Link>
          <h2 className="text-xl font-semibold">{conversation?.title ?? "Диалог"}</h2>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowSettings((s) => !s)}
            className="rounded-lg border bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Настройки агента
          </button>
          {conversation?.status === "open" && (
            <button
              onClick={() => closeMut.mutate()}
              className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
            >
              Закрыть диалог
            </button>
          )}
        </div>
      </div>

      {showSettings && conversation && (
        <AgentSettingsForm conversation={conversation} onSaved={() => setShowSettings(false)} />
      )}

      {conversation?.stats && (
        <div className="rounded-xl bg-slate-200 p-3 text-xs text-slate-700">
          Статистика (RPC close_conversation): {JSON.stringify(conversation.stats)}
        </div>
      )}

      {status === "reconnecting" && (
        <div className="rounded-lg bg-amber-100 px-3 py-2 text-sm text-amber-800">
          Соединение оборвалось, переподключение (попытка {attempt + 1}/{MAX_ATTEMPTS})…
        </div>
      )}
      {status === "error" && (
        <div className="rounded-lg bg-red-100 px-3 py-2 text-sm text-red-700">
          Не удалось восстановить соединение после {MAX_ATTEMPTS} попыток.
        </div>
      )}

      <div className="rounded-xl bg-white p-4 shadow-sm">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-slate-100" />)}
          </div>
        ) : (
          <MessageList
            messages={messages ?? []}
            draft={draft}
            draftToolCalls={draftToolCalls}
            streaming={streaming}
          />
        )}
        <div ref={bottomRef} />
      </div>

      <Composer
        disabled={conversation?.status === "closed" || sendMut.isPending}
        streaming={streaming}
        onSend={(text) => sendMut.mutate(text)}
        onStop={handleStop}
      />
    </div>
  );
}
