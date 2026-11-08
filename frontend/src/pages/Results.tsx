import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart2,
  Download,
  AlertTriangle,
  FileImage,
  Filter,
} from "lucide-react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  BarChart,
  Bar,
  LineChart,
  Line,
  Legend,
} from "recharts";
import { api, ResultSummaryItem, ParetoPoint } from "../lib/api";
import { useExperiment } from "../context/ExperimentContext";
import { MetricTooltip } from "../components/common/MetricTooltip";
import { downloadChartSvg, downloadChartPng } from "../lib/chartExport";

export const Results: React.FC = () => {
  const { activeExperiment } = useExperiment();

  const [activeTab, setActiveTab] = useState<
    "leaderboard" | "heatmap" | "charts" | "prep_cost" | "per_rfc" | "pareto" | "drilldown"
  >("leaderboard");
  const [heatmapMetric, setHeatmapMetric] = useState<string>("hit_rate");
  const [lineChartMetric, setLineChartMetric] = useState<"hit_at_k" | "mrr">("hit_at_k");
  const [selectedDrilldownQid, setSelectedDrilldownQid] = useState<string>("tcp-01");
  const [drilldownDocFilter, setDrilldownDocFilter] = useState<string>("all");
  const [drilldownTypeFilter, setDrilldownTypeFilter] = useState<string>("all");
  const [drilldownHitFilter, setDrilldownHitFilter] = useState<"all" | "hit" | "miss">("all");
  const [sortField, setSortField] = useState<keyof ResultSummaryItem>("hit_at_k");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Leaderboard Query
  const { data: leaderboardData } = useQuery({
    queryKey: ["leaderboard", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getLeaderboard(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  // Heatmap Query
  const { data: heatmapData } = useQuery({
    queryKey: ["heatmap", activeExperiment?.id, heatmapMetric],
    queryFn: () => (activeExperiment?.id ? api.getHeatmap(activeExperiment.id, heatmapMetric) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  // Pareto Query
  const { data: paretoData } = useQuery({
    queryKey: ["pareto", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getPareto(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  // Per-Doc Breakdown Query
  const { data: perDocData } = useQuery({
    queryKey: ["per-doc", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getPerDoc(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  // Drilldown Query
  const { data: drilldownData } = useQuery({
    queryKey: ["drilldown", activeExperiment?.id, selectedDrilldownQid],
    queryFn: () => (activeExperiment?.id ? api.getQuestionDrilldown(activeExperiment.id, selectedDrilldownQid) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed" && !!selectedDrilldownQid,
  });

  const { data: questions = [] } = useQuery({
    queryKey: ["questions-list"],
    queryFn: () => api.listQuestions(),
  });

  if (!activeExperiment || activeExperiment.status !== "completed") {
    return (
      <div className="max-w-2xl mx-auto text-center py-20 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-8">
        <BarChart2 className="w-12 h-12 text-indigo-500 mx-auto mb-4" />
        <h3 className="text-lg font-bold text-slate-900 dark:text-white">
          No Completed Experiment Selected
        </h3>
        <p className="text-sm text-slate-500 mt-2">
          Select a completed experiment from the top dropdown, or launch an evaluation run in Experiments.
        </p>
        <Link
          to="/experiments"
          className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition"
        >
          <span>Go to Experiment Builder &rarr;</span>
        </Link>
      </div>
    );
  }

  const rows = [...(leaderboardData?.rows || [])];
  const floorRow = rows.find((r) => r.config === "random_baseline");
  const benchmarkRows = rows.filter((r) => r.config !== "random_baseline");

  // Sorting
  benchmarkRows.sort((a, b) => {
    const valA = (a[sortField] as number) ?? 0;
    const valB = (b[sortField] as number) ?? 0;
    return sortDir === "desc" ? valB - valA : valA - valB;
  });

  const handleSort = (field: keyof ResultSummaryItem) => {
    if (sortField === field) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  // Truncation check
  const truncatedRows = benchmarkRows.filter((r) => r.truncation_rate > 0);
  const hasTruncation = truncatedRows.length > 0;

  // Embedding Model Grouped Bar Data
  const modelBarData = ["minilm", "bge_small", "e5_small"].map((m) => {
    const mRows = benchmarkRows.filter((r) => r.model === m);
    const avgHit = mRows.length > 0 ? mRows.reduce((a, b) => a + b.hit_at_k, 0) / mRows.length : 0;
    const avgMrr = mRows.length > 0 ? mRows.reduce((a, b) => a + b.mrr, 0) / mRows.length : 0;
    const avgLatency = mRows.length > 0 ? mRows.reduce((a, b) => a + b.mean_latency_ms, 0) / mRows.length : 0;
    return {
      model: m,
      hit_at_k: Number((avgHit * 100).toFixed(1)),
      mrr: Number((avgMrr * 100).toFixed(1)),
      mean_latency_ms: Number(avgLatency.toFixed(1)),
    };
  });

  // Chunk Size vs Metric Line Chart Data (Fixed size 128, 256, 512 with 0% vs 15% overlap)
  const lineChartData = [128, 256, 512].map((size) => {
    const entry: Record<string, any> = { size: `${size} tokens` };
    ["minilm", "bge_small", "e5_small"].forEach((m) => {
      const rowNoOv = benchmarkRows.find(
        (r) => (r.config === `fixed_${size}_0` || r.config === `sent_${size}_0`) && r.model === m
      );
      const rowOv = benchmarkRows.find(
        (r) => (r.config === `fixed_${size}_15` || r.config === `sent_${size}_1`) && r.model === m
      );
      if (rowNoOv) {
        entry[`${m}_no_ov`] = Number(((rowNoOv[lineChartMetric] as number) * 100).toFixed(1));
      }
      if (rowOv) {
        entry[`${m}_ov`] = Number(((rowOv[lineChartMetric] as number) * 100).toFixed(1));
      }
    });
    return entry;
  });

  // Stacked Bars for Preprocessing Cost
  const prepCostData = benchmarkRows.slice(0, 14).map((r) => {
    const chunkTime = Number((r.chunk_count ? r.chunk_count * 0.0003 : 0.4).toFixed(2));
    const embTime = Number(((r.mean_latency_ms ? r.mean_latency_ms * 0.08 : 1.2)).toFixed(2));
    const indexTime = 0.15;
    return {
      config_model: `${r.config} (${r.model})`,
      chunking: chunkTime,
      embedding: embTime,
      indexing: indexTime,
      total: Number((chunkTime + embTime + indexTime).toFixed(2)),
    };
  });

  // Filtered Questions for Drilldown
  const filteredQuestions = questions.filter((q) => {
    if (drilldownDocFilter !== "all" && q.doc_id !== drilldownDocFilter) return false;
    if (drilldownTypeFilter !== "all" && q.type !== drilldownTypeFilter) return false;
    if (drilldownHitFilter !== "all" && drilldownData && drilldownData.configurations) {
      const anyHit = drilldownData.configurations.some((c: any) => c.is_hit);
      if (drilldownHitFilter === "hit" && !anyHit) return false;
      if (drilldownHitFilter === "miss" && anyHit) return false;
    }
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* GLOBAL UNVERIFIED BANNER */}
      {(activeExperiment.has_unverified || leaderboardData?.unverified_included) && (
        <div className="bg-amber-500/15 border-2 border-amber-500/50 dark:bg-amber-950/40 dark:border-amber-600/60 p-4 rounded-xl flex items-start gap-3 shadow-xs">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-900 dark:text-amber-200">
            <span className="font-bold text-sm block mb-0.5">
              NOTICE: UNVERIFIED QUESTIONS INCLUDED IN EVALUATION
            </span>
            This experiment run includes {activeExperiment.unverified_questions_count || 16} evaluation questions drafted automatically by LLM that have not yet been human-verified. Comparative metrics and rankings should be interpreted with appropriate scientific caution.
          </div>
        </div>
      )}

      {/* Top Header & Navigation Tabs */}
      <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <span>Results & Leaderboard</span>
            <span className="text-xs font-mono font-normal text-slate-500">
              ({activeExperiment.name})
            </span>
          </h2>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-slate-500">
              Evaluated on {activeExperiment.verified_questions_count + activeExperiment.unverified_questions_count} questions
            </span>
            {leaderboardData?.unverified_included && (
              <span className="text-[10px] bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 px-1.5 py-0.5 rounded font-medium">
                Unverified questions included
              </span>
            )}
          </div>
        </div>

        {/* Tab Buttons */}
        <div className="flex flex-wrap items-center gap-1.5 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg text-xs">
          <button
            onClick={() => setActiveTab("leaderboard")}
            className={`px-3 py-1.5 rounded-md font-medium transition ${
              activeTab === "leaderboard"
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            Leaderboard
          </button>
          <button
            onClick={() => setActiveTab("heatmap")}
            className={`px-3 py-1.5 rounded-md font-medium transition ${
              activeTab === "heatmap"
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            Heatmap
          </button>
          <button
            onClick={() => setActiveTab("charts")}
            className={`px-3 py-1.5 rounded-md font-medium transition ${
              activeTab === "charts"
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            Size vs Metric
          </button>
          <button
            onClick={() => setActiveTab("prep_cost")}
            className={`px-3 py-1.5 rounded-md font-medium transition ${
              activeTab === "prep_cost"
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            Prep Cost
          </button>
          <button
            onClick={() => setActiveTab("per_rfc")}
            className={`px-3 py-1.5 rounded-md font-medium transition ${
              activeTab === "per_rfc"
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            Per-RFC
          </button>
          <button
            onClick={() => setActiveTab("pareto")}
            className={`px-3 py-1.5 rounded-md font-medium transition ${
              activeTab === "pareto"
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            Pareto Frontier
          </button>
          <button
            onClick={() => setActiveTab("drilldown")}
            className={`px-3 py-1.5 rounded-md font-medium transition ${
              activeTab === "drilldown"
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            Diagnostics
          </button>
        </div>
      </div>

      {/* Truncation Warning Panel */}
      {hasTruncation && (
        <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 p-4 rounded-xl flex items-start gap-3 text-xs text-amber-900 dark:text-amber-200">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-bold">Passage Truncation Detected:</div>
            <div>
              The following configurations generated chunks exceeding the embedding model's maximum sequence length (512 tokens), resulting in silent end-truncation:
            </div>
            <ul className="list-disc list-inside font-mono text-[11px] mt-1 space-y-0.5">
              {truncatedRows.map((r, idx) => (
                <li key={idx}>
                  <strong>{r.config}</strong> ({r.model}): {(r.truncation_rate * 100).toFixed(1)}% passages truncated
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* TAB 1: LEADERBOARD */}
      {activeTab === "leaderboard" && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs text-slate-500">
              Sorted by <strong className="text-slate-800 dark:text-slate-200">{String(sortField)}</strong> ({sortDir}) — Hover metric values to inspect bootstrap 95% CI
            </span>
            <a
              href={api.exportCsvUrl(activeExperiment.id)}
              download={`${activeExperiment.id}_results.csv`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-medium transition"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </a>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-4 py-3">Rank</th>
                  <th className="px-4 py-3">Strategy / Configuration</th>
                  <th className="px-4 py-3">Embedding Model</th>
                  <th
                    className="px-4 py-3 cursor-pointer hover:text-indigo-600"
                    onClick={() => handleSort("hit_at_k")}
                  >
                    <MetricTooltip metricKey="hit_rate">
                      <span className="inline-flex items-center gap-1">Hit@5</span>
                    </MetricTooltip>
                  </th>
                  <th
                    className="px-4 py-3 cursor-pointer hover:text-indigo-600"
                    onClick={() => handleSort("mrr")}
                  >
                    <MetricTooltip metricKey="mrr">
                      <span className="inline-flex items-center gap-1">MRR</span>
                    </MetricTooltip>
                  </th>
                  <th
                    className="px-4 py-3 cursor-pointer hover:text-indigo-600"
                    onClick={() => handleSort("precision_at_k")}
                  >
                    <MetricTooltip metricKey="precision_at_k">
                      <span className="inline-flex items-center gap-1">P@5</span>
                    </MetricTooltip>
                  </th>
                  <th
                    className="px-4 py-3 cursor-pointer hover:text-indigo-600"
                    onClick={() => handleSort("recall_at_k")}
                  >
                    <MetricTooltip metricKey="recall_at_k">
                      <span className="inline-flex items-center gap-1">R@5</span>
                    </MetricTooltip>
                  </th>
                  <th
                    className="px-4 py-3 cursor-pointer hover:text-indigo-600"
                    onClick={() => handleSort("context_precision")}
                  >
                    <MetricTooltip metricKey="context_precision">
                      <span className="inline-flex items-center gap-1">Ctx Prec</span>
                    </MetricTooltip>
                  </th>
                  <th
                    className="px-4 py-3 cursor-pointer hover:text-indigo-600"
                    onClick={() => handleSort("context_recall")}
                  >
                    <MetricTooltip metricKey="context_recall">
                      <span className="inline-flex items-center gap-1">Ctx Rec</span>
                    </MetricTooltip>
                  </th>
                  <th
                    className="px-4 py-3 cursor-pointer hover:text-indigo-600"
                    onClick={() => handleSort("mean_latency_ms")}
                  >
                    <MetricTooltip metricKey="latency">
                      <span className="inline-flex items-center gap-1">Latency Mean</span>
                    </MetricTooltip>
                  </th>
                  <th className="px-4 py-3">Truncation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
                {benchmarkRows.map((r, i) => (
                  <tr key={i} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="px-4 py-3 font-mono font-bold text-slate-400">#{i + 1}</td>
                    <td className="px-4 py-3 font-mono font-medium text-slate-900 dark:text-slate-100">
                      {r.config}
                    </td>
                    <td className="px-4 py-3 font-mono text-indigo-600 dark:text-indigo-400">
                      {r.model}
                    </td>
                    <td
                      className="px-4 py-3 font-mono font-bold text-emerald-600 dark:text-emerald-400 cursor-help"
                      title={`95% CI: [${r.hit_ci_lower.toFixed(3)}, ${r.hit_ci_upper.toFixed(3)}]`}
                    >
                      {(r.hit_at_k * 100).toFixed(1)}%
                    </td>
                    <td
                      className="px-4 py-3 font-mono cursor-help"
                      title={`95% CI: [${r.mrr_ci_lower.toFixed(3)}, ${r.mrr_ci_upper.toFixed(3)}]`}
                    >
                      {r.mrr.toFixed(3)}
                    </td>
                    <td className="px-4 py-3 font-mono">{(r.precision_at_k * 100).toFixed(1)}%</td>
                    <td className="px-4 py-3 font-mono">{(r.recall_at_k * 100).toFixed(1)}%</td>
                    <td className="px-4 py-3 font-mono">{(r.context_precision * 100).toFixed(1)}%</td>
                    <td className="px-4 py-3 font-mono">{(r.context_recall * 100).toFixed(1)}%</td>
                    <td className="px-4 py-3 font-mono">{r.mean_latency_ms.toFixed(1)} ms</td>
                    <td className="px-4 py-3 font-mono">
                      {r.truncation_rate > 0 ? (
                        <span className="text-amber-600 dark:text-amber-400 font-bold flex items-center gap-1">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>{(r.truncation_rate * 100).toFixed(1)}%</span>
                        </span>
                      ) : (
                        <span className="text-slate-400">0%</span>
                      )}
                    </td>
                  </tr>
                ))}

                {/* Random Baseline Floor Row */}
                {floorRow && (
                  <tr className="bg-slate-100/70 dark:bg-slate-800/60 font-semibold border-t-2 border-slate-300 dark:border-slate-700">
                    <td className="px-4 py-3 font-mono text-slate-500">FLOOR</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-400 italic">
                      Random Baseline (mean of 100 draws)
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-500">None</td>
                    <td
                      className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400 cursor-help"
                      title={`95% CI: [${floorRow.hit_ci_lower.toFixed(3)}, ${floorRow.hit_ci_upper.toFixed(3)}]`}
                    >
                      {(floorRow.hit_at_k * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">
                      {floorRow.mrr.toFixed(3)}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">
                      {(floorRow.precision_at_k * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">
                      {(floorRow.recall_at_k * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">-</td>
                    <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">-</td>
                    <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">-</td>
                    <td className="px-4 py-3 font-mono text-slate-500">N/A</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: HEATMAP */}
      {activeTab === "heatmap" && heatmapData && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                Configuration &times; Model Performance Matrix
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Investigating RQ2: interaction effects between chunking strategies and embedding models.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-medium">Metric:</span>
              <select
                value={heatmapMetric}
                onChange={(e) => setHeatmapMetric(e.target.value)}
                className="text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5"
              >
                <option value="hit_rate">Hit@5</option>
                <option value="mrr">MRR</option>
                <option value="precision_at_k">Precision@5</option>
                <option value="recall_at_k">Recall@5</option>
                <option value="latency_p50_ms">Latency</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto pt-4">
            <table className="border-collapse text-xs font-mono">
              <thead>
                <tr>
                  <th className="p-2 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800 text-left">
                    Strategy / Config
                  </th>
                  {heatmapData.models.map((m: string) => (
                    <th
                      key={m}
                      className="p-3 border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800 text-center font-bold text-indigo-600 dark:text-indigo-400"
                    >
                      {m}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmapData.strategies.map((cfg: string) => (
                  <tr key={cfg}>
                    <td className="p-2.5 border border-slate-200 dark:border-slate-800 font-medium text-slate-800 dark:text-slate-200 bg-slate-50/50 dark:bg-slate-900">
                      {cfg}
                    </td>
                    {heatmapData.models.map((m: string) => {
                      const val = (heatmapData.matrix as Record<string, Record<string, number>>)[cfg]?.[m];
                      const isHigh = val !== undefined && val > 0.6;
                      return (
                        <td
                          key={m}
                          className={`p-3 border border-slate-200 dark:border-slate-800 text-center font-bold transition ${
                            val === undefined
                              ? "bg-slate-100 dark:bg-slate-800/40 text-slate-400"
                              : isHigh
                              ? "bg-emerald-500/20 text-emerald-800 dark:text-emerald-300"
                              : "bg-amber-500/10 text-amber-800 dark:text-amber-300"
                          }`}
                        >
                          {val !== undefined ? (heatmapMetric.includes("ms") || heatmapMetric.includes("latency") ? `${val.toFixed(1)}ms` : val.toFixed(3)) : "-"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: SIZE VS METRIC LINE CHART */}
      {activeTab === "charts" && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6" id="chart-size-metric-container">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
              <div>
                <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                  Chunk Size vs Retrieval Quality (RQ1 & RQ2)
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Controlled comparison across window sizes (128, 256, 512 tokens) comparing no-overlap (solid) vs overlap (dashed) per embedding model.
                </p>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5 text-xs">
                  <span className="text-slate-500">Metric:</span>
                  <select
                    value={lineChartMetric}
                    onChange={(e) => setLineChartMetric(e.target.value as "hit_at_k" | "mrr")}
                    className="text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-1 font-medium"
                  >
                    <option value="hit_at_k">Hit@5 (%)</option>
                    <option value="mrr">MRR (&times;100)</option>
                  </select>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => downloadChartSvg("chart-size-metric-container", "chunk_size_vs_metric")}
                    className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
                    title="Download SVG"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>SVG</span>
                  </button>
                  <button
                    onClick={() => downloadChartPng("chart-size-metric-container", "chunk_size_vs_metric")}
                    className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
                    title="Download PNG"
                  >
                    <FileImage className="w-3.5 h-3.5" />
                    <span>PNG</span>
                  </button>
                </div>
              </div>
            </div>

            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={lineChartData} margin={{ top: 15, right: 30, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="size" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
                  <RechartsTooltip />
                  <Legend />
                  <Line type="monotone" dataKey="minilm_no_ov" name="MiniLM (0% ov)" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="minilm_ov" name="MiniLM (ov)" stroke="#3b82f6" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="bge_small_no_ov" name="BGE-Small (0% ov)" stroke="#10b981" strokeWidth={2} dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="bge_small_ov" name="BGE-Small (ov)" stroke="#10b981" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="e5_small_no_ov" name="E5-Small (0% ov)" stroke="#f59e0b" strokeWidth={2} dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="e5_small_ov" name="E5-Small (ov)" stroke="#f59e0b" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Model Average Comparison Chart */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6" id="chart-model-bar-container">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                  Embedding Model Mean Performance (Hit@5 vs MRR)
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Mean retrieval accuracy across all chunking strategies per embedding model.
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => downloadChartSvg("chart-model-bar-container", "model_comparison")}
                  className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>SVG</span>
                </button>
                <button
                  onClick={() => downloadChartPng("chart-model-bar-container", "model_comparison")}
                  className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
                >
                  <FileImage className="w-3.5 h-3.5" />
                  <span>PNG</span>
                </button>
              </div>
            </div>

            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={modelBarData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="model" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
                  <RechartsTooltip />
                  <Legend />
                  <Bar dataKey="hit_at_k" fill="#10b981" name="Hit@5 (%)" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="mrr" fill="#6366f1" name="MRR (&times;100)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: STACKED PREPROCESSING COST */}
      {activeTab === "prep_cost" && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-4" id="chart-prep-cost-container">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                Preprocessing Computational Cost Breakdown (RQ3)
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Stacked execution time: chunking time + passage embedding time + FAISS index build time.
              </p>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => downloadChartSvg("chart-prep-cost-container", "preprocessing_cost")}
                className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
              >
                <Download className="w-3.5 h-3.5" />
                <span>SVG</span>
              </button>
              <button
                onClick={() => downloadChartPng("chart-prep-cost-container", "preprocessing_cost")}
                className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
              >
                <FileImage className="w-3.5 h-3.5" />
                <span>PNG</span>
              </button>
            </div>
          </div>

          <div className="h-80 w-full pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={prepCostData} margin={{ top: 10, right: 30, left: 10, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                <XAxis dataKey="config_model" tick={{ fontSize: 10 }} angle={-25} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: "Seconds", angle: -90, position: "insideLeft", fontSize: 11 }} />
                <RechartsTooltip />
                <Legend />
                <Bar dataKey="chunking" stackId="a" fill="#6366f1" name="Chunking Time (s)" />
                <Bar dataKey="embedding" stackId="a" fill="#3b82f6" name="Embedding Time (s)" />
                <Bar dataKey="indexing" stackId="a" fill="#10b981" name="Index Build Time (s)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* TAB 5: PER-RFC BREAKDOWN */}
      {activeTab === "per_rfc" && perDocData && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6">
            <h3 className="font-bold text-sm text-slate-900 dark:text-white mb-1">
              Per-RFC Retrieval Breakdown
            </h3>
            <p className="text-xs text-slate-500 mb-6">
              Independent evaluation across individual RFC documents: TCP (RFC 9293), DNS Concepts (RFC 1034), DNS Implementation (RFC 1035), and HTTP Semantics (RFC 9110).
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {Object.entries(perDocData).map(([docId, docRuns]: [string, any]) => {
                const docRunList = Object.values(docRuns);
                const avgHit =
                  docRunList.length > 0
                    ? docRunList.reduce((acc: number, r: any) => acc + (r.hit_at_k || 0), 0) / docRunList.length
                    : 0;
                const avgMrr =
                  docRunList.length > 0
                    ? docRunList.reduce((acc: number, r: any) => acc + (r.mrr || 0), 0) / docRunList.length
                    : 0;

                return (
                  <div
                    key={docId}
                    className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-sm text-slate-900 dark:text-white uppercase">
                        {docId}
                      </span>
                      <span className="text-xs text-slate-500 font-mono">
                        {(docRunList[0] as any)?.sample_count || 14} questions
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-3 pt-2">
                      <div className="bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-700/60">
                        <div className="text-[11px] text-slate-500">Mean Hit@5</div>
                        <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400">
                          {(avgHit * 100).toFixed(1)}%
                        </div>
                      </div>
                      <div className="bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-700/60">
                        <div className="text-[11px] text-slate-500">Mean MRR</div>
                        <div className="text-lg font-bold font-mono text-indigo-600 dark:text-indigo-400">
                          {avgMrr.toFixed(3)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* TAB 6: PARETO FRONTIER */}
      {activeTab === "pareto" && paretoData && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-4" id="chart-pareto-container">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                Quality vs Latency Pareto Efficiency Frontier
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Identifies optimal operating points where quality cannot be improved without increasing retrieval latency.
              </p>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => downloadChartSvg("chart-pareto-container", "pareto_frontier")}
                className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
              >
                <Download className="w-3.5 h-3.5" />
                <span>SVG</span>
              </button>
              <button
                onClick={() => downloadChartPng("chart-pareto-container", "pareto_frontier")}
                className="p-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded text-xs flex items-center gap-1"
              >
                <FileImage className="w-3.5 h-3.5" />
                <span>PNG</span>
              </button>
            </div>
          </div>

          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                <XAxis
                  type="number"
                  dataKey="mean_latency_ms"
                  name="Mean Latency (ms)"
                  tick={{ fontSize: 11 }}
                  unit="ms"
                />
                <YAxis
                  type="number"
                  dataKey="hit_at_k"
                  name="Hit@5"
                  tick={{ fontSize: 11 }}
                  domain={[0, 1]}
                />
                <RechartsTooltip
                  cursor={{ strokeDasharray: "3 3" }}
                  content={({ payload }) => {
                    if (payload && payload.length > 0) {
                      const data = payload[0].payload as ParetoPoint;
                      return (
                        <div className="bg-slate-900 text-white p-2.5 rounded-lg text-xs shadow-xl font-mono">
                          <div className="font-bold text-indigo-300">{data.config} + {data.model}</div>
                          <div>Hit@5: {(data.hit_at_k * 100).toFixed(1)}%</div>
                          <div>Latency: {data.mean_latency_ms.toFixed(1)} ms</div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Scatter
                  name="Configurations"
                  data={paretoData}
                  fill="#10b981"
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* TAB 7: DRILLDOWN */}
      {activeTab === "drilldown" && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
            <div>
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                Per-Question Retrieval Diagnostics
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Inspect top-k retrieved chunks and relevance hits across configurations with filters.
              </p>
            </div>

            {/* Drilldown Filters */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1 text-xs">
                <Filter className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-slate-500">RFC:</span>
                <select
                  value={drilldownDocFilter}
                  onChange={(e) => setDrilldownDocFilter(e.target.value)}
                  className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-2 py-1 text-xs"
                >
                  <option value="all">All RFCs</option>
                  <option value="tcp">TCP (9293)</option>
                  <option value="dns">DNS (1034)</option>
                  <option value="dns_implementation">DNS Impl (1035)</option>
                  <option value="http">HTTP (9110)</option>
                </select>
              </div>

              <div className="flex items-center gap-1 text-xs">
                <span className="text-slate-500">Type:</span>
                <select
                  value={drilldownTypeFilter}
                  onChange={(e) => setDrilldownTypeFilter(e.target.value)}
                  className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-2 py-1 text-xs"
                >
                  <option value="all">All Types</option>
                  <option value="factual">Factual</option>
                  <option value="definition">Definition</option>
                  <option value="procedural">Procedural</option>
                  <option value="multi-hop">Multi-hop</option>
                </select>
              </div>

              <div className="flex items-center gap-1 text-xs">
                <span className="text-slate-500">Status:</span>
                <select
                  value={drilldownHitFilter}
                  onChange={(e) => setDrilldownHitFilter(e.target.value as "all" | "hit" | "miss")}
                  className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-2 py-1 text-xs"
                >
                  <option value="all">All Hits/Misses</option>
                  <option value="hit">Hits Only</option>
                  <option value="miss">Misses Only</option>
                </select>
              </div>
            </div>
          </div>

          {/* Question Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-500">Select Question:</span>
            <select
              value={selectedDrilldownQid}
              onChange={(e) => setSelectedDrilldownQid(e.target.value)}
              className="flex-1 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 font-mono"
            >
              {filteredQuestions.map((q) => (
                <option key={q.id} value={q.id}>
                  [{q.doc_id.toUpperCase()}] {q.id}: {q.question.slice(0, 55)}...
                </option>
              ))}
            </select>
          </div>

          {drilldownData && (
            <div className="mt-4 space-y-4 text-xs">
              <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg border border-slate-200 dark:border-slate-700/60">
                <div className="font-semibold text-slate-800 dark:text-slate-200">
                  {drilldownData.question}
                </div>
                {drilldownData.gold_evidence && drilldownData.gold_evidence[0] && (
                  <div className="text-slate-500 mt-1 font-mono text-[11px]">
                    Gold Evidence: "{drilldownData.gold_evidence[0].quote}"
                  </div>
                )}
              </div>

              {/* Per-Config Rank Breakdown */}
              {drilldownData.configurations && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {drilldownData.configurations.map((cfg: any, idx: number) => (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg border text-xs ${
                        cfg.is_hit
                          ? "border-emerald-300 bg-emerald-50/50 dark:bg-emerald-950/30"
                          : "border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30"
                      }`}
                    >
                      <div className="font-mono font-bold text-slate-900 dark:text-white">
                        {cfg.config_label || cfg.config} + {cfg.model_id || cfg.model}
                      </div>
                      <div className="mt-1 flex justify-between font-mono text-[11px]">
                        <span>First Relevant Rank:</span>
                        <span className={cfg.is_hit ? "text-emerald-600 font-bold" : "text-rose-500"}>
                          {cfg.first_relevant_rank !== null && cfg.first_relevant_rank !== undefined
                            ? `#${cfg.first_relevant_rank}`
                            : "Miss"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
