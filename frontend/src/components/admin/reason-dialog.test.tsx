import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReasonDialog } from "./reason-dialog";

function setup(required = true, onSubmit = vi.fn(async () => {})) {
  const onOpenChange = vi.fn();
  render(
    <ReasonDialog open onOpenChange={onOpenChange} title="Từ chối An?" description="Mô tả" confirmLabel="Từ chối" required={required} onSubmit={onSubmit} />,
  );
  return { onSubmit, onOpenChange, user: userEvent.setup() };
}

describe("ReasonDialog", () => {
  it("bắt buộc lý do: để trống thì báo lỗi, không gửi", async () => {
    const { onSubmit, user } = setup();
    await user.type(screen.getByLabelText("Lý do"), "   ");
    await user.click(screen.getByRole("button", { name: "Từ chối" }));
    expect(await screen.findByText("Cần nhập lý do")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("gửi lý do đã cắt khoảng trắng rồi đóng", async () => {
    const { onSubmit, onOpenChange, user } = setup();
    await user.type(screen.getByLabelText("Lý do"), "  Thiếu hồ sơ  ");
    await user.click(screen.getByRole("button", { name: "Từ chối" }));
    expect(onSubmit).toHaveBeenCalledWith("Thiếu hồ sơ");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("lý do không bắt buộc: gửi được khi để trống; lỗi thì giữ hộp thoại mở", async () => {
    const failing = vi.fn(async () => {
      throw new Error("x");
    });
    const { onOpenChange, user } = setup(false, failing);
    await user.click(screen.getByRole("button", { name: "Từ chối" }));
    expect(failing).toHaveBeenCalledWith("");
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
