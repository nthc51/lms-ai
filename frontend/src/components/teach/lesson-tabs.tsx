"use client";

import { ClipboardCheck, FileText, ListChecks } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

/** Thanh chuyển giữa 3 phần soạn một bài: Nội dung | Câu hỏi | Quiz (mỗi phần một trang riêng). */
export function LessonTabs({ slug, lessonId }: { slug: string; lessonId: string }) {
  const pathname = usePathname();
  const base = `/teach/${slug}/lessons/${lessonId}`;
  const tabs = [
    { href: base, label: "Nội dung", icon: FileText },
    { href: `${base}/questions`, label: "Câu hỏi", icon: ListChecks },
    { href: `${base}/quizzes`, label: "Quiz", icon: ClipboardCheck },
  ];
  return (
    <nav aria-label="Phần soạn bài" className="mb-6 flex gap-1 overflow-x-auto border-b">
      {tabs.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px flex h-11 shrink-0 items-center gap-2 border-b-2 border-transparent px-3 text-sm transition-colors duration-150 hover:text-primary",
              active ? "border-primary font-medium text-primary" : "text-muted-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
