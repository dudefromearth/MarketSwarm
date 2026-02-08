/**
 * AI-Assisted CSV Analysis
 *
 * Uses AI to analyze unknown CSV formats and suggest column mappings
 * for trade import.
 */

import type { Platform } from './index';

export interface ColumnMapping {
  date?: number;
  time?: number;
  symbol?: number;
  expiration?: number;
  strike?: number;
  type?: number;        // call/put
  quantity?: number;
  price?: number;
  commission?: number;
  fees?: number;
  effect?: number;      // open/close
  side?: number;        // buy/sell (alternative to signed quantity)
}

export interface AIAnalysisResult {
  success: boolean;
  platform?: Platform | 'unknown';
  platformConfidence?: number;
  columnMapping: ColumnMapping;
  dateFormat?: string;
  notes?: string[];
  sampleParsed?: Array<{
    date: string;
    symbol: string;
    strike: number;
    type: string;
    quantity: number;
    price: number;
  }>;
  error?: string;
}

/**
 * Analyze CSV content using AI to detect format and column mappings
 */
export async function analyzeWithAI(content: string): Promise<AIAnalysisResult> {
  // Extract first 20 lines for analysis (header + sample data)
  const lines = content.split(/\r?\n/).filter(line => line.trim());
  const sampleLines = lines.slice(0, 20);
  const sampleContent = sampleLines.join('\n');

  try {
    const response = await fetch('/api/ai/analyze-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        sample: sampleContent,
        totalRows: lines.length,
      }),
    });

    if (!response.ok) {
      throw new Error(`AI analysis failed: ${response.status}`);
    }

    const result = await response.json();

    if (!result.success) {
      return {
        success: false,
        columnMapping: {},
        error: result.error || 'AI analysis failed',
      };
    }

    return {
      success: true,
      platform: result.platform || 'unknown',
      platformConfidence: result.platformConfidence,
      columnMapping: result.columnMapping || {},
      dateFormat: result.dateFormat,
      notes: result.notes || [],
      sampleParsed: result.sampleParsed,
    };
  } catch (err) {
    return {
      success: false,
      columnMapping: {},
      error: err instanceof Error ? err.message : 'Failed to analyze CSV',
    };
  }
}

/**
 * Parse CSV using AI-detected column mappings
 */
export function parseWithMapping(
  content: string,
  mapping: ColumnMapping,
  dateFormat?: string
): { trades: any[]; errors: string[] } {
  const lines = content.split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 2) {
    return { trades: [], errors: ['No data rows found'] };
  }

  const trades: any[] = [];
  const errors: string[] = [];

  // Skip header row
  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);

    try {
      const date = mapping.date !== undefined ? values[mapping.date] : '';
      const time = mapping.time !== undefined ? values[mapping.time] : '';
      const symbol = mapping.symbol !== undefined ? values[mapping.symbol] : 'SPX';
      const expiration = mapping.expiration !== undefined ? values[mapping.expiration] : '';
      const strike = mapping.strike !== undefined ? parseFloat(values[mapping.strike]) : 0;
      const typeRaw = mapping.type !== undefined ? values[mapping.type] : 'call';
      const qtyRaw = mapping.quantity !== undefined ? values[mapping.quantity] : '1';
      const price = mapping.price !== undefined ? parseFloat(values[mapping.price]) : 0;
      const commission = mapping.commission !== undefined ? parseFloat(values[mapping.commission]) || 0 : 0;
      const fees = mapping.fees !== undefined ? parseFloat(values[mapping.fees]) || 0 : 0;
      const effect = mapping.effect !== undefined ? values[mapping.effect] : 'open';
      const side = mapping.side !== undefined ? values[mapping.side] : '';

      // Determine quantity sign from side if present
      let quantity = parseInt(qtyRaw.replace(/[^-\d]/g, '')) || 1;
      if (side) {
        const sideLower = side.toLowerCase();
        if (sideLower.includes('sell') || sideLower.includes('sold') || sideLower.includes('short')) {
          quantity = -Math.abs(quantity);
        } else {
          quantity = Math.abs(quantity);
        }
      }

      // Normalize type
      const type = typeRaw.toLowerCase().includes('put') ? 'put' : 'call';

      // Normalize effect
      const positionEffect = effect.toLowerCase().includes('close') ? 'close' : 'open';

      if (!date || strike === 0) {
        continue; // Skip invalid rows
      }

      trades.push({
        id: `ai-${i}`,
        platform: 'custom' as Platform,
        tradeDate: normalizeDate(date, dateFormat),
        tradeTime: time || undefined,
        symbol: symbol.toUpperCase().replace(/[^A-Z]/g, ''),
        legs: [{
          symbol: symbol.toUpperCase().replace(/[^A-Z]/g, ''),
          expiration: normalizeDate(expiration, dateFormat),
          strike,
          type,
          quantity,
          price,
        }],
        totalPrice: price * quantity * 100,
        commission,
        fees,
        positionEffect,
      });
    } catch (err) {
      errors.push(`Row ${i + 1}: ${err}`);
    }
  }

  // Group trades by date+time
  const grouped = groupByDateTime(trades);

  return { trades: grouped, errors };
}

function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  return result;
}

function normalizeDate(dateStr: string, format?: string): string {
  if (!dateStr) return '';

  // Already ISO format
  if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) {
    return dateStr.split(/[T\s]/)[0];
  }

  // US format: MM/DD/YYYY or M/D/YY
  const usMatch = dateStr.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
  if (usMatch) {
    const [, month, day, year] = usMatch;
    const fullYear = parseInt(year) < 100 ? 2000 + parseInt(year) : parseInt(year);
    return `${fullYear}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
  }

  // Try to parse with Date
  try {
    const d = new Date(dateStr);
    if (!isNaN(d.getTime())) {
      return d.toISOString().split('T')[0];
    }
  } catch {}

  return dateStr;
}

function groupByDateTime(trades: any[]): any[] {
  const groups = new Map<string, any[]>();

  for (const trade of trades) {
    const key = `${trade.tradeDate}-${trade.tradeTime || ''}`;
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(trade);
  }

  const result: any[] = [];
  let idx = 0;

  for (const [, groupTrades] of groups) {
    if (groupTrades.length === 1) {
      result.push({ ...groupTrades[0], id: `ai-grouped-${idx++}` });
    } else {
      // Combine legs
      const first = groupTrades[0];
      result.push({
        ...first,
        id: `ai-grouped-${idx++}`,
        legs: groupTrades.flatMap(t => t.legs),
        totalPrice: groupTrades.reduce((sum, t) => sum + t.totalPrice, 0),
        commission: groupTrades.reduce((sum, t) => sum + t.commission, 0),
        fees: groupTrades.reduce((sum, t) => sum + t.fees, 0),
      });
    }
  }

  return result;
}
