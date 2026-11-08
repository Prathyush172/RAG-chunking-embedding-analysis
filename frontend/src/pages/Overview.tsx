import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  CheckCircle2,
  Clock,
  Zap,
  ArrowRight,
  TrendingUp,
  Layers,
  Sparkles,
} from "lucide-react";
import { api } from "../lib/api";
import { useExperiment } from "../context/ExperimentContext";

export const Overview: React.FC = () => {
  const { activeExperiment, experiments } = useExperiment();

  const { data: documents = [] } = useQuery({
    queryKey: ["corpus-docs"],
    queryFn: () => api.listDocuments(),
  });

  const { data: reviewProgress } = useQuery({
    queryKey: ["review-progress"],
    queryFn: () => api.getReviewProgress(),
  });

  const { data: leaderboard } = useQuery({
    queryKey: ["leaderboard", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getLeaderboard(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  // Calculate best performers from active experiment if completed
  const rows = leaderboard?.rows || [];
  const bestHit = rows.length > 0 ? [...rows].sort((a, b) => b.hit_rate - a.hit_rate)[0] : null;
  const bestMrr = rows.length > 0 ? [...rows].sort((a, b) => b.mrr - a.mrr)[0] : null;
  const lowestLatency = rows.length > 0 ? [...rows].sort((a, b) => a.latency_p50_ms - b.latency_p50_ms)[0] : null;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Title & Introduction */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-white">
            RFC RAG Chunking Lab
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 max-w-3xl">
            Controlled empirical comparison of <strong>Chunking Strategies</strong> (Fixed-size,
            Sentence-level, Semantic) and <strong>Embedding Models</strong> (MiniLM, BGE-Small, E5-Small)
            on technical networking RFCs (TCP, DNS, HTTP).
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/experiments"
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition shadow-sm"
          >
            <Zap className="w-4 h-4" />
            <span>Run Experiment</span>
          </Link>
          <Link
            to="/results"
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 rounded-lg text-sm font-medium transition"
          >
            <span>View Results</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      {/* Top Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Review Progress Card */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Evaluation Set</span>
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-slate-900 dark:text-white">
                {reviewProgress?.verified ?? 0}
              </span>
              <span className="text-xs text-slate-500">/ {reviewProgress?.total ?? 56} verified</span>
            </div>
            {/* Progress Bar */}
            <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full mt-3 overflow-hidden">
              <div
                className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${reviewProgress?.percent_complete ?? 0}%` }}
              />
            </div>
            <div className="text-right text-[11px] text-slate-500 mt-1">
              {reviewProgress?.percent_complete ?? 0}% human verified
            </div>
          </div>

          <Link
            to="/review"
            className="mt-4 inline-flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md bg-emerald-50 dark:bg-emerald-950/50 hover:bg-emerald-100 text-emerald-700 dark:text-emerald-300 text-xs font-medium transition"
          >
            <span>Launch Review Interface</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Corpus Documents Card */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Target Corpus</span>
              <FileText className="w-4 h-4 text-indigo-500" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-slate-900 dark:text-white">
                {documents.length}
              </span>
              <span className="text-xs text-slate-500">IETF Standards</span>
            </div>
            <div className="mt-3 text-xs text-slate-600 dark:text-slate-400 space-y-1">
              <div className="flex justify-between">
                <span>Total Characters:</span>
                <span className="font-mono font-medium">
                  {documents.reduce((acc, d) => acc + d.char_count, 0).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Clean Corpus Status:</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-medium">Verified Clean</span>
              </div>
            </div>
          </div>

          <Link
            to="/dataset"
            className="mt-4 inline-flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md bg-indigo-50 dark:bg-indigo-950/50 hover:bg-indigo-100 text-indigo-700 dark:text-indigo-300 text-xs font-medium transition"
          >
            <span>Explore Documents & Sections</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Active Experiment Run Card */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Active Experiment</span>
              <Layers className="w-4 h-4 text-purple-500" />
            </div>
            {activeExperiment ? (
              <>
                <div className="font-bold text-base text-slate-900 dark:text-white truncate">
                  {activeExperiment.name}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className={`inline-block px-2 py-0.5 rounded text-[11px] font-mono font-medium ${
                      activeExperiment.status === "completed"
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                        : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                    }`}
                  >
                    {activeExperiment.status}
                  </span>
                  <span className="text-xs text-slate-500">
                    Preset: {activeExperiment.preset || "Custom"}
                  </span>
                </div>
                <div className="mt-3 text-xs text-slate-600 dark:text-slate-400 space-y-1">
                  <div className="flex justify-between">
                    <span>Questions evaluated:</span>
                    <span className="font-mono">
                      {activeExperiment.verified_questions_count + activeExperiment.unverified_questions_count}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Verified Only:</span>
                    <span className="font-mono">{activeExperiment.verified_only ? "Yes" : "No"}</span>
                  </div>
                </div>
              </>
            ) : (
              <div className="text-xs text-slate-500 italic mt-2">
                No active experiment. Select or launch one in Experiments.
              </div>
            )}
          </div>

          <Link
            to="/results"
            className="mt-4 inline-flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md bg-purple-50 dark:bg-purple-950/50 hover:bg-purple-100 text-purple-700 dark:text-purple-300 text-xs font-medium transition"
          >
            <span>Analyze Leaderboard & Charts</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* Highlights / Best Performers of Active Run */}
      {bestHit && (
        <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-500" />
            Active Run Performance Highlights ({activeExperiment?.name})
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
              <div className="text-xs text-slate-500 dark:text-slate-400">Highest Hit@5</div>
              <div className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-1">
                {(bestHit.hit_rate * 100).toFixed(1)}%
              </div>
              <div className="text-xs text-slate-700 dark:text-slate-300 font-mono mt-1 truncate">
                {bestHit.config_label} + {bestHit.model_id}
              </div>
            </div>

            <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
              <div className="text-xs text-slate-500 dark:text-slate-400">Highest MRR</div>
              <div className="text-2xl font-bold font-mono text-indigo-600 dark:text-indigo-400 mt-1">
                {bestMrr?.mrr.toFixed(3)}
              </div>
              <div className="text-xs text-slate-700 dark:text-slate-300 font-mono mt-1 truncate">
                {bestMrr?.config_label} + {bestMrr?.model_id}
              </div>
            </div>

            <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
              <div className="text-xs text-slate-500 dark:text-slate-400">Lowest Latency (p50)</div>
              <div className="text-2xl font-bold font-mono text-amber-600 dark:text-amber-400 mt-1">
                {lowestLatency?.latency_p50_ms.toFixed(1)} ms
              </div>
              <div className="text-xs text-slate-700 dark:text-slate-300 font-mono mt-1 truncate">
                {lowestLatency?.config_label} + {lowestLatency?.model_id}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Corpus Overview Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-200 dark:border-slate-800">
          <h3 className="font-bold text-base text-slate-900 dark:text-white">Corpus Specifications</h3>
          <p className="text-xs text-slate-500 mt-1">
            Raw RFC text preprocessed with headers/footers stripped and ASCII tables preserved.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="px-6 py-3">Doc ID</th>
                <th className="px-6 py-3">RFC #</th>
                <th className="px-6 py-3">Title</th>
                <th className="px-6 py-3">Characters</th>
                <th className="px-6 py-3">Lines</th>
                <th className="px-6 py-3">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
              {documents.map((doc) => (
                <tr key={doc.doc_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                  <td className="px-6 py-3 font-mono font-semibold text-indigo-600 dark:text-indigo-400">
                    {doc.doc_id}
                  </td>
                  <td className="px-6 py-3 font-mono">RFC {doc.rfc_number}</td>
                  <td className="px-6 py-3 font-medium text-slate-900 dark:text-slate-100">
                    {doc.title}
                  </td>
                  <td className="px-6 py-3 font-mono">{doc.char_count.toLocaleString()}</td>
                  <td className="px-6 py-3 font-mono">{doc.line_count.toLocaleString()}</td>
                  <td className="px-6 py-3">
                    <Link
                      to={`/dataset?doc_id=${doc.doc_id}`}
                      className="text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                    >
                      View in Reader &rarr;
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
