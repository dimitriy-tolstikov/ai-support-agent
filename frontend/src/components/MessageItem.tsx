// демонстрирует: сообщение с коллапсируемым блоком вызовов LLM-инструментов и метаданными (latency)
import { useState } from "react";
import type { Message } from "../api/client";

export default function MessageItem({ message, live }: { message: Message; live?: boolean }) {
  const [toolsOpen, setToolsOpen] = useState(false);
  const isUser = message.role === "user";
  const toolCalls = message.metadata?.tool_calls ?? [];
  const latency = message.metadata?.latency;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm shadow-sm ${
          isUser ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-900"
        }`}
      >
        {toolCalls.length > 0 && (
          <div className="mb-1">
            <button
              onClick={() => setToolsOpen((o) => !o)}
              className="text-xs text-slate-500 underline decoration-dotted"
            >
              {toolsOpen ? "▾" : "▸"} вызовы инструментов ({toolCalls.length})
            </button>
            {toolsOpen && (
              <div className="mt-1 space-y-1">
                {toolCalls.map((tc, i) => (
                  <pre key={i} className="overflow-x-auto rounded-lg bg-slate-800 p-2 text-xs text-green-300">
                    {tc.name}({JSON.stringify(tc.arguments, null, 1)})
                  </pre>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="whitespace-pre-wrap">
          {message.content}
          {live && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-slate-400" />}
        </div>
        {latency && (
          <div className="mt-1 text-[10px] text-slate-400">
            TTFT {latency.ttft_ms} мс · всего {latency.total_ms} мс
          </div>
        )}
      </div>
    </div>
  );
}
