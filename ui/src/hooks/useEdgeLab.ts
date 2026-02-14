// hooks/useEdgeLab.ts
// React hook for Edge Lab data management

import { useState, useCallback } from 'react';

// Types
export interface EdgeLabSetup {
  id: string;
  userId: number;
  tradeId: string | null;
  positionId: string | null;
  setupDate: string;
  regime: string;
  gexPosture: string;
  volState: string;
  timeStructure: string;
  heatmapColor: string;
  positionStructure: string;
  widthBucket: string;
  directionalBias: string;
  entryLogic: string | null;
  exitLogic: string | null;
  entryDefined: boolean;
  exitDefined: boolean;
  structureSignature: string;
  biasState: Record<string, string> | null;
  status: string;
  createdAt: string;
  updatedAt: string;
  hypothesis?: EdgeLabHypothesis;
  outcome?: EdgeLabOutcome;
}

export interface EdgeLabHypothesis {
  id: string;
  setupId: string;
  userId: number;
  thesis: string;
  convexitySource: string;
  failureCondition: string;
  maxRiskDefined: boolean;
  lockedAt: string | null;
  isLocked: boolean;
  createdAt: string;
}

export interface EdgeLabOutcome {
  id: string;
  setupId: string;
  userId: number;
  outcomeType: string;
  systemSuggestion: string | null;
  suggestionConfidence: number | null;
  suggestionReasoning: string | null;
  hypothesisValid: number | null;
  structureResolved: number | null;
  exitPerPlan: number | null;
  notes: string | null;
  pnlResult: number | null;
  confirmedAt: string | null;
  isConfirmed: boolean;
  createdAt: string;
}

export interface EdgeScoreData {
  id: number;
  userId: number;
  windowStart: string;
  windowEnd: string;
  scope: string;
  structuralIntegrity: number;
  executionDiscipline: number;
  biasInterferenceRate: number;
  regimeAlignment: number;
  finalScore: number;
  sampleSize: number;
  computedAt: string;
}

export interface OutcomeSuggestion {
  suggestion: string | null;
  confidence: number;
  reasoning: string;
}

interface RegimeCorrelationData {
  dimensions: Record<string, Record<string, {
    structural_validity_rate: number | null;
    sample_size: number;
    structural_wins: number;
    insufficient_sample: boolean;
  }>>;
  total_records: number;
  date_range: { start: string; end: string };
}

interface BiasOverlayData {
  dimensions: Record<string, Record<string, {
    outcomes: Record<string, number>;
    sample_size: number;
    insufficient_sample: boolean;
  }>>;
  total_records: number;
  date_range: { start: string; end: string };
}

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Request failed');
  return json.data;
}

export function useEdgeLab() {
  const [setups, setSetups] = useState<EdgeLabSetup[]>([]);
  const [loading, setLoading] = useState(false);
  const [edgeScore, setEdgeScore] = useState<EdgeScoreData | null>(null);
  const [edgeScoreStatus, setEdgeScoreStatus] = useState<string>('');
  const [regimeData, setRegimeData] = useState<RegimeCorrelationData | null>(null);
  const [biasData, setBiasData] = useState<BiasOverlayData | null>(null);
  const [scoreHistory, setScoreHistory] = useState<EdgeScoreData[]>([]);

  // CRUD
  const fetchSetups = useCallback(async (filters?: Record<string, string>) => {
    setLoading(true);
    try {
      const params = new URLSearchParams(filters || {});
      const data = await apiFetch<EdgeLabSetup[]>(`/api/edge-lab/setups?${params}`);
      setSetups(data);
      return data;
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSetup = useCallback(async (id: string) => {
    return apiFetch<EdgeLabSetup>(`/api/edge-lab/setups/${id}`);
  }, []);

  const createSetup = useCallback(async (data: Record<string, unknown>) => {
    const result = await apiFetch<EdgeLabSetup>('/api/edge-lab/setups', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    setSetups(prev => [result, ...prev]);
    return result;
  }, []);

  const updateSetup = useCallback(async (id: string, data: Record<string, unknown>) => {
    const result = await apiFetch<EdgeLabSetup>(`/api/edge-lab/setups/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    setSetups(prev => prev.map(s => s.id === id ? result : s));
    return result;
  }, []);

  // Hypotheses
  const createHypothesis = useCallback(async (data: {
    setupId: string;
    thesis: string;
    convexitySource: string;
    failureCondition: string;
    maxRiskDefined?: boolean;
  }) => {
    return apiFetch<EdgeLabHypothesis>('/api/edge-lab/hypotheses', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }, []);

  const lockHypothesis = useCallback(async (id: string) => {
    return apiFetch<EdgeLabHypothesis>(`/api/edge-lab/hypotheses/${id}/lock`, {
      method: 'POST',
    });
  }, []);

  // Outcomes
  const createOutcome = useCallback(async (data: Record<string, unknown>) => {
    return apiFetch<EdgeLabOutcome>('/api/edge-lab/outcomes', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }, []);

  const confirmOutcome = useCallback(async (id: string) => {
    return apiFetch<EdgeLabOutcome>(`/api/edge-lab/outcomes/${id}/confirm`, {
      method: 'POST',
    });
  }, []);

  // Analytics
  const suggestOutcome = useCallback(async (setupId: string) => {
    return apiFetch<OutcomeSuggestion>(`/api/edge-lab/setups/${setupId}/suggest-outcome`);
  }, []);

  const fetchRegimeCorrelation = useCallback(async (start: string, end: string) => {
    const data = await apiFetch<RegimeCorrelationData>(
      `/api/edge-lab/analytics/regime-correlation?start=${start}&end=${end}`
    );
    setRegimeData(data);
    return data;
  }, []);

  const fetchBiasOverlay = useCallback(async (start: string, end: string) => {
    const data = await apiFetch<BiasOverlayData>(
      `/api/edge-lab/analytics/bias-overlay?start=${start}&end=${end}`
    );
    setBiasData(data);
    return data;
  }, []);

  const fetchEdgeScore = useCallback(async (start: string, end: string, scope = 'all') => {
    const result = await apiFetch<{ status: string; data?: EdgeScoreData; sample_size?: number }>(
      `/api/edge-lab/analytics/edge-score?start=${start}&end=${end}&scope=${scope}`
    );
    setEdgeScoreStatus(result.status);
    if (result.data) setEdgeScore(result.data);
    return result;
  }, []);

  const fetchEdgeScoreHistory = useCallback(async (days = 90) => {
    const data = await apiFetch<EdgeScoreData[]>(
      `/api/edge-lab/analytics/edge-score/history?days=${days}`
    );
    setScoreHistory(data);
    return data;
  }, []);

  return {
    // State
    setups,
    loading,
    edgeScore,
    edgeScoreStatus,
    regimeData,
    biasData,
    scoreHistory,

    // CRUD
    fetchSetups,
    fetchSetup,
    createSetup,
    updateSetup,

    // Hypotheses
    createHypothesis,
    lockHypothesis,

    // Outcomes
    createOutcome,
    confirmOutcome,

    // Analytics
    suggestOutcome,
    fetchRegimeCorrelation,
    fetchBiasOverlay,
    fetchEdgeScore,
    fetchEdgeScoreHistory,
  };
}
