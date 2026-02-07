/**
 * Position Formatting
 *
 * Utilities for formatting positions for display.
 * Uses TastyTrade/CBOE notation conventions.
 */
import { POSITION_TYPE_LABELS, POSITION_TYPE_CODES, POSITION_TYPE_COLORS } from './types.js';
/**
 * Format a single leg for display
 * Example: "+1 5900C" or "-2 5950P"
 */
export function formatLeg(leg) {
    const sign = leg.quantity > 0 ? '+' : '';
    const right = leg.right === 'call' ? 'C' : 'P';
    return `${sign}${leg.quantity} ${leg.strike}${right}`;
}
/**
 * Format all legs as a compact notation string
 * Example: "+1 5880C / -2 5900C / +1 5920C"
 */
export function formatLegsDisplay(legs) {
    if (legs.length === 0)
        return '';
    // Sort by strike for consistent display
    const sorted = [...legs].sort((a, b) => a.strike - b.strike);
    // For iron condors/flies, separate put and call sides with |
    const puts = sorted.filter(l => l.right === 'put');
    const calls = sorted.filter(l => l.right === 'call');
    if (puts.length >= 2 && calls.length >= 2) {
        const putPart = puts.map(formatLeg).join(' / ');
        const callPart = calls.map(formatLeg).join(' / ');
        return `${putPart} | ${callPart}`;
    }
    return sorted.map(formatLeg).join(' / ');
}
/**
 * Format the full position label
 * Example: "Long Call Butterfly" or "Short Iron Condor"
 */
export function formatPositionLabel(positionType, direction, legs) {
    const dirLabel = direction === 'long' ? 'Long' : 'Short';
    const typeLabel = POSITION_TYPE_LABELS[positionType];
    // Add call/put for single-type positions
    const singleTypePositions = [
        'single', 'vertical', 'calendar', 'diagonal', 'butterfly', 'bwb', 'condor'
    ];
    if (singleTypePositions.includes(positionType)) {
        const rights = new Set(legs.map(l => l.right));
        const firstLeg = legs[0];
        if (rights.size === 1 && firstLeg) {
            const sideLabel = firstLeg.right === 'call' ? 'Call' : 'Put';
            return `${dirLabel} ${sideLabel} ${typeLabel}`;
        }
    }
    return `${dirLabel} ${typeLabel}`;
}
/**
 * Format position for compact list display
 */
export function formatPositionForDisplay(symbol, positionType, direction, legs, dte, debit, isSymmetric) {
    return {
        symbol,
        label: formatPositionLabel(positionType, direction, legs),
        legsNotation: formatLegsDisplay(legs),
        dte: `${dte}d`,
        debit: debit !== null ? `$${debit.toFixed(2)}` : '',
        isAsymmetric: positionType === 'bwb' || (isSymmetric === false),
    };
}
/**
 * Get short type code for badge display
 */
export function getPositionTypeCode(positionType) {
    return POSITION_TYPE_CODES[positionType] || 'CUST';
}
/**
 * Get badge color for position type
 */
export function getPositionTypeColor(positionType) {
    return POSITION_TYPE_COLORS[positionType] || '#6b7280';
}
/**
 * Get human-readable label for position type
 */
export function getPositionTypeLabel(positionType) {
    return POSITION_TYPE_LABELS[positionType] || 'Custom';
}
/**
 * Format expiration date for display
 * Example: "Mar 14" or "Mar 14 '25"
 */
export function formatExpiration(expiration, includeYear = false) {
    const date = new Date(expiration + 'T00:00:00');
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[date.getMonth()];
    const day = date.getDate();
    if (includeYear) {
        const year = date.getFullYear().toString().slice(-2);
        return `${month} ${day} '${year}`;
    }
    return `${month} ${day}`;
}
/**
 * Check if multiple legs have different expirations
 */
export function hasMultipleExpirations(legs) {
    const expirations = new Set(legs.map(l => l.expiration));
    return expirations.size > 1;
}
/**
 * Get all unique expirations from legs, sorted by date
 */
export function getUniqueExpirations(legs) {
    const expirations = [...new Set(legs.map(l => l.expiration))];
    return expirations.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
}
/**
 * Format a cost basis value with currency symbol
 */
export function formatCostBasis(value, type) {
    if (value === null || value === undefined)
        return '';
    const formatted = `$${Math.abs(value).toFixed(2)}`;
    if (type === 'credit') {
        return `(${formatted})`; // Credits shown in parentheses
    }
    return formatted;
}
/**
 * Format a price change or P&L value
 */
export function formatPnL(value) {
    const sign = value >= 0 ? '+' : '';
    return `${sign}$${value.toFixed(2)}`;
}
/**
 * Format a percentage value
 */
export function formatPercent(value, decimals = 1) {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(decimals)}%`;
}
//# sourceMappingURL=formatting.js.map