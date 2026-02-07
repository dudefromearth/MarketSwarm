/**
 * Position Module
 *
 * Core position types, recognition, formatting, and factory utilities.
 */
export { POSITION_TYPE_LABELS, POSITION_TYPE_CODES, POSITION_TYPE_COLORS, } from './types.js';
export { recognizePositionType, strategyToLegs, getCenterStrike, getWidth, getPrimaryExpiration, getDominantSide, hasSameExpiration, hasSameRight, } from './recognition.js';
export { formatLeg, formatLegsDisplay, formatPositionLabel, formatPositionForDisplay, getPositionTypeCode, getPositionTypeColor, getPositionTypeLabel, formatExpiration, hasMultipleExpirations, getUniqueExpirations, formatCostBasis, formatPnL, formatPercent, } from './formatting.js';
export { createPosition, createPositionFromLegacy, updateDerivedFields, cloneWithLegs, toLegacyFormat, } from './factory.js';
//# sourceMappingURL=index.js.map