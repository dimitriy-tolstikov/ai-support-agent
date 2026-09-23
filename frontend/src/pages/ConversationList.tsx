// демонстрирует: список диалогов на TanStack Query — skeleton при загрузке, mutation создания, ошибки
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useToast } from "../components/Toaster";

export default function ConversationList() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["conversations"],
    queryFn: api.listConversations,
  });

  const createMut = useMutation({
    mutationFn: () => api.createConversation("Новый диалог"),
    onSuccess: (conv) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      navigate(`/c/${conv.id}`);
    },
    onError: (e) => toast(`Не удалось создать диалог: ${e.message}`),
  });

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Диалоги</h2>
        <button
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {createMut.isPending ? "Создаю…" : "Новый диалог"}
        </button>
      </div>

      {isLoading && (
        <ul className="space-y-2">
          {[1, 2, 3].map((i) => (
            <li key={i} className="h-16 animate-pulse rounded-xl bg-slate-200" />
          ))}
        </ul>
      )}
      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Ошибка загрузки: {error.message}
        </div>
      )}

      <ul className="space-y-2">
        {data?.map((c) => (
          <li key={c.id}>
            <Link
              to={`/c/${c.id}`}
              className="flex items-center justify-between rounded-xl bg-white p-4 shadow-sm hover:shadow"
            >
              <div>
                <div className="font-medium">{c.title}</div>
                <div className="text-xs text-slate-500">
                  {new Date(c.updated_at).toLocaleString("ru-RU")}
                </div>
              </div>
              <span
                className={`rounded-full px-2 py-1 text-xs ${
                  c.status === "open" ? "bg-green-100 text-green-700" : "bg-slate-200 text-slate-600"
                }`}
              >
                {c.status === "open" ? "открыт" : "закрыт"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {data?.length === 0 && <p className="text-sm text-slate-500">Диалогов пока нет.</p>}
    </div>
  );
}
