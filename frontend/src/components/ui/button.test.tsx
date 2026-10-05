import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("khi loading: bị khóa, aria-busy và đổi chữ", () => {
    render(
      <Button loading loadingText="Đang nộp…">
        Nộp bài
      </Button>,
    );
    const btn = screen.getByRole("button", { name: "Đang nộp…" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
  });

  it("mặc định là nút chính cao 40px", () => {
    render(<Button>Gửi câu hỏi</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-primary", "h-10");
  });
});
