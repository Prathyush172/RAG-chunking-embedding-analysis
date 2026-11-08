import React from "react";
import { Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Database,
  CheckCircle,
  PlaySquare,
  BarChart2,
  GitCompare,
  Compass,
  Sliders,
  Download,
  Settings,
  Sun,
  Moon,
  AlertTriangle,
  Server,
} from "lucide-react";
import { useTheme } from "../../context/ThemeContext";
import { useExperiment } from "../../context/ExperimentContext";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

const NAV_ITEMS = [
  { path: "/", label: "Overview", icon: LayoutDashboard },
  { path: "/dataset", label: "Dataset", icon: Database },
  { path: "/review", label: "Review", icon: CheckCircle },
  { path: "/experiments", label: "Experiments", icon: PlaySquare },
  { path: "/results", label: "Results", icon: BarChart2 },
  { path: "/compare", label: "Compare", icon: GitCompare },
  { path: "/playground", label: "Playground", icon: Compass },
  { path: "/decision-matrix", label: "Decision Matrix", icon: Sliders },
  { path: "/export", label: "Export", icon: Download },
  { path: "/settings", label: "Settings", icon: Settings },
];

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const { experiments, activeExperimentId, setActiveExperimentId, activeExperiment } = useExperiment();

  const { data: health, isError: isHealthError } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    refetchInterval: 15000,
  });

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 font-sans">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 flex flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 select-none">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold tracking-wider shadow-sm">
            RFC
          </div>
          <div>
            <h1 className="font-bold text-sm leading-tight text-slate-900 dark:text-white">
              RFC RAG Lab
            </h1>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Chunking & Retrieval Analysis
            </p>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? "bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-400 font-semibold"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                <Icon className={`w-4 h-4 ${active ? "text-indigo-600 dark:text-indigo-400" : ""}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Sidebar Footer info */}
        <div className="p-3 border-t border-slate-200 dark:border-slate-800 text-xs text-slate-400">
          <div className="flex items-center justify-between">
            <span>RFCs 9293, 1034, 1035, 9110</span>
            <span className="font-mono text-[10px] bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">v1.0</span>
          </div>
        </div>
      </aside>

      {/* Main Container */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Navbar */}
        <header className="h-14 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between px-6 z-10">
          {/* Active Experiment Selector */}
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Active Run:</span>
            {experiments.length === 0 ? (
              <span className="text-xs text-slate-400 italic">No experiments yet</span>
            ) : (
              <select
                value={activeExperimentId || ""}
                onChange={(e) => setActiveExperimentId(e.target.value)}
                className="text-xs font-mono bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-md px-2.5 py-1.5 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {experiments.map((exp) => (
                  <option key={exp.id} value={exp.id}>
                    {exp.name} ({exp.id.slice(0, 8)}... - {exp.status})
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Right Header items */}
          <div className="flex items-center gap-4">
            {/* Health Badge */}
            <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <Server className="w-3.5 h-3.5" />
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  isHealthError || !health ? "bg-rose-500 animate-pulse" : "bg-emerald-500"
                }`}
              />
              <span className="font-mono text-[11px]">
                {isHealthError || !health ? "Offline" : "Backend Ready"}
              </span>
            </div>

            {/* Dark / Light Toggle */}
            <button
              onClick={toggleTheme}
              aria-label="Toggle theme"
              className="p-2 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              {theme === "dark" ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </header>

        {/* Global UNVERIFIED Warning Banner */}
        {activeExperiment && activeExperiment.has_unverified && (
          <div className="bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200 dark:border-amber-800/60 px-6 py-2.5 flex items-center justify-between text-xs text-amber-900 dark:text-amber-200">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
              <span>
                <strong>UNVERIFIED QUESTIONS IN RUN:</strong> This experiment includes{" "}
                <span className="font-semibold underline">
                  {activeExperiment.unverified_questions_count} unverified questions
                </span>{" "}
                (out of {activeExperiment.verified_questions_count + activeExperiment.unverified_questions_count} total).
                Official publication numbers require a verified-only run.
              </span>
            </div>
            <Link
              to="/review"
              className="ml-4 font-semibold text-amber-800 dark:text-amber-300 hover:underline flex-shrink-0"
            >
              Review Questions &rarr;
            </Link>
          </div>
        )}

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
};
