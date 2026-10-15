"use client";

import { ArrowRight, Compass, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
import { Pagination } from "@/components/course/course-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import type { components } from "@/lib/api/schema";
import { useAuth } from "@/lib/auth/auth-context";
import { flattenLessons, useCatalog, useCourse, useMyCourses } from "@/lib/queries";
import { useDebounced } from "@/lib/use-debounced";

type CatalogItem = components["schemas"]["CourseCard"];

const minutes = (sec: number | null | undefined) => (sec ? `${Math.max(1, Math.round(sec / 60))} phút` : null);

/** Vài bài đầu của khóa nổi bật (lấy từ trang chi tiết khóa). */
function FirstLessons({ slug }: { slug: string }) {
  const course = useCourse(slug);
  if (course.isPending) return <Skeleton className="h-32 w-full" />;
  if (course.isError) return null;
  const lessons = flattenLessons(course.data).slice(0, 3);
  if (lessons.length === 0) return <p className="text-muted-foreground">Khóa học đang được soạn bài.</p>;
  return (
    <>
      <h3 className="text-[15px] font-semibold text-muted-foreground">Những bài đầu tiên</h3>
      <ol className="flex flex-col">
        {lessons.map((l) => (
          <li key={l.id} className="flex justify-between gap-4 py-2.5 text-base">
            <span className="min-w-0">{l.title}</span>
            {minutes(l.duration_sec) ? <span className="shrink-0 text-sm text-muted-foreground">{minutes(l.duration_sec)}</span> : null}
          </li>
        ))}
      </ol>
    </>
  );
}

/** Khóa mới nhất (đầu danh sách, catalog xếp mới trước) đặt trong một khối màu lớn. */
function FeaturedCourse({ c, enrolled }: { c: CatalogItem; enrolled: boolean }) {
  return (
    <article aria-labelledby={`c-${c.id}`} className="grid bg-field-2 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <h2 id={`c-${c.id}`} className="text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.02] tracking-[-0.04em]">
          {c.title}
        </h2>
        <p className="text-[15px] font-semibold">
          Khóa mới nhất · {c.teacher_name}
          {enrolled ? " · Bạn đang học" : ""}
        </p>
        {c.description ? <p className="line-clamp-4 max-w-[40ch] text-lg leading-snug md:text-xl">{c.description}</p> : null}
        <Button asChild size="lg" className="mt-auto h-14 self-start text-base">
          <Link href={`/courses/${c.slug}`}>
            Xem khóa học <ArrowRight className="size-5" />
          </Link>
        </Button>
      </div>
      <div className="flex flex-col justify-center gap-3 bg-surface p-6 md:p-10">
        <FirstLessons slug={c.slug} />
      </div>
    </article>
  );
}

/** Một dòng trong mục lục khóa học: tên lớn bên trái, mô tả bên phải. */
function CatalogEntry({ c, enrolled }: { c: CatalogItem; enrolled: boolean }) {
  return (
    <li>
      <Link
        href={`/courses/${c.slug}`}
        className="group grid gap-3 bg-surface px-4 py-6 transition-colors duration-150 hover:bg-field-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto] md:gap-8 md:px-6 md:py-7"
      >
        <span className="min-w-0">
          <span className="block text-[clamp(1.375rem,1.1rem+1vw,2rem)] font-extrabold leading-[1.08] tracking-[-0.035em]">{c.title}</span>
          {enrolled ? <span className="mt-2.5 inline-block bg-field-1 px-2 py-0.5 text-[13px] font-semibold">Bạn đang học</span> : null}
        </span>
        <span className="min-w-0">
          {c.description ? <span className="line-clamp-3 block max-w-[52ch] text-base leading-relaxed">{c.description}</span> : null}
          <span className="mt-2 block text-sm font-semibold text-muted-foreground">{c.teacher_name}</span>
        </span>
        <span className="inline-flex items-center gap-2 pt-1 text-[15px] font-semibold text-primary">
          Xem <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" aria-hidden />
        </span>
      </Link>
    </li>
  );
}

export default function ExplorePage() {
  const { user } = useAuth();
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  // đổi từ khóa thì quay về trang 1 (trang gắn với từ khóa đã tìm)
  const [paging, setPaging] = React.useState({ query: "", page: 1 });
  const page = paging.query === query ? paging.page : 1;
  const setPage = (p: number) => setPaging({ query, page: p });
  const catalog = useCatalog(query, page);
  // Học viên: đánh dấu khóa đã đăng ký (chỉ trang đầu danh sách khóa của tôi, đủ cho số khóa một học viên học)
  const my = useMyCourses(1, user?.role === "student");
  const enrolled = new Set((my.data?.items ?? []).map((c) => c.course_id));

  const items = catalog.data?.items ?? [];
  const featured = !query && page === 1 && items.length > 1 ? items[0] : null;
  const rest = featured ? items.slice(1) : items;

  return (
    <>
      <div className="mb-8 grid items-end gap-6 pt-4 md:mb-10 md:pt-8 lg:grid-cols-[minmax(0,1fr)_minmax(260px,380px)]">
        <div>
          <h1 className="text-[clamp(2.25rem,1.3rem+3vw,4.25rem)] font-extrabold leading-[1] tracking-[-0.045em]">Khám phá khóa học</h1>
          <p className="mt-4 max-w-[46ch] text-lg leading-snug text-muted-foreground md:text-xl">
            {catalog.data && !query
              ? `${catalog.data.total} khóa học đang mở. Khóa nào cũng có AI Tutor trả lời theo đúng tài liệu của khóa.`
              : "Khóa nào cũng có AI Tutor trả lời theo đúng tài liệu của khóa."}
          </p>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="catalog-search" className="sr-only">
            Tìm khóa học
          </label>
          <input
            id="catalog-search"
            type="search"
            placeholder="Tìm theo tên, gõ không dấu cũng được"
            className="h-14 w-full bg-surface pl-12 pr-4 text-base outline-2 outline-transparent transition-[outline-color] duration-150 placeholder:text-muted-foreground focus:outline-primary"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      {catalog.isPending ? (
        <CardListSkeleton />
      ) : catalog.isError ? (
        <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={Compass} title={query ? `Không tìm thấy khóa học nào cho “${query}”.` : "Chưa có khóa học nào được xuất bản."} />
      ) : (
        <div aria-busy={catalog.isFetching} className="flex flex-col gap-1.5">
          {featured ? <FeaturedCourse c={featured} enrolled={enrolled.has(featured.id)} /> : null}
          <ul className="flex flex-col gap-1.5">
            {rest.map((c) => (
              <CatalogEntry key={c.id} c={c} enrolled={enrolled.has(c.id)} />
            ))}
          </ul>
          <Pagination page={page} total={catalog.data.total} size={catalog.data.size} onPage={setPage} />
        </div>
      )}
    </>
  );
}
