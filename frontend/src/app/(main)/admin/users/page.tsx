"use client";

import { Search, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { FilterTabs } from "@/components/admin/filter-tabs";
import { UserTable } from "@/components/admin/user-table";
import { Pagination } from "@/components/course/course-card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { type UserFilter, useAdminUsers } from "@/lib/admin-queries";
import { useDebounced } from "@/lib/use-debounced";

const TABS = [
  { value: "pending", label: "Chờ duyệt", filter: { role: "teacher", status: "pending" } },
  { value: "teacher", label: "Giảng viên", filter: { role: "teacher" } },
  { value: "student", label: "Học viên", filter: { role: "student" } },
  { value: "locked", label: "Đã khóa", filter: { status: "locked" } },
  { value: "all", label: "Tất cả", filter: {} },
] as const satisfies readonly { value: string; label: string; filter: Omit<UserFilter, "page"> }[];
type Tab = (typeof TABS)[number]["value"];
const isTab = (v: string | null): v is Tab => TABS.some((t) => t.value === v);

export default function AdminUsersPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <UsersView />
    </React.Suspense>
  );
}

function UsersView() {
  const router = useRouter();
  const params = useSearchParams();
  const tabParam = params.get("tab");
  const tab: Tab = isTab(tabParam) ? tabParam : "pending";
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  // đổi tab hoặc từ khóa thì về trang 1
  const [paging, setPaging] = React.useState({ key: "", page: 1 });
  const key = `${tab}|${query}`;
  const page = paging.key === key ? paging.page : 1;
  const filter = TABS.find((t) => t.value === tab)!.filter;
  const users = useAdminUsers({ ...filter, q: query, page });

  return (
    <>
      <PageHeader title="Người dùng">Duyệt giảng viên mới, tìm kiếm và khóa tài khoản vi phạm.</PageHeader>
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterTabs label="Lọc người dùng" value={tab} options={TABS.map(({ value, label }) => ({ value, label }))} onChange={(v) => router.replace(`/admin/users?tab=${v}`)} />
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="user-search" className="sr-only">
            Tìm người dùng
          </label>
          <Input id="user-search" type="search" placeholder="Tìm theo tên hoặc email…" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {users.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => users.refetch()} />
      ) : users.data.items.length === 0 ? (
        <EmptyState icon={Users} title={query ? `Không tìm thấy ai cho “${query}”.` : tab === "pending" ? "Không có giảng viên nào đang chờ duyệt." : "Chưa có người dùng nào."} />
      ) : (
        <div aria-busy={users.isFetching}>
          <UserTable users={users.data.items} caption={`Danh sách người dùng: ${TABS.find((t) => t.value === tab)!.label}`} />
          <Pagination page={page} total={users.data.total} size={users.data.size} onPage={(p) => setPaging({ key, page: p })} />
        </div>
      )}
    </>
  );
}
