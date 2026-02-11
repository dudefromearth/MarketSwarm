/**
 * Symbol Configuration Registry
 *
 * Single source of truth for per-symbol trading parameters:
 * strike increments, spread widths, strike ranges, expiration patterns.
 *
 * Resolution order: symbolOverrides → assetTypeDefaults → HARDCODED_DEFAULTS
 * Backed by settings table (key=symbol_config_registry, category=trading).
 */

import { useState, useEffect, useCallback, useRef } from 'react';

// ── Types ───────────────────────────────────────────────────────────────────

export interface AssetTypeConfig {
  strikeIncrement: number;
  defaultWidth: number;
  minWidth: number;
  strikeRange: number;
  expirationPattern: 'daily' | 'weekly' | 'monthly';
}

export interface SymbolOverride extends Partial<AssetTypeConfig> {
  spotKey?: string;
}

export interface SymbolConfigRegistry {
  assetTypeDefaults: Record<string, AssetTypeConfig>;
  symbolOverrides: Record<string, SymbolOverride>;
}

export interface ResolvedSymbolConfig extends AssetTypeConfig {
  spotKey: string;
}

interface AvailableSymbol {
  symbol: string;
  name: string;
  asset_type: string;
  enabled: boolean;
}

// ── Hardcoded Defaults (fallback when registry unavailable) ─────────────────

export const HARDCODED_DEFAULTS: SymbolConfigRegistry = {
  assetTypeDefaults: {
    index_option: { strikeIncrement: 5, defaultWidth: 20, minWidth: 5, strikeRange: 500, expirationPattern: 'daily' },
    etf_option:   { strikeIncrement: 1, defaultWidth: 5,  minWidth: 1, strikeRange: 50,  expirationPattern: 'daily' },
    stock:        { strikeIncrement: 1, defaultWidth: 5,  minWidth: 1, strikeRange: 100, expirationPattern: 'weekly' },
    future:       { strikeIncrement: 5, defaultWidth: 20, minWidth: 5, strikeRange: 200, expirationPattern: 'monthly' },
  },
  symbolOverrides: {
    SPX:  { spotKey: 'I:SPX', strikeIncrement: 5, defaultWidth: 20, minWidth: 5, strikeRange: 500, expirationPattern: 'daily' },
    SPXW: { spotKey: 'I:SPX', strikeIncrement: 5, defaultWidth: 20, minWidth: 5, strikeRange: 500, expirationPattern: 'daily' },
    NDX:  { spotKey: 'I:NDX', strikeIncrement: 25, defaultWidth: 50, minWidth: 25, strikeRange: 500, expirationPattern: 'daily' },
    NDXP: { spotKey: 'I:NDX', strikeIncrement: 25, defaultWidth: 50, minWidth: 25, strikeRange: 500, expirationPattern: 'daily' },
    VIX:  { spotKey: 'I:VIX', strikeIncrement: 1, defaultWidth: 2, minWidth: 1, strikeRange: 30, expirationPattern: 'daily' },
    RUT:  { spotKey: 'I:RUT', strikeIncrement: 5, defaultWidth: 20, minWidth: 5, strikeRange: 500, expirationPattern: 'daily' },
    XSP:  { spotKey: 'I:XSP', strikeIncrement: 1, defaultWidth: 2, minWidth: 1, strikeRange: 50, expirationPattern: 'daily' },
  },
};

const FALLBACK_ASSET_CONFIG: AssetTypeConfig = {
  strikeIncrement: 1,
  defaultWidth: 5,
  minWidth: 1,
  strikeRange: 100,
  expirationPattern: 'weekly',
};

const JOURNAL_API = '';

// ── Module-Level Cache ──────────────────────────────────────────────────────

let _registryCache: SymbolConfigRegistry | null = null;
let _symbolsCache: AvailableSymbol[] | null = null;
let _fetchPromise: Promise<void> | null = null;

export function getRegistryCache(): SymbolConfigRegistry | null {
  return _registryCache;
}

export function getSymbolsCache(): AvailableSymbol[] | null {
  return _symbolsCache;
}

function invalidateCache() {
  _registryCache = null;
  _symbolsCache = null;
  _fetchPromise = null;
}

// ── Core Resolution ─────────────────────────────────────────────────────────

/** Look up the asset_type for a symbol from the symbols list */
function getAssetType(symbol: string, symbols: AvailableSymbol[]): string | undefined {
  return symbols.find(s => s.symbol === symbol)?.asset_type;
}

/**
 * Resolve full config for a symbol.
 * Merges: assetTypeDefaults[asset_type] ← symbolOverrides[symbol]
 */
export function resolveSymbolConfig(
  symbol: string,
  registry: SymbolConfigRegistry,
  symbols: AvailableSymbol[],
): ResolvedSymbolConfig {
  const assetType = getAssetType(symbol, symbols);
  const base = (assetType && registry.assetTypeDefaults[assetType]) || FALLBACK_ASSET_CONFIG;
  const override = registry.symbolOverrides[symbol] || {};

  return {
    strikeIncrement: override.strikeIncrement ?? base.strikeIncrement,
    defaultWidth: override.defaultWidth ?? base.defaultWidth,
    minWidth: override.minWidth ?? base.minWidth,
    strikeRange: override.strikeRange ?? base.strikeRange,
    expirationPattern: override.expirationPattern ?? base.expirationPattern,
    spotKey: override.spotKey ?? symbol, // stocks use raw ticker
  };
}

/**
 * Resolve just the SSE spot key for a symbol.
 * Used by symbolResolver.ts backward-compat wrapper.
 */
