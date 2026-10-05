import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useShortcuts } from "./use-shortcuts";

function Harness({ onF }: { onF: () => void }) {
  useShortcuts({ f: onF });
  return <input aria-label="ô nhập" />;
}

describe("useShortcuts", () => {
  it("gọi handler khi bấm phím ngoài ô nhập (không phân biệt hoa thường)", () => {
    const onF = vi.fn();
    render(<Harness onF={onF} />);
    fireEvent.keyDown(window, { key: "F" });
    expect(onF).toHaveBeenCalledTimes(1);
  });

  it("bỏ qua khi đang gõ trong ô nhập hoặc có Ctrl", () => {
    const onF = vi.fn();
    const { getByLabelText } = render(<Harness onF={onF} />);
    fireEvent.keyDown(getByLabelText("ô nhập"), { key: "f" });
    fireEvent.keyDown(window, { key: "f", ctrlKey: true });
    expect(onF).not.toHaveBeenCalled();
  });

  it("bỏ qua phím mũi tên trên <video> nhưng vẫn nhận Escape", () => {
    const onRight = vi.fn();
    const onEsc = vi.fn();
    function H() {
      useShortcuts({ ArrowRight: onRight, Escape: onEsc });
      return <video aria-label="video" tabIndex={0} />;
    }
    const { getByLabelText } = render(<H />);
    fireEvent.keyDown(getByLabelText("video"), { key: "ArrowRight" });
    expect(onRight).not.toHaveBeenCalled();
    fireEvent.keyDown(getByLabelText("video"), { key: "Escape" });
    expect(onEsc).toHaveBeenCalledTimes(1);
  });

  it("bỏ qua mọi phím (kể cả Escape) bên trong [role=dialog]", () => {
    const onF = vi.fn();
    const onEsc = vi.fn();
    function H() {
      useShortcuts({ f: onF, Escape: onEsc });
      return (
        <div role="dialog">
          <button>trong dialog</button>
        </div>
      );
    }
    const { getByText } = render(<H />);
    fireEvent.keyDown(getByText("trong dialog"), { key: "f" });
    fireEvent.keyDown(getByText("trong dialog"), { key: "Escape" });
    expect(onF).not.toHaveBeenCalled();
    expect(onEsc).not.toHaveBeenCalled();
  });
});
