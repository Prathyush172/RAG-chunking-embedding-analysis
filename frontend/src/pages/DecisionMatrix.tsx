import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Award, HelpCircle } from "lucide-react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip as RechartsTooltip,
} from "recharts";
import { api, DecisionMatrixWeights, DecisionMatrixRankItem } from "../lib/api";
import { useExperiment } from "../context/ExperimentContext";

export const DecisionMatrix: React.FC = () => {
  const { activeExperiment } = useExperiment();

  // Preset query
  const { data: presets } = useQuery({
    queryKey: ["decision-matrix-presets"],
    queryFn: () => api.getDecisionMatrixPresets(),
  });

  // Configurable Quality choice: Hit@5 or MRR
  const [qualityChoice, setQualityChoice] = useState<"hit_at_k" | "mrr">("hit_at_k");

  // Weights state matching backend DecisionMatrixWeights schema
  const [weights, setWeights] = useState<DecisionMatrixWeights>({
    hit_at_k: 0.3,
    groundedness: 0.2,
    latency: 0.25,
    index_size: 0.1,
    cost: 0.15,
  });

  // Compute Query
  const { data: matrixData } = useQuery({
    queryKey: ["decision-matrix", activeExperiment?.id, weights, qualityChoice],
    queryFn: () => (activeExperiment?.id ? api.computeDecisionMatrix(weights, activeExperiment.id) : null),
    enabled: !!activeExperiment && activeExperiment.status === "completed",
  });

  const applyPreset = (presetName: string) => {
    if (presets && presets[presetName]) {
      setWeights(presets[presetName]);
    }
  };

  const handleSliderChange = (field: keyof DecisionMatrixWeights, val: number) => {
    setWeights((prev) => ({ ...prev, [field]: val }));
  };

  const ranked: DecisionMatrixRankItem[] = matrixData?.ranked_results || [];
  const top3 = ranked.slice(0, 3);

  // Radar chart data for top 3
  const radarDimensions = [
    { key: "hit_at_k", label: qualityChoice === "hit_at_k" ? "Quality (Hit@5)" : "Quality (MRR)" },
    { key: "groundedness", label: "Groundedness" },
    { key: "latency", label: "Speed (Low Latency)" },
    { key: "index_size", label: "Compact Storage" },
    { key: "cost", label: "Preprocessing Efficiency" },
  ];

  const radarData = radarDimensions.map((dim) => {
    const entry: Record<string, string | number> = { dimension: dim.label };
    top3.forEach((c, idx) => {
      const breakdown = (c.subscores || {}) as Record<string, number>;
      entry[`Rank #${idx + 1}`] = Number(((breakdown[dim.key] ?? 0) * 100).toFixed(1));
    });
    return entry;
  });

  const groundednessRun = false; // Groundedness LLM evaluation is optional and off by default

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span>Multi-Criteria Decision Matrix</span>
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Investigating RQ3: empirical trade-offs between retrieval effectiveness, query latency, preprocessing cost, and storage footprint.
        </p>
      </div>

      {/* Preset Buttons & Weight Sliders */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-6">
        {/* Preset Selector */}
        <div>
          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-2">
            Engineering Presets
          </span>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { id: "Accuracy first", desc: "Prioritizes retrieval quality (0.60 quality)" },
              { id: "Low latency", desc: "Prioritizes real-time query latency (0.45 latency)" },
              { id: "Constrained hardware", desc: "Prioritizes minimal memory/storage (0.35 storage)" },
              { id: "Balanced", desc: "Evenly balanced multi-objective trade-off" },
            ].map((p) => (
              <button
                key={p.id}
                onClick={() => applyPreset(p.id)}
                className="p-3 text-left rounded-lg border border-slate-200 dark:border-slate-800 hover:border-indigo-500 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition"
              >
                <div className="font-semibold text-xs text-slate-900 dark:text-white">{p.id}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{p.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Sliders Grid */}
        <div className="pt-4 border-t border-slate-200 dark:border-slate-800 grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6">
          {/* Quality Slider with Toggle */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-700 dark:text-slate-300">
                Quality Metric
              </span>
              <span className="font-mono font-bold text-indigo-600">{(weights.hit_at_k ?? 0).toFixed(2)}</span>
            </div>
            <div className="flex gap-1 mb-1">
              <button
                type="button"
                onClick={() => setQualityChoice("hit_at_k")}
                className={`flex-1 py-0.5 text-[10px] font-bold rounded ${
                  qualityChoice === "hit_at_k"
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-600"
                }`}
              >
                Hit@5
              </button>
              <button
                type="button"
                onClick={() => setQualityChoice("mrr")}
                className={`flex-1 py-0.5 text-[10px] font-bold rounded ${
                  qualityChoice === "mrr"
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-600"
                }`}
              >
                MRR
              </button>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={weights.hit_at_k ?? 0}
              onChange={(e) => handleSliderChange("hit_at_k", Number(e.target.value))}
              className="w-full accent-indigo-600"
            />
          </div>

          {/* Groundedness Slider (Greyed out if not run) */}
          <div className={`space-y-1.5 ${!groundednessRun ? "opacity-60" : ""}`}>
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-slate-700 dark:text-slate-300">Groundedness</span>
              <span className="font-mono font-bold text-indigo-600">{(weights.groundedness ?? 0).toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              disabled={!groundednessRun}
              value={weights.groundedness ?? 0}
              onChange={(e) => handleSliderChange("groundedness", Number(e.target.value))}
              className="w-full accent-indigo-600 cursor-not-allowed"
            />
            {!groundednessRun && (
              <span className="text-[10px] text-amber-600 dark:text-amber-400 block leading-tight">
                Not evaluated (weight re-normalized)
              </span>
            )}
          </div>

          {/* Latency Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-slate-700 dark:text-slate-300">Query Latency</span>
              <span className="font-mono font-bold text-indigo-600">{(weights.latency ?? 0).toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={weights.latency ?? 0}
              onChange={(e) => handleSliderChange("latency", Number(e.target.value))}
              className="w-full accent-indigo-600"
            />
          </div>

          {/* Preprocessing Cost Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-slate-700 dark:text-slate-300">Prep Cost</span>
              <span className="font-mono font-bold text-indigo-600">{(weights.cost ?? 0).toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={weights.cost ?? 0}
              onChange={(e) => handleSliderChange("cost", Number(e.target.value))}
              className="w-full accent-indigo-600"
            />
            <span className="text-[10px] text-slate-400 block leading-tight">
              Chunk + Embed + Index time
            </span>
          </div>

          {/* Storage Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-slate-700 dark:text-slate-300">Storage / Index Size</span>
              <span className="font-mono font-bold text-indigo-600">{(weights.index_size ?? 0).toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={weights.index_size ?? 0}
              onChange={(e) => handleSliderChange("index_size", Number(e.target.value))}
              className="w-full accent-indigo-600"
            />
          </div>
        </div>
      </div>

      {/* HOW THE SCORE IS COMPUTED MATHEMATICAL PANEL */}
      <div className="bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl p-5 text-xs text-slate-700 dark:text-slate-300 space-y-2">
        <div className="flex items-center gap-1.5 font-bold text-slate-900 dark:text-white text-sm">
          <HelpCircle className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
          <span>How the Composite Utility Score is Computed</span>
        </div>
        <p className="leading-relaxed">
          The decision matrix computes a normalized linear utility score U(c) in [0, 1] for each configuration c:
        </p>
        <div className="p-3 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 font-mono text-[11px] space-y-1">
          <div><strong>Formula:</strong> U(c) = &Sigma; [w&apos;_i &times; x&#770;_i(c)]</div>
          <div><strong>Weight Re-normalization:</strong> w&apos;_i = w_i / (&Sigma; w_j) (when groundedness is omitted, active weights sum strictly to 1.0)</div>
          <div><strong>Higher-is-better (Quality):</strong> x&#770; = (x - x_min) / (x_max - x_min)</div>
          <div><strong>Lower-is-better (Latency, Prep Cost, Storage):</strong> x&#770; = (x_max - x) / (x_max - x_min)</div>
        </div>
      </div>

      {/* Main Grid: Left Ranked Utility Table (7 Cols), Right Radar Chart (5 Cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Table */}
        <div className="lg:col-span-7 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <h3 className="font-bold text-xs uppercase tracking-wider text-slate-500">
              Ranked Composite Utility Scores
            </h3>
            <span className="text-[11px] text-slate-400 font-mono">
              Score Range: [0.000, 1.000]
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-4 py-3 font-sans">Rank</th>
                  <th className="px-4 py-3">Configuration</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3 text-right">Utility Score</th>
                  <th className="px-4 py-3 text-right">Raw {qualityChoice === "hit_at_k" ? "Hit@5" : "MRR"}</th>
                  <th className="px-4 py-3 text-right">Raw Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
                {ranked.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="px-4 py-3 font-bold font-sans">
                      {idx === 0 ? (
                        <span className="text-amber-500 font-bold flex items-center gap-1">
                          <Award className="w-4 h-4" />
                          <span>#1</span>
                        </span>
                      ) : (
                        <span className="text-slate-400">#{idx + 1}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-bold text-slate-900 dark:text-slate-100">
                      {item.config}
                    </td>
                    <td className="px-4 py-3 text-indigo-600 dark:text-indigo-400">
                      {item.model}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-emerald-600 dark:text-emerald-400">
                      {item.total_utility_score.toFixed(3)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {item.raw_metrics && item.raw_metrics.hit_at_k !== undefined
                        ? qualityChoice === "hit_at_k"
                          ? `${(item.raw_metrics.hit_at_k * 100).toFixed(1)}%`
                          : (item.raw_metrics.mrr ?? 0).toFixed(3)
                        : "-"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {item.raw_metrics && item.raw_metrics.mean_latency_ms !== undefined
                        ? `${item.raw_metrics.mean_latency_ms.toFixed(1)} ms`
                        : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Radar Chart for Top 3 */}
        <div className="lg:col-span-5 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 flex flex-col justify-between">
          <div>
            <h3 className="font-bold text-xs uppercase tracking-wider text-slate-500 mb-1">
              Top 3 Configurations Profile
            </h3>
            <p className="text-xs text-slate-400">
              Normalized dimension subscores (0-100%) for the 3 highest ranked configurations.
            </p>
          </div>

          <div className="h-72 w-full my-auto">
            {top3.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#cbd5e1" strokeDasharray="3 3" opacity={0.3} />
                  <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 10 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9 }} />
                  <Radar
                    name={`#1: ${top3[0]?.config}`}
                    dataKey="Rank #1"
                    stroke="#10b981"
                    fill="#10b981"
                    fillOpacity={0.3}
                  />
                  {top3[1] && (
                    <Radar
                      name={`#2: ${top3[1]?.config}`}
                      dataKey="Rank #2"
                      stroke="#6366f1"
                      fill="#6366f1"
                      fillOpacity={0.2}
                    />
                  )}
                  {top3[2] && (
                    <Radar
                      name={`#3: ${top3[2]?.config}`}
                      dataKey="Rank #3"
                      stroke="#f59e0b"
                      fill="#f59e0b"
                      fillOpacity={0.1}
                    />
                  )}
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <RechartsTooltip />
                </RadarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center py-24 text-slate-400 text-xs italic">
                Awaiting completed experiment data...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
