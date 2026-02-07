/**
 * positionFormatting.ts - Re-exports from @market-swarm/core
 *
 * This file now re-exports position formatting utilities from the
 * shared core package. Kept for backward compatibility with existing imports.
 *
 * @deprecated Import directly from '@market-swarm/core' instead
 */

export {
  // Types
  type FormattedPosition,

  // Functions
  formatLeg,
  formatLegsDisplay,
  formatPositionLabel,
  formatPositionForDisplay,
  getPositionTypeCode,
  getPositionTypeColor,
  getPositionTypeLabel,
  formatExpiration,
  hasMultipleExpirations,
  getUniqueExpirations,
  formatCostBasis,
  formatPnL,
  formatPercent,
} from '@market-swarm/core';
