import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "../lib/api";

describe("API Error Handling", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("surfaces 409 Conflict error message when verified-only with zero verified questions", async () => {
    const errorBody = {
      error: {
        code: "NO_VERIFIED_QUESTIONS",
        message: "Conflict: Cannot launch experiment with verified_only=True because 0 questions are verified.",
      },
    };

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => errorBody,
      text: async () => JSON.stringify(errorBody),
    } as Response);

    await expect(
      api.createExperiment({ preset: "quick", verified_only: true })
    ).rejects.toThrow("Conflict: Cannot launch experiment with verified_only=True because 0 questions are verified.");
  });

  it("surfaces 422 Unprocessable Entity validation details", async () => {
    const errorBody = {
      detail: [
        { loc: ["body", "k"], msg: "Input should be greater than 0", type: "greater_than" },
      ],
    };

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      json: async () => errorBody,
      text: async () => JSON.stringify(errorBody),
    } as Response);

    await expect(
      api.createExperiment({ configs: ["fixed_256_0"], models: ["minilm"], k: 0 })
    ).rejects.toThrow("Input should be greater than 0");
  });
});
