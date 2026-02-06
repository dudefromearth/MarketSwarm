/**
 * Dealer Gravity Context
 *
 * Provides Dealer Gravity state, configurations, and operations to the UI.
 *
 * Architecture:
 *   - Artifacts are fetched from SSE gateway (pre-computed)
 *   - SSE subscription triggers refetch on artifact_version change
 *   - Frontend is a RENDERER, not an analyst
 *
 * Dealer Gravity Lexicon:
 *   - Volume Node: Concentrated attention
 *   - Volume Well: Neglect
 *   - Crevasse: Extended scarcity region
 *   - Market Memory: Persistent topology
 */

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from 'react';

import type {
  DGArtifact,
  DGContextSnapshot,
  DGStructures,
  DealerGravityConfig,
  DealerGravityConfigUpdate,
  GexPanelConfig,
  GexPanelConfigUpdate,
  DGAnalysisResult,
} from '../types/dealerGravity';

import {
  fetchArtifact,
  fetchContext,
  fetchDGConfigs,
  createDGConfig,
  updateDGConfig as apiUpdateDGConfig,
  deleteDGConfig as apiDeleteDGConfig,
  fetchGexConfigs,
  createGexConfig,
  updateGexConfig as apiUpdateGexConfig,
  analyzeChart as apiAnalyzeChart,
  fetchAnalysisHistory,
  subscribeToDealerGravity,
} from '../services/dealerGravityService';

// ============================================================================
// Context Types
// ============================================================================

interface DealerGravityContextValue {
  // Artifact state (Tier 1: Visualization)
  artifact: DGArtifact | null;
  structures: DGStructures | null;
  artifactVersion: string | null;

  // Context snapshot (Tier 2: System)
  contextSnapshot: DGContextSnapshot | null;

  // Configuration state
  config: DealerGravityConfig | null;
  configs: DealerGravityConfig[];
  gexConfig: GexPanelConfig | null;
  gexConfigs: GexPanelConfig[];

  // Analysis state
  analysisHistory: DGAnalysisResult[];
  analyzing: boolean;

  // Connection state
  connected: boolean;
  loading: boolean;

  // Config operations
  updateConfig: (updates: DealerGravityConfigUpdate) => Promise<boolean>;
  createConfig: (config: Partial<DealerGravityConfig>) => Promise<number | null>;
  deleteConfig: (id: number) => Promise<boolean>;
  selectConfig: (id: number) => void;

  // GEX config operations
  updateGexConfig: (updates: GexPanelConfigUpdate) => Promise<boolean>;
  createGexConfigFn: (config: Partial<GexPanelConfig>) => Promise<number | null>;
  selectGexConfig: (id: number) => void;

  // Analysis operations
  analyzeChart: (imageBase64: string, spotPrice: number) => Promise<DGAnalysisResult | null>;

  // Refresh operations
  refreshArtifact: () => Promise<void>;
  refreshContext: () => Promise<void>;
}

const DealerGravityContext = createContext<DealerGravityContextValue | null>(null);

// ============================================================================
// Default Configurations
// ============================================================================

const DEFAULT_DG_CONFIG: DealerGravityConfig = {
  id: 0,
  name: 'Default',
  enabled: true,
  mode: 'tv',
  widthPercent: 15,
  numBins: 50,
  cappingSigma: 2.0,
  color: '#9333ea',
  transparency: 50,
  showVolumeNodes: true,
  showVolumeWells: true,
  showCrevasses: true,
  isDefault: true,
};

const DEFAULT_GEX_CONFIG: GexPanelConfig = {
  id: 0,
  enabled: true,
  mode: 'combined',
  callsColor: '#22c55e',
  putsColor: '#ef4444',
  widthPx: 60,
  isDefault: true,
};

// ============================================================================
// Provider Component
// ============================================================================

interface DealerGravityProviderProps {
  children: React.ReactNode;
}

