import React, { createContext, useContext, useState, ReactNode } from 'react';
import { PIIDetection } from '../workspaces/pii/PIITypes';

interface PIIContextValue {
  detections: PIIDetection[];
  selectedId: string | null;
  setDetections: (detections: PIIDetection[]) => void;
  setSelectedId: (id: string | null) => void;
  updateDetection: (id: string, updates: Partial<PIIDetection>) => void;
}

const PIIContext = createContext<PIIContextValue | undefined>(undefined);

export function PIIProvider({ children }: { children: ReactNode }) {
  const [detections, setDetections] = useState<PIIDetection[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const updateDetection = (id: string, updates: Partial<PIIDetection>) => {
    setDetections(prev => prev.map(d => d.id === id ? { ...d, ...updates } : d));
  };

  return (
    <PIIContext.Provider value={{ detections, selectedId, setDetections, setSelectedId, updateDetection }}>
      {children}
    </PIIContext.Provider>
  );
}

export function usePII() {
  const context = useContext(PIIContext);
  if (context === undefined) {
    return null;
  }
  return context;
}
