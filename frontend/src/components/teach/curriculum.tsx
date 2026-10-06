"use client";

import { closestCenter, DndContext, type DragEndEvent, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowDown, ArrowUp, FileText, GripVertical, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { errorMessage } from "@/lib/api/errors";
import type { CourseDetail } from "@/lib/queries";
import { moveItem, sortedSections, useCourseMutations } from "@/lib/teach-queries";
import { InlineAdd } from "./inline-add";

type Sections = ReturnType<typeof sortedSections>;
type Mut = ReturnType<typeof useCourseMutations>;

/**
 * Mục lục chương/bài của trình soạn. Sắp xếp bằng kéo thả (chuột, bàn phím: Space rồi ↑↓)
 * hoặc nút ↑↓ (điện thoại). Mọi thay đổi thứ tự lưu ngay, lỗi thì trả về thứ tự cũ.
 */
export function Curriculum({ course, mut }: { course: CourseDetail; mut: Mut }) {
  const sections = sortedSections(course);
  const [pendingDelete, setPendingDelete] = React.useState<
    { kind: "section"; id: string; title: string; lessons: number } | { kind: "lesson"; id: string; title: string } | null
  >(null);

  const reorder = (next: Sections) =>
    mut.reorder.mutate(next, { onError: (err) => toast.error(`Không lưu được thứ tự: ${errorMessage(err)}`) });

  const moveSection = (from: number, to: number) => reorder(moveItem(sections, from, to));
  const moveLesson = (si: number, from: number, to: number) =>
    reorder(sections.map((s, i) => (i === si ? { ...s, lessons: moveItem(s.lessons, from, to) } : s)));

  const run = async (p: Promise<unknown>, ok: string) => {
    try {
      await p;
      toast.success(ok);
    } catch (err) {
      toast.error(errorMessage(err));
      throw err;
    }
  };

  return (
    <section aria-labelledby="curriculum-title">
      <div className="mb-3 flex items-center justify-between">
        <h2 id="curriculum-title" className="text-lg font-semibold">
          Nội dung khóa học
        </h2>
      </div>
      {sections.length === 0 ? (
        <p className="mb-3 text-sm text-muted-foreground">Bắt đầu bằng việc thêm chương đầu tiên.</p>
      ) : null}
      <ol className="space-y-4">
        {sections.map((s, si) => (
          <SectionCard
            key={s.id}
            course={course}
            section={s}
            index={si}
            count={sections.length}
            mut={mut}
            onMove={(to) => moveSection(si, to)}
            onMoveLesson={(from, to) => moveLesson(si, from, to)}
            onDelete={() => setPendingDelete({ kind: "section", id: s.id, title: s.title, lessons: s.lessons.length })}
            onDeleteLesson={(l) => setPendingDelete({ kind: "lesson", id: l.id, title: l.title })}
          />
        ))}
      </ol>
      <div className="mt-4">
        <InlineAdd label="Thêm chương" placeholder="Tên chương mới" onAdd={(t) => run(mut.addSection.mutateAsync(t), "Đã thêm chương")} />
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        destructive
        title={pendingDelete?.kind === "section" ? `Xóa chương “${pendingDelete.title}”?` : `Xóa bài “${pendingDelete?.title}”?`}
        description={
          pendingDelete?.kind === "section"
            ? `Chương này có ${pendingDelete.lessons} bài. Toàn bộ bài, tài liệu và tiến độ học của các bài đó sẽ bị xóa và không khôi phục được.`
            : "Nội dung, video, tài liệu PDF và tiến độ học của bài sẽ bị xóa và không khôi phục được."
        }
        confirmLabel={pendingDelete?.kind === "section" ? "Xóa chương" : "Xóa bài"}
        pendingLabel="Đang xóa…"
        onConfirm={() =>
          pendingDelete!.kind === "section"
            ? run(mut.deleteSection.mutateAsync(pendingDelete!.id), "Đã xóa chương")
            : run(mut.deleteLesson.mutateAsync(pendingDelete!.id), "Đã xóa bài")
        }
      />
    </section>
  );
}

function SectionCard({
  course,
  section,
  index,
  count,
  mut,
  onMove,
  onMoveLesson,
  onDelete,
  onDeleteLesson,
}: {
  course: CourseDetail;
  section: Sections[number];
  index: number;
  count: number;
  mut: Mut;
  onMove: (to: number) => void;
  onMoveLesson: (from: number, to: number) => void;
  onDelete: () => void;
  onDeleteLesson: (l: { id: string; title: string }) => void;
}) {
  const [renaming, setRenaming] = React.useState(false);
  const [title, setTitle] = React.useState(section.title);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function onDragEnd(e: DragEndEvent) {
    if (!e.over || e.active.id === e.over.id) return;
    const from = section.lessons.findIndex((l) => l.id === e.active.id);
    const to = section.lessons.findIndex((l) => l.id === e.over!.id);
    onMoveLesson(from, to);
  }

  async function saveTitle(e: React.FormEvent) {
    e.preventDefault();
    try {
      await mut.renameSection.mutateAsync({ id: section.id, title: title.trim() });
      setRenaming(false);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <li className="rounded-lg border bg-surface">
      <div className="flex items-center gap-1 border-b px-3 py-2">
        {renaming ? (
          <form onSubmit={saveTitle} className="flex flex-1 gap-2">
            <Input aria-label="Tên chương" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
            <Button type="submit" variant="outline" loading={mut.renameSection.isPending} loadingText="Đang lưu…">
              Lưu
            </Button>
          </form>
        ) : (
          <h3 className="flex-1 font-medium">
            Chương {index + 1}. {section.title}
          </h3>
        )}
        <Button variant="ghost" size="icon" aria-label={`Đưa chương ${section.title} lên`} disabled={index === 0} onClick={() => onMove(index - 1)}>
          <ArrowUp />
        </Button>
        <Button variant="ghost" size="icon" aria-label={`Đưa chương ${section.title} xuống`} disabled={index === count - 1} onClick={() => onMove(index + 1)}>
          <ArrowDown />
        </Button>
        <Menu>
          <MenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={`Thao tác với chương ${section.title}`}>
              <MoreHorizontal />
            </Button>
          </MenuTrigger>
          <MenuContent>
            <MenuItem onSelect={() => setRenaming(true)}>
              <Pencil /> Đổi tên
            </MenuItem>
            <MenuSeparator />
            <MenuItem destructive onSelect={onDelete}>
              <Trash2 /> Xóa chương
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={section.lessons.map((l) => l.id)} strategy={verticalListSortingStrategy}>
          <ul>
            {section.lessons.map((l, li) => (
              <LessonRow
                key={l.id}
                href={`/teach/${course.slug}/lessons/${l.id}`}
                lesson={l}
                first={li === 0}
                last={li === section.lessons.length - 1}
                onUp={() => onMoveLesson(li, li - 1)}
                onDown={() => onMoveLesson(li, li + 1)}
                onDelete={() => onDeleteLesson(l)}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>

      <div className="px-3 py-3">
        <InlineAdd
          label="Thêm bài"
          placeholder="Tên bài mới"
          onAdd={async (t) => {
            try {
              await mut.addLesson.mutateAsync({ sectionId: section.id, title: t });
              toast.success("Đã thêm bài");
            } catch (err) {
              toast.error(errorMessage(err));
              throw err;
            }
          }}
        />
      </div>
    </li>
  );
}

function LessonRow({
  href,
  lesson,
  first,
  last,
  onUp,
  onDown,
  onDelete,
}: {
  href: string;
  lesson: { id: string; title: string };
  first: boolean;
  last: boolean;
  onUp: () => void;
  onDown: () => void;
  onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: lesson.id });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-1 border-b px-2 py-1 last:border-b-0 ${isDragging ? "relative z-10 bg-muted shadow" : ""}`}
    >
      <button
        ref={setActivatorNodeRef}
        type="button"
        aria-label={`Kéo để sắp xếp bài ${lesson.title}`}
        className="hidden size-10 cursor-grab items-center justify-center rounded text-muted-foreground hover:bg-muted md:inline-flex"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>
      <Link href={href} className="flex min-h-10 flex-1 items-center gap-2 rounded px-2 text-sm hover:text-primary hover:underline">
        <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        {lesson.title}
      </Link>
      <Button variant="ghost" size="icon" aria-label={`Đưa bài ${lesson.title} lên`} disabled={first} onClick={onUp}>
        <ArrowUp />
      </Button>
      <Button variant="ghost" size="icon" aria-label={`Đưa bài ${lesson.title} xuống`} disabled={last} onClick={onDown}>
        <ArrowDown />
      </Button>
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`Thao tác với bài ${lesson.title}`}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          <MenuItem destructive onSelect={onDelete}>
            <Trash2 /> Xóa bài
          </MenuItem>
        </MenuContent>
      </Menu>
    </li>
  );
}
