/**
 * Core Position Types
 *
 * Platform-agnostic position types using TastyTrade/CBOE conventions.
 * This is the source of truth for all position-related types across
 * web, desktop, and mobile applications.
 */
// ============================================================
// Display Constants
// ============================================================
/** Human-readable labels for position types */
export const POSITION_TYPE_LABELS = {
    single: 'Single',
    vertical: 'Vertical',
    calendar: 'Calendar',
    diagonal: 'Diagonal',
    butterfly: 'Butterfly',
    bwb: 'BWB',
    condor: 'Condor',
    straddle: 'Straddle',
    strangle: 'Strangle',
    iron_fly: 'Iron Fly',
    iron_condor: 'Iron Condor',
    custom: 'Custom',
};
/** Short codes for compact display */
export const POSITION_TYPE_CODES = {
    single: 'SGL',
    vertical: 'VS',
    calendar: 'CAL',
    diagonal: 'DIAG',
    butterfly: 'BF',
    bwb: 'BWB',
    condor: 'CDR',
    straddle: 'STR',
    strangle: 'STRG',
    iron_fly: 'IF',
    iron_condor: 'IC',
    custom: 'CUST',
};
/** Badge colors for position types */
export const POSITION_TYPE_COLORS = {
    single: '#6b7280', // gray
    vertical: '#3b82f6', // blue
    calendar: '#8b5cf6', // purple
    diagonal: '#a855f7', // violet
    butterfly: '#22c55e', // green
    bwb: '#eab308', // yellow
    condor: '#06b6d4', // cyan
    straddle: '#f97316', // orange
    strangle: '#f59e0b', // amber
    iron_fly: '#ec4899', // pink
    iron_condor: '#ef4444', // red
    custom: '#9ca3af', // gray
};
//# sourceMappingURL=types.js.map