export function DealerGravityProvider({ children }: DealerGravityProviderProps) {
  // Artifact state
  const [artifact, setArtifact] = useState<DGArtifact | null>(null);
  const [contextSnapshot, setContextSnapshot] = useState<DGContextSnapshot | null>(null);

  // Configuration state
  const [configs, setConfigs] = useState<DealerGravityConfig[]>([]);
  const [selectedConfigId, setSelectedConfigId] = useState<number | null>(null);
  const [gexConfigs, setGexConfigs] = useState<GexPanelConfig[]>([]);
  const [selectedGexConfigId, setSelectedGexConfigId] = useState<number | null>(null);

  // Analysis state
  const [analysisHistory, setAnalysisHistory] = useState<DGAnalysisResult[]>([]);
  const [analyzing, setAnalyzing] = useState(false);

  // Connection state
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  // Refs for cleanup
  const subscriptionRef = useRef<{ close: () => void } | null>(null);

  // ============================================================================
  // Derived State
  // ============================================================================

  const config = useMemo(() => {
    if (selectedConfigId !== null) {
      return configs.find((c) => c.id === selectedConfigId) ?? null;
    }
    // Return default config or first config
    return configs.find((c) => c.isDefault) ?? configs[0] ?? DEFAULT_DG_CONFIG;
  }, [configs, selectedConfigId]);

  const gexConfig = useMemo(() => {
    if (selectedGexConfigId !== null) {
      return gexConfigs.find((c) => c.id === selectedGexConfigId) ?? null;
    }
    return gexConfigs.find((c) => c.isDefault) ?? gexConfigs[0] ?? DEFAULT_GEX_CONFIG;
  }, [gexConfigs, selectedGexConfigId]);

  const structures = useMemo(() => artifact?.structures ?? null, [artifact]);
  const artifactVersion = useMemo(() => artifact?.meta?.artifactVersion ?? null, [artifact]);

  // ============================================================================
  // Refresh Functions
  // ============================================================================

  const refreshArtifact = useCallback(async () => {
    const newArtifact = await fetchArtifact();
    if (newArtifact) {
      setArtifact(newArtifact);
    }
  }, []);

  const refreshContext = useCallback(async () => {
    const newContext = await fetchContext();
    if (newContext) {
      setContextSnapshot(newContext);
    }
  }, []);

  const refreshConfigs = useCallback(async () => {
    const [dgConfigs, gexConfigsList] = await Promise.all([
      fetchDGConfigs(),
      fetchGexConfigs(),
    ]);
    setConfigs(dgConfigs);
    setGexConfigs(gexConfigsList);
  }, []);

  const refreshAnalysisHistory = useCallback(async () => {
    const history = await fetchAnalysisHistory(10);
    setAnalysisHistory(history);
  }, []);

  // ============================================================================
  // Config Operations
  // ============================================================================

  const updateConfig = useCallback(
    async (updates: DealerGravityConfigUpdate): Promise<boolean> => {
      if (!config || config.id === 0) {
        // Need to create first
        const result = await createDGConfig({ ...DEFAULT_DG_CONFIG, ...updates });
        if (result) {
          await refreshConfigs();
          setSelectedConfigId(result.id);
          return true;
        }
        return false;
      }

      const success = await apiUpdateDGConfig(config.id, updates);
      if (success) {
        await refreshConfigs();
      }
      return success;
    },
    [config, refreshConfigs]
  );

  const createConfigFn = useCallback(
    async (newConfig: Partial<DealerGravityConfig>): Promise<number | null> => {
      const result = await createDGConfig(newConfig);
      if (result) {
        await refreshConfigs();
        return result.id;
      }
      return null;
    },
    [refreshConfigs]
  );

  const deleteConfigFn = useCallback(
    async (id: number): Promise<boolean> => {
      const success = await apiDeleteDGConfig(id);
      if (success) {
        await refreshConfigs();
        if (selectedConfigId === id) {
          setSelectedConfigId(null);
        }
      }
      return success;
    },
    [refreshConfigs, selectedConfigId]
  );

  const selectConfig = useCallback((id: number) => {
    setSelectedConfigId(id);
  }, []);

  // ============================================================================
  // GEX Config Operations
  // ============================================================================

  const updateGexConfigFn = useCallback(
    async (updates: GexPanelConfigUpdate): Promise<boolean> => {
      if (!gexConfig || gexConfig.id === 0) {
        const result = await createGexConfig({ ...DEFAULT_GEX_CONFIG, ...updates });
        if (result) {
          await refreshConfigs();
          setSelectedGexConfigId(result.id);
          return true;
        }
        return false;
      }

      const success = await apiUpdateGexConfig(gexConfig.id, updates);
      if (success) {
        await refreshConfigs();
      }
      return success;
    },
    [gexConfig, refreshConfigs]
  );

  const createGexConfigFn = useCallback(
    async (newConfig: Partial<GexPanelConfig>): Promise<number | null> => {
      const result = await createGexConfig(newConfig);
      if (result) {
        await refreshConfigs();
        return result.id;
      }
      return null;
    },
    [refreshConfigs]
  );

  const selectGexConfig = useCallback((id: number) => {
    setSelectedGexConfigId(id);
  }, []);

  // ============================================================================
  // Analysis Operations
  // ============================================================================

  const analyzeChartFn = useCallback(
    async (imageBase64: string, spotPrice: number): Promise<DGAnalysisResult | null> => {
      setAnalyzing(true);
      try {
        const result = await apiAnalyzeChart(imageBase64, spotPrice);
        if (result) {
          setAnalysisHistory((prev) => [result, ...prev.slice(0, 9)]);
        }
        return result;
      } finally {
        setAnalyzing(false);
      }
    },
    []
  );

  // ============================================================================
  // Initial Load & SSE Subscription
  // ============================================================================

  useEffect(() => {
    let mounted = true;

    async function init() {
      setLoading(true);

      // Load all data in parallel
      const [artifactResult, contextResult] = await Promise.all([
        fetchArtifact(),
        fetchContext(),
        refreshConfigs(),
        refreshAnalysisHistory(),
      ]);

      if (!mounted) return;

      if (artifactResult) setArtifact(artifactResult);
      if (contextResult) setContextSnapshot(contextResult);
      setLoading(false);

      // Subscribe to SSE updates
      subscriptionRef.current = subscribeToDealerGravity(
        (event) => {
          console.log('[DG] Artifact updated:', event.artifactVersion);
          // Refetch artifact and context when version changes
          refreshArtifact();
          refreshContext();
        },
        () => {
          if (mounted) setConnected(true);
        },
        () => {
          if (mounted) setConnected(false);
        }
      );
    }

    init();

    return () => {
      mounted = false;
      subscriptionRef.current?.close();
    };
  }, [refreshArtifact, refreshContext, refreshConfigs, refreshAnalysisHistory]);

  // ============================================================================
  // Context Value
  // ============================================================================

  const value = useMemo<DealerGravityContextValue>(
    () => ({
      // Artifact state
      artifact,
      structures,
      artifactVersion,

      // Context snapshot
      contextSnapshot,

      // Configuration state
      config,
      configs,
      gexConfig,
      gexConfigs,

      // Analysis state
      analysisHistory,
      analyzing,

      // Connection state
      connected,
      loading,

      // Config operations
      updateConfig,
      createConfig: createConfigFn,
      deleteConfig: deleteConfigFn,
      selectConfig,

      // GEX config operations
      updateGexConfig: updateGexConfigFn,
      createGexConfigFn,
      selectGexConfig,

      // Analysis operations
      analyzeChart: analyzeChartFn,

      // Refresh operations
      refreshArtifact,
      refreshContext,
    }),
    [
      artifact,
      structures,
      artifactVersion,
      contextSnapshot,
      config,
      configs,
      gexConfig,
      gexConfigs,
      analysisHistory,
      analyzing,
      connected,
      loading,
      updateConfig,
      createConfigFn,
      deleteConfigFn,
      selectConfig,
      updateGexConfigFn,
      createGexConfigFn,
      selectGexConfig,
      analyzeChartFn,
      refreshArtifact,
      refreshContext,
    ]
  );

  return (
    <DealerGravityContext.Provider value={value}>
      {children}
    </DealerGravityContext.Provider>
  );
}

// ============================================================================
// Hook
// ============================================================================

export function useDealerGravity(): DealerGravityContextValue {
  const context = useContext(DealerGravityContext);
  if (!context) {
    throw new Error('useDealerGravity must be used within a DealerGravityProvider');
  }
  return context;
}

export default DealerGravityContext;
