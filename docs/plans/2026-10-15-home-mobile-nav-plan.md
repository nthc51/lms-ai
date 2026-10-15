# Trang chủ học viên và thanh điều hướng điện thoại: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** khi soát ảnh chụp sau `2026-10-15-ui-profile-plan.md` thấy ba chỗ chưa ổn:

1. Học viên chưa có khóa nào vẫn thấy link "Xem tất cả khóa của tôi" dẫn tới trang trống.
2. Thanh dưới trên điện thoại còn mục "Tài khoản", trùng với nút chữ cái ở góc trên.
3. Trang chủ học viên chưa có lối vào học tiếp nổi bật. Muốn học tiếp phải tìm đúng thẻ khóa học trong danh sách.

**Mục tiêu:**

- **Link "Xem tất cả N khóa của tôi":** chỉ hiện khi còn khóa chưa hiện trên trang chủ (tổng nhiều hơn 3).
- **Thẻ "Học tiếp" ở đầu trang chủ học viên:**
  - Chọn khóa chưa hoàn thành đầu tiên mà máy này còn nhớ bài đang học (dùng `lastLesson` sẵn có).
  - Thẻ có tên khóa, thanh tiến độ, nút lớn "Học tiếp" vào thẳng bài đó.
  - Chưa học bài nào trên máy này thì không hiện thẻ.
- **Thanh dưới điện thoại:** tối đa 3 mục. Bỏ mục "Tài khoản" vì đã có menu góc trên; khách thì thấy nút "Đăng nhập" ở góc trên.

**Không đổi:** backend, API, trang `/my`. Thanh chọn chế độ màu ở trang học bài vẫn giữ trên thanh trên, vì đọc bài hay cần đổi nhanh.

**Thứ tự làm:** **sau** `2026-10-15-ui-profile-plan.md` (diff tạo trên kết quả của plan đó).

**Mã trong plan đã được chạy thử:** `tsc`, `eslint` sạch.

- Unit test: **168 pass** (164 + 4 mới).
- E2E cả bộ: **97 pass + 1 bỏ qua có chủ ý** (95 + 2 lượt mới ở 375px và 1280px, có kiểm axe).
- Đã chụp màn hình trang chủ học viên ở 375px và 1280px để soát.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Commit **không** thêm dòng `Co-Authored-By` hay `Claude-Session`.

---

## Task 1: Thẻ Học tiếp, link Xem tất cả, thanh dưới 3 mục

**Files:**
- Modify: `frontend/src/components/course/my-course-list.tsx`, `frontend/src/app/(main)/page.tsx`
- Create: `frontend/src/components/course/my-course-list.test.tsx`
- Modify: `frontend/src/components/app/app-shell.tsx`, `nav-items.ts`, `nav-items.test.ts`
- Create: `frontend/e2e/home-student.spec.ts`
- Modify: `docs/design/design-system.md`

- [ ] **Bước 1: Test (sẽ fail)**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { lastLesson } from "@/lib/study/storage";
import { api as url, server } from "@/test/msw";
import { MyCourseList, ResumeCard } from "./my-course-list";

const course = (n: number, over: Record<string, unknown> = {}) => ({
  course_id: `c${n}`,
  title: `Khóa ${n}`,
  slug: `khoa-${n}`,
  enrolled_at: "2026-09-02T00:00:00Z",
  completed_at: null,
  total_lessons: 10,
  done_lessons: 4,
  progress_pct: 40,
  ...over,
});

function serve(items: ReturnType<typeof course>[], total = items.length) {
  server.use(http.get(url("/me/courses"), () => HttpResponse.json({ items, total, page: 1, size: 20 })));
}

