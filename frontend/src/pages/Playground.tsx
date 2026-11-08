import React, { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Compass,
  Search,
  Plus,
  Trash2,
  Sparkles,
  Layers,
  CheckCircle,
  AlertTriangle,
  Clock,
  Loader2,
} from "lucide-react";
import {
  api,
  PlaygroundQueryRequest,
  MultiPlaygroundResponse,
  SinglePlaygroundResponse,
} from "../lib/api";

const SAMPLE_QUERIES = [
  "How does TCP select and establish an initial sequence number?",
  "What format and fields are defined for DNS resource records?",
  "When does an HTTP server respond with 206 Partial Content?",
  "How are TCP connection socket pairs and incarnations identified?",
  "Explain the difference between authoritative and recursive DNS lookups.",
];

interface PlaygroundConfigSlot {
  chunk_config: string;
  model_id: string;
}

export const Playground: React.FC = () => {
  const [query, setQuery] = useState(SAMPLE_QUERIES[0]);
  const [kValue, setKValue] = useState(3);
  const [configs, setConfigs] = useState<PlaygroundConfigSlot[]>([
    { chunk_config: "fixed_256_0", model_id: "minilm" },
    { chunk_config: "sent_256_0", model_id: "bge_small" },
  ]);

  const addConfigSlot = () => {
    if (configs.length < 3) {
      setConfigs([...configs, { chunk_config: "semantic", model_id: "minilm" }]);
    }
  };

  const removeConfigSlot = (idx: number) => {
    if (configs.length > 1) {
      setConfigs(configs.filter((_, i) => i !== idx));
    }
  };

  const updateConfigSlot = (idx: number, field: keyof PlaygroundConfigSlot, val: string) => {
    const updated = [...configs];
    updated[idx] = { ...updated[idx], [field]: val };
    setConfigs(updated);
  };

  // Mutation
  const queryMutation = useMutation({
    mutationFn: (req: PlaygroundQueryRequest) => api.queryPlayground(req),
  });

  const handleExecute = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    queryMutation.mutate({
      query: query.trim(),
      configs: configs.map((c) => ({
        chunk_config: c.chunk_config,
        model_id: c.model_id,
      })),
      k: kValue,
    });
  };

  // Parse result blocks
  const resultData = queryMutation.data as MultiPlaygroundResponse | undefined;
  const blocks = resultData?.results || [];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span>Retrieval Playground</span>
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Execute arbitrary technical queries against live FAISS indexes and observe retrieval differences side by side.
        </p>
      </div>

      {/* Query Form & Configuration Bar */}
      <form
        onSubmit={handleExecute}
        className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4"
      >
        {/* Query Input */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
            Technical Search Query
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter question or query..."
              className="flex-1 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2.5 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-medium"
            />
            <button
              type="submit"
              disabled={queryMutation.isPending}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center gap-2 transition shadow-sm"
            >
              {queryMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Retrieving...</span>
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  <span>Run Retrieval</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Sample queries pill picker */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-400 text-[11px] font-medium">Sample Queries:</span>
          {SAMPLE_QUERIES.map((sq, i) => (
            <button
              type="button"
              key={i}
              onClick={() => setQuery(sq)}
              className="text-[11px] px-2.5 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition"
            >
              {sq.slice(0, 38)}...
            </button>
          ))}
        </div>

        {/* Configurations Picker (up to 3) */}
        <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
              Active Configurations to Compare (Up to 3)
            </span>
            {configs.length < 3 && (
              <button
                type="button"
                onClick={addConfigSlot}
                className="text-xs text-indigo-600 dark:text-indigo-400 font-semibold flex items-center gap-1 hover:underline"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Configuration Slot</span>
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {configs.map((cfg, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/60 relative space-y-2"
              >
                <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500">
                  <span>Slot #{idx + 1}</span>
                  {configs.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeConfigSlot(idx)}
                      className="text-slate-400 hover:text-rose-500"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                <div className="space-y-2">
                  <div>
                    <label className="block text-[10px] uppercase font-bold text-slate-400 mb-0.5">
                      Strategy
                    </label>
                    <select
                      value={cfg.chunk_config}
                      onChange={(e) => updateConfigSlot(idx, "chunk_config", e.target.value)}
                      className="w-full text-xs font-mono bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded p-1.5"
                    >
                      <option value="fixed_128_0">fixed_128_0</option>
                      <option value="fixed_256_0">fixed_256_0</option>
                      <option value="fixed_512_0">fixed_512_0</option>
                      <option value="sent_128_0">sent_128_0</option>
                      <option value="sent_256_0">sent_256_0</option>
                      <option value="sent_512_0">sent_512_0</option>
                      <option value="semantic">semantic</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase font-bold text-slate-400 mb-0.5">
                      Model
                    </label>
                    <select
                      value={cfg.model_id}
                      onChange={(e) => updateConfigSlot(idx, "model_id", e.target.value)}
                      className="w-full text-xs font-mono bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded p-1.5"
                    >
                      <option value="minilm">minilm</option>
                      <option value="bge_small">bge_small</option>
                      <option value="e5_small">e5_small</option>
                    </select>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </form>

      {/* Side-by-Side Results Display */}
      {blocks.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {blocks.map((block, bIdx) => (
            <div
              key={bIdx}
              className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col overflow-hidden"
            >
              {/* Block Header */}
              <div className="p-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="font-mono font-bold text-xs text-slate-900 dark:text-white">
                  {block.chunk_config} + {block.model_id}
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-0.5 flex items-center justify-between">
                  <span>Latency: {block.latency_ms.toFixed(1)} ms</span>
                  {block.status === "building" && (
                    <span className="text-amber-500 font-bold flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      <span>Building Index...</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Retrieved Chunks list */}
              <div className="flex-1 p-4 space-y-3 overflow-y-auto max-h-[600px]">
                {block.results.map((chunk, cIdx) => (
                  <div
                    key={cIdx}
                    className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 text-xs space-y-2"
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                        Rank #{chunk.rank}
                      </span>
                      <span className="font-mono text-slate-500">
                        Score: {chunk.score.toFixed(4)}
                      </span>
                    </div>

                    <div className="text-[11px] font-mono text-slate-500 truncate" title={chunk.section}>
                      <strong>Doc:</strong> {chunk.doc_id.toUpperCase()} | <strong>Sec:</strong> {chunk.section}
                    </div>

                    <div className="font-mono text-[11px] leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap bg-white dark:bg-slate-900 p-2 rounded border border-slate-200 dark:border-slate-800">
                      {chunk.text}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
