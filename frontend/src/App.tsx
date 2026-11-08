import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "./context/ThemeContext";
import { ExperimentProvider } from "./context/ExperimentContext";
import { AppShell } from "./components/layout/AppShell";

import { Overview } from "./pages/Overview";
import { Dataset } from "./pages/Dataset";
import { Review } from "./pages/Review";
import { Experiments } from "./pages/Experiments";
import { Results } from "./pages/Results";
import { Compare } from "./pages/Compare";
import { Playground } from "./pages/Playground";
import { DecisionMatrix } from "./pages/DecisionMatrix";
import { Export } from "./pages/Export";
import { Settings } from "./pages/Settings";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: false,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ExperimentProvider>
          <BrowserRouter>
            <AppShell>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/dataset" element={<Dataset />} />
                <Route path="/review" element={<Review />} />
                <Route path="/experiments" element={<Experiments />} />
                <Route path="/results" element={<Results />} />
                <Route path="/compare" element={<Compare />} />
                <Route path="/playground" element={<Playground />} />
                <Route path="/decision-matrix" element={<DecisionMatrix />} />
                <Route path="/export" element={<Export />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </AppShell>
          </BrowserRouter>
        </ExperimentProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
