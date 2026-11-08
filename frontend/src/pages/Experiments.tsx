import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Play,
  RotateCcw,
  StopCircle,
  Clock,
  Cpu,
  Layers,
  Terminal,
  CheckCircle,
  AlertTriangle,
  Trash2,
  Check,
} from "lucide-react";
import {
  api,
  ExperimentCreateRequest,
  EstimateRequest,
  ExperimentResponse,
} from "../lib/api";
import { useExperiment } from "../context/ExperimentContext";

const ALL_CONFIGS = [
  { id: "fixed_128_0", label: "Fixed 128 / 0% ov" },
  { id: "fixed_128_15", label: "Fixed 128 / 15% ov" },
  { id: "fixed_256_0", label: "Fixed 256 / 0% ov" },
  { id: "fixed_256_15", label: "Fixed 256 / 15% ov" },
  { id: "fixed_512_0", label: "Fixed 512 / 0% ov" },
  { id: "fixed_512_15", label: "Fixed 512 / 15% ov" },
  { id: "sent_128_0", label: "Sentence 128 / 0 ov" },
  { id: "sent_128_1", label: "Sentence 128 / 1 ov" },
  { id: "sent_256_0", label: "Sentence 256 / 0 ov" },
  { id: "sent_256_1", label: "Sentence 256 / 1 ov" },
  { id: "sent_512_0", label: "Sentence 512 / 0 ov" },
  { id: "sent_512_1", label: "Sentence 512 / 1 ov" },
  { id: "semantic", label: "Semantic (all-MiniLM break)" },
];

const ALL_MODELS = [
  { id: "minilm", label: "all-MiniLM-L6-v2 (384d)" },
  { id: "bge_small", label: "bge-small-en-v1.5 (384d)" },
  { id: "e5_small", label: "e5-small-v2 (384d)" },
];

