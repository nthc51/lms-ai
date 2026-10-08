"use client";

import { Library, Search } from "lucide-react";
import * as React from "react";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { CourseTable } from "@/components/admin/course-table";
import { FilterTabs } from "@/components/admin/filter-tabs";
import { Pagination } from "@/components/course/course-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { type CourseFilter, useAdminCourses } from "@/lib/admin-queries";
import { useDebounced } from "@/lib/use-debounced";

type Status = NonNullable<CourseFilter["status"]> | "all";
const OPTIONS: { value: Status; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "published", label: "Đã xuất bản" },
  { value: "draft", label: "Nháp" },
  { value: "hidden", label: "Đã ẩn" },
];

export default function AdminCoursesPage() {
  const [status, setStatus] = React.useState<Status>("all");
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  const [paging, setPaging] = React.useState({ key: "", page: 1 });
  const key = `${status}|${query}`;
  const page = paging.key === key ? paging.page : 1;
  const courses = useAdminCourses({ status: status === "all" ? undefined : status, q: query, page });

  return (
    <>
      <PageHeader title="Khóa học">Toàn bộ khóa của mọi giảng viên. Ẩn khóa vi phạm kèm lý do cho giảng viên.</PageHeader>
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterTabs label="Lọc theo trạng thái" value={status} options={OPTIONS} onChange={setStatus} />
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="course-search" className="sr-only">
            Tìm khóa học
          </label>
          <Input id="course-search" type="search" placeholder="Tìm theo tên khóa hoặc giảng viên…" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {courses.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : courses.isError ? (
        <ErrorState error={courses.error} onRetry={() => courses.refetch()} />
      ) : courses.data.items.length === 0 ? (
        page > 1 ? (
          <EmptyState
            icon={Library}
            title="Trang này không còn khóa nào."
            action={
              <Button variant="outline" onClick={() => setPaging({ key, page: 1 })}>
                Về trang đầu
              </Button>
            }
          />
        ) : (
          <EmptyState icon={Library} title={query ? `Không tìm thấy khóa nào cho “${query}”.` : "Không có khóa học nào."} />
        )
      ) : (
        <div aria-busy={courses.isFetching}>
          <CourseTable courses={courses.data.items} />
          <Pagination page={page} total={courses.data.total} size={courses.data.size} onPage={(p) => setPaging({ key, page: p })} />
        </div>
      )}
    </>
  );
}
