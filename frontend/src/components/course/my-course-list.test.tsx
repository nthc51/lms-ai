import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { lastLesson } from "@/lib/study/storage";
import { api as url, server } from "@/test/msw";
import { CourseBoard, CourseRows, pickResume } from "./my-course-list";

const course = (n: number, over: Record<string, unknown> = {}) => ({
  course_id: `c${n}`,
  title: `Khóa ${n}`,
  slug: `khoa-${n}`,
  enrolled_at: "2026-09-02T00:00:00Z",
  completed_at: null as string | null,
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

describe("pickResume", () => {
  it("ưu tiên khóa chưa xong mà máy này nhớ bài đang học; không có thì khóa chưa xong đầu tiên", () => {
    lastLesson.set("c1", "l-xong"); // khóa 1 đã xong: bỏ qua
    lastLesson.set("c3", "l-7");
    const items = [course(1, { completed_at: "2026-10-01T00:00:00Z" }), course(2), course(3)];
    expect(pickResume(items)).toEqual({ course: items[2], lessonId: "l-7" });
    localStorage.clear();
    expect(pickResume(items)).toEqual({ course: items[1], lessonId: null });
    expect(pickResume([items[0]])).toBeNull();
  });
});

describe("CourseRows", () => {
  it("không có khóa: chỉ ô trống mời khám phá, không có liên kết Xem tất cả", async () => {
    serve([]);
    wrap(<CourseRows limit={3} moreHref="/my" />);
    expect(await screen.findByText("Bạn chưa đăng ký khóa học nào.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Xem tất cả/ })).not.toBeInTheDocument();
  });

  it("chỉ hiện Xem tất cả khi còn khóa chưa hiện; hàng dẫn vào bài đang học", async () => {
    lastLesson.set("c2", "l-5");
    serve([course(1), course(2), course(3), course(4)]);
    const { unmount } = wrap(<CourseRows limit={3} moreHref="/my" />);
    expect(await screen.findByRole("link", { name: /Xem tất cả 4 khóa của tôi/ })).toHaveAttribute("href", "/my");
    expect(screen.getByRole("link", { name: /Khóa 2/ })).toHaveAttribute("href", "/learn/khoa-2/l-5");
    expect(screen.getByRole("link", { name: /Khóa 1/ })).toHaveAttribute("href", "/courses/khoa-1");
    expect(screen.queryByRole("link", { name: /Khóa 4/ })).not.toBeInTheDocument();
    unmount();
    serve([course(1), course(2)]);
    wrap(<CourseRows limit={3} moreHref="/my" />);
    expect(await screen.findByRole("link", { name: /Khóa 2/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Xem tất cả/ })).not.toBeInTheDocument();
  });
});

describe("CourseBoard", () => {
  it("tách Đang học / Đã xong, đếm đúng, đổi nhóm bằng nút", async () => {
    serve([course(1), course(2, { completed_at: "2026-10-02T00:00:00Z", progress_pct: 100 }), course(3)]);
    wrap(<CourseBoard />);
    const doing = await screen.findByRole("button", { name: "Đang học · 2" });
    expect(doing).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: /Khóa 1/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Khóa 2/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Đã xong · 1" }));
    expect(screen.getByRole("link", { name: /Khóa 2/ })).toHaveTextContent("Xem lại khóa");
    expect(screen.queryByRole("link", { name: /Khóa 1/ })).not.toBeInTheDocument();
  });
});
