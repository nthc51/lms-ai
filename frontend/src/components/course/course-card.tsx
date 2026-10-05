import Link from "next/link";
import { Progress } from "@/components/ui/misc";

export function CourseCard({
  href,
  title,
  subtitle,
  description,
  progress,
}: {
  href: string;
  title: string;
  subtitle?: string;
  description?: string;
  progress?: { pct: number; done: number; total: number };
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-lg border bg-surface p-4 transition-colors duration-150 hover:border-primary/50"
    >
      <h2 className="font-semibold group-hover:text-primary">{title}</h2>
      {subtitle ? <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p> : null}
      {description ? <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{description}</p> : null}
      {progress ? (
        <div className="mt-auto pt-4">
          <Progress value={progress.pct} label={`Tiến độ ${title}`} />
          <p className="mt-1.5 text-xs text-muted-foreground">
            {progress.done}/{progress.total} bài · {progress.pct}%
          </p>
        </div>
      ) : null}
    </Link>
  );
}

export function Pagination({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Phân trang" className="mt-6 flex items-center justify-center gap-3 text-sm">
      <button className="h-10 rounded-md border px-3 disabled:opacity-50" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Trang trước
      </button>
      <span aria-current="page">
        {page}/{pages}
      </span>
      <button className="h-10 rounded-md border px-3 disabled:opacity-50" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Trang sau
      </button>
    </nav>
  );
}
