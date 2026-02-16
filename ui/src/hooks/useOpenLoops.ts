/**
 * useOpenLoops - Aggregates open loop data for the Routine Drawer
 *
 * Surfaces unresolved commitments:
 * - Open trades (positions with status='open')
 * - Expiring soon (open trades within 24h of expiration)
 * - Needs settlement (status='expired', awaiting manual close)
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
  expiringSoon: LegacyTrade[];
  needsSettlement: LegacyTrade[];
  unjournaled: LegacyTrade[];
  armedAlerts: Alert[];
  incompleteRetros: string[];
  totalCount: number;
}

export function useOpenLoops(): OpenLoops {
  const { alerts } = useAlerts();
  const { openTrades, expiredTrades } = useTradeLog();

  return useMemo(() => {
    const now = Date.now();
    const twentyFourHours = 24 * 60 * 60 * 1000;

    // Open trades expiring within 24 hours
    const expiringSoon = openTrades.filter((t) => {
      const exp = (t as any).expiration_date;
      if (!exp) return false;
      const expTime = new Date(exp).getTime();
      return expTime > now && expTime - now <= twentyFourHours;
    });

    // Expired trades awaiting manual settlement
    const needsSettlement = expiredTrades;

    // Armed alerts: enabled and not triggered
    const armedAlerts = alerts.filter((a) => a.enabled && !a.triggered);

    // Unjournaled: placeholder for future journal integration
    const unjournaled: LegacyTrade[] = [];

    const totalCount =
      openTrades.length +
      needsSettlement.length +
      unjournaled.length +
      armedAlerts.length;

    return {
      openTrades,
      expiringSoon,
      needsSettlement,
      unjournaled,
      armedAlerts,
      incompleteRetros: [],
      totalCount,
    };
  }, [alerts, openTrades, expiredTrades]);
}