export function resolveSpotKey(symbol: string, registry: SymbolConfigRegistry): string {
  return registry.symbolOverrides[symbol]?.spotKey ?? symbol;
}

// ── Expiration Utilities ────────────────────────────────────────────────────

/** Check if a date is an expiration day for the given pattern */
export function isExpirationDay(date: Date, pattern: 'daily' | 'weekly' | 'monthly'): boolean {
  const day = date.getDay();
  if (day === 0 || day === 6) return false; // weekends never expire

  switch (pattern) {
    case 'daily':
      return true; // Mon-Fri
    case 'weekly':
      return day === 5; // Friday
    case 'monthly': {
      // 3rd Friday of the month
      if (day !== 5) return false;
      const d = date.getDate();
      return d >= 15 && d <= 21;
    }
    default:
      return day === 1 || day === 3 || day === 5; // fallback: Mon/Wed/Fri
  }
}

/**
 * Get current Eastern Time minutes since midnight.
 * Uses Intl to handle EST/EDT automatically.
 */
function getETMinutes(): number {
  const now = new Date();
  const etStr = now.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false });
  // Format: "M/D/YYYY, HH:MM:SS"
  const timePart = etStr.split(', ')[1];
  const [h, m] = timePart.split(':').map(Number);
  return h * 60 + m;
}

/** Has the market already closed for the day? (past 4:00 PM ET) */
function isAfterMarketClose(): boolean {
  return getETMinutes() >= 960; // 16:00 ET
}

/**
 * Get the current (or next) expiration date for a pattern.
 *
 * Rules:
 * - If today is an expiration day and market has NOT yet closed → use today
 *   (includes pre-market: you're building a position for today's expiration)
 * - If today is an expiration day but market already closed → next expiration
 * - If today is not an expiration day → next expiration
 */
export function getCurrentExpiration(pattern: 'daily' | 'weekly' | 'monthly'): Date {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (isExpirationDay(today, pattern) && !isAfterMarketClose()) {
    return today;
  }

  // Find next expiration day
  const next = new Date(today);
  for (let i = 0; i < 35; i++) {
    next.setDate(next.getDate() + 1);
    if (isExpirationDay(next, pattern)) {
      return next;
    }
  }
  return next;
}

/** Get the next expiration after a given date */
export function getNextExpiration(current: Date, pattern: 'daily' | 'weekly' | 'monthly'): Date {
  const next = new Date(current);
  for (let i = 0; i < 35; i++) {
    next.setDate(next.getDate() + 1);
    if (isExpirationDay(next, pattern)) {
      return next;
    }
  }
  return next;
}

// ── Fetch & Seed ────────────────────────────────────────────────────────────

async function fetchRegistryAndSymbols(): Promise<void> {
  const [regRes, symRes] = await Promise.all([
    fetch(`${JOURNAL_API}/api/settings/symbol_config_registry`, { credentials: 'include' }),
    fetch(`${JOURNAL_API}/api/symbols`, { credentials: 'include' }),
  ]);

  // Handle symbols
  if (symRes.ok) {
    const symData = await symRes.json();
    if (symData.success && symData.data) {
      _symbolsCache = symData.data.filter((s: AvailableSymbol) => s.enabled);
    }
  }

  // Handle registry — seed if missing
  if (regRes.ok) {
    const regData = await regRes.json();
    if (regData.success && regData.data?.value) {
      _registryCache = regData.data.value;
    } else {
      // Setting exists but value is unexpected — use and seed defaults
      await seedDefaults();
    }
  } else if (regRes.status === 404) {
    await seedDefaults();
  } else {
    // Non-404 error — use hardcoded defaults
    _registryCache = HARDCODED_DEFAULTS;
  }
}

async function seedDefaults(): Promise<void> {
  _registryCache = HARDCODED_DEFAULTS;
  try {
    await fetch(`${JOURNAL_API}/api/settings/symbol_config_registry`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ value: HARDCODED_DEFAULTS, category: 'trading' }),
    });
  } catch {
    // Seeding failed — still using in-memory defaults, no problem
  }
}

function ensureFetched(): Promise<void> {
  if (_registryCache && _symbolsCache) return Promise.resolve();
  if (!_fetchPromise) {
    _fetchPromise = fetchRegistryAndSymbols().catch(() => {
      _registryCache = HARDCODED_DEFAULTS;
      _fetchPromise = null;
    });
  }
  return _fetchPromise;
}

// ── React Hook ──────────────────────────────────────────────────────────────

export function useSymbolConfig() {
  const [registry, setRegistry] = useState<SymbolConfigRegistry>(_registryCache || HARDCODED_DEFAULTS);
  const [symbols, setSymbols] = useState<AvailableSymbol[]>(_symbolsCache || []);
  const [loading, setLoading] = useState(!_registryCache || !_symbolsCache);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    ensureFetched().then(() => {
      if (!mountedRef.current) return;
      if (_registryCache) setRegistry(_registryCache);
      if (_symbolsCache) setSymbols(_symbolsCache);
      setLoading(false);
    });
    return () => { mountedRef.current = false; };
  }, []);

  const getConfig = useCallback(
    (symbol: string): ResolvedSymbolConfig => resolveSymbolConfig(symbol, registry, symbols),
    [registry, symbols],
  );

  const refresh = useCallback(async () => {
    invalidateCache();
    setLoading(true);
    await ensureFetched();
    if (mountedRef.current) {
      if (_registryCache) setRegistry(_registryCache);
      if (_symbolsCache) setSymbols(_symbolsCache);
      setLoading(false);
    }
  }, []);

  return { registry, symbols, loading, getConfig, refresh };
}
