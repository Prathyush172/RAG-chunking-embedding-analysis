import React, { useState, useEffect, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  X,
  Edit2,
  ChevronRight,
  User,
  AlertTriangle,
  FileText,
  Save,
  Undo2,
} from "lucide-react";
import { api, QuestionSchema, QuestionReviewRequest } from "../lib/api";

export const Review: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // Reviewer Name persisted in localStorage
  const [reviewerName, setReviewerName] = useState(() => {
    return localStorage.getItem("rfclab_reviewer_name") || "Human Evaluator";
  });

  const handleReviewerChange = (val: string) => {
    setReviewerName(val);
    localStorage.setItem("rfclab_reviewer_name", val);
  };

  // Queries
  const { data: questions = [], isLoading: isLoadingQuestions } = useQuery({
    queryKey: ["questions-list"],
    queryFn: () => api.listQuestions(),
  });

  const { data: reviewProgress } = useQuery({
    queryKey: ["review-progress"],
    queryFn: () => api.getReviewProgress(),
  });

  // Current active question ID
  const paramId = searchParams.get("id");
  const currentQuestion: QuestionSchema | null =
    (paramId ? questions.find((q) => q.id === paramId) : null) ||
    questions.find((q) => !q.verified) ||
    questions[0] ||
    null;

  // Active question document text for evidence highlighting
  const { data: docTextData } = useQuery({
    queryKey: ["doc-text", currentQuestion?.doc_id],
    queryFn: () => (currentQuestion?.doc_id ? api.getDocumentText(currentQuestion.doc_id) : null),
    enabled: !!currentQuestion?.doc_id,
  });

  // Edit Mode state
  const [isEditing, setIsEditing] = useState(false);
  const [editedQuestionText, setEditedQuestionText] = useState("");
  const [editedRefAnswer, setEditedRefAnswer] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");

  // Reject Modal state
  const [isRejectOpen, setIsRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("Evidence not uniquely decisive or question flawed");

  const evidenceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentQuestion) {
      setEditedQuestionText(currentQuestion.question);
      setEditedRefAnswer(currentQuestion.reference_answer);
      setReviewNotes(currentQuestion.notes || "");
      setIsEditing(false);
    }
  }, [currentQuestion?.id]);

  // Scroll to evidence highlight when doc text or question changes
  useEffect(() => {
    if (evidenceRef.current) {
      evidenceRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [currentQuestion?.id, docTextData]);

  // Review Mutation
  const reviewMutation = useMutation({
    mutationFn: ({ qid, data }: { qid: string; data: QuestionReviewRequest }) =>
      api.reviewQuestion(qid, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["questions-list"] });
      queryClient.invalidateQueries({ queryKey: ["review-progress"] });
      queryClient.invalidateQueries({ queryKey: ["questions-validation"] });
      queryClient.invalidateQueries({ queryKey: ["question-stats"] });
      goToNext();
    },
    onError: (err: Error) => {
      alert(`Review action failed: ${err.message}`);
    },
  });

  const goToNext = () => {
    if (!currentQuestion) return;
    const currentIndex = questions.findIndex((q) => q.id === currentQuestion.id);
    // Find next unverified
    const nextUnverified = questions.slice(currentIndex + 1).find((q) => !q.verified);
    if (nextUnverified) {
      setSearchParams({ id: nextUnverified.id });
    } else {
      // Wrap around or pick next in list
      const nextQ = questions[(currentIndex + 1) % questions.length];
      if (nextQ) setSearchParams({ id: nextQ.id });
    }
  };

  const handleApprove = () => {
    if (!currentQuestion) return;
    reviewMutation.mutate({
      qid: currentQuestion.id,
      data: {
        verdict: "approve",
        reviewer: reviewerName.trim() || "Human Evaluator",
        notes: reviewNotes.trim() || undefined,
      },
    });
  };

  const handleSaveEdit = () => {
    if (!currentQuestion) return;
    reviewMutation.mutate({
      qid: currentQuestion.id,
      data: {
        verdict: "edit",
        reviewer: reviewerName.trim() || "Human Evaluator",
        question: editedQuestionText.trim(),
        reference_answer: editedRefAnswer.trim(),
        notes: reviewNotes.trim() || undefined,
      },
    });
    setIsEditing(false);
  };

  const handleConfirmReject = () => {
    if (!currentQuestion) return;
    reviewMutation.mutate({
      qid: currentQuestion.id,
      data: {
        verdict: "reject",
        reviewer: reviewerName.trim() || "Human Evaluator",
        notes: rejectReason.trim() || "Rejected by human reviewer",
      },
    });
    setIsRejectOpen(false);
  };

  // Global Keyboard Shortcuts (A, E, R, N)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger hotkeys if typing inside an input or textarea
      if (
        ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName) ||
        isEditing ||
        isRejectOpen
      ) {
        return;
      }

      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        handleApprove();
      } else if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        setIsEditing(true);
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        setIsRejectOpen(true);
      } else if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        goToNext();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentQuestion, reviewerName, reviewNotes, isEditing, isRejectOpen, questions]);

  if (isLoadingQuestions) {
    return <div className="text-center py-16 text-slate-400">Loading evaluation questions...</div>;
  }

  if (!currentQuestion) {
    return (
      <div className="max-w-xl mx-auto text-center py-16 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-8">
        <Check className="w-12 h-12 text-emerald-500 mx-auto mb-4" />
        <h3 className="text-lg font-bold text-slate-900 dark:text-white">All Questions Reviewed!</h3>
        <p className="text-sm text-slate-500 mt-2">
          Every evaluation question has been human verified. You are ready to run publication-grade experiments.
        </p>
        <button
          onClick={() => navigate("/experiments")}
          className="mt-6 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition"
        >
          Launch Experiment &rarr;
        </button>
      </div>
    );
  }

  // Calculate text splitting for evidence highlight
  const firstEvidence = currentQuestion.evidence[0];
  const charStart = firstEvidence?.char_start ?? -1;
  const charEnd = firstEvidence?.char_end ?? -1;
  const fullText = docTextData?.text || "";

  let beforeHighlight = "";
  let highlightText = "";
  let afterHighlight = "";

  if (charStart >= 0 && charEnd > charStart && fullText.length >= charEnd) {
    beforeHighlight = fullText.slice(Math.max(0, charStart - 1200), charStart);
    highlightText = fullText.slice(charStart, charEnd);
    afterHighlight = fullText.slice(charEnd, Math.min(fullText.length, charEnd + 1200));
  } else {
    highlightText = firstEvidence?.quote || "";
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Top Review Bar & Progress */}
      <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Progress status */}
        <div className="flex-1 max-w-md">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              Review Progress: {reviewProgress?.verified ?? 0} of {reviewProgress?.total ?? 56} verified
            </span>
            <span className="font-mono text-indigo-600 dark:text-indigo-400 font-bold">
              {reviewProgress?.percent_complete ?? 0}%
            </span>
          </div>
          <div className="w-full bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="bg-emerald-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${reviewProgress?.percent_complete ?? 0}%` }}
            />
          </div>
        </div>

        {/* Reviewer Name Input */}
        <div className="flex items-center gap-2">
          <User className="w-4 h-4 text-slate-400" />
          <span className="text-xs text-slate-500 font-medium">Reviewer:</span>
          <input
            type="text"
            value={reviewerName}
            onChange={(e) => handleReviewerChange(e.target.value)}
            className="text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1 text-slate-900 dark:text-slate-100 font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Your Name"
          />
        </div>
      </div>

      {/* Main Review Two-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Question Details & Form (5 Cols) */}
        <div className="lg:col-span-5 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 flex flex-col justify-between">
          <div className="space-y-4">
            {/* Header info */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
              <div>
                <span className="font-mono font-bold text-base text-slate-900 dark:text-white">
                  {currentQuestion.id}
                </span>
                <span className="ml-2 px-2 py-0.5 rounded text-[11px] font-mono bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 font-semibold uppercase">
                  {currentQuestion.doc_id}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium capitalize px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                  {currentQuestion.type}
                </span>
                <span className="text-xs font-medium capitalize px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                  {currentQuestion.difficulty}
                </span>
              </div>
            </div>

            {/* Derived Section */}
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Derived Section
              </span>
              <div className="font-mono text-xs text-slate-800 dark:text-slate-200 mt-0.5">
                {currentQuestion.section}
              </div>
            </div>

            {/* Lexical Overlap Stats & Too Easy Warning */}
            <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Lexical Overlap:</span>
                <span className="font-mono font-medium">
                  {currentQuestion.lexical_overlap_run} words run / {currentQuestion.lexical_overlap_jaccard.toFixed(3)} Jaccard
                </span>
              </div>
              {currentQuestion.flagged_too_easy && (
                <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400 mt-2 text-[11px] font-semibold">
                  <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>Flagged as Too Easy (lexical overlap run &ge; 5 or Jaccard &gt; 0.5)</span>
                </div>
              )}
            </div>

            {/* Question Text */}
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                Question
              </label>
              {isEditing ? (
                <textarea
                  rows={3}
                  value={editedQuestionText}
                  onChange={(e) => setEditedQuestionText(e.target.value)}
                  className="w-full text-xs bg-white dark:bg-slate-800 border border-indigo-400 rounded-lg p-2.5 text-slate-900 dark:text-slate-100 focus:outline-none"
                />
              ) : (
                <p className="text-sm font-semibold text-slate-900 dark:text-white leading-snug">
                  {currentQuestion.question}
                </p>
              )}
            </div>

            {/* Reference Answer */}
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                Reference Answer
              </label>
              {isEditing ? (
                <textarea
                  rows={3}
                  value={editedRefAnswer}
                  onChange={(e) => setEditedRefAnswer(e.target.value)}
                  className="w-full text-xs bg-white dark:bg-slate-800 border border-indigo-400 rounded-lg p-2.5 text-slate-900 dark:text-slate-100 focus:outline-none"
                />
              ) : (
                <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-800/40 p-3 rounded-lg border border-slate-200 dark:border-slate-800">
                  {currentQuestion.reference_answer}
                </p>
              )}
            </div>

            {/* Review Notes */}
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                Review Notes (Optional)
              </label>
              <input
                type="text"
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)}
                placeholder="e.g. Verified against Section 3.4.1"
                className="w-full text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="pt-6 border-t border-slate-200 dark:border-slate-800 mt-6 space-y-3">
            {isEditing ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSaveEdit}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition"
                >
                  <Save className="w-4 h-4" />
                  <span>Save Edits</span>
                </button>
                <button
                  onClick={() => setIsEditing(false)}
                  className="px-4 py-2.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold hover:bg-slate-200 transition"
                >
                  <Undo2 className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-4 gap-2">
                <button
                  onClick={handleApprove}
                  className="flex items-center justify-center gap-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition shadow-sm"
                  title="Hotkey: A"
                >
                  <Check className="w-4 h-4" />
                  <span>Approve [A]</span>
                </button>

                <button
                  onClick={() => setIsEditing(true)}
                  className="flex items-center justify-center gap-1 py-2.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 rounded-lg text-xs font-semibold transition"
                  title="Hotkey: E"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                  <span>Edit [E]</span>
                </button>

                <button
                  onClick={() => setIsRejectOpen(true)}
                  className="flex items-center justify-center gap-1 py-2.5 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/60 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-300 rounded-lg text-xs font-semibold transition"
                  title="Hotkey: R"
                >
                  <X className="w-4 h-4" />
                  <span>Reject [R]</span>
                </button>

                <button
                  onClick={goToNext}
                  className="flex items-center justify-center gap-1 py-2.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold transition"
                  title="Hotkey: N"
                >
                  <span>Skip [N]</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: RFC Context & Gold Evidence Highlight (7 Cols) */}
        <div className="lg:col-span-7 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col overflow-hidden h-[720px]">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/30">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              <span className="font-semibold text-xs text-slate-800 dark:text-slate-200">
                Ground-Truth Passage in {currentQuestion.doc_id.toUpperCase()}
              </span>
            </div>
            <div className="font-mono text-[11px] text-slate-500">
              Offset [{charStart} : {charEnd}]
            </div>
          </div>

          {/* Passage Reader with highlight */}
          <div className="flex-1 overflow-y-auto p-6 font-mono text-xs leading-relaxed whitespace-pre-wrap select-text text-slate-800 dark:text-slate-200 bg-white dark:bg-slate-950">
            {charStart >= 0 ? (
              <>
                <span className="text-slate-400 dark:text-slate-600">{beforeHighlight}</span>
                <mark
                  ref={evidenceRef}
                  className="bg-amber-200 text-slate-900 dark:bg-amber-900/60 dark:text-amber-100 font-bold px-1 py-0.5 rounded shadow-sm border border-amber-300 dark:border-amber-700 inline"
                >
                  {highlightText}
                </mark>
                <span className="text-slate-400 dark:text-slate-600">{afterHighlight}</span>
              </>
            ) : (
              <div className="p-4 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 text-amber-900 dark:text-amber-200 font-mono text-xs">
                <strong>Verbatim Quote:</strong>
                <p className="mt-2 whitespace-pre-wrap">"{highlightText}"</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* REJECT CONFIRMATION MODAL */}
      {isRejectOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-xl shadow-2xl p-6 border border-slate-200 dark:border-slate-800 space-y-4">
            <h3 className="font-bold text-base text-rose-600 dark:text-rose-400">
              Reject Question {currentQuestion.id}
            </h3>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              This question will be permanently removed from <code>data/eval/questions.json</code> and archived into <code>data/eval/rejected.json</code>.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Rejection Reason
              </label>
              <textarea
                rows={3}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                className="w-full text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2.5 text-slate-900 dark:text-slate-100 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setIsRejectOpen(false)}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold hover:bg-slate-200 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmReject}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold transition"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
