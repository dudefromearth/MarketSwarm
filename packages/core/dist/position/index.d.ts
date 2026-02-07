/**
 * Position Module
 *
 * Core position types, recognition, formatting, and factory utilities.
 */
export type { PositionType, PositionDirection, OptionRight, CostBasisType, PositionLeg, Position, ImportSource, ImportMetadata, } from './types.js';
export { POSITION_TYPE_LABELS, POSITION_TYPE_CODES, POSITION_TYPE_COLORS, } from './types.js';
export type { PositionRecognitionResult } from './recognition.js';
export { recognizePositionType, strategyToLegs, getCenterStrike, getWidth, getPrimaryExpiration, getDominantSide, hasSameExpiration, hasSameRight, } from './recognition.js';
export type { FormattedPosition } from './formatting.js';
export { formatLeg, formatLegsDisplay, formatPositionLabel, formatPositionForDisplay, getPositionTypeCode, getPositionTypeColor, getPositionTypeLabel, formatExpiration, hasMultipleExpirations, getUniqueExpirations, formatCostBasis, formatPnL, formatPercent, } from './formatting.js';
export type { CreatePositionInput, CreatePositionOptions, LegacyStrategyInput, LegacyStrategy, } from './factory.js';
export { createPosition, createPositionFromLegacy, updateDerivedFields, cloneWithLegs, toLegacyFormat, } from './factory.js';
//# sourceMappingURL=index.d.ts.map