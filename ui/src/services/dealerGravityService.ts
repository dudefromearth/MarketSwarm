/**
 * Dealer Gravity Service
 *
 * HTTP client + SSE subscription for Dealer Gravity artifacts.
 *
 * Architecture:
 *   - Artifacts are pre-computed by Massive service (Python)
 *   - SSE gateway serves final artifacts from Redis (passthrough)
 *   - Frontend is a RENDERER, not an analyst
 *
 * Dealer Gravity Lexicon:
 *   - Volume Node: Concentrated attention
 *   - Volume Well: Neglect
 *   - Crevasse: Extended scarcity region
 *   - Market Memory: Persistent topology
 */

import type {
  DGArtifact,
  DGArtifactResponse,
  DGContextSnapshot,
  DGContextResponse,
  DealerGravityConfig,
  DGConfigsResponse,
  DealerGravityConfigUpdate,
  GexPanelConfig,
  GexConfigsResponse,
  GexPanelConfigUpdate,
  DGAnalysisResult,
  DGAnalysesResponse,
  DGArtifactUpdatedEvent,
} from '../types/dealerGravity';

const API_BASE = '/api/dealer-gravity';

// ============================================================================
// Tier 1: Visualization Artifact API
// ============================================================================

/**
 * Fetch the current visualization artifact.
 * Returns render-ready bins, structures, and metadata.
 */
export async function fetchArtifact(): Promise<DGArtifact | null> {
  try {
    const response = await fetch(`${API_BASE}/artifact`, {
      credentials: 'include',
    });

    if (!response.ok) {
      if (response.status === 503) {
        console.warn('[DG] Artifact not ready - pipeline initializing');
        return null;
      }
      throw new Error(`HTTP ${response.status}`);
    }

    const data: DGArtifactResponse = await response.json();
    if (!data.success || !data.data) {
      return null;
    }

    // Convert snake_case to camelCase for frontend use
    return {
      profile: data.data.profile,
      structures: {
        volumeNodes: data.data.structures.volume_nodes ?? data.data.structures.volumeNodes ?? [],
        volumeWells: data.data.structures.volume_wells ?? data.data.structures.volumeWells ?? [],
        crevasses: data.data.structures.crevasses ?? [],
      },
      meta: {
        spot: data.data.meta.spot,
        algorithm: data.data.meta.algorithm,
        normalizedScale: data.data.meta.normalized_scale ?? data.data.meta.normalizedScale ?? 1000,
        artifactVersion: data.data.meta.artifact_version ?? data.data.meta.artifactVersion ?? '',
        lastUpdate: data.data.meta.last_update ?? data.data.meta.lastUpdate ?? '',
      },
    };
  } catch (error) {
    console.error('[DG] Failed to fetch artifact:', error);
    return null;
  }
}

// ============================================================================
// Tier 2: Context Snapshot API
// ============================================================================

/**
 * Fetch the current context snapshot.
 * Returns ML-ready facts for Trade Selector, RiskGraph, etc.
 */
export async function fetchContext(): Promise<DGContextSnapshot | null> {
  try {
    const response = await fetch(`${API_BASE}/context`, {
      credentials: 'include',
    });

    if (!response.ok) {
      if (response.status === 503) {
        console.warn('[DG] Context not ready - pipeline initializing');
        return null;
      }
      throw new Error(`HTTP ${response.status}`);
    }

    const data: DGContextResponse = await response.json();
    if (!data.success || !data.data) {
      return null;
    }

    // Convert snake_case to camelCase
    const raw = data.data;
    return {
      symbol: raw.symbol,
      spot: raw.spot,
      nearestVolumeNode: raw.nearest_volume_node ?? raw.nearestVolumeNode ?? null,
      nearestVolumeNodeDist: raw.nearest_volume_node_dist ?? raw.nearestVolumeNodeDist ?? null,
      volumeWellProximity: raw.volume_well_proximity ?? raw.volumeWellProximity ?? null,
      inCrevasse: raw.in_crevasse ?? raw.inCrevasse ?? false,
      marketMemoryStrength: raw.market_memory_strength ?? raw.marketMemoryStrength ?? 0,
      gammaAlignment: raw.gamma_alignment ?? raw.gammaAlignment ?? null,
      artifactVersion: raw.artifact_version ?? raw.artifactVersion ?? '',
      timestamp: raw.timestamp ?? '',
    };
  } catch (error) {
    console.error('[DG] Failed to fetch context:', error);
    return null;
  }
}

// ============================================================================
// Configuration APIs
// ============================================================================

/**
 * Fetch user's Dealer Gravity display configurations.
 */
