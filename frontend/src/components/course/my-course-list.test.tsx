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
