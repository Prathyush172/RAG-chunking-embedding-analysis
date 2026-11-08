import { describe, it, expect } from "vitest";
import { METRIC_GLOSSARY } from "../components/common/MetricTooltip";

describe("Metric Glossary Completeness", () => {
  const REQUIRED_METRICS = [
    "hit_rate",
    "mrr",
    "precision_at_k",
    "recall_at_k",
    "context_precision",
    "context_recall",
    "groundedness",
    "truncation_rate",
    "latency",
  ];

  it("defines every required UI metric", () => {
    for (const key of REQUIRED_METRICS) {
      expect(METRIC_GLOSSARY[key], `Missing glossary definition for '${key}'`).toBeDefined();
    }
  });

  it("provides title, mathematical formula, and descriptive explanation for each metric", () => {
    for (const [key, entry] of Object.entries(METRIC_GLOSSARY)) {
      expect(entry.title.length, `Empty title for ${key}`).toBeGreaterThan(0);
      expect(entry.formula.length, `Empty formula for ${key}`).toBeGreaterThan(0);
      expect(entry.description.length, `Empty description for ${key}`).toBeGreaterThan(10);
    }
  });
});
