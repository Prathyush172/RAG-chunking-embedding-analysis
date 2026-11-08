import React, { createContext, useContext, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ExperimentResponse } from "../lib/api";

interface ExperimentContextType {
  experiments: ExperimentResponse[];
  activeExperimentId: string | null;
  setActiveExperimentId: (id: string | null) => void;
  activeExperiment: ExperimentResponse | null;
  isLoading: boolean;
  refetch: () => void;
}

const ExperimentContext = createContext<ExperimentContextType>({
  experiments: [],
  activeExperimentId: null,
  setActiveExperimentId: () => {},
  activeExperiment: null,
  isLoading: false,
  refetch: () => {},
});

export const ExperimentProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeExperimentId, setActiveExperimentIdState] = useState<string | null>(() => {
    return localStorage.getItem("rfclab_active_experiment") || null;
  });

  const { data: experiments = [], isLoading, refetch } = useQuery({
    queryKey: ["experiments"],
    queryFn: () => api.listExperiments(),
    refetchInterval: 10000,
  });

  useEffect(() => {
    if (experiments.length > 0) {
      if (!activeExperimentId || !experiments.some((e) => e.id === activeExperimentId)) {
        // Default to the latest completed experiment, or simply the latest experiment
        const completed = experiments.find((e) => e.status === "completed") || experiments[0];
        setActiveExperimentIdState(completed.id);
        localStorage.setItem("rfclab_active_experiment", completed.id);
      }
    } else {
      setActiveExperimentIdState(null);
      localStorage.removeItem("rfclab_active_experiment");
    }
  }, [experiments, activeExperimentId]);

  const setActiveExperimentId = (id: string | null) => {
    setActiveExperimentIdState(id);
    if (id) {
      localStorage.setItem("rfclab_active_experiment", id);
    } else {
      localStorage.removeItem("rfclab_active_experiment");
    }
  };

  const activeExperiment = experiments.find((e) => e.id === activeExperimentId) || null;

  return (
    <ExperimentContext.Provider
      value={{
        experiments,
        activeExperimentId,
        setActiveExperimentId,
        activeExperiment,
        isLoading,
        refetch,
      }}
    >
      {children}
    </ExperimentContext.Provider>
  );
};

export const useExperiment = () => useContext(ExperimentContext);
