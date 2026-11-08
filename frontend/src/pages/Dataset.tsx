import React, { useState, useRef, useEffect } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  HelpCircle,
  Search,
  CheckCircle,
  AlertCircle,
  Plus,
  Download,
  Upload,
  ArrowRight,
  ExternalLink,
  ChevronRight,
  X,
} from "lucide-react";
import { api, QuestionSchema, QuestionCreateSchema } from "../lib/api";
import { getSelectionOffsets, TextSpan } from "../lib/offsetMapper";

export const Dataset: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  const activeTab = searchParams.get("tab") || "documents";
  const selectedDocId = searchParams.get("doc_id") || "tcp";

  // Tab switcher
  const setTab = (tab: "documents" | "questions") => {
    setSearchParams({ tab, doc_id: selectedDocId });
  };

  const setDocId = (docId: string) => {
    setSearchParams({ tab: activeTab, doc_id: docId });
  };

  // Queries
  const { data: documents = [] } = useQuery({
    queryKey: ["corpus-docs"],
    queryFn: () => api.listDocuments(),
  });

  const { data: docText } = useQuery({
    queryKey: ["doc-text", selectedDocId],
    queryFn: () => api.getDocumentText(selectedDocId),
  });

  const { data: sections = [] } = useQuery({
    queryKey: ["doc-sections", selectedDocId],
    queryFn: () => api.getDocumentSections(selectedDocId),
  });

  const { data: questions = [], isLoading: isLoadingQuestions } = useQuery({
    queryKey: ["questions-list"],
    queryFn: () => api.listQuestions(),
  });

  const { data: validation } = useQuery({
    queryKey: ["questions-validation"],
    queryFn: () => api.validateQuestions(),
  });

  // Local state for Documents tab
  const [docSearchQuery, setDocSearchQuery] = useState("");
  const [selectedSpan, setSelectedSpan] = useState<TextSpan | null>(null);
  const readerRef = useRef<HTMLDivElement>(null);

  // Question Creation Drawer
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<"create" | "view">("create");
  const [viewingQuestion, setViewingQuestion] = useState<QuestionSchema | null>(null);

  // New Question form state
  const [newQuestionText, setNewQuestionText] = useState("");
  const [newRefAnswer, setNewRefAnswer] = useState("");
  const [newType, setNewType] = useState<"factual" | "definition" | "procedural" | "multi-hop">("factual");
  const [newDifficulty, setNewDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [formError, setFormError] = useState<string | null>(null);

  // Questions tab filters
  const [qDocFilter, setQDocFilter] = useState<string>("all");
  const [qVerifiedFilter, setQVerifiedFilter] = useState<string>("all");
  const [qTypeFilter, setQTypeFilter] = useState<string>("all");
  const [qSearchText, setQSearchText] = useState("");

  const currentDoc = documents.find((d) => d.doc_id === selectedDocId);

  // DOM Selection listener in Documents Reader
  const handleMouseUp = () => {
    if (!readerRef.current || !docText) return;
    const span = getSelectionOffsets(readerRef.current, 0, docText.text);
    if (span && span.text.trim().length > 10) {
      setSelectedSpan(span);
    } else {
      setSelectedSpan(null);
    }
  };

  const openCreateWithSelection = () => {
    if (!selectedSpan) return;
    setDrawerMode("create");
    setViewingQuestion(null);
    setNewQuestionText("");
    setNewRefAnswer("");
    setFormError(null);
    setIsDrawerOpen(true);
  };

  const createQuestionMutation = useMutation({
    mutationFn: (data: QuestionCreateSchema) => api.createQuestion(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["questions-list"] });
      queryClient.invalidateQueries({ queryKey: ["review-progress"] });
      queryClient.invalidateQueries({ queryKey: ["questions-validation"] });
      setIsDrawerOpen(false);
      setSelectedSpan(null);
      setTab("questions");
    },
    onError: (err: Error) => {
      setFormError(err.message);
    },
  });

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSpan) {
      setFormError("No evidence quote selected.");
      return;
    }
    if (!newQuestionText.trim() || !newRefAnswer.trim()) {
      setFormError("Question and reference answer cannot be empty.");
      return;
    }

    createQuestionMutation.mutate({
      doc_id: selectedDocId,
      question: newQuestionText.trim(),
      evidence: [
        {
          doc_id: selectedDocId,
          quote: selectedSpan.text,
        },
      ],
      reference_answer: newRefAnswer.trim(),
      type: newType,
      difficulty: newDifficulty,
    });
  };

  // Jump to section in reader
  const jumpToSection = (charStart: number) => {
    if (!readerRef.current || !docText) return;
    const totalChars = docText.text.length;
    const scrollHeight = readerRef.current.scrollHeight;
    const targetScroll = (charStart / totalChars) * scrollHeight;
    readerRef.current.scrollTo({ top: targetScroll - 40, behavior: "smooth" });
  };

  // Filtered questions
  const filteredQuestions = questions.filter((q) => {
    if (qDocFilter !== "all" && q.doc_id !== qDocFilter) return false;
    if (qVerifiedFilter === "verified" && !q.verified) return false;
    if (qVerifiedFilter === "unverified" && q.verified) return false;
    if (qTypeFilter !== "all" && q.type !== qTypeFilter) return false;
    if (qSearchText) {
      const lower = qSearchText.toLowerCase();
      return (
        q.question.toLowerCase().includes(lower) ||
        q.id.toLowerCase().includes(lower) ||
        q.section.toLowerCase().includes(lower)
      );
    }
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Top Header & Tab Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTab("documents")}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition ${
              activeTab === "documents"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>Corpus Documents</span>
          </button>
          <button
            onClick={() => setTab("questions")}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition ${
              activeTab === "questions"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            <HelpCircle className="w-4 h-4" />
            <span>Evaluation Questions ({questions.length})</span>
          </button>
        </div>

        {/* Validation Status Indicator */}
        {validation && (
          <div className="flex items-center gap-2 text-xs">
            {validation.valid ? (
              <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-50 dark:bg-emerald-950/40 px-3 py-1.5 rounded-lg border border-emerald-200 dark:border-emerald-800">
                <CheckCircle className="w-4 h-4" />
                <span>Dataset Valid ({validation.total_questions} questions)</span>
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400 font-medium bg-rose-50 dark:bg-rose-950/40 px-3 py-1.5 rounded-lg border border-rose-200 dark:border-rose-800">
                <AlertCircle className="w-4 h-4" />
                <span>{validation.issues.length} Schema / Span Issues Found</span>
              </span>
            )}
          </div>
        )}
      </div>

      {/* TAB 1: DOCUMENTS VIEWER */}
      {activeTab === "documents" && (
        <div className="space-y-4">
          {/* Document Picker Tabs & Metadata */}
          <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              {documents.map((doc) => (
                <button
                  key={doc.doc_id}
                  onClick={() => setDocId(doc.doc_id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
                    selectedDocId === doc.doc_id
                      ? "bg-slate-900 text-white dark:bg-indigo-600 shadow-sm"
                      : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
                  }`}
                >
                  {doc.doc_id.toUpperCase()} (RFC {doc.rfc_number})
                </button>
              ))}
            </div>

            {currentDoc && (
              <div className="text-xs text-slate-500 flex items-center gap-4">
                <span>
                  <strong>Title:</strong> {currentDoc.title}
                </span>
                <span>
                  <strong>Chars:</strong> {currentDoc.char_count.toLocaleString()}
                </span>
                <span>
                  <strong>Lines:</strong> {currentDoc.line_count.toLocaleString()}
                </span>
              </div>
            )}
          </div>

          {/* Reader Area with Outline Sidebar and Monospaced Text */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 h-[720px]">
            {/* Outline Tree */}
            <div className="lg:col-span-1 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col overflow-hidden">
              <div className="p-3 border-b border-slate-200 dark:border-slate-800 font-semibold text-xs text-slate-700 dark:text-slate-300">
                Section Outline ({sections.length})
              </div>
              <div className="flex-1 overflow-y-auto p-2 space-y-0.5 text-xs font-mono">
                {sections.map((sec, i) => (
                  <button
                    key={i}
                    onClick={() => jumpToSection(sec.char_start)}
                    className="w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 truncate transition flex items-center gap-1.5"
                    title={sec.label}
                  >
                    <ChevronRight className="w-3 h-3 flex-shrink-0 text-slate-400" />
                    <span className="truncate">{sec.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Document Reader Container */}
            <div className="lg:col-span-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col overflow-hidden relative">
              {/* Search Bar & Hint */}
              <div className="p-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-4 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="flex items-center gap-2 flex-1 max-w-sm">
                  <Search className="w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    value={docSearchQuery}
                    onChange={(e) => setDocSearchQuery(e.target.value)}
                    placeholder="Search document text..."
                    className="w-full text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-2 py-1 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div className="text-[11px] text-slate-400 italic">
                  Tip: Highlight text with cursor to extract evidence quote
                </div>
              </div>

              {/* Monospaced Reader */}
              <div
                ref={readerRef}
                onMouseUp={handleMouseUp}
                className="flex-1 overflow-y-auto p-6 font-mono text-xs leading-relaxed whitespace-pre-wrap select-text text-slate-800 dark:text-slate-200 bg-white dark:bg-slate-950"
              >
                {docText ? docText.text : "Loading document text..."}
              </div>

              {/* Floating Action Pill on Selection */}
              {selectedSpan && (
                <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 bg-slate-900 text-white px-4 py-2 rounded-full shadow-2xl border border-slate-700 animate-in fade-in slide-in-from-bottom-2">
                  <span className="text-xs font-mono text-indigo-300">
                    [{selectedSpan.char_start} : {selectedSpan.char_end}] ({selectedSpan.text.length} chars)
                  </span>
                  <button
                    onClick={openCreateWithSelection}
                    className="flex items-center gap-1.5 px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-full text-xs font-semibold transition"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Use selection as question evidence</span>
                  </button>
                  <button
                    onClick={() => setSelectedSpan(null)}
                    className="text-slate-400 hover:text-white"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: QUESTIONS TABLE */}
      {activeTab === "questions" && (
        <div className="space-y-4">
          {/* Controls / Filter Bar */}
          <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              {/* Document Filter */}
              <select
                value={qDocFilter}
                onChange={(e) => setQDocFilter(e.target.value)}
                className="text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5"
              >
                <option value="all">All Documents</option>
                <option value="tcp">TCP (RFC 9293)</option>
                <option value="dns">DNS (RFC 1034)</option>
                <option value="dns_implementation">DNS-Impl (RFC 1035)</option>
                <option value="http">HTTP (RFC 9110)</option>
              </select>

              {/* Verified Filter */}
              <select
                value={qVerifiedFilter}
                onChange={(e) => setQVerifiedFilter(e.target.value)}
                className="text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5"
              >
                <option value="all">All Verification States</option>
                <option value="verified">Verified Only</option>
                <option value="unverified">Unverified Only</option>
              </select>

              {/* Type Filter */}
              <select
                value={qTypeFilter}
                onChange={(e) => setQTypeFilter(e.target.value)}
                className="text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5"
              >
                <option value="all">All Types</option>
                <option value="factual">Factual</option>
                <option value="definition">Definition</option>
                <option value="procedural">Procedural</option>
                <option value="multi-hop">Multi-Hop</option>
              </select>

              {/* Search text */}
              <input
                type="text"
                placeholder="Search questions..."
                value={qSearchText}
                onChange={(e) => setQSearchText(e.target.value)}
                className="text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 w-48 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <a
                href={api.exportQuestionsCsvUrl()}
                download="questions_review.csv"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-medium transition"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export CSV</span>
              </a>

              <label className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-medium transition cursor-pointer">
                <Upload className="w-3.5 h-3.5" />
                <span>Import CSV</span>
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      try {
                        await api.importQuestionsCsv(file);
                        queryClient.invalidateQueries({ queryKey: ["questions-list"] });
                        queryClient.invalidateQueries({ queryKey: ["review-progress"] });
                      } catch (err: unknown) {
                        alert(err instanceof Error ? err.message : String(err));
                      }
                    }
                  }}
                />
              </label>

              <button
                onClick={() => {
                  setDrawerMode("create");
                  setViewingQuestion(null);
                  setSelectedSpan(null);
                  setIsDrawerOpen(true);
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-medium transition shadow-sm"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Question</span>
              </button>
            </div>
          </div>

          {/* Questions Table */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Doc</th>
                    <th className="px-4 py-3">Question</th>
                    <th className="px-4 py-3">Derived Section</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Diff</th>
                    <th className="px-4 py-3">Overlap (Run / Jac)</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
                  {isLoadingQuestions ? (
                    <tr>
                      <td colSpan={9} className="px-4 py-8 text-center text-slate-400">
                        Loading questions...
                      </td>
                    </tr>
                  ) : filteredQuestions.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-4 py-8 text-center text-slate-400">
                        No questions match the current filters.
                      </td>
                    </tr>
                  ) : (
                    filteredQuestions.map((q) => (
                      <tr key={q.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                        <td className="px-4 py-3 font-mono font-medium text-slate-900 dark:text-slate-100">
                          {q.id}
                        </td>
                        <td className="px-4 py-3 font-mono text-indigo-600 dark:text-indigo-400">
                          {q.doc_id}
                        </td>
                        <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100 max-w-xs truncate">
                          {q.question}
                        </td>
                        <td className="px-4 py-3 text-slate-500 font-mono text-[11px] max-w-[180px] truncate" title={q.section}>
                          {q.section}
                        </td>
                        <td className="px-4 py-3 capitalize text-slate-600 dark:text-slate-400">
                          {q.type}
                        </td>
                        <td className="px-4 py-3 capitalize text-slate-600 dark:text-slate-400">
                          {q.difficulty}
                        </td>
                        <td className="px-4 py-3 font-mono text-[11px]">
                          {q.lexical_overlap_run} words / {q.lexical_overlap_jaccard.toFixed(2)}
                          {q.flagged_too_easy && (
                            <span className="ml-1 text-rose-500 font-bold" title="Flagged: too easy overlap">
                              *
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {q.verified ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                              <CheckCircle className="w-3 h-3" />
                              <span>Verified</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                              <span>Unverified</span>
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => {
                              setDrawerMode("view");
                              setViewingQuestion(q);
                              setIsDrawerOpen(true);
                            }}
                            className="text-indigo-600 dark:text-indigo-400 hover:underline font-medium text-xs"
                          >
                            Details &rarr;
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* QUESTION DRAWER (Create / View) */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-lg bg-white dark:bg-slate-900 h-full shadow-2xl p-6 overflow-y-auto flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
                <h3 className="font-bold text-base text-slate-900 dark:text-white">
                  {drawerMode === "create" ? "Add Evaluation Question" : `Question ${viewingQuestion?.id}`}
                </h3>
                <button onClick={() => setIsDrawerOpen(false)} className="text-slate-400 hover:text-slate-600">
                  <X className="w-5 h-5" />
                </button>
              </div>

              {drawerMode === "create" ? (
                <form onSubmit={handleCreateSubmit} className="mt-4 space-y-4">
                  {formError && (
                    <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/50 border border-rose-200 text-rose-800 dark:text-rose-300 text-xs">
                      {formError}
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Target RFC Document
                    </label>
                    <input
                      type="text"
                      disabled
                      value={selectedDocId}
                      className="w-full text-xs font-mono bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-600 dark:text-slate-400"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Evidence Quote (Verbatim from RFC)
                    </label>
                    <textarea
                      rows={3}
                      value={selectedSpan ? selectedSpan.text : ""}
                      readOnly
                      placeholder="Select text in the document viewer first..."
                      className="w-full text-xs font-mono bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-800 dark:text-slate-200 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Question (Paraphrased, realistic phrasing)
                    </label>
                    <textarea
                      rows={2}
                      value={newQuestionText}
                      onChange={(e) => setNewQuestionText(e.target.value)}
                      placeholder="e.g. How does TCP establish an initial sequence number?"
                      className="w-full text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Reference Answer (Derived strictly from evidence)
                    </label>
                    <textarea
                      rows={2}
                      value={newRefAnswer}
                      onChange={(e) => setNewRefAnswer(e.target.value)}
                      placeholder="e.g. TCP uses a clock-driven 32-bit counter..."
                      className="w-full text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        Type
                      </label>
                      <select
                        value={newType}
                        onChange={(e) => setNewType(e.target.value as any)}
                        className="w-full text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2"
                      >
                        <option value="factual">Factual</option>
                        <option value="definition">Definition</option>
                        <option value="procedural">Procedural</option>
                        <option value="multi-hop">Multi-Hop</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        Difficulty
                      </label>
                      <select
                        value={newDifficulty}
                        onChange={(e) => setNewDifficulty(e.target.value as any)}
                        className="w-full text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2"
                      >
                        <option value="easy">Easy</option>
                        <option value="medium">Medium</option>
                        <option value="hard">Hard</option>
                      </select>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={createQuestionMutation.isPending}
                    className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition shadow-sm mt-4"
                  >
                    {createQuestionMutation.isPending ? "Validating & Creating..." : "Save Question"}
                  </button>
                </form>
              ) : (
                viewingQuestion && (
                  <div className="mt-4 space-y-4 text-xs">
                    <div>
                      <span className="font-semibold text-slate-500">Question:</span>
                      <p className="font-medium text-slate-900 dark:text-slate-100 mt-1">
                        {viewingQuestion.question}
                      </p>
                    </div>

                    <div>
                      <span className="font-semibold text-slate-500">Derived Section:</span>
                      <p className="font-mono text-slate-700 dark:text-slate-300 mt-1">
                        {viewingQuestion.section}
                      </p>
                    </div>

                    <div>
                      <span className="font-semibold text-slate-500">Reference Answer:</span>
                      <p className="text-slate-700 dark:text-slate-300 mt-1 bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-lg border border-slate-200 dark:border-slate-700">
                        {viewingQuestion.reference_answer}
                      </p>
                    </div>

                    <div>
                      <span className="font-semibold text-slate-500">Evidence Quotes:</span>
                      <div className="space-y-2 mt-1">
                        {viewingQuestion.evidence.map((ev, idx) => (
                          <div
                            key={idx}
                            className="p-2.5 rounded-lg bg-indigo-50/50 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-800/60 font-mono text-[11px]"
                          >
                            <div className="text-indigo-600 dark:text-indigo-400 font-semibold mb-1">
                              Doc: {ev.doc_id} [{ev.char_start} : {ev.char_end}]
                            </div>
                            <div className="text-slate-800 dark:text-slate-200 whitespace-pre-wrap">
                              "{ev.quote}"
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
                      <div>
                        <span className="font-semibold text-slate-500">Overlap Run:</span>
                        <div className="font-mono">{viewingQuestion.lexical_overlap_run} words</div>
                      </div>
                      <div>
                        <span className="font-semibold text-slate-500">Overlap Jaccard:</span>
                        <div className="font-mono">{viewingQuestion.lexical_overlap_jaccard.toFixed(3)}</div>
                      </div>
                      <div>
                        <span className="font-semibold text-slate-500">Verification:</span>
                        <div>{viewingQuestion.verified ? "Verified (Human)" : "Unverified (LLM Draft)"}</div>
                      </div>
                      <div>
                        <span className="font-semibold text-slate-500">Reviewer:</span>
                        <div>{viewingQuestion.reviewer || "None"}</div>
                      </div>
                    </div>

                    <div className="pt-4">
                      <Link
                        to={`/review?id=${viewingQuestion.id}`}
                        className="inline-flex items-center justify-center gap-1.5 w-full py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition"
                      >
                        <span>Open in Sequential Reviewer</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