export async function fetchDGConfigs(): Promise<DealerGravityConfig[]> {
  try {
    const response = await fetch(`${API_BASE}/configs`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data: DGConfigsResponse = await response.json();
    return data.data ?? [];
  } catch (error) {
    console.error('[DG] Failed to fetch configs:', error);
    return [];
  }
}

/**
 * Create a new DG configuration.
 */
export async function createDGConfig(
  config: Partial<DealerGravityConfig>
): Promise<{ id: number } | null> {
  try {
    const response = await fetch(`${API_BASE}/configs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(config),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.data ?? null;
  } catch (error) {
    console.error('[DG] Failed to create config:', error);
    return null;
  }
}

/**
 * Update a DG configuration.
 */
export async function updateDGConfig(
  id: number,
  updates: DealerGravityConfigUpdate
): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/configs/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(updates),
    });

    return response.ok;
  } catch (error) {
    console.error('[DG] Failed to update config:', error);
    return false;
  }
}

/**
 * Delete a DG configuration.
 */
export async function deleteDGConfig(id: number): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/configs/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    });

    return response.ok;
  } catch (error) {
    console.error('[DG] Failed to delete config:', error);
    return false;
  }
}

// ============================================================================
// GEX Panel Configuration APIs
// ============================================================================

/**
 * Fetch user's GEX panel configurations.
 */
export async function fetchGexConfigs(): Promise<GexPanelConfig[]> {
  try {
    const response = await fetch(`${API_BASE}/gex-configs`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data: GexConfigsResponse = await response.json();
    return data.data ?? [];
  } catch (error) {
    console.error('[DG] Failed to fetch GEX configs:', error);
    return [];
  }
}

/**
 * Create a new GEX panel configuration.
 */
export async function createGexConfig(
  config: Partial<GexPanelConfig>
): Promise<{ id: number } | null> {
  try {
    const response = await fetch(`${API_BASE}/gex-configs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(config),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.data ?? null;
  } catch (error) {
    console.error('[DG] Failed to create GEX config:', error);
    return null;
  }
}

/**
 * Update a GEX panel configuration.
 */
export async function updateGexConfig(
  id: number,
  updates: GexPanelConfigUpdate
): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/gex-configs/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(updates),
    });

    return response.ok;
  } catch (error) {
    console.error('[DG] Failed to update GEX config:', error);
    return false;
  }
}

// ============================================================================
// AI Analysis APIs
// ============================================================================

/**
 * Request AI visual analysis of the chart.
 */
export async function analyzeChart(
  imageBase64: string,
  spotPrice: number
): Promise<DGAnalysisResult | null> {
  try {
    const response = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ imageBase64, spotPrice }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.data ?? null;
  } catch (error) {
    console.error('[DG] Failed to analyze chart:', error);
    return null;
  }
}

/**
 * Fetch analysis history.
 */
export async function fetchAnalysisHistory(limit = 10): Promise<DGAnalysisResult[]> {
  try {
    const response = await fetch(`${API_BASE}/analyses?limit=${limit}`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data: DGAnalysesResponse = await response.json();
    return data.data ?? [];
  } catch (error) {
    console.error('[DG] Failed to fetch analysis history:', error);
    return [];
  }
}

// ============================================================================
// SSE Subscription
// ============================================================================

export interface DGSubscription {
  close: () => void;
  reconnect: () => void;
}

/**
 * Subscribe to Dealer Gravity artifact update events.
 *
 * When artifact_version changes, the callback is invoked.
 * The callback should refetch the artifact to get updated data.
 */
export function subscribeToDealerGravity(
  onUpdate: (event: DGArtifactUpdatedEvent) => void,
  onConnect?: () => void,
  onDisconnect?: () => void
): DGSubscription {
  let eventSource: EventSource | null = null;
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const MAX_RECONNECT_DELAY = 30000;
  const BASE_DELAY = 1000;

  function connect() {
    if (closed) return;

    eventSource = new EventSource('/sse/dealer-gravity', {
      withCredentials: true,
    });

    eventSource.addEventListener('connected', () => {
      console.log('[DG] SSE connected');
      reconnectAttempts = 0;
      onConnect?.();
    });

    eventSource.addEventListener('dealer_gravity_artifact_updated', (e) => {
      try {
        const rawData = JSON.parse(e.data);
        // Convert snake_case to camelCase
        const event: DGArtifactUpdatedEvent = {
          type: 'dealer_gravity_artifact_updated',
          symbol: rawData.symbol,
          artifactVersion: rawData.artifact_version ?? rawData.artifactVersion ?? '',
          occurredAt: rawData.occurred_at ?? rawData.occurredAt ?? '',
        };
        onUpdate(event);
      } catch (err) {
        console.error('[DG] Failed to parse SSE event:', err);
      }
    });

    eventSource.onerror = () => {
      console.warn('[DG] SSE connection error');
      eventSource?.close();
      onDisconnect?.();
      scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    if (closed) return;

    const delay = Math.min(
      BASE_DELAY * Math.pow(2, reconnectAttempts) + Math.random() * 1000,
      MAX_RECONNECT_DELAY
    );
    reconnectAttempts++;

    console.log(`[DG] Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts})`);
    reconnectTimer = setTimeout(connect, delay);
  }

  function close() {
    closed = true;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function reconnect() {
    if (eventSource) {
      eventSource.close();
    }
    reconnectAttempts = 0;
    connect();
  }

  // Initial connection
  connect();

  return { close, reconnect };
}
