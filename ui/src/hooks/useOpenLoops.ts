/**
 * useOpenLoops - Aggregates open loop data for the Routine Drawer
 *
 * Surfaces unresolved commitments:
 * - Open trades (positions with status='open')
 * - Unjournaled trades (closed trades without journal entry)
 * - Armed alerts (enabled && !triggered)
 * - Incomplete retros (missing weekly/monthly - future feature)
 */

import { useMemo } from 'react';
import { useAlerts } from '../contexts/AlertContext';
import { useTradeLog } from '../contexts/TradeLogContext';
import type { Alert } from '../types/alerts';
import type { LegacyTrade } from '../types/tradeLog';

export interface OpenLoops {
  openTrades: LegacyTrade[];
  unjournaled: LegacyTrade[];
  armedAlerts: Alert[];
  incompleteRetros: string[]; // Placeholder for future weekly/monthly periods
  totalCount: number;
}

export function useOpenLoops(): OpenLoops {
  const { alerts } = useAlerts();
  const { openTrades } = useTradeLog();

  return useMemo(() => {
    // Armed alerts: enabled and not triggered
    const armedAlerts = alerts.filter((a) => a.enabled && !a.triggered);

    // Unjournaled: placeholder for future journal integration
    // TODO: Add API call to check which closed trades lack journal entries
    const unjournaled: LegacyTrade[] = [];

    const totalCount =
      openTrades.length +
      unjournaled.length +
      armedAlerts.length;

    return {
      openTrades,
      unjournaled,
      armedAlerts,
      incompleteRetros: [], // Future feature
      totalCount,
    };
  }, [alerts, openTrades]);
}
