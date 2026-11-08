import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Download,
  Copy,
  Check,
  FileCode,
  FileSpreadsheet,
  FileText,
  FileImage,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
} from "recharts";
import { api } from "../lib/api";
import { useExperiment } from "../context/ExperimentContext";
import { downloadChartSvg, downloadChartPng } from "../lib/chartExport";

export const Export: React.FC = () => {
  const { activeExperiment } = useExperiment();
  const [copiedType, setCopiedType] = useState<string | null>(null);

  const { data: manifest } = useQuery({
    queryKey: ["manifest", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getManifest(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  const { data: methodologyData } = useQuery({
    queryKey: ["methodology", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getMethodology(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  const { data: leaderboardData } = useQuery({
    queryKey: ["leaderboard", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getLeaderboard(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  const { data: paretoData } = useQuery({
    queryKey: ["pareto", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getPareto(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  const handleCopy = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    setCopiedType(type);
    setTimeout(() => setCopiedType(null), 2000);
  };

  if (!activeExperiment || activeExperiment.status !== "completed") {
    return (
      <div className="max-w-xl mx-auto text-center py-16 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-8">
        <Download className="w-12 h-12 text-indigo-500 mx-auto mb-4" />
        <h3 className="text-base font-bold text-slate-900 dark:text-white">Select a Completed Run</h3>
        <p className="text-xs text-slate-500 mt-2">
          Exporting artifacts, tables, and manifests requires an active completed experiment.
        </p>
      </div>
    );
  }

  const rows = leaderboardData?.rows || [];
  const benchmarkRows = rows.filter((r) => r.config !== "random_baseline");

  const modelBarData = ["minilm", "bge_small", "e5_small"].map((m) => {
    const mRows = benchmarkRows.filter((r) => r.model === m);
    const avgHit = mRows.length > 0 ? mRows.reduce((a, b) => a + b.hit_at_k, 0) / mRows.length : 0;
    const avgMrr = mRows.length > 0 ? mRows.reduce((a, b) => a + b.mrr, 0) / mRows.length : 0;
    return {
      model: m,
      hit_at_k: Number((avgHit * 100).toFixed(1)),
      mrr: Number((avgMrr * 100).toFixed(1)),
    };
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* GLOBAL UNVERIFIED BANNER */}
      {(activeExperiment.has_unverified || leaderboardData?.unverified_included) && (
        <div className="bg-amber-500/15 border-2 border-amber-500/50 dark:bg-amber-950/40 dark:border-amber-600/60 p-4 rounded-xl flex items-start gap-3 shadow-xs">
          <div className="text-xs text-amber-900 dark:text-amber-200">
            <span className="font-bold text-sm block mb-0.5">
              NOTICE: UNVERIFIED QUESTIONS INCLUDED IN EXPORT DATA
            </span>
            Generated tables, figures, and manifests include evaluations on unverified draft questions ({activeExperiment.unverified_questions_count} questions).
          </div>
        </div>
      )}

      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span>Export & Reproducibility Hub</span>
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Generate publication-ready tables (CSV, Markdown, LaTeX), download vector figures (SVG/PNG), inspect execution manifests, and copy methodology text.
        </p>
      </div>

      {/* Export Format Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* CSV Card */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
          <div>
            <FileSpreadsheet className="w-8 h-8 text-emerald-500 mb-3" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">CSV Data Table</h3>
            <p className="text-xs text-slate-500 mt-1">
              Raw tabular metrics with bootstrap confidence intervals, latencies, and metadata.
            </p>
          </div>
          <a
            href={api.exportCsvUrl(activeExperiment.id)}
            download={`${activeExperiment.id}_results.csv`}
            className="mt-6 flex items-center justify-center gap-2 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition"
          >
            <Download className="w-4 h-4" />
            <span>Download CSV</span>
          </a>
        </div>

        {/* Markdown Card */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
          <div>
            <FileText className="w-8 h-8 text-indigo-500 mb-3" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">GitHub Markdown Table</h3>
            <p className="text-xs text-slate-500 mt-1">
              Clean GFM table formatted for repository READMEs and project documentation.
            </p>
          </div>
          <a
            href={api.exportMarkdownUrl(activeExperiment.id)}
            download={`${activeExperiment.id}_table.md`}
            className="mt-6 flex items-center justify-center gap-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition"
          >
            <Download className="w-4 h-4" />
            <span>Download Markdown</span>
          </a>
        </div>

        {/* LaTeX Card */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
          <div>
            <FileCode className="w-8 h-8 text-purple-500 mb-3" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">LaTeX Table (booktabs)</h3>
            <p className="text-xs text-slate-500 mt-1">
              Academic paper table with booktabs syntax and special character escaping (%, _, &, #).
            </p>
          </div>
          <a
            href={api.exportLatexUrl(activeExperiment.id)}
            download={`${activeExperiment.id}_table.tex`}
            className="mt-6 flex items-center justify-center gap-2 py-2.5 px-4 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-semibold transition"
          >
            <Download className="w-4 h-4" />
            <span>Download LaTeX (.tex)</span>
          </a>
        </div>
      </div>

      {/* Publication Figures Download Section */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-6">
        <div>
          <h3 className="font-bold text-sm text-slate-900 dark:text-white">
            Publication Figures (SVG & PNG Export)
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Download vector SVG files for publication manuscripts or high-resolution 2x raster PNG images.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Figure 1: Model Comparison */}
          <div className="p-4 border border-slate-200 dark:border-slate-800 rounded-lg space-y-3" id="export-chart-fig1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-xs text-slate-800 dark:text-slate-200">
                Figure 1: Embedding Model Accuracy
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => downloadChartSvg("export-chart-fig1", "figure1_model_accuracy")}
                  className="px-2 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 rounded text-[11px] font-medium flex items-center gap-1"
                >
                  <Download className="w-3 h-3" />
                  <span>SVG</span>
                </button>
                <button
                  type="button"
                  onClick={() => downloadChartPng("export-chart-fig1", "figure1_model_accuracy")}
                  className="px-2 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 rounded text-[11px] font-medium flex items-center gap-1"
                >
                  <FileImage className="w-3 h-3" />
                  <span>PNG</span>
                </button>
              </div>
            </div>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={modelBarData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="model" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
                  <RechartsTooltip />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Bar dataKey="hit_at_k" fill="#10b981" name="Hit@5 (%)" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="mrr" fill="#6366f1" name="MRR (&times;100)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Figure 2: Pareto Scatter */}
          <div className="p-4 border border-slate-200 dark:border-slate-800 rounded-lg space-y-3" id="export-chart-fig2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-xs text-slate-800 dark:text-slate-200">
                Figure 2: Quality vs Latency Pareto
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => downloadChartSvg("export-chart-fig2", "figure2_pareto_frontier")}
                  className="px-2 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 rounded text-[11px] font-medium flex items-center gap-1"
                >
                  <Download className="w-3 h-3" />
                  <span>SVG</span>
                </button>
                <button
                  type="button"
                  onClick={() => downloadChartPng("export-chart-fig2", "figure2_pareto_frontier")}
                  className="px-2 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 rounded text-[11px] font-medium flex items-center gap-1"
                >
                  <FileImage className="w-3 h-3" />
                  <span>PNG</span>
                </button>
              </div>
            </div>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis type="number" dataKey="mean_latency_ms" name="Latency (ms)" tick={{ fontSize: 10 }} unit="ms" />
                  <YAxis type="number" dataKey="hit_at_k" name="Hit@5" tick={{ fontSize: 10 }} domain={[0, 1]} />
                  <RechartsTooltip />
                  <Scatter data={paretoData || []} fill="#10b981" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* Methodology Section */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">
              Generated Methodology Description
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Dynamically composed strictly from the experiment manifest parameters.
            </p>
          </div>
          <button
            onClick={() => handleCopy(methodologyData?.methodology_markdown || "", "methodology")}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 rounded-lg text-xs font-semibold transition"
          >
            {copiedType === "methodology" ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-500" />
                <span>Copied!</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copy Methodology</span>
              </>
            )}
          </button>
        </div>

        <div className="bg-slate-50 dark:bg-slate-800/40 p-4 rounded-lg font-mono text-xs leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap border border-slate-200 dark:border-slate-700/60">
          {methodologyData?.methodology_markdown || "Generating methodology text..."}
        </div>
      </div>

      {/* Manifest Viewer */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">
              Run Manifest & Provenance Data
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Complete hardware environment, model checksums, corpus hashes, and execution seeds.
            </p>
          </div>
          <button
            onClick={() => handleCopy(JSON.stringify(manifest || {}, null, 2), "manifest")}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 rounded-lg text-xs font-semibold transition"
          >
            {copiedType === "manifest" ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-500" />
                <span>Copied!</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copy Manifest JSON</span>
              </>
            )}
          </button>
        </div>

        <div className="bg-slate-950 p-4 rounded-lg font-mono text-xs leading-relaxed text-slate-200 max-h-80 overflow-y-auto">
          <pre>{JSON.stringify(manifest || {}, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
};
