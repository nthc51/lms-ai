import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import type { CourseDetail } from "@/lib/queries";
import { api as url, server } from "@/test/msw";
import { moveItem, useCourseMutations, useCreateCourse } from "./teach-queries";

describe("moveItem", () => {
  it("chuyển phần tử lên/xuống", () => {
    expect(moveItem(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(moveItem(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
  });
  it("giữ nguyên khi vượt biên", () => {
    const list = ["a", "b"];
    expect(moveItem(list, 0, -1)).toBe(list);
    expect(moveItem(list, 1, 2)).toBe(list);
  });
});

describe("danh sách khóa của giảng viên được tải lại", () => {
  const course = { id: "c1", slug: "toan-12", sections: [] } as unknown as CourseDetail;

  function setup() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
    const invalidatedTeacherList = () => spy.mock.calls.some(([f]) => JSON.stringify(f?.queryKey) === JSON.stringify(["teacher-courses"]));
    return { wrapper, invalidatedTeacherList };
  }

  it("sau khi tạo khóa", async () => {
    server.use(http.post(url("/courses"), () => HttpResponse.json({ id: "c2", slug: "moi" }, { status: 201 })));
    const { wrapper, invalidatedTeacherList } = setup();
    const { result } = renderHook(() => useCreateCourse(), { wrapper });
    await result.current.mutateAsync({ title: "Khóa mới", description: "" });
    await waitFor(() => expect(invalidatedTeacherList()).toBe(true));
  });

  it("sau khi xuất bản", async () => {
    server.use(http.post(url("/courses/c1/publish"), () => HttpResponse.json({ id: "c1", status: "published" })));
    const { wrapper, invalidatedTeacherList } = setup();
    const { result } = renderHook(() => useCourseMutations(course), { wrapper });
    await result.current.publish.mutateAsync();
    await waitFor(() => expect(invalidatedTeacherList()).toBe(true));
  });

  it("sau khi xóa khóa", async () => {
    server.use(http.delete(url("/courses/c1"), () => new HttpResponse(null, { status: 204 })));
    const { wrapper, invalidatedTeacherList } = setup();
    const { result } = renderHook(() => useCourseMutations(course), { wrapper });
    await result.current.deleteCourse.mutateAsync();
    await waitFor(() => expect(invalidatedTeacherList()).toBe(true));
  });
});
