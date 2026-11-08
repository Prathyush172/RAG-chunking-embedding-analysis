import React from "react";
import { Link } from "react-router-dom";
import { HelpCircle, ArrowLeft } from "lucide-react";

export const NotFound: React.FC = () => {
  return (
    <div className="max-w-md mx-auto text-center py-24 space-y-4">
      <div className="w-16 h-16 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 rounded-2xl flex items-center justify-center mx-auto shadow-inner">
        <HelpCircle className="w-8 h-8" />
      </div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
        404 — Page Not Found
      </h1>
      <p className="text-xs text-slate-500 leading-relaxed">
        The requested routing view does not exist in the RFC RAG Chunking Lab application.
      </p>
      <div className="pt-2">
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Return to Corpus Overview</span>
        </Link>
      </div>
    </div>
  );
};
