"use client";

import { BookOpen, User } from "lucide-react";
import { type AdminAction, actionLabel, fmtDateTime } from "@/lib/admin-queries";

export function ActionLog({ items }: { items: AdminAction[] }) {
  if (items.length === 0) return <p className="rounded-lg border border-dashed p-6 text-center text-muted-foreground">Chưa có thao tác quản trị nào.</p>;
  return (
    <ol className="divide-y rounded-lg border bg-surface">
      {items.map((a) => {
        const Icon = a.target_type === "course" ? BookOpen : User;
        return (
          <li key={a.id} className="flex gap-3 px-4 py-3 text-sm">
            <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <p>
                <span className="font-medium">{actionLabel(a.action)}</span> · <span className="break-all">{a.target_label}</span>
              </p>
              {a.note ? <p className="text-muted-foreground">Lý do: {a.note}</p> : null}
              <p className="text-xs text-muted-foreground">
                {a.admin_name ?? "Quản trị viên đã xóa"} · <time dateTime={a.created_at}>{fmtDateTime(a.created_at)}</time>
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
