/**
 * positionRecognition.ts - Re-exports from @market-swarm/core
 *
 * This file now re-exports position recognition utilities from the
 * shared core package. Kept for backward compatibility with existing imports.
 *
 * @deprecated Import directly from '@market-swarm/core' instead
 */

export {
  // Types
  type PositionRecognitionResult,

  // Functions
  recognizePositionType,
  strategyToLegs,
  getCenterStrike,
  getWidth,
  getPrimaryExpiration,
  getDominantSide,
  hasSameExpiration,
  hasSameRight,
} from '@market-swarm/core';

// Re-export types that components may need
export type {
  PositionLeg,
  PositionType,
  PositionDirection,
} from '@market-swarm/core';
