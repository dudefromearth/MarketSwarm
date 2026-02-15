/**
 * TierGatesContext - App-wide tier gate enforcement
 *
 * Wraps useTierGates() hook in a React context so any component
 * can check gate status without re-fetching.
 */

import { createContext, useContext, type ReactNode } from 'react';
import { useTierGates, type TierGatesResult } from '../hooks/useTierGates';

const TierGatesContext = createContext<TierGatesResult | null>(null);

interface TierGatesProviderProps {
  children: ReactNode;
}

export function TierGatesProvider({ children }: TierGatesProviderProps) {
  const gates = useTierGates();
  return (
    <TierGatesContext.Provider value={gates}>
      {children}
    </TierGatesContext.Provider>
  );
}

export function useTierGatesContext(): TierGatesResult {
  const ctx = useContext(TierGatesContext);
  if (!ctx) {
    // Return safe defaults if used outside provider
    return {
      config: null,
      loading: false,
      isActive: false,
      userTier: 'observer',
      isGated: () => false,
      getLimit: () => null,
      refresh: async () => {},
    };
  }
  return ctx;
}
