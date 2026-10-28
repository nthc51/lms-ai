import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CourseDetail } from "@/lib/queries";
import { CourseOutline } from "./course-outline";

const course = {
  id: "c1",
  slug: "khoa",
  title: "Khóa",
  sections: [
    {
      id: "s1",
      title: "Chương 1",
      position: 0,
      lessons: [
        { id: "l1", title: "Bài một", position: 0, duration_sec: null },
        { id: "l2", title: "Bài hai", position: 1, duration_sec: null },
      ],
    },
  ],
  done_lesson_ids: ["l1"],
} as unknown as CourseDetail;

describe("CourseOutline", () => {
  it("bài đã học xong (done_lesson_ids) có dấu tích, bài chưa học thì không", () => {
    render(<CourseOutline course={course} currentLessonId="l2" />);
    expect(screen.getByRole("link", { name: /Bài một/ })).toContainElement(screen.getByLabelText("Đã học"));
    expect(screen.getAllByLabelText("Đã học")).toHaveLength(1);
    expect(screen.getByRole("link", { name: /Bài hai/ })).toHaveAttribute("aria-current", "page");
  });
});
