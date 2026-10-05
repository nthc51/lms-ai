import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./markdown";

describe("Markdown", () => {
  it("render tiêu đề, bảng GFM và công thức KaTeX", () => {
    const { container } = render(<Markdown>{"## Đạo hàm\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n$x^2$"}</Markdown>);
    expect(screen.getByRole("heading", { name: "Đạo hàm" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("không render HTML thô", () => {
    const { container } = render(<Markdown>{'<img src=x onerror="alert(1)">'}</Markdown>);
    expect(container.querySelector("img")).toBeNull();
  });
});
