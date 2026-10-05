"use client";

import { Compass, Search } from "lucide-react";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { CourseCard, Pagination } from "@/components/course/course-card";
import { Input } from "@/components/ui/input";
import { useCatalog } from "@/lib/queries";
import { useDebounced } from "@/lib/use-debounced";

export default function ExplorePage() {
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  // đổi từ khóa thì quay về trang 1 (trang gắn với từ khóa đã tìm)
  const [paging, setPaging] = React.useState({ query: "", page: 1 });
  const page = paging.query === query ? paging.page : 1;
  const setPage = (p: number) => setPaging({ query, page: p });
  const catalog = useCatalog(query, page);

  return (
    <>
      <PageHeader title="Khám phá khóa học" />
      <div className="relative mb-6 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <label htmlFor="catalog-search" className="sr-only">
          Tìm khóa học
        </label>
        <Input
          id="catalog-search"
          type="search"
          placeholder="Tìm theo tên khóa học (có thể gõ không dấu)…"
          className="pl-9"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {catalog.isPending ? (
        <CardListSkeleton />
      ) : catalog.isError ? (
        <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} />
      ) : catalog.data.items.length === 0 ? (
        <EmptyState icon={Compass} title={query ? `Không tìm thấy khóa học nào cho “${query}”.` : "Chưa có khóa học nào được xuất bản."} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy={catalog.isFetching}>
            {catalog.data.items.map((c) => (
              <CourseCard key={c.id} href={`/courses/${c.slug}`} title={c.title} subtitle={c.teacher_name} description={c.description} />
            ))}
          </div>
          <Pagination page={page} total={catalog.data.total} size={catalog.data.size} onPage={setPage} />
        </>
      )}
    </>
  );
}
