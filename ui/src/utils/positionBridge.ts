// utils/positionBridge.ts
// Bridge utilities for converting between new Position model and legacy RiskGraphStrategy
//
// This allows gradual migration while keeping existing components working.

import type { Position, PositionLeg, PositionType, PositionDirection, CostBasisType } from '@market-swarm/core';
import type { RiskGraphStrategy } from '../components/RiskGraphPanel';
import { getCenterStrike, getWidth } from './positionRecognition';

/**
 * Convert a Position (new leg-based model) to RiskGraphStrategy (legacy format)
 *
 * The RiskGraphStrategy format is used by:
 * - RiskGraphPanel
 * - useRiskGraphCalculations hook
 * - PnLChart
 *
 * This bridge allows the UI to work with the new Position model while
 * maintaining compatibility with existing components.
 */
export function positionToRiskGraphStrategy(position: Position): RiskGraphStrategy {
  // Get derived values from legs
  const centerStrike = getCenterStrike(position.legs);
  const wingWidth = getWidth(position.legs);

  // Determine legacy strategy type
  let strategy: 'butterfly' | 'vertical' | 'single';
  switch (position.positionType) {
    case 'butterfly':
    case 'bwb':
      strategy = 'butterfly';
      break;
    case 'vertical':
    case 'calendar':
    case 'diagonal':
      strategy = 'vertical';
      break;
    case 'iron_fly':
    case 'iron_condor':
    case 'condor':
      // Iron structures map to butterfly for P&L display
      // The legs will provide accurate pricing
      strategy = 'butterfly';
      break;
    case 'straddle':
    case 'strangle':
      // Straddles/strangles: use vertical as approximation
      // The legs will provide accurate pricing
      strategy = 'vertical';
      break;
    default:
      strategy = 'single';
  }

  // Determine side from legs
  const hasCall = position.legs.some(l => l.right === 'call');
  const hasPut = position.legs.some(l => l.right === 'put');
  const side: 'call' | 'put' = hasCall && !hasPut ? 'call' : 'put';

  // Get primary expiration
  const expiration = position.primaryExpiration ||
    position.legs[0]?.expiration ||
    new Date().toISOString().split('T')[0];

  return {
    id: position.id,
    strategy,
    side,
    strike: centerStrike ?? position.legs[0]?.strike ?? 0,
    width: wingWidth ?? 0,
    dte: position.dte,
    expiration,
    debit: position.costBasis,
    symbol: position.symbol,
    addedAt: position.addedAt,
    visible: position.visible,
    // New leg-based fields (passed through for display)
    legs: position.legs,
    positionType: position.positionType,
    direction: position.direction,
    costBasis: position.costBasis,
    costBasisType: position.costBasisType,
  };
}

/**
 * Convert a RiskGraphStrategy (legacy format) to Position (new leg-based model)
 *
 * Used when creating/updating positions from legacy UI interactions.
 */
export function riskGraphStrategyToPosition(
  strategy: RiskGraphStrategy,
  userId: number = 0
): Omit<Position, 'createdAt' | 'updatedAt' | 'version'> {
  // Use existing legs if available, otherwise derive from legacy fields
  const legs: PositionLeg[] = strategy.legs || deriveLegsfromLegacy(strategy);

  // Determine position type
  let positionType: PositionType;
  if (strategy.positionType) {
    positionType = strategy.positionType;
  } else {
    switch (strategy.strategy) {
      case 'butterfly':
        positionType = 'butterfly';
        break;
      case 'vertical':
        positionType = 'vertical';
        break;
      default:
        positionType = 'single';
    }
  }

  // Determine direction
  const direction: PositionDirection = strategy.direction ||
    (strategy.debit !== null && strategy.debit >= 0 ? 'long' : 'short');

  return {
    id: strategy.id,
    userId,
    symbol: strategy.symbol || 'SPX',
    positionType,
    direction,
    legs,
    primaryExpiration: strategy.expiration,
    dte: strategy.dte,
    costBasis: strategy.costBasis ?? strategy.debit ?? null,
    costBasisType: strategy.costBasisType || 'debit',
    visible: strategy.visible,
    sortOrder: 0,
    color: null,
    label: null,
    addedAt: strategy.addedAt,
  };
}

/**
 * Derive legs from legacy strategy fields
 */
function deriveLegsfromLegacy(strategy: RiskGraphStrategy): PositionLeg[] {
  const { strike, width, side, strategy: strategyType, expiration } = strategy;
  const right = side;

  switch (strategyType) {
    case 'butterfly':
      // Long butterfly: +1 lower, -2 center, +1 upper
      return [
        { strike: strike - width, expiration, right, quantity: 1 },
        { strike: strike, expiration, right, quantity: -2 },
        { strike: strike + width, expiration, right, quantity: 1 },
      ];

    case 'vertical':
      // Vertical spread: +1 lower, -1 upper (for call) or vice versa
      if (side === 'call') {
        // Debit call spread: long lower, short upper
        return [
          { strike: strike, expiration, right, quantity: 1 },
          { strike: strike + width, expiration, right, quantity: -1 },
        ];
      } else {
        // Debit put spread: long upper, short lower
        return [
          { strike: strike, expiration, right, quantity: 1 },
          { strike: strike - width, expiration, right, quantity: -1 },
        ];
      }

    case 'single':
    default:
      // Single leg
      return [
        { strike, expiration, right, quantity: 1 },
      ];
  }
}

/**
 * Convert an array of Positions to RiskGraphStrategies
 */
export function positionsToStrategies(positions: Position[]): RiskGraphStrategy[] {
  return positions.map(positionToRiskGraphStrategy);
}

/**
 * Convert an array of RiskGraphStrategies to Positions
 */
export function strategiesToPositions(
  strategies: RiskGraphStrategy[],
  userId: number = 0
): Array<Omit<Position, 'createdAt' | 'updatedAt' | 'version'>> {
  return strategies.map(s => riskGraphStrategyToPosition(s, userId));
}
