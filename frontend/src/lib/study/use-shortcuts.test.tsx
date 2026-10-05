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
});
