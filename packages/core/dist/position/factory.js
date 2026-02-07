/**
 * Position Factory
 *
 * Creates Position objects from various inputs (legs, parsed scripts, legacy formats).
 * Handles all derived field computation.
 */
import { recognizePositionType, getCenterStrike, getWidth, getPrimaryExpiration, } from './recognition.js';
/**
 * Generate a unique position ID
 *
 * Uses a combination of timestamp and random string for uniqueness.
 * Platform-agnostic implementation that works in all environments.
 */
function defaultGenerateId() {
    // Simple unique ID that works everywhere
    const timestamp = Date.now().toString(36);
    const random1 = Math.random().toString(36).slice(2, 11);
    const random2 = Math.random().toString(36).slice(2, 6);
    return `pos_${timestamp}_${random1}${random2}`;
}
/**
 * Calculate days to expiration from a date string
 */
function calculateDTE(expiration, now) {
    const expDate = new Date(expiration + 'T16:00:00'); // 4pm ET market close
    const diffMs = expDate.getTime() - now;
    return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}
/**
 * Create a Position from legs
 *
 * This is the primary factory function. It:
 * 1. Recognizes the position type from the legs
 * 2. Computes derived fields (strike, width, dte, expiration)
 * 3. Sets timestamps
 * 4. Returns a complete Position object
 */
export function createPosition(input, options = {}) {
    const { userId, symbol, underlying = `I:${symbol}`, legs, costBasis = 0, costBasisType = 'debit', visible = true, sortOrder = 0, color = null, label = null, importMetadata, } = input;
    const generateId = options.generateId ?? defaultGenerateId;
    const now = options.now ?? Date.now();
    const nowISO = new Date(now).toISOString();
    // Recognize position type from legs
    const recognition = recognizePositionType(legs);
    // Compute derived fields
    const primaryExpiration = getPrimaryExpiration(legs);
    const dte = primaryExpiration ? calculateDTE(primaryExpiration, now) : 0;
    const strike = getCenterStrike(legs);
    const width = getWidth(legs);
    return {
        id: generateId(),
        userId,
        symbol,
        underlying,
        positionType: recognition.type,
        direction: recognition.direction,
        legs,
        primaryExpiration,
        dte,
        strike,
        width,
        costBasis,
        costBasisType,
        visible,
        sortOrder,
        color,
        label,
        importMetadata,
        addedAt: now,
        createdAt: nowISO,
        updatedAt: nowISO,
    };
}
/**
 * Create a Position from legacy strategy format
 *
 * Converts strike/width format to legs, then creates a Position.
 */
export function createPositionFromLegacy(input, options = {}) {
    const { userId, symbol, underlying = `I:${symbol}`, strategy, side, strike, width, expiration, debit, visible = true, sortOrder = 0, color = null, label = null, } = input;
    // Build legs from legacy format
    const legs = [];
    switch (strategy) {
        case 'single':
            legs.push({
                strike,
                expiration,
                right: side,
                quantity: 1,
            });
            break;
        case 'vertical':
            if (side === 'call') {
                // Bull call spread: long lower, short higher
                legs.push({ strike, expiration, right: 'call', quantity: 1 });
                legs.push({ strike: strike + width, expiration, right: 'call', quantity: -1 });
            }
            else {
                // Bear put spread: long higher, short lower
                legs.push({ strike: strike - width, expiration, right: 'put', quantity: -1 });
                legs.push({ strike, expiration, right: 'put', quantity: 1 });
            }
            break;
        case 'butterfly':
            legs.push({ strike: strike - width, expiration, right: side, quantity: 1 });
            legs.push({ strike, expiration, right: side, quantity: -2 });
            legs.push({ strike: strike + width, expiration, right: side, quantity: 1 });
            break;
    }
    return createPosition({
        userId,
        symbol,
        underlying,
        legs,
        costBasis: debit !== null && debit !== undefined ? Math.abs(debit) : 0,
        costBasisType: 'debit',
        visible,
        sortOrder,
        color,
        label,
    }, options);
}
/**
 * Update derived fields after legs change
 *
 * Call this when modifying legs to recompute type, strike, width, etc.
 */
export function updateDerivedFields(position, now = Date.now()) {
    const recognition = recognizePositionType(position.legs);
    const primaryExpiration = getPrimaryExpiration(position.legs);
    const dte = primaryExpiration ? calculateDTE(primaryExpiration, now) : 0;
    const strike = getCenterStrike(position.legs);
    const width = getWidth(position.legs);
    return {
        ...position,
        positionType: recognition.type,
        direction: recognition.direction,
        primaryExpiration,
        dte,
        strike,
        width,
        updatedAt: new Date(now).toISOString(),
    };
}
/**
 * Clone a position with new legs
 *
 * Creates a copy with updated legs and recomputed derived fields.
 */
export function cloneWithLegs(position, legs, now = Date.now()) {
    return updateDerivedFields({
        ...position,
        legs,
        updatedAt: new Date(now).toISOString(),
    }, now);
}
export function toLegacyFormat(position) {
    // Map position type to legacy strategy type
    let strategy = 'single';
    if (position.positionType === 'butterfly' || position.positionType === 'bwb') {
        strategy = 'butterfly';
    }
    else if (position.positionType === 'vertical') {
        strategy = 'vertical';
    }
    // Determine side from legs
    const calls = position.legs.filter(l => l.right === 'call').length;
    const puts = position.legs.filter(l => l.right === 'put').length;
    const side = calls >= puts ? 'call' : 'put';
    return {
        id: position.id,
        strategy,
        side,
        strike: position.strike,
        width: position.width ?? 0,
        dte: position.dte,
        expiration: position.primaryExpiration,
        debit: position.costBasisType === 'debit' ? position.costBasis : -position.costBasis,
        visible: position.visible,
        addedAt: position.addedAt,
        symbol: position.symbol,
    };
}
//# sourceMappingURL=factory.js.map