export const Experiments: React.FC = () => {
  const queryClient = useQueryClient();
  const { experiments, activeExperimentId, setActiveExperimentId, refetch: refetchExperiments } =
    useExperiment();

  // Builder Mode
  const [selectedPreset, setSelectedPreset] = useState<"quick" | "full" | "custom">("quick");
  const [customConfigs, setCustomConfigs] = useState<string[]>(["fixed_256_0", "sent_256_0"]);
  const [customModels, setCustomModels] = useState<string[]>(["minilm", "bge_small"]);
  const [kValue, setKValue] = useState<number>(5);
  const [verifiedOnly, setVerifiedOnly] = useState<boolean>(false);
  const [evalGroundedness, setEvalGroundedness] = useState<boolean>(false);
  const [showGroundednessWarning, setShowGroundednessWarning] = useState<boolean>(false);
  const [expName, setExpName] = useState<string>("");

  // Live Running state
  const runningExp = experiments.find((e) => e.status === "running" || e.status === "queued");

  // SSE & Logs state for active/running experiment
  const [logLines, setLogLines] = useState<string[]>([]);
  const activeExpForLogs = runningExp || experiments[0];

  // Estimate Query
  const estimateReq: EstimateRequest = {
    preset: selectedPreset === "custom" ? undefined : selectedPreset,
    chunk_configs: selectedPreset === "custom" ? customConfigs : undefined,
    models: selectedPreset === "custom" ? customModels : undefined,
    k: kValue,
    verified_only: verifiedOnly,
  };

  const { data: estimate } = useQuery({
    queryKey: ["estimate", estimateReq],
    queryFn: () => api.estimateExperiment(estimateReq),
  });

  // Launch Mutation
  const launchMutation = useMutation({
    mutationFn: (req: ExperimentCreateRequest) => api.createExperiment(req),
    onSuccess: (newExp) => {
      refetchExperiments();
      setActiveExperimentId(newExp.id);
    },
    onError: (err: Error) => {
      alert(`Failed to launch experiment: ${err.message}`);
    },
  });

  // Cancel Mutation
  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.cancelExperiment(id),
    onSuccess: () => refetchExperiments(),
  });

  // Resume Mutation
  const resumeMutation = useMutation({
    mutationFn: (id: string) => api.resumeExperiment(id),
    onSuccess: () => refetchExperiments(),
  });

  // Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteExperiment(id),
    onSuccess: () => refetchExperiments(),
  });

  const handleLaunch = () => {
    const name =
      expName.trim() ||
      `${selectedPreset.toUpperCase()} Run (${new Date().toLocaleTimeString()})`;

    launchMutation.mutate({
      name,
      preset: selectedPreset === "custom" ? undefined : selectedPreset,
      configs: selectedPreset === "custom" ? customConfigs : undefined,
      models: selectedPreset === "custom" ? customModels : undefined,
      k: kValue,
      verified_only: verifiedOnly,
    });
  };

  // SSE Stream Listener
  useEffect(() => {
    if (!runningExp) return;

    const eventSource = new EventSource(`/api/experiments/${runningExp.id}/events`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "log" && data.message) {
          setLogLines((prev) => [...prev.slice(-300), data.message]);
        } else if (data.type === "done" || data.type === "cancelled") {
          refetchExperiments();
          eventSource.close();
        }
      } catch {
        // Raw string message fallback
        setLogLines((prev) => [...prev.slice(-300), event.data]);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [runningExp?.id]);

  // Periodic Log Fetch fallback
  useEffect(() => {
    if (!activeExpForLogs) return;
    const fetchLogs = async () => {
      try {
        const res = await api.getExperimentLogs(activeExpForLogs.id, 50);
        if (res.lines && res.lines.length > 0) {
          setLogLines(res.lines);
        }
      } catch {
        // Silently handle
      }
    };

    fetchLogs();
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, [activeExpForLogs?.id]);

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Page Title */}
      <div>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">Experiment Studio</h2>
        <p className="text-xs text-slate-500 mt-1">
          Configure controlled evaluation grids, stream live progress, and manage experiment runs.
        </p>
      </div>

      {/* Main Grid: Left Config Panel (7 cols), Right Live Runner & Stats (5 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Experiment Builder */}
        <div className="lg:col-span-7 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-6">
          <div className="font-bold text-sm text-slate-900 dark:text-white pb-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <span>Experiment Configuration</span>
            <span className="text-xs font-normal text-slate-500">Controlled benchmark setup</span>
          </div>

          {/* Name */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Experiment Run Name
            </label>
            <input
              type="text"
              value={expName}
              onChange={(e) => setExpName(e.target.value)}
              placeholder="e.g. Quick Validation Run #1"
              className="w-full text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2.5 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Preset Selector */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Execution Grid Preset
            </label>
            <div className="grid grid-cols-3 gap-3">
              <button
                type="button"
                onClick={() => setSelectedPreset("quick")}
                className={`p-3 rounded-lg border text-left transition ${
                  selectedPreset === "quick"
                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-900 dark:text-indigo-200"
                    : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                }`}
              >
                <div className="font-semibold text-xs">Quick Preset</div>
                <div className="text-[11px] text-slate-500 mt-1">2 configs &times; 2 models (4 runs)</div>
              </button>

              <button
                type="button"
                onClick={() => setSelectedPreset("full")}
                className={`p-3 rounded-lg border text-left transition ${
                  selectedPreset === "full"
                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-900 dark:text-indigo-200"
                    : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                }`}
              >
                <div className="font-semibold text-xs">Full Grid</div>
                <div className="text-[11px] text-slate-500 mt-1">9 configs &times; 3 models (27 runs)</div>
              </button>

              <button
                type="button"
                onClick={() => setSelectedPreset("custom")}
                className={`p-3 rounded-lg border text-left transition ${
                  selectedPreset === "custom"
                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-900 dark:text-indigo-200"
                    : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                }`}
              >
                <div className="font-semibold text-xs">Custom Grid</div>
                <div className="text-[11px] text-slate-500 mt-1">Hand-pick configs & models</div>
              </button>
            </div>
          </div>

          {/* Custom Grid Options */}
          {selectedPreset === "custom" && (
            <div className="space-y-4 p-4 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/60">
              {/* Models multi-select */}
              <div>
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1.5">
                  Embedding Models
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {ALL_MODELS.map((m) => {
                    const checked = customModels.includes(m.id);
                    return (
                      <label
                        key={m.id}
                        className={`flex items-center gap-2 p-2 rounded border text-xs cursor-pointer ${
                          checked
                            ? "border-indigo-500 bg-white dark:bg-slate-800 font-medium"
                            : "border-slate-200 dark:border-slate-700 text-slate-500"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) setCustomModels([...customModels, m.id]);
                            else setCustomModels(customModels.filter((id) => id !== m.id));
                          }}
                          className="rounded text-indigo-600"
                        />
                        <span>{m.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Chunking Configs multi-select */}
              <div>
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1.5">
                  Chunking Strategies
                </span>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-48 overflow-y-auto p-1">
                  {ALL_CONFIGS.map((c) => {
                    const checked = customConfigs.includes(c.id);
                    return (
                      <label
                        key={c.id}
                        className={`flex items-center gap-2 p-1.5 rounded border text-xs cursor-pointer ${
                          checked
                            ? "border-indigo-500 bg-white dark:bg-slate-800 font-medium"
                            : "border-slate-200 dark:border-slate-700 text-slate-500"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) setCustomConfigs([...customConfigs, c.id]);
                            else setCustomConfigs(customConfigs.filter((id) => id !== c.id));
                          }}
                          className="rounded text-indigo-600"
                        />
                        <span className="truncate">{c.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Top-k and Controls */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Top-k Cutoff
              </label>
              <select
                value={kValue}
                onChange={(e) => setKValue(Number(e.target.value))}
                className="w-full text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 font-mono"
              >
                <option value={3}>k = 3</option>
                <option value={5}>k = 5 (Standard)</option>
                <option value={10}>k = 10</option>
              </select>
            </div>

            <div className="flex flex-col justify-end space-y-2">
              <label className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={verifiedOnly}
                  onChange={(e) => setVerifiedOnly(e.target.checked)}
                  className="rounded text-indigo-600"
                />
                <span>Verified questions only</span>
              </label>

              <label className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={evalGroundedness}
                  onChange={(e) => {
                    if (e.target.checked) setShowGroundednessWarning(true);
                    setEvalGroundedness(e.target.checked);
                  }}
                  className="rounded text-indigo-600"
                />
                <span>Evaluate Groundedness (LLM Judge)</span>
              </label>
            </div>
          </div>

          {/* Launch Button */}
          <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
            <button
              onClick={handleLaunch}
              disabled={launchMutation.isPending || !!runningExp}
              className={`w-full py-3 rounded-lg text-xs font-bold flex items-center justify-center gap-2 transition shadow-sm ${
                runningExp
                  ? "bg-slate-200 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-700 text-white"
              }`}
            >
              <Play className="w-4 h-4 fill-current" />
              <span>
                {runningExp
                  ? "Experiment Already Running..."
                  : launchMutation.isPending
                  ? "Submitting Job..."
                  : "Start Controlled Experiment"}
              </span>
            </button>
          </div>
        </div>

        {/* Right: Estimation Card & Live Execution Terminal */}
        <div className="lg:col-span-5 space-y-6">
          {/* Estimation Card */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Run Cost & Latency Estimation
            </h3>

            {estimate ? (
              <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
                  <div className="text-[11px] text-slate-500 font-sans">Combinations</div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white mt-0.5">
                    {estimate.total_combinations}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
                  <div className="text-[11px] text-slate-500 font-sans">Total Queries</div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white mt-0.5">
                    {estimate.total_queries}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
                  <div className="text-[11px] text-slate-500 font-sans">Estimated Time</div>
                  <div className="text-xl font-bold text-indigo-600 dark:text-indigo-400 mt-0.5">
                    ~{Math.round(estimate.total_estimated_sec)}s
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60">
                  <div className="text-[11px] text-slate-500 font-sans">Memory Est.</div>
                  <div className="text-xl font-bold text-slate-900 dark:text-white mt-0.5">
                    ~{estimate.estimated_memory_mb} MB
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-400 italic">Calculating estimate...</div>
            )}
          </div>

          {/* Live Runner / Active Run Status */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden flex flex-col h-[380px]">
            <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/30">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                <span className="font-semibold text-xs text-slate-900 dark:text-white">
                  Live Execution Console
                </span>
              </div>
              {runningExp && (
                <button
                  onClick={() => cancelMutation.mutate(runningExp.id)}
                  className="flex items-center gap-1 px-2.5 py-1 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950 dark:hover:bg-rose-900 text-rose-700 dark:text-rose-300 rounded text-[11px] font-semibold transition"
                >
                  <StopCircle className="w-3.5 h-3.5" />
                  <span>Cancel Run</span>
                </button>
              )}
            </div>

            {/* Console Log Lines */}
            <div className="flex-1 p-4 font-mono text-[11px] leading-relaxed bg-slate-950 text-slate-200 overflow-y-auto space-y-1">
              {logLines.length === 0 ? (
                <div className="text-slate-500 italic">Console output will appear here during execution...</div>
              ) : (
                logLines.map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap break-all">
                    {line}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* History Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <h3 className="font-bold text-sm text-slate-900 dark:text-white">Experiment History</h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="px-4 py-3">Run ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Preset</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Questions (V / Unv)</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
              {experiments.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No experiments conducted yet.
                  </td>
                </tr>
              ) : (
                experiments.map((exp) => (
                  <tr key={exp.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="px-4 py-3 font-mono font-medium text-slate-900 dark:text-slate-100">
                      {exp.id.slice(0, 8)}...
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                      {exp.name}
                      {exp.id === activeExperimentId && (
                        <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 font-bold">
                          ACTIVE
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono capitalize">{exp.preset || "Custom"}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                          exp.status === "completed"
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                            : exp.status === "cancelled"
                            ? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                            : exp.status === "running"
                            ? "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 animate-pulse"
                            : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300"
                        }`}
                      >
                        {exp.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {exp.verified_questions_count} / {exp.unverified_questions_count}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {new Date(exp.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {exp.status === "cancelled" && (
                        <button
                          onClick={() => resumeMutation.mutate(exp.id)}
                          className="text-amber-600 dark:text-amber-400 hover:underline font-semibold"
                        >
                          Resume
                        </button>
                      )}
                      <button
                        onClick={() => setActiveExperimentId(exp.id)}
                        className="text-indigo-600 dark:text-indigo-400 hover:underline font-semibold"
                      >
                        Select
                      </button>
                      <button
                        onClick={() => deleteMutation.mutate(exp.id)}
                        className="text-slate-400 hover:text-rose-500 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5 inline" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* GROUNDEDNESS WARNING MODAL */}
      {showGroundednessWarning && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-xl shadow-2xl p-6 border border-slate-200 dark:border-slate-800 space-y-4">
            <h3 className="font-bold text-base text-amber-600 dark:text-amber-400 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              <span>LLM Judge Groundedness Evaluation</span>
            </h3>
            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Evaluating groundedness triggers LLM calls for every question &times; configuration combination
              (up to 1,500+ LLM judge requests). This will consume API tokens or local compute and increase execution time.
            </p>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => {
                  setEvalGroundedness(false);
                  setShowGroundednessWarning(false);
                }}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold hover:bg-slate-200 transition"
              >
                Cancel
              </button>
              <button
                onClick={() => setShowGroundednessWarning(false)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition"
              >
                Proceed With Groundedness
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
