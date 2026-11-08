import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Settings as SettingsIcon,
  Save,
  Trash2,
  Key,
  Shield,
  Server,
  Database,
  CheckCircle,
} from "lucide-react";
import { api, SettingsSchema } from "../lib/api";

export const Settings: React.FC = () => {
  const queryClient = useQueryClient();

  const { data: settingsData } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const { data: healthData } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
  });

  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-4o-mini");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);

  useEffect(() => {
    if (settingsData) {
      setProvider(settingsData.llm_judge_provider);
      setModel(settingsData.llm_judge_model);
      setApiKeyInput(""); // API key is masked as ******** by default
    }
  }, [settingsData]);

  const updateMutation = useMutation({
    mutationFn: (data: SettingsSchema) => api.updateSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    },
    onError: (err: Error) => {
      alert(`Failed to save settings: ${err.message}`);
    },
  });

  const clearCacheMutation = useMutation({
    mutationFn: (which: "faiss" | "llm" | "all") => api.clearCache(which),
    onSuccess: (res) => {
      setCacheMessage(res.message);
      setTimeout(() => setCacheMessage(null), 3000);
    },
  });

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    updateMutation.mutate({
      llm_judge_provider: provider,
      llm_judge_model: model,
      llm_judge_api_key: apiKeyInput ? apiKeyInput.trim() : undefined,
    });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <span>Settings & Diagnostics</span>
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Configure external LLM judge credentials, manage vector caches, and inspect backend status.
        </p>
      </div>

      {/* LLM Judge Configuration Card */}
      <form
        onSubmit={handleSave}
        className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4"
      >
        <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
          <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
            <Key className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            <span>LLM Judge Configuration (Groundedness Evaluation)</span>
          </h3>
          <span className="text-[11px] text-slate-400 font-mono flex items-center gap-1">
            <Shield className="w-3.5 h-3.5 text-emerald-500" />
            <span>Write-Only Keys (Never Exposed)</span>
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Provider
            </label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="w-full text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-900 dark:text-slate-100"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="gemini">Google Gemini</option>
              <option value="ollama">Ollama / Local</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Model Identifier
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gpt-4o-mini"
              className="w-full text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-900 dark:text-slate-100"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
            API Key
          </label>
          <input
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder={settingsData?.llm_judge_api_key || "Leave blank to keep existing key"}
            className="w-full text-xs font-mono bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-900 dark:text-slate-100"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Keys are encrypted/masked in transit and storage and are never returned by the API.
          </p>
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-slate-200 dark:border-slate-800">
          {saveSuccess ? (
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1.5">
              <CheckCircle className="w-4 h-4" />
              <span>Settings updated successfully!</span>
            </span>
          ) : (
            <span />
          )}

          <button
            type="submit"
            disabled={updateMutation.isPending}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center gap-2 transition"
          >
            <Save className="w-4 h-4" />
            <span>Save Settings</span>
          </button>
        </div>
      </form>

      {/* Cache Invalidation Card */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
          <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
            <Database className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            <span>Disk Cache Management</span>
          </h3>
          {cacheMessage && (
            <span className="text-xs text-emerald-600 font-semibold">{cacheMessage}</span>
          )}
        </div>

        <p className="text-xs text-slate-500">
          FAISS vector indexes and judge evaluation answers are stored with SHA-256 hashes under{" "}
          <code>artifacts/indexes/</code> and <code>artifacts/llm_cache/</code>.
        </p>

        <div className="flex flex-wrap items-center gap-3 pt-2">
          <button
            onClick={() => clearCacheMutation.mutate("faiss")}
            disabled={clearCacheMutation.isPending}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold transition"
          >
            Clear FAISS Index Cache
          </button>
          <button
            onClick={() => clearCacheMutation.mutate("llm")}
            disabled={clearCacheMutation.isPending}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold transition"
          >
            Clear LLM Response Cache
          </button>
          <button
            onClick={() => clearCacheMutation.mutate("all")}
            disabled={clearCacheMutation.isPending}
            className="px-4 py-2 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950 dark:hover:bg-rose-900 text-rose-700 dark:text-rose-300 rounded-lg text-xs font-semibold transition flex items-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear All Caches</span>
          </button>
        </div>
      </div>

      {/* Backend Environment Diagnostics Card */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-3">
        <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
          <Server className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          <span>System & Backend Diagnostics</span>
        </h3>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono pt-2">
          <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg border border-slate-200 dark:border-slate-700/60">
            <div className="text-[11px] text-slate-500 font-sans">Backend Status</div>
            <div className="font-bold text-emerald-600 mt-0.5">
              {healthData?.status || "Connecting..."}
            </div>
          </div>

          <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg border border-slate-200 dark:border-slate-700/60">
            <div className="text-[11px] text-slate-500 font-sans">Active Models</div>
            <div className="font-bold text-slate-900 dark:text-white mt-0.5">
              {healthData?.models?.length || 3}
            </div>
          </div>

          <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg border border-slate-200 dark:border-slate-700/60">
            <div className="text-[11px] text-slate-500 font-sans">Clean Documents</div>
            <div className="font-bold text-slate-900 dark:text-white mt-0.5">
              {healthData?.docs?.length || 4}
            </div>
          </div>

          <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg border border-slate-200 dark:border-slate-700/60">
            <div className="text-[11px] text-slate-500 font-sans">Questions Pool</div>
            <div className="font-bold text-slate-900 dark:text-white mt-0.5">
              {healthData?.questions_count || 56}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
