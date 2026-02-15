/**
 * useTierGates - Hook for fetching and using tier gate configuration
 *
 * Fetches gate config from /api/tier-gates/config on mount.
 * Provides helpers to check if features are gated for the current user.
 */

import { useState, useEffect, useCallback } from 'react';

export interface TierGateFeature {
  type: 'boolean' | 'number';
  label: string;
  value: boolean | number;
}

export interface TierGatesConfig {
  mode: 'full_production' | 'tier_limited';
  defaults: Record<string, TierGateFeature>;
  tiers: Record<string, Record<string, boolean | number>>;
  user_tier?: string;
  updated_at?: string;
}

export interface TierGatesResult {
  config: TierGatesConfig | null;
  loading: boolean;
  /** True if gating mode is active (tier_limited) */
  isActive: boolean;
  /** User's resolved tier from backend */
  userTier: string;
  /** Check if a boolean feature is gated (blocked) for the current user */
  isGated: (featureKey: string) => boolean;
  /** Get the numeric limit for a feature (-1 = unlimited, null if not applicable) */
  getLimit: (featureKey: string) => number | null;
  /** Refresh config from server */
  refresh: () => Promise<void>;
}

export function useTierGates(): TierGatesResult {
  const [config, setConfig] = useState<TierGatesConfig | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchConfig = useCallback(async () => {
    try {
      const resp = await fetch('/api/tier-gates/config', { credentials: 'include' });
      if (resp.ok) {
        const data = await resp.json();
        setConfig(data);
      }
    } catch {
      // Silently fail — full_production mode assumed
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const isActive = config?.mode === 'tier_limited';
  const userTier = config?.user_tier || 'observer';

  const isGated = useCallback(
    (featureKey: string): boolean => {
      if (!config || config.mode === 'full_production') return false;
      if (userTier === 'administrator' || userTier === 'coaching') return false;

      const tierOverrides = config.tiers?.[userTier] || {};
      if (featureKey in tierOverrides) {
        return !tierOverrides[featureKey];
      }

      const feat = config.defaults?.[featureKey];
      if (feat && feat.type === 'boolean') {
        return !feat.value;
      }

      return false; // unknown features are allowed
    },
    [config, userTier],
  );

  const getLimit = useCallback(
    (featureKey: string): number | null => {
      if (!config || config.mode === 'full_production') return null;
      if (userTier === 'administrator' || userTier === 'coaching') return null;

      const tierOverrides = config.tiers?.[userTier] || {};
      if (featureKey in tierOverrides) {
        const val = tierOverrides[featureKey];
        return typeof val === 'number' ? val : null;
      }

      const feat = config.defaults?.[featureKey];
      if (feat && feat.type === 'number') {
        return feat.value as number;
      }

      return null;
    },
    [config, userTier],
  );

  return {
    config,
    loading,
    isActive,
    userTier,
    isGated,
    getLimit,
    refresh: fetchConfig,
  };
}
