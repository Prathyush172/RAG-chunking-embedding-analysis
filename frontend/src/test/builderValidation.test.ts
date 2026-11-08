import { describe, it, expect } from "vitest";

describe("Custom Experiment Builder Grid Validation", () => {
  function validateCustomGrid(configs: string[], models: string[]): { isValid: boolean; error?: string } {
    if (configs.length === 0) {
      return { isValid: false, error: "Please select at least one chunking strategy." };
    }
    if (models.length === 0) {
      return { isValid: false, error: "Please select at least one embedding model." };
    }
    return { isValid: true };
  }

  function computeEstimatedRuns(configs: string[], models: string[]): number {
    return configs.length * models.length;
  }

  it("fails validation when zero chunking strategies are selected", () => {
    const res = validateCustomGrid([], ["minilm"]);
    expect(res.isValid).toBe(false);
    expect(res.error).toBe("Please select at least one chunking strategy.");
  });

  it("fails validation when zero models are selected", () => {
    const res = validateCustomGrid(["fixed_256_0"], []);
    expect(res.isValid).toBe(false);
    expect(res.error).toBe("Please select at least one embedding model.");
  });

  it("passes validation when at least one chunking strategy and one model are selected", () => {
    const res = validateCustomGrid(["fixed_256_0", "sent_256_0"], ["minilm", "bge_small"]);
    expect(res.isValid).toBe(true);
    expect(res.error).toBeUndefined();
  });

  it("calculates estimated runs count dynamically based on selected grid", () => {
    expect(computeEstimatedRuns(["fixed_256_0"], ["minilm"])).toBe(1);
    expect(computeEstimatedRuns(["fixed_256_0", "sent_256_0", "semantic_default"], ["minilm", "bge_small", "e5_small"])).toBe(9);
    expect(computeEstimatedRuns(
      ["fixed_128_0", "fixed_128_15", "fixed_256_0", "fixed_256_15", "fixed_512_0", "fixed_512_15",
       "sent_128_0", "sent_128_1", "sent_256_0", "sent_256_1", "sent_512_0", "sent_512_1",
       "semantic_default", "semantic_p15"],
      ["minilm", "bge_small", "e5_small"]
    )).toBe(42);
  });
});
