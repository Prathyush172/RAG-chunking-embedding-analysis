import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitCompare, CheckCircle } from "lucide-react";
import { api, CompareRequest } from "../lib/api";
import { useExperiment } from "../context/ExperimentContext";
import { MetricTooltip } from "../components/common/MetricTooltip";

export const Compare: React.FC = () => {
  const { activeExperiment } = useExperiment();

  // Pickers for Config A and Config B
  const [baseConfig, setBaseConfig] = useState<string>("fixed_256_0");
  const [baseModel, setBaseModel] = useState<string>("minilm");
  const [targetConfig, setTargetConfig] = useState<string>("sent_256_0");
  const [targetModel, setTargetModel] = useState<string>("bge_small");

  // Leaderboard data to populate available configs
  const { data: leaderboardData } = useQuery({
    queryKey: ["leaderboard", activeExperiment?.id],
    queryFn: () => (activeExperiment?.id ? api.getLeaderboard(activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  const availableConfigs = Array.from(
    new Set(leaderboardData?.rows.filter((r) => r.config !== "random_baseline").map((r) => r.config) || [])
  );
  const availableModels = Array.from(
    new Set(leaderboardData?.rows.filter((r) => r.config !== "random_baseline").map((r) => r.model) || [])
  );

  const compareReq: CompareRequest = {
    experiment_id: activeExperiment?.id || "",
    base_config: baseConfig,
    base_model: baseModel,
    target_config: targetConfig,
    target_model: targetModel,
  };

  const { data: compareData } = useQuery({
    queryKey: ["compare", compareReq],
    queryFn: () => (activeExperiment?.id ? api.compareRuns(compareReq) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  if (!activeExperiment || activeExperiment.status !== "completed") {
    return (
      <div className="max-w-xl mx-auto text-center py-16 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-8">
        <GitCompare className="w-12 h-12 text-indigo-500 mx-auto mb-4" />
        <h3 className="text-base font-bold text-slate-900 dark:text-white">Select a Completed Run</h3>
        <p className="text-xs text-slate-500 mt-2">
          Pairwise comparison requires an active completed experiment.
        </p>
      </div>
    );
  }

  const winCount = compareData?.win_loss_tie?.wins ?? 0;
  const lossCount = compareData?.win_loss_tie?.losses ?? 0;
  const tieCount = compareData?.win_loss_tie?.ties ?? 0;
  const total = winCount + lossCount + tieCount || 1;

  const winPct = (winCount / total) * 100;
  const tiePct = (tieCount / total) * 100;
  const lossPct = (lossCount / total) * 100;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* GLOBAL UNVERIFIED BANNER */}
      {activeExperiment.has_unverified && (
        <div className="bg-amber-500/15 border-2 border-amber-500/50 dark:bg-amber-950/40 dark:border-amber-600/60 p-4 rounded-xl flex items-start gap-3 shadow-xs">
          <div className="text-xs text-amber-900 dark:text-amber-200">
            <span className="font-bold text-sm block mb-0.5">
              NOTICE: UNVERIFIED QUESTIONS INCLUDED IN EVALUATION
            </span>
            This comparison was evaluated over unverified draft questions ({activeExperiment.unverified_questions_count} unverified). P-values and statistical deltas reflect unverified test samples.
          </div>
        </div>
      )}

      {/* Top Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span>Pairwise Configuration Comparison</span>
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Controlled statistical testing (paired differences with bootstrap 95% CIs and Wilcoxon signed-rank test).
        </p>
      </div>

      {/* PLAIN-LANGUAGE STATISTICAL SUMMARY */}
      {compareData && (
        <div
          className={`p-4 rounded-xl border text-xs leading-relaxed ${
            (compareData.metrics.find((m) => m.metric === "hit_at_k")?.p_value ?? 1.0) >= 0.05
              ? "bg-slate-50 dark:bg-slate-800/40 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300"
              : (compareData.metrics.find((m) => m.metric === "hit_at_k")?.delta ?? 0) > 0
              ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200"
              : "bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800 text-rose-900 dark:text-rose-200"
          }`}
        >
          <div className="font-bold text-sm mb-1">
            Statistical Significance Verdict:
          </div>
          {(() => {
            const hitMetric = compareData.metrics.find((m) => m.metric === "hit_at_k") || compareData.metrics[0];
            if (!hitMetric || hitMetric.p_value >= 0.05) {
              return (
                <span>
                  The observed retrieval difference between <strong>Configuration A ({baseConfig} + {baseModel})</strong> and <strong>Configuration B ({targetConfig} + {targetModel})</strong> is not statistically significant (p = {hitMetric ? hitMetric.p_value.toFixed(4) : "1.0000"} &ge; 0.05). Based on this controlled empirical comparison, <strong>neither strategy can be claimed superior</strong>.
                </span>
              );
            }
            if (hitMetric.delta > 0) {
              return (
                <span>
                  <strong>Candidate Configuration B ({targetConfig} + {targetModel})</strong> achieved a statistically significant improvement over <strong>Baseline A ({baseConfig} + {baseModel})</strong> on {hitMetric.metric} (&Delta; = +{hitMetric.delta.toFixed(3)}, p = {hitMetric.p_value.toFixed(4)} &lt; 0.05, 95% CI [{hitMetric.delta_ci_lower.toFixed(3)}, {hitMetric.delta_ci_upper.toFixed(3)}]).
                </span>
              );
            }
            return (
              <span>
                <strong>Baseline Configuration A ({baseConfig} + {baseModel})</strong> significantly outperformed <strong>Candidate B ({targetConfig} + {targetModel})</strong> on {hitMetric.metric} (&Delta; = {hitMetric.delta.toFixed(3)}, p = {hitMetric.p_value.toFixed(4)} &lt; 0.05).
              </span>
            );
          })()}
        </div>
      )}

      {/* Pickers Bar */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm grid grid-cols-1 md:grid-cols-2 gap-6 relative">
        {/* Baseline (Config A) */}
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Baseline (Configuration A)
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                Strategy
              </label>
              <select
                value={baseConfig}
                onChange={(e) => setBaseConfig(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2"
              >
                {availableConfigs.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                Model
              </label>
              <select
                value={baseModel}
                onChange={(e) => setBaseModel(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2"
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Target (Config B) */}
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
            Candidate (Configuration B)
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                Strategy
              </label>
              <select
                value={targetConfig}
                onChange={(e) => setTargetConfig(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2"
              >
                {availableConfigs.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                Model
              </label>
              <select
                value={targetModel}
                onChange={(e) => setTargetModel(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2"
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Win / Loss / Tie Stacked Bar */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-slate-700 dark:text-slate-300">
            Query-Level Win / Loss / Tie Distribution
          </span>
          <span className="font-mono text-slate-500">
            Candidate Wins: <strong className="text-emerald-600">{winCount}</strong> | Ties:{" "}
            <strong className="text-slate-600">{tieCount}</strong> | Candidate Losses:{" "}
            <strong className="text-rose-600">{lossCount}</strong>
          </span>
        </div>

        {/* Stacked bar */}
        <div className="w-full h-3 rounded-full flex overflow-hidden bg-slate-100 dark:bg-slate-800">
          <div
            className="bg-emerald-500 h-full transition-all duration-300"
            style={{ width: `${winPct}%` }}
            title={`Wins: ${winCount} (${winPct.toFixed(1)}%)`}
          />
          <div
            className="bg-slate-300 dark:bg-slate-600 h-full transition-all duration-300"
            style={{ width: `${tiePct}%` }}
            title={`Ties: ${tieCount} (${tiePct.toFixed(1)}%)`}
          />
          <div
            className="bg-rose-500 h-full transition-all duration-300"
            style={{ width: `${lossPct}%` }}
            title={`Losses: ${lossCount} (${lossPct.toFixed(1)}%)`}
          />
        </div>
      </div>

      {/* Metric Delta Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <h3 className="font-bold text-xs uppercase tracking-wider text-slate-500">
            Statistical Metric Differences (&Delta; = B &minus; A)
          </h3>
          {compareData?.note && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1 italic">
              Note: {compareData.note}
            </p>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="px-6 py-3 font-sans">Metric</th>
                <th className="px-6 py-3">Baseline A ({baseConfig} + {baseModel})</th>
                <th className="px-6 py-3">Candidate B ({targetConfig} + {targetModel})</th>
                <th className="px-6 py-3">&Delta; (B &minus; A)</th>
                <th className="px-6 py-3">Bootstrap 95% CI</th>
                <th className="px-6 py-3">Wilcoxon p-value</th>
                <th className="px-6 py-3 font-sans">Significant (p &lt; 0.05)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
              {compareData?.metrics.map((m, idx) => {
                const isSig = m.statistically_significant;
                const isPositive = m.delta > 0;
                return (
                  <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="px-6 py-3 font-sans font-medium text-slate-900 dark:text-slate-100">
                      <MetricTooltip metricKey={m.metric}>
                        <span>{m.metric}</span>
                      </MetricTooltip>
                    </td>
                    <td className="px-6 py-3">{m.base_mean.toFixed(3)}</td>
                    <td className="px-6 py-3 font-bold text-slate-900 dark:text-slate-100">
                      {m.target_mean.toFixed(3)}
                    </td>
                    <td
                      className={`px-6 py-3 font-bold ${
                        m.delta === 0
                          ? "text-slate-500"
                          : isPositive
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-rose-600 dark:text-rose-400"
                      }`}
                    >
                      {isPositive ? `+${m.delta.toFixed(3)}` : m.delta.toFixed(3)}
                    </td>
                    <td className="px-6 py-3 text-slate-500">
                      [{m.delta_ci_lower.toFixed(3)}, {m.delta_ci_upper.toFixed(3)}]
                    </td>
                    <td className="px-6 py-3">p = {m.p_value.toFixed(4)}</td>
                    <td className="px-6 py-3 font-sans">
                      {isSig ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-bold">
                          <CheckCircle className="w-3.5 h-3.5" />
                          <span>Yes</span>
                        </span>
                      ) : (
                        <span className="text-slate-400">No</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
