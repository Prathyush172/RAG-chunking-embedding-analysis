import React, { useState } from "react";
import { HelpCircle } from "lucide-react";

export const METRIC_GLOSSARY: Record<string, { title: string; formula: string; description: string }> = {
  hit_rate: {
    title: "Hit@5",
    formula: "Hit@k = 1 if any retrieved chunk at rank <= k contains gold evidence else 0",
    description: "Proportion of queries where at least one ground-truth evidence chunk was retrieved in the top 5.",
  },
  mrr: {
    title: "MRR (Mean Reciprocal Rank)",
    formula: "MRR = 1 / rank_first_relevant",
    description: "Reciprocal rank of the highest-ranking relevant chunk. Awards full credit for rank 1, half credit for rank 2, etc.",
  },
  precision_at_k: {
    title: "Precision@5",
    formula: "P@k = |relevant retrieved chunks in top-k| / k",
    description: "Fraction of the top-5 retrieved chunks that contain gold evidence.",
  },
  recall_at_k: {
    title: "Recall@5",
    formula: "R@k = |relevant retrieved chunks in top-k| / |total relevant chunks|",
    description: "Fraction of all gold-evidence chunks successfully retrieved in the top-5.",
  },
  context_precision: {
    title: "Context Precision",
    formula: "Sum_{k=1}^K (P@k * v_k) / |total relevant chunks in top-K|",
    description: "Evaluates whether relevant chunks are concentrated at the highest ranks rather than pushed down.",
  },
  context_recall: {
    title: "Context Recall",
    formula: "Recall = |ground-truth evidence claims covered by top-K| / |total evidence claims|",
    description: "Measures whether the retrieved context contains all necessary factual information to answer the question.",
  },
  groundedness: {
    title: "Groundedness / Faithfulness",
    formula: "Score in [1, 5] assessed by LLM Judge",
    description: "Degree to which generated answers are directly supported by retrieved RFC context without hallucination.",
  },
  truncation_rate: {
    title: "Truncation Rate",
    formula: "Truncated = |chunks exceeding model max_seq_length| / |total chunks|",
    description: "Percentage of passages that exceed the embedding model's context window and had tokens discarded.",
  },
  latency: {
    title: "Retrieval Latency (p50 / p95)",
    formula: "Measured wall-clock FAISS query time (ms)",
    description: "Time required to encode the query and retrieve top-k nearest neighbor vectors from the FAISS index.",
  },
};

interface MetricTooltipProps {
  metricKey: string;
  label?: string;
  children?: React.ReactNode;
}

export const MetricTooltip: React.FC<MetricTooltipProps> = ({ metricKey, label, children }) => {
  const [open, setOpen] = useState(false);
  const info = METRIC_GLOSSARY[metricKey];

  if (!info) {
    return <span>{children || label}</span>;
  }

  return (
    <div
      className="relative inline-flex items-center gap-1 cursor-help group"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={() => setOpen(!open)}
    >
      <span>{children || label || info.title}</span>
      <HelpCircle className="w-3.5 h-3.5 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400" />

      {open && (
        <div className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 w-64 p-3 bg-slate-900 text-slate-100 dark:bg-slate-800 text-xs rounded-lg shadow-xl pointer-events-none transition-all">
          <div className="font-semibold text-slate-100 mb-1">{info.title}</div>
          <div className="font-mono text-[10px] text-indigo-300 dark:text-indigo-200 mb-1.5 bg-slate-950/60 p-1 rounded">
            {info.formula}
          </div>
          <div className="text-slate-300 leading-relaxed">{info.description}</div>
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-slate-800" />
        </div>
      )}
    </div>
  );
};
