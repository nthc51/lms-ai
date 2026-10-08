"use client";

import { AlertTriangle, Loader2, RefreshCw, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { FilterTabs } from "@/components/admin/filter-tabs";
import { errorMessage } from "@/lib/api/errors";
import { KINDS, type Scope, type StudioItem, type StudioKind, useRequestArtifact, useStudioOverview } from "@/lib/studio/queries";
import { ArtifactViewer } from "./artifact-viewer";

const fmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/**
 * Studio (kiểu NotebookLM): 5 loại tài liệu học AI soạn từ tài liệu của bài / cả khóa. Sinh một lần, cả lớp dùng
 * chung. Đang sinh thì thẻ hiện "AI đang soạn…" và tự cập nhật; trang vẫn học tiếp được.
 */
export function StudioPanel({ courseId, lessonId }: { courseId: string; lessonId: string }) {
  const [whole, setWhole] = React.useState<"lesson" | "course">("lesson");
  const scope: Scope = { courseId, lessonId: whole === "lesson" ? lessonId : null };
  const overview = useStudioOverview(scope);
  const request = useRequestArtifact(scope);
  const [open, setOpen] = React.useState<{ id: string; title: string } | null>(null);
  // kind vừa bấm "Tạo": khi sinh xong thì tự mở (người dùng đang chờ đúng tài liệu đó)
  const waiting = React.useRef<StudioKind | null>(null);

  const items = React.useMemo(() => overview.data?.items ?? [], [overview.data]);
  React.useEffect(() => {
    const kind = waiting.current;
    if (!kind) return;
    const item = items.find((i) => i.kind === kind);
    if (item?.status === "ready" && item.artifact_id) {
      waiting.current = null;
      toast.success(`${KINDS.find((k) => k.kind === kind)?.label} đã sẵn sàng`, {
        action: { label: "Mở", onClick: () => setOpen({ id: item.artifact_id!, title: KINDS.find((k) => k.kind === kind)!.label }) },
      });
    } else if (item?.status === "failed") {
      waiting.current = null;
    }
  }, [items]);

  async function generate(kind: StudioKind, force = false) {
    try {
      const out = await request.mutateAsync({ kind, force });
      const label = KINDS.find((k) => k.kind === kind)!.label;
      if (out.status === "ready") setOpen({ id: out.artifact_id, title: label });
      else waiting.current = kind;
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b p-4">
        <p className="text-sm text-muted-foreground">AI soạn tài liệu học từ tài liệu của giảng viên, có ghi nguồn. Cả lớp dùng chung.</p>
        <FilterTabs
          label="Phạm vi"
          value={whole}
          options={[
            { value: "lesson", label: "Bài này" },
            { value: "course", label: "Cả khóa" },
          ]}
          onChange={setWhole}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {overview.isPending ? (
          <div className="grid grid-cols-2 gap-3" aria-busy="true" aria-label="Đang tải">
            {KINDS.map((k) => (
              <Skeleton key={k.kind} className="h-28" />
            ))}
          </div>
        ) : overview.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(overview.error)}
          </p>
        ) : !overview.data.has_content ? (
          <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            Chưa có tài liệu nào được xử lý xong {whole === "lesson" ? "trong bài này" : "trong khóa"}, nên AI chưa soạn được gì.
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-3">
            {KINDS.map((k) => {
              const item = items.find((i) => i.kind === k.kind)!;
              return (
                <li key={k.kind}>
                  <StudioCard
                    label={k.label}
                    hint={k.hint}
                    icon={k.icon}
                    item={item}
                    busy={request.isPending && request.variables?.kind === k.kind}
                    canRegenerate={overview.data.can_regenerate}
                    onOpen={() => item.artifact_id && setOpen({ id: item.artifact_id, title: k.label })}
                    onGenerate={(force) => generate(k.kind, force)}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <ArtifactViewer
        artifactId={open?.id ?? null}
        title={open?.title ?? ""}
        canEdit={!!overview.data?.can_regenerate}
        lessonId={lessonId}
        onOpenChange={(o) => !o && setOpen(null)}
      />
    </div>
  );
}

function StudioCard({
  label,
  hint,
  icon: Icon,
  item,
  busy,
  canRegenerate,
  onOpen,
  onGenerate,
}: {
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  item: StudioItem;
  busy: boolean;
  canRegenerate: boolean;
  onOpen: () => void;
  onGenerate: (force?: boolean) => void;
}) {
  const ready = !!item.artifact_id;
  return (
    <div className="flex h-full flex-col rounded-lg border bg-surface p-3">
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{label}</h3>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
      </div>
      <div className="mt-auto space-y-2 pt-3">
        {item.status === "generating" ? (
          <p role="status" className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" aria-hidden /> AI đang soạn… (≈30 giây)
          </p>
        ) : item.status === "failed" ? (
          <p role="status" className="flex items-start gap-1.5 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> Lần tạo gần nhất bị lỗi
          </p>
        ) : item.stale ? (
          <p className="text-xs text-muted-foreground">Tài liệu đã đổi sau khi tạo bản này.</p>
        ) : ready && item.created_at ? (
          <p className="text-xs text-muted-foreground">Tạo lúc {fmt.format(new Date(item.created_at))}</p>
        ) : null}
        <div className="flex flex-wrap gap-1.5">
          {ready ? (
            <Button size="sm" onClick={onOpen} aria-label={`Mở ${label}`}>
              Mở
            </Button>
          ) : null}
          {item.status !== "generating" && (!ready || item.stale || item.status === "failed") ? (
            <Button
              size="sm"
              variant={ready ? "outline" : "default"}
              onClick={() => onGenerate(false)}
              loading={busy}
              loadingText="Đang gửi…"
              aria-label={`${ready ? "Tạo bản mới" : item.status === "failed" ? "Thử lại" : "Tạo"} ${label}`}
            >
              <Sparkles /> {ready ? "Tạo bản mới" : item.status === "failed" ? "Thử lại" : "Tạo"}
            </Button>
          ) : null}
          {canRegenerate && ready && !item.stale && item.status !== "generating" ? (
            <Button size="sm" variant="ghost" onClick={() => onGenerate(true)} aria-label={`Sinh lại ${label}`}>
              <RefreshCw /> Sinh lại
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
