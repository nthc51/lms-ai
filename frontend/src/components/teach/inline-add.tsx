"use client";

import { Plus } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Nút "Thêm …" mở ô nhập tên ngay tại chỗ, con trỏ tự vào ô (design-system §5.3). */
export function InlineAdd({ label, placeholder, onAdd }: { label: string; placeholder: string; onAdd: (title: string) => Promise<unknown> }) {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState("");
  const [pending, setPending] = React.useState(false);

  if (!editing)
    return (
      <Button variant="outline" size="sm" className="h-10 md:h-8" onClick={() => setEditing(true)}>
        <Plus /> {label}
      </Button>
    );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setPending(true);
    try {
      await onAdd(value.trim());
      setValue("");
      setEditing(false);
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex gap-2">
      <Input
        autoFocus
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        maxLength={200}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
      />
      <Button type="submit" variant="outline" loading={pending} loadingText="Đang thêm…">
        Thêm
      </Button>
      <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
        Hủy
      </Button>
    </form>
  );
}
