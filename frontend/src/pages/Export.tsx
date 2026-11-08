import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Download,
  Copy,
  Check,
  FileCode,
  FileSpreadsheet,
  FileText,
} from "lucide-react";
import { api } from "../lib/api";
import { useExperiment } from "../context/ExperimentContext";

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

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span>Export & Reproducibility Hub</span>
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Generate publication-ready tables (CSV, Markdown, LaTeX), inspect execution manifests, and copy methodology text.
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
