// демонстрирует: ввод сообщения + кнопка «Стоп» (прерывание SSE через AbortController)
import { useState } from "react";

interface Props {
  disabled: boolean;
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export default function Composer({ disabled, streaming, onSend, onStop }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value);
    setText("");
  };

  return (
    <div className="flex gap-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Сообщение… (Enter — отправить)"
        rows={2}
        disabled={disabled}
        className="flex-1 resize-none rounded-xl border p-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-300 disabled:bg-slate-100"
      />
      {streaming ? (
        <button
          onClick={onStop}
          className="self-end rounded-xl bg-red-600 px-5 py-2.5 text-sm text-white hover:bg-red-700"
        >
          Стоп
        </button>
      ) : (
        <button
          onClick={submit}
          disabled={disabled || !text.trim()}
          className="self-end rounded-xl bg-blue-600 px-5 py-2.5 text-sm text-white hover:bg-blue-700 disabled:opacity-40"
        >
          Отправить
        </button>
      )}
    </div>
  );
}
