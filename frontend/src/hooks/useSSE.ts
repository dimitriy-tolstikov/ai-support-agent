// демонстрирует: SSE-клиент с состояниями, AbortController («Стоп») и реконнектом
// с экспоненциальным backoff (макс. 3 попытки)
import { useCallback, useEffect, useRef, useState } from "react";

export type SSEStatus = "idle" | "connecting" | "streaming" | "reconnecting" | "done" | "error";

export interface SSEEvent {
  type: "first_token" | "token" | "tool_call" | "done" | "error";
  [key: string]: unknown;
}

export const MAX_ATTEMPTS = 3;

export function useSSE(
  conversationId: string | null,
  active: boolean,
  onEvent: (e: SSEEvent) => void,
) {
  const [status, setStatus] = useState<SSEStatus>("idle");
  const [attempt, setAttempt] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const manualStopRef = useRef(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const stop = useCallback(() => {
    manualStopRef.current = true;
    abortRef.current?.abort();
    setStatus("idle");
  }, []);

  useEffect(() => {
    if (!active || !conversationId) return;
    manualStopRef.current = false;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const connect = async (attempts: number) => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setAttempt(attempts);
      setStatus(attempts === 0 ? "connecting" : "reconnecting");
      try {
        const resp = await fetch(`/api/v1/conversations/${conversationId}/stream`, {
          signal: ctrl.signal,
        });
        if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
        setStatus("streaming");
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.split("\n").find((l) => l.startsWith("data: "));
            if (!line) continue;
            const event = JSON.parse(line.slice(6)) as SSEEvent;
            onEventRef.current(event);
            if (event.type === "done" || event.type === "error") {
              setStatus(event.type === "done" ? "done" : "error");
              return;
            }
          }
        }
        throw new Error("SSE stream closed without done");
      } catch (err) {
        if (cancelled || manualStopRef.current) return;
        if (attempts + 1 >= MAX_ATTEMPTS) {
          setStatus("error");
          return;
        }
        const delay = 500 * 2 ** attempts; // backoff: 0.5s, 1s, 2s
        timer = setTimeout(() => void connect(attempts + 1), delay);
      }
    };

    void connect(0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [active, conversationId]);

  return { status, attempt, stop };
}
