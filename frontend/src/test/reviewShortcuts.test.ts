import { describe, it, expect, vi } from "vitest";

describe("Review Keyboard Shortcuts (A/E/R/N)", () => {
  function handleKeyDown(
    key: string,
    callbacks: {
      onApprove: () => void;
      onReject: () => void;
      onEdit: () => void;
      onNext: () => void;
    }
  ): void {
    const k = key.toLowerCase();
    if (k === "a") callbacks.onApprove();
    else if (k === "r") callbacks.onReject();
    else if (k === "e") callbacks.onEdit();
    else if (k === "n") callbacks.onNext();
  }

  it("dispatches approve on 'a' or 'A'", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const onEdit = vi.fn();
    const onNext = vi.fn();

    handleKeyDown("a", { onApprove, onReject, onEdit, onNext });
    handleKeyDown("A", { onApprove, onReject, onEdit, onNext });

    expect(onApprove).toHaveBeenCalledTimes(2);
    expect(onReject).not.toHaveBeenCalled();
  });

  it("dispatches reject on 'r' or 'R'", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const onEdit = vi.fn();
    const onNext = vi.fn();

    handleKeyDown("r", { onApprove, onReject, onEdit, onNext });
    expect(onReject).toHaveBeenCalledTimes(1);
  });

  it("dispatches edit on 'e' or 'E'", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const onEdit = vi.fn();
    const onNext = vi.fn();

    handleKeyDown("e", { onApprove, onReject, onEdit, onNext });
    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it("dispatches next on 'n' or 'N'", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const onEdit = vi.fn();
    const onNext = vi.fn();

    handleKeyDown("n", { onApprove, onReject, onEdit, onNext });
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});