function wrap(ui: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe("MyCourseList", () => {
  it("không có khóa: chỉ ô trống mời khám phá, không có liên kết Xem tất cả", async () => {
    serve([]);
    wrap(<MyCourseList limit={3} moreHref="/my" />);
    expect(await screen.findByText("Bạn chưa đăng ký khóa học nào.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Xem tất cả/ })).not.toBeInTheDocument();
  });

  it("chỉ hiện Xem tất cả khi còn khóa chưa hiện", async () => {
    serve([course(1), course(2), course(3), course(4)]);
    const { unmount } = wrap(<MyCourseList limit={3} moreHref="/my" />);
    expect(await screen.findByRole("link", { name: /Xem tất cả 4 khóa của tôi/ })).toHaveAttribute("href", "/my");
    expect(screen.getAllByRole("link", { name: /Khóa \d/ })).toHaveLength(3);
    unmount();
    serve([course(1), course(2)]);
    wrap(<MyCourseList limit={3} moreHref="/my" />);
    expect(await screen.findByRole("link", { name: /Khóa 2/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Xem tất cả/ })).not.toBeInTheDocument();
  });
});

describe("ResumeCard", () => {
  it("chọn khóa chưa xong đầu tiên mà máy này nhớ bài đang học, vào thẳng bài đó", async () => {
    lastLesson.set("c1", "l-xong"); // khóa 1 đã hoàn thành: bỏ qua
    lastLesson.set("c3", "l-7");
    serve([course(1, { completed_at: "2026-10-01T00:00:00Z" }), course(2), course(3)]);
    wrap(<ResumeCard />);
    expect(await screen.findByRole("heading", { name: "Khóa 3" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Học tiếp/ })).toHaveAttribute("href", "/learn/khoa-3/l-7");
    expect(screen.getByText("4/10 bài · 40%")).toBeInTheDocument();
  });

  it("chưa học bài nào trên máy này thì không hiện", async () => {
    serve([course(1)]);
    const { container } = wrap(<ResumeCard />);
    await new Promise((r) => setTimeout(r, 50));
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Bước 2: Danh sách khóa và thẻ Học tiếp.** `ResumeCard` đọc `localStorage` nên chỉ vẽ sau khi đã mount (`useMounted`). Thẻ dùng chung truy vấn `/me/courses` với danh sách khóa (cùng query key), nên không gọi API thêm lần nào.

```diff
--- a/frontend/src/components/course/my-course-list.tsx
+++ b/frontend/src/components/course/my-course-list.tsx
@@ -1,20 +1,59 @@
 "use client";
 
-import { BookMarked } from "lucide-react";
+import { ArrowRight, BookMarked, PlayCircle } from "lucide-react";
 import Link from "next/link";
 import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
 import { CourseCard } from "@/components/course/course-card";
 import { Button } from "@/components/ui/button";
+import { Progress } from "@/components/ui/misc";
 import { useMyCourses } from "@/lib/queries";
 import { lastLesson } from "@/lib/study/storage";
+import { useMounted } from "@/lib/use-mounted";
 
 /** Có bài mở gần nhất trên máy này → vào thẳng bài đó; không thì mở trang khóa. */
-function resumeHref(courseId: string, slug: string) {
+export function resumeHref(courseId: string, slug: string) {
   const last = lastLesson.get(courseId);
   return last ? `/learn/${slug}/${last}` : `/courses/${slug}`;
 }
 
-export function MyCourseList({ limit }: { limit?: number }) {
+/**
+ * Thẻ "Học tiếp" ở đầu trang chủ học viên: khóa chưa xong đầu tiên (theo thứ tự danh sách) mà máy này
+ * còn nhớ bài đang học, bấm một lần là vào đúng bài. Chưa học bài nào trên máy này thì không hiện.
+ */
+export function ResumeCard() {
+  const my = useMyCourses();
+  const mounted = useMounted(); // bài gần nhất nằm trong localStorage, chỉ đọc được trên trình duyệt
+  if (!mounted || !my.data) return null;
+  const course = my.data.items.find((c) => !c.completed_at && lastLesson.get(c.course_id));
+  if (!course) return null;
+  return (
+    <section
+      aria-labelledby="resume-title"
+      className="mb-8 flex flex-col gap-4 rounded-lg border bg-surface p-5 sm:flex-row sm:items-center sm:justify-between"
+    >
+      <div className="min-w-0 flex-1">
+        <p className="text-sm text-muted-foreground">Khóa bạn đang học</p>
+        <h2 id="resume-title" className="mt-0.5 truncate text-lg font-semibold">
+          {course.title}
+        </h2>
+        <div className="mt-3 max-w-sm">
+          <Progress value={course.progress_pct} label={`Tiến độ ${course.title}`} />
+          <p className="mt-1.5 text-xs text-muted-foreground">
+            {course.done_lessons}/{course.total_lessons} bài · {course.progress_pct}%
+          </p>
+        </div>
+      </div>
+      <Button asChild size="lg" className="shrink-0">
+        <Link href={resumeHref(course.course_id, course.slug)}>
+          <PlayCircle /> Học tiếp
+        </Link>
+      </Button>
+    </section>
+  );
+}
+
+/** `moreHref`: hiện liên kết xem tất cả, chỉ khi còn khóa chưa hiện (tổng nhiều hơn `limit`). */
+export function MyCourseList({ limit, moreHref }: { limit?: number; moreHref?: string }) {
   const my = useMyCourses();
   if (my.isPending) return <CardListSkeleton count={limit ?? 3} />;
   if (my.isError) return <ErrorState error={my.error} onRetry={() => my.refetch()} />;
@@ -32,16 +71,25 @@
     );
   const items = limit ? my.data.items.slice(0, limit) : my.data.items;
   return (
-    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
-      {items.map((c) => (
-        <CourseCard
-          key={c.course_id}
-          href={resumeHref(c.course_id, c.slug)}
-          title={c.title}
-          subtitle={c.completed_at ? "Đã hoàn thành" : undefined}
-          progress={{ pct: c.progress_pct, done: c.done_lessons, total: c.total_lessons }}
-        />
-      ))}
-    </div>
+    <>
+      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
+        {items.map((c) => (
+          <CourseCard
+            key={c.course_id}
+            href={resumeHref(c.course_id, c.slug)}
+            title={c.title}
+            subtitle={c.completed_at ? "Đã hoàn thành" : undefined}
+            progress={{ pct: c.progress_pct, done: c.done_lessons, total: c.total_lessons }}
+          />
+        ))}
+      </div>
+      {moreHref && my.data.total > items.length ? (
+        <Button asChild variant="link" className="mt-4">
+          <Link href={moreHref}>
+            Xem tất cả {my.data.total} khóa của tôi <ArrowRight />
+          </Link>
+        </Button>
+      ) : null}
+    </>
   );
 }
```

```diff
--- a/frontend/src/app/(main)/page.tsx
+++ b/frontend/src/app/(main)/page.tsx
@@ -1,12 +1,12 @@
 "use client";
 
-import { ArrowRight, Clock, XCircle } from "lucide-react";
+import { Clock, XCircle } from "lucide-react";
 import Link from "next/link";
 import { useRouter } from "next/navigation";
 import * as React from "react";
 import { toast } from "sonner";
 import { PageHeader } from "@/components/app/states";
-import { MyCourseList } from "@/components/course/my-course-list";
+import { MyCourseList, ResumeCard } from "@/components/course/my-course-list";
 import { Landing } from "@/components/landing/landing";
 import { Button } from "@/components/ui/button";
 import { Skeleton } from "@/components/ui/misc";
@@ -82,12 +82,8 @@
       <TeacherReviewNotice user={user} />
       {user.role === "student" ? (
         <>
-          <MyCourseList limit={3} />
-          <Button asChild variant="link" className="mt-4">
-            <Link href="/my">
-              Xem tất cả khóa của tôi <ArrowRight />
-            </Link>
-          </Button>
+          <ResumeCard />
+          <MyCourseList limit={3} moreHref="/my" />
         </>
       ) : (
         <Button asChild>
```

- [ ] **Bước 3: Thanh dưới điện thoại 3 mục**

```diff
--- a/frontend/src/components/app/app-shell.tsx
+++ b/frontend/src/components/app/app-shell.tsx
@@ -1,6 +1,5 @@
 "use client";
 
-import { User as UserIcon } from "lucide-react";
 import Link from "next/link";
 import { usePathname } from "next/navigation";
 import * as React from "react";
@@ -11,7 +10,7 @@
 
 /**
  * Khung chung: thanh bên 240px (≥1024px), thu gọn icon 64px (768–1023px),
- * thanh dưới tối đa 4 mục (<768px). Góc trên luôn có menu tài khoản (hồ sơ, ghi chú, chế độ màu, đăng xuất).
+ * thanh dưới tối đa 3 mục (<768px; tài khoản nằm ở menu góc trên). Góc trên luôn có menu tài khoản (hồ sơ, ghi chú, chế độ màu, đăng xuất).
  * Trang bài học và quiz không dùng khung này nhưng có cùng menu tài khoản ở thanh trên.
  */
 export function AppShell({ children }: { children: React.ReactNode }) {
@@ -67,7 +66,7 @@
       <nav
         aria-label="Điều hướng chính"
         className="fixed inset-x-0 bottom-0 z-30 grid h-16 border-t bg-surface md:hidden"
-        style={{ gridTemplateColumns: `repeat(${items.length + 1}, minmax(0, 1fr))` }}
+        style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
       >
         {items.map(({ href, label, icon: Icon }) => (
           <Link
@@ -83,17 +82,6 @@
             {label}
           </Link>
         ))}
-        <Link
-          href={user ? "/account" : "/login"}
-          aria-current={isActive(pathname, "/account") ? "page" : undefined}
-          className={cn(
-            "flex flex-col items-center justify-center gap-0.5 text-xs",
-            isActive(pathname, "/account") ? "text-primary" : "text-muted-foreground",
-          )}
-        >
-          <UserIcon className="size-5" aria-hidden />
-          {user ? "Tài khoản" : "Đăng nhập"}
-        </Link>
       </nav>
     </div>
   );
```

```diff
--- a/frontend/src/components/app/nav-items.ts
+++ b/frontend/src/components/app/nav-items.ts
@@ -3,7 +3,7 @@
 
 export type NavItem = { href: string; label: string; icon: LucideIcon };
 
-/** Mục điều hướng theo vai trò (design-system §7.1). Điện thoại hiển thị tối đa 4 mục. */
+/** Mục điều hướng theo vai trò (design-system §7.1). Thanh dưới điện thoại hiển thị tối đa 3 mục. */
 export function navItems(user: User | null): NavItem[] {
   const base: NavItem[] = [
     { href: "/", label: "Trang chủ", icon: Home },
```

```diff
--- a/frontend/src/components/app/nav-items.test.ts
+++ b/frontend/src/components/app/nav-items.test.ts
@@ -16,7 +16,7 @@
     expect(navItems(user("teacher", "approved")).map((i) => i.href)).toEqual(["/teach", "/explore"]);
     expect(navItems(user("teacher", "pending")).map((i) => i.href)).toEqual(["/explore"]);
   });
-  it("tối đa 3 mục (thanh dưới thêm mục Tài khoản = 4)", () => {
+  it("tối đa 3 mục (tài khoản nằm ở menu góc trên, không chiếm chỗ thanh dưới)", () => {
     for (const r of ["student", "teacher", "admin"] as const) expect(navItems(user(r, "approved")).length).toBeLessThanOrEqual(3);
   });
   it("isActive khớp tiền tố nhưng / chỉ khớp chính nó", () => {
```

- [ ] **Bước 4: E2E**

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, L2, mockApi } from "./mock-api";

test("trang chủ học viên: thẻ Học tiếp vào thẳng bài đang học, thanh dưới không còn mục Tài khoản", async ({ page, isMobile }) => {
  await page.addInitScript(
    ([courseId, lessonId]) => localStorage.setItem(`lms:last-lesson:${courseId}`, JSON.stringify(lessonId)),
    [COURSE_ID, L2],
  );
  await mockApi(page);
  await page.goto("/");
  const resume = page.getByRole("region", { name: "Giải tích 1" });
  await expect(resume.getByRole("link", { name: "Học tiếp" })).toHaveAttribute("href", `/learn/giai-tich-1/${L2}`);
  // chỉ 1 khóa nên không có "Xem tất cả"
  await expect(page.getByRole("link", { name: /Xem tất cả/ })).toHaveCount(0);
  if (isMobile) {
    const bottom = page.getByRole("navigation", { name: "Điều hướng chính" }).last();
    await expect(bottom.getByRole("link")).toHaveCount(3);
    await expect(bottom.getByRole("link", { name: "Tài khoản" })).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: /Nguyễn Văn An/ })).toBeVisible();
  await expectAccessible(page);
  await expectNoHorizontalScroll(page);
});
```

- [ ] **Bước 5: Design system**

```diff
--- a/docs/design/design-system.md
+++ b/docs/design/design-system.md
@@ -174,7 +174,7 @@
   - Giảng viên: Khóa đang dạy, Câu hỏi chờ duyệt.
   - Admin: Duyệt giảng viên.
   - Menu tài khoản ở góc trên phải.
-- **Điện thoại (< 768px):** thanh điều hướng dưới cùng, **tối đa 4 mục**, có icon và chữ. Trang bài học **ẩn thanh dưới** để có thêm chỗ đọc.
+- **Điện thoại (< 768px):** thanh điều hướng dưới cùng, **tối đa 3 mục**, có icon và chữ. Tài khoản (hồ sơ, đăng xuất) nằm ở nút chữ cái tròn góc trên, có ở mọi trang. Trang bài học **ẩn thanh dưới** để có thêm chỗ đọc.
 - **Tablet:** thanh bên thu gọn (icon).
 - **Breadcrumb** (Khóa học › Chương › Bài) trên desktop. Trên điện thoại chỉ hiện nút ← với tên cấp cha.
 
```

- [ ] **Bước 6: Kiểm tra + commit**

```powershell
cd frontend
npx tsc --noEmit ; npx eslint .
npx vitest run                     # 168 pass
npx playwright test                # 97 pass + 1 bỏ qua có chủ ý
cd ..
git add frontend docs/design
git commit -m "feat(web): thẻ Học tiếp ở trang chủ học viên, thanh dưới điện thoại 3 mục, chỉ hiện Xem tất cả khi còn khóa"
```

---

## Task 2: Kiểm tay (bạn làm)

- [ ] **Thẻ "Học tiếp":** học viên mở một bài của khóa A rồi về trang chủ. Thẻ hiện khóa A; bấm "Học tiếp" mở đúng bài vừa học.
- [ ] **Học viên mới, chưa đăng ký khóa nào:** chỉ thấy ô "Bạn chưa đăng ký khóa học nào" và nút "Khám phá khóa học", không có link "Xem tất cả".
- [ ] **Đăng ký từ 4 khóa trở lên:** trang chủ hiện 3 thẻ khóa và link "Xem tất cả N khóa của tôi".
- [ ] **Điện thoại (F12, 375px):**
  - Thanh dưới chỉ còn 3 mục.
  - Nút chữ cái góc trên mở được Hồ sơ cá nhân và Đăng xuất.
  - Khách thấy nút "Đăng nhập" ở góc trên.
- [ ] **Giảng viên và quản trị:** xem nhanh các trang của mình ở 375px sau khi đổi màu và bo góc. E2E đã kiểm không cuộn ngang và độ tương phản cho các trang chính; chỗ nào trông chưa đẹp thì chụp màn hình gửi Claude.
