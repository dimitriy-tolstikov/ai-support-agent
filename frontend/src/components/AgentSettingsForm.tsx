// демонстрирует: форму настроек агента на React Hook Form + Zod-валидация + TanStack Query mutation
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Conversation } from "../api/client";
import { useToast } from "./Toaster";

const SettingsSchema = z.object({
  system_prompt: z
    .string()
    .max(2000, "Не более 2000 символов")
    .nullable()
    .transform((v) => (v?.trim() ? v : null)),
  temperature: z.coerce
    .number({ invalid_type_error: "Введите число" })
    .min(0, "От 0 до 2")
    .max(2, "От 0 до 2"),
});
type SettingsFormValues = z.input<typeof SettingsSchema>;

export default function AgentSettingsForm({
  conversation,
  onSaved,
}: {
  conversation: Conversation;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SettingsFormValues>({
    resolver: zodResolver(SettingsSchema),
    defaultValues: {
      system_prompt: conversation.agent_settings.system_prompt ?? "",
      temperature: conversation.agent_settings.temperature ?? 0.7,
    },
  });

  const mut = useMutation({
    mutationFn: (values: { system_prompt: string | null; temperature: number }) =>
      api.putSettings(conversation.id, values),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      toast("Настройки сохранены", "info");
      onSaved();
    },
    onError: (e) => toast(e.message),
  });

  return (
    <form
      onSubmit={handleSubmit((v) => mut.mutate(SettingsSchema.parse(v)))}
      className="space-y-3 rounded-xl border bg-white p-4 shadow-sm"
    >
      <div>
        <label className="mb-1 block text-sm font-medium">Системный промпт</label>
        <textarea
          {...register("system_prompt")}
          rows={3}
          placeholder="Пусто — используется промпт по умолчанию"
          className="w-full rounded-lg border p-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        {errors.system_prompt && (
          <p className="mt-1 text-xs text-red-600">{errors.system_prompt.message}</p>
        )}
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium">Температура (0–2)</label>
        <input
          type="number"
          step="0.1"
          {...register("temperature")}
          className="w-32 rounded-lg border p-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        {errors.temperature && (
          <p className="mt-1 text-xs text-red-600">{errors.temperature.message}</p>
        )}
      </div>
      <button
        type="submit"
        disabled={mut.isPending}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {mut.isPending ? "Сохраняю…" : "Сохранить"}
      </button>
    </form>
  );
}
