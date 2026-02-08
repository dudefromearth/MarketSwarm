/**
 * Trade Importers - Parse CSV exports from various trading platforms
 *
 * Supported Platforms:
 * - ThinkOrSwim (TOS) - Account Statement CSV
 * - Custom CSV - User-fillable template for any broker
 * - Tastytrade (planned)
 * - Interactive Brokers (planned)
 */

export type Platform = 'tos' | 'tastytrade' | 'ibkr' | 'custom';

export interface ImportedLeg {
  symbol: string;           // Underlying symbol (SPX, NDX, etc.)
  expiration: string;       // ISO date: YYYY-MM-DD
  strike: number;
  type: 'call' | 'put';
  quantity: number;         // Positive = long, negative = short
  price: number;            // Per-contract price
}

export interface ImportedTrade {
  id: string;               // Generated unique ID
  platform: Platform;
  tradeDate: string;        // ISO date: YYYY-MM-DD
  tradeTime?: string;       // HH:MM:SS if available
  symbol: string;           // Underlying
  legs: ImportedLeg[];
  totalPrice: number;       // Net debit/credit for the trade
  commission: number;
  fees: number;
  positionEffect: 'open' | 'close';
  rawData?: Record<string, string>;  // Original CSV row for debugging
}

export interface ImportResult {
  success: boolean;
  trades: ImportedTrade[];
  errors: string[];
  warnings: string[];
  stats: {
    totalRows: number;
    parsedTrades: number;
    skippedRows: number;
  };
}

/**
 * Detect platform from CSV content
 */
export function detectPlatform(content: string): Platform | null {
  const upper = content.toUpperCase();

  // TOS: Account Statement header
  if (upper.includes('ACCOUNT STATEMENT FOR') || upper.includes('THINKORSWIM')) {
    return 'tos';
  }

  // Tastytrade: specific column headers
  if (upper.includes('INSTRUMENT TYPE') && upper.includes('ROOT SYMBOL')) {
    return 'tastytrade';
  }

  // IBKR: Flex Query markers
  if (upper.includes('FLEX') || upper.includes('INTERACTIVE BROKERS')) {
    return 'ibkr';
  }

  return null;
}

export { parseTosAccountStatement } from './thinkorswim';
export { parseCustomCsv, generateCustomTemplate } from './custom';
export { analyzeWithAI, parseWithMapping, type ColumnMapping, type AIAnalysisResult } from './aiAnalyzer';
export { recognizeStrategy, type RecognizedStrategy } from './strategyRecognition';
