/**
 * Safe formatting utilities for handling API data with potential type mismatches
 *
 * These utilities gracefully handle:
 * - null/undefined values
 * - Wrong types (string instead of number, etc.)
 * - Missing properties
 *
 * Instead of crashing, they return fallback values and log warnings.
 */

type LogLevel = 'warn' | 'error' | 'silent';

interface FormatOptions {
  logLevel?: LogLevel;
  context?: string;
}

const defaultOptions: FormatOptions = {
  logLevel: 'warn',
  context: 'unknown',
};

/**
 * Log a type mismatch warning
 */
function logMismatch(
  expected: string,
  actual: string,
  value: unknown,
  context: string,
  level: LogLevel
) {
  if (level === 'silent') return;

  const message = `[SafeFormat] Type mismatch in ${context}: expected ${expected}, got ${actual}`;
  const details = { value, context };

  if (level === 'error') {
    console.error(message, details);
  } else {
    console.warn(message, details);
  }
}

/**
 * Safely format a number with fixed decimals
 * Handles: null, undefined, strings, NaN
 */
export function safeFixed(
  value: unknown,
  decimals: number = 2,
  fallback: string = '—',
  options: FormatOptions = {}
): string {
  const opts = { ...defaultOptions, ...options };

  if (value == null) {
    return fallback;
  }

  const num = typeof value === 'string' ? parseFloat(value) : Number(value);

  if (isNaN(num)) {
    logMismatch('number', typeof value, value, opts.context!, opts.logLevel!);
    return fallback;
  }

  return num.toFixed(decimals);
}

/**
 * Safely format a currency value
 * Handles: null, undefined, strings, NaN
 */
export function safeCurrency(
  value: unknown,
  decimals: number = 2,
  fallback: string = '—',
  options: FormatOptions = {}
): string {
  const formatted = safeFixed(value, decimals, '', options);
  if (formatted === '') return fallback;
  return `$${formatted}`;
}

/**
 * Safely format a percentage
 * Handles: null, undefined, strings, NaN
 */
export function safePercent(
  value: unknown,
  decimals: number = 1,
  fallback: string = '—',
  options: FormatOptions = {}
): string {
  const formatted = safeFixed(value, decimals, '', options);
  if (formatted === '') return fallback;
  return `${formatted}%`;
}

/**
 * Safely get a string value
 * Handles: null, undefined, non-strings
 */
export function safeString(
  value: unknown,
  fallback: string = '—',
  options: FormatOptions = {}
): string {
  const opts = { ...defaultOptions, ...options };

  if (value == null) {
    return fallback;
  }

  if (typeof value !== 'string') {
    logMismatch('string', typeof value, value, opts.context!, opts.logLevel!);
    return String(value);
  }

  return value || fallback;
}

/**
 * Safely get a number value
 * Handles: null, undefined, strings, NaN
 */
export function safeNumber(
  value: unknown,
  fallback: number = 0,
  options: FormatOptions = {}
): number {
  const opts = { ...defaultOptions, ...options };

  if (value == null) {
    return fallback;
  }

  const num = typeof value === 'string' ? parseFloat(value) : Number(value);

  if (isNaN(num)) {
    logMismatch('number', typeof value, value, opts.context!, opts.logLevel!);
    return fallback;
  }

  return num;
}

/**
 * Safely format a date
 * Handles: null, undefined, invalid dates, various formats
 */
export function safeDate(
  value: unknown,
  format: 'date' | 'time' | 'datetime' | 'relative' = 'date',
  fallback: string = '—',
  options: FormatOptions = {}
): string {
  const opts = { ...defaultOptions, ...options };

  if (value == null) {
    return fallback;
  }

  let date: Date;

  if (value instanceof Date) {
    date = value;
  } else if (typeof value === 'string' || typeof value === 'number') {
    date = new Date(value);
  } else {
    logMismatch('Date|string|number', typeof value, value, opts.context!, opts.logLevel!);
    return fallback;
  }

  if (isNaN(date.getTime())) {
    logMismatch('valid date', 'invalid date', value, opts.context!, opts.logLevel!);
    return fallback;
  }

  switch (format) {
    case 'date':
      return date.toLocaleDateString();
    case 'time':
      return date.toLocaleTimeString();
    case 'datetime':
      return date.toLocaleString();
    case 'relative':
      return getRelativeTime(date);
    default:
      return date.toLocaleDateString();
  }
}

/**
 * Get relative time string (e.g., "2 hours ago")
 */
function getRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

/**
 * Safely access a nested property
 * Handles: null, undefined, missing properties
 */
export function safeGet<T>(
  obj: unknown,
  path: string,
  fallback: T
): T {
  if (obj == null) return fallback;

  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (current == null || typeof current !== 'object') {
      return fallback;
    }
    current = (current as Record<string, unknown>)[key];
  }

  return (current ?? fallback) as T;
}

/**
 * Create a safe formatter with preset options
 */
export function createSafeFormatter(defaultContext: string) {
  const opts: FormatOptions = { context: defaultContext };

  return {
    fixed: (value: unknown, decimals?: number, fallback?: string) =>
      safeFixed(value, decimals, fallback, opts),
    currency: (value: unknown, decimals?: number, fallback?: string) =>
      safeCurrency(value, decimals, fallback, opts),
    percent: (value: unknown, decimals?: number, fallback?: string) =>
      safePercent(value, decimals, fallback, opts),
    string: (value: unknown, fallback?: string) =>
      safeString(value, fallback, opts),
    number: (value: unknown, fallback?: number) =>
      safeNumber(value, fallback, opts),
    date: (value: unknown, format?: 'date' | 'time' | 'datetime' | 'relative', fallback?: string) =>
      safeDate(value, format, fallback, opts),
    get: <T>(obj: unknown, path: string, fallback: T) =>
      safeGet(obj, path, fallback),
  };
}

export default {
  fixed: safeFixed,
  currency: safeCurrency,
  percent: safePercent,
  string: safeString,
  number: safeNumber,
  date: safeDate,
  get: safeGet,
  createFormatter: createSafeFormatter,
};
