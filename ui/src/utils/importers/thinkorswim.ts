/**
 * ThinkOrSwim (TOS) Account Statement CSV Parser
 *
 * Parses the CSV export from TOS Account Statement.
 *
 * Known format characteristics:
 * - Header lines with account info before data
 * - Multiple sections (Account Summary, Trades, etc.)
 * - "Account Trade History" section contains trades
 * - Option symbols in format: .SPX250221C6000 or descriptive
 *
 * Expected columns (may vary by export settings):
 * Exec Time, Spread, Side, Qty, Pos Effect, Symbol, Exp, Strike, Type, Price, Net Price
 */

import type { ImportedTrade, ImportedLeg, ImportResult } from './index';

// Month abbreviations
const MONTHS: Record<string, number> = {
  JAN: 1, FEB: 2, MAR: 3, APR: 4, MAY: 5, JUN: 6,
  JUL: 7, AUG: 8, SEP: 9, OCT: 10, NOV: 11, DEC: 12,
};

interface TosTradeRow {
  execTime?: string;
  spread?: string;
  side?: string;
  qty?: string;
  posEffect?: string;
  symbol?: string;
  exp?: string;
  strike?: string;
  type?: string;
  price?: string;
  netPrice?: string;
  description?: string;
  commissions?: string;
  fees?: string;
  [key: string]: string | undefined;
}

/**
 * Parse TOS option symbol format
 * Examples:
 *   .SPX250221C6000 -> { symbol: 'SPX', exp: '2025-02-21', strike: 6000, type: 'call' }
 *   .SPXW250221C6000 -> { symbol: 'SPX', exp: '2025-02-21', strike: 6000, type: 'call' }
 *   100 SPX 21 FEB 25 6000 CALL -> parsed from components
 */
function parseTosOptionSymbol(symbol: string): Partial<ImportedLeg> | null {
  if (!symbol) return null;

  // Format 1: .SPX250221C6000 or .SPXW250221C6000
  const compactMatch = symbol.match(/\.?([A-Z]+)W?(\d{2})(\d{2})(\d{2})([CP])(\d+)/);
  if (compactMatch) {
    const [, underlying, yy, mm, dd, cp, strike] = compactMatch;
    const year = 2000 + parseInt(yy);
    const month = parseInt(mm).toString().padStart(2, '0');
    const day = parseInt(dd).toString().padStart(2, '0');

    return {
      symbol: underlying.replace(/W$/, ''),  // Remove trailing W for weeklies
      expiration: `${year}-${month}-${day}`,
      strike: parseInt(strike),
      type: cp === 'C' ? 'call' : 'put',
    };
  }

  // Format 2: 100 SPX 21 FEB 25 6000 CALL (descriptive)
  const descriptiveMatch = symbol.match(/(\d+)\s+([A-Z]+)\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{2,4})\s+(\d+)\s+(CALL|PUT)/i);
  if (descriptiveMatch) {
    const [, , underlying, day, monthStr, year, strike, typeStr] = descriptiveMatch;
    const month = MONTHS[monthStr.toUpperCase()];
    if (!month) return null;

    const fullYear = parseInt(year) < 100 ? 2000 + parseInt(year) : parseInt(year);

    return {
      symbol: underlying,
      expiration: `${fullYear}-${month.toString().padStart(2, '0')}-${day.padStart(2, '0')}`,
      strike: parseInt(strike),
      type: typeStr.toLowerCase() as 'call' | 'put',
    };
  }

  return null;
}

/**
 * Parse date from various TOS formats
 * Examples: "2/21/25 10:30:00", "02/21/2025", "2025-02-21"
 */
function parseTosDate(dateStr: string): { date: string; time?: string } | null {
  if (!dateStr) return null;

  // ISO format: 2025-02-21
  if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) {
    const [date, time] = dateStr.split(/[T\s]/);
    return { date, time };
  }

  // US format: M/D/YY HH:MM:SS or MM/DD/YYYY
  const usMatch = dateStr.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?/);
  if (usMatch) {
    const [, month, day, year, time] = usMatch;
    const fullYear = parseInt(year) < 100 ? 2000 + parseInt(year) : parseInt(year);
    const date = `${fullYear}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    return { date, time };
  }

  return null;
}

/**
 * Parse quantity - handle +/- prefixes
 */
function parseQuantity(qtyStr: string, side?: string): number {
  if (!qtyStr) return 0;

  const cleaned = qtyStr.replace(/[,\s]/g, '');
  let qty = parseInt(cleaned);

  if (isNaN(qty)) return 0;

  // Determine sign from side if not in qty string
  if (side) {
    const upperSide = side.toUpperCase();
    if (upperSide.includes('SOLD') || upperSide.includes('SELL')) {
      qty = -Math.abs(qty);
    } else if (upperSide.includes('BOT') || upperSide.includes('BUY')) {
      qty = Math.abs(qty);
    }
  }

  return qty;
}

/**
 * Parse price string to number
 */
function parsePrice(priceStr: string): number {
  if (!priceStr) return 0;
  const cleaned = priceStr.replace(/[$,\s]/g, '');
  const price = parseFloat(cleaned);
  return isNaN(price) ? 0 : price;
}

/**
 * Normalize column header to known key
 */
function normalizeHeader(header: string): string {
  const h = header.toLowerCase().trim();

  // Map various column names to standard keys
  const mappings: Record<string, string> = {
    'exec time': 'execTime',
    'execution time': 'execTime',
    'date/time': 'execTime',
    'date': 'execTime',
    'time': 'execTime',
    'spread': 'spread',
    'strategy': 'spread',
    'side': 'side',
    'action': 'side',
    'qty': 'qty',
    'quantity': 'qty',
    'pos effect': 'posEffect',
    'position effect': 'posEffect',
    'effect': 'posEffect',
    'symbol': 'symbol',
    'underlying': 'symbol',
    'exp': 'exp',
    'expiration': 'exp',
    'exp date': 'exp',
    'strike': 'strike',
    'strike price': 'strike',
    'type': 'type',
    'call/put': 'type',
    'option type': 'type',
    'price': 'price',
    'fill price': 'price',
    'exec price': 'price',
    'net price': 'netPrice',
    'net': 'netPrice',
    'description': 'description',
    'desc': 'description',
    'commission': 'commissions',
    'commissions': 'commissions',
    'comm': 'commissions',
    'fee': 'fees',
    'fees': 'fees',
    'reg fee': 'fees',
  };

  return mappings[h] || h.replace(/\s+/g, '');
}

/**
 * Parse CSV line handling quoted fields
 */
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

/**
 * Find the trade history section and extract header + data rows
 */
function extractTradeSection(lines: string[]): { headers: string[]; rows: string[][] } | null {
  let inTradeSection = false;
  let headers: string[] = [];
  const rows: string[][] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const upper = line.toUpperCase();

    // Detect start of trade section
    if (upper.includes('ACCOUNT TRADE HISTORY') ||
        upper.includes('TRADE HISTORY') ||
        upper.includes('TRANSACTIONS')) {
      inTradeSection = true;
      continue;
    }

    // Detect end of trade section (next section header)
    if (inTradeSection && (
      upper.includes('ACCOUNT SUMMARY') ||
      upper.includes('PROFITS AND LOSSES') ||
      upper.includes('CASH BALANCE') ||
      upper.includes('FOREX') ||
      upper.startsWith('TOTAL')
    )) {
      break;
    }

    if (!inTradeSection) continue;

    const fields = parseCSVLine(line);

    // Detect header row (contains expected column names)
    if (headers.length === 0) {
      const hasExpectedColumns = fields.some(f => {
        const lower = f.toLowerCase();
        return lower.includes('symbol') ||
               lower.includes('qty') ||
               lower.includes('strike') ||
               lower.includes('exec');
      });

      if (hasExpectedColumns) {
        headers = fields.map(normalizeHeader);
        continue;
      }
    }

    // Data row
    if (headers.length > 0 && fields.length >= 3) {
      rows.push(fields);
    }
  }

  if (headers.length === 0 || rows.length === 0) {
    return null;
  }

  return { headers, rows };
}

/**
 * Convert row array to object using headers
 */
function rowToObject(headers: string[], row: string[]): TosTradeRow {
  const obj: TosTradeRow = {};
  for (let i = 0; i < headers.length && i < row.length; i++) {
    obj[headers[i]] = row[i];
  }
  return obj;
}

/**
 * Parse a single trade row into ImportedTrade
 */
function parseTradeRow(row: TosTradeRow, index: number): ImportedTrade | null {
  // Need at least symbol or description to parse
  const symbolStr = row.symbol || row.description || '';
  if (!symbolStr) return null;

  // Parse option symbol
  let parsedOption = parseTosOptionSymbol(symbolStr);

  // If symbol parsing failed, try to build from individual columns
  if (!parsedOption && row.strike && row.type) {
    const strike = parsePrice(row.strike);
    const type = row.type.toLowerCase().includes('call') ? 'call' : 'put';

    // Try to get symbol from the symbol field (might be "SPX" directly)
    let underlying = 'SPX';  // Default
    const symbolMatch = symbolStr.match(/\b(SPX|NDX|RUT|SPY|QQQ|IWM)\b/i);
    if (symbolMatch) {
      underlying = symbolMatch[1].toUpperCase();
    }

    // Parse expiration from exp column
    let expiration = '';
    if (row.exp) {
      const expMatch = row.exp.match(/(\d{1,2})\s*([A-Z]{3})\s*(\d{2,4})/i);
      if (expMatch) {
        const [, day, monthStr, year] = expMatch;
        const month = MONTHS[monthStr.toUpperCase()];
        const fullYear = parseInt(year) < 100 ? 2000 + parseInt(year) : parseInt(year);
        expiration = `${fullYear}-${month.toString().padStart(2, '0')}-${day.padStart(2, '0')}`;
      }
    }

    if (strike > 0 && expiration) {
      parsedOption = { symbol: underlying, expiration, strike, type };
    }
  }

  if (!parsedOption || !parsedOption.symbol || !parsedOption.expiration) {
    return null;  // Can't parse this row
  }

  // Parse date
  const dateInfo = parseTosDate(row.execTime || '');
  const tradeDate = dateInfo?.date || new Date().toISOString().split('T')[0];
  const tradeTime = dateInfo?.time;

  // Parse quantity
  const quantity = parseQuantity(row.qty || '1', row.side);
  if (quantity === 0) return null;

  // Parse prices
  const price = parsePrice(row.price || row.netPrice || '0');
  const commission = parsePrice(row.commissions || '0');
  const fees = parsePrice(row.fees || '0');

  // Position effect
  const posEffect = row.posEffect?.toUpperCase();
  const isOpen = !posEffect || posEffect.includes('OPEN');

  // Create leg
  const leg: ImportedLeg = {
    symbol: parsedOption.symbol,
    expiration: parsedOption.expiration,
    strike: parsedOption.strike!,
    type: parsedOption.type!,
    quantity,
    price,
  };

  // Create trade
  const trade: ImportedTrade = {
    id: `tos-${tradeDate}-${index}`,
    platform: 'tos',
    tradeDate,
    tradeTime,
    symbol: parsedOption.symbol,
    legs: [leg],
    totalPrice: price * Math.abs(quantity) * 100,  // Options multiplier
    commission,
    fees,
    positionEffect: isOpen ? 'open' : 'close',
    rawData: row as Record<string, string>,
  };

  return trade;
}

/**
 * Parse time string to seconds since midnight for comparison
 */
function timeToSeconds(timeStr: string | undefined): number {
  if (!timeStr) return 0;
  const match = timeStr.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/);
  if (!match) return 0;
  const hours = parseInt(match[1]);
  const minutes = parseInt(match[2]);
  const seconds = parseInt(match[3] || '0');
  return hours * 3600 + minutes * 60 + seconds;
}

/**
 * Group trades by spread/time to combine multi-leg trades
 * Uses smarter grouping: same symbol, same expiration, same effect, within time window
 */
function groupMultiLegTrades(trades: ImportedTrade[]): ImportedTrade[] {
  // First pass: group by date + symbol + expiration + effect
  const groups = new Map<string, ImportedTrade[]>();

  for (const trade of trades) {
    // Get expiration from first leg
    const expiration = trade.legs[0]?.expiration || '';

    // Create grouping key (without exact time)
    const key = `${trade.tradeDate}-${trade.symbol}-${expiration}-${trade.positionEffect}`;

    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(trade);
  }

  // Second pass: within each group, cluster by time proximity (within 10 seconds)
  const result: ImportedTrade[] = [];
  const TIME_WINDOW_SECONDS = 10;

  for (const [, groupTrades] of groups) {
    // Sort by time
    const sorted = [...groupTrades].sort((a, b) => {
      return timeToSeconds(a.tradeTime) - timeToSeconds(b.tradeTime);
    });

    // Cluster by time proximity
    const clusters: ImportedTrade[][] = [];
    let currentCluster: ImportedTrade[] = [];

    for (const trade of sorted) {
      if (currentCluster.length === 0) {
        currentCluster.push(trade);
      } else {
        const lastTime = timeToSeconds(currentCluster[currentCluster.length - 1].tradeTime);
        const thisTime = timeToSeconds(trade.tradeTime);

        if (Math.abs(thisTime - lastTime) <= TIME_WINDOW_SECONDS) {
          currentCluster.push(trade);
        } else {
          clusters.push(currentCluster);
          currentCluster = [trade];
        }
      }
    }
    if (currentCluster.length > 0) {
      clusters.push(currentCluster);
    }

    // Merge each cluster
    for (const cluster of clusters) {
      if (cluster.length === 1) {
        result.push(cluster[0]);
      } else {
        // Check if this looks like a multi-leg structure (butterfly, vertical, etc.)
        const allLegs = cluster.flatMap(t => t.legs);
        const strikes = [...new Set(allLegs.map(l => l.strike))].sort((a, b) => a - b);

        // If we have 2-4 different strikes, likely a spread
        if (strikes.length >= 2 && strikes.length <= 4) {
          const first = cluster[0];
          const combined: ImportedTrade = {
            ...first,
            id: `tos-${first.tradeDate}-combined-${strikes.join('-')}`,
            legs: allLegs,
            totalPrice: cluster.reduce((sum, t) => sum + t.totalPrice, 0),
            commission: cluster.reduce((sum, t) => sum + t.commission, 0),
            fees: cluster.reduce((sum, t) => sum + t.fees, 0),
          };
          result.push(combined);
        } else {
          // Can't determine structure, keep separate
          result.push(...cluster);
        }
      }
    }
  }

  return result;
}

/**
 * Main parser function
 */
export function parseTosAccountStatement(content: string): ImportResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const trades: ImportedTrade[] = [];

  // Split into lines
  const lines = content.split(/\r?\n/);

  // Extract trade section
  const section = extractTradeSection(lines);

  if (!section) {
    return {
      success: false,
      trades: [],
      errors: ['Could not find trade history section in file. Make sure you exported from Account Statement > Transactions.'],
      warnings: [],
      stats: { totalRows: lines.length, parsedTrades: 0, skippedRows: lines.length },
    };
  }

  const { headers, rows } = section;
  let skippedRows = 0;

  // Parse each row
  for (let i = 0; i < rows.length; i++) {
    const rowObj = rowToObject(headers, rows[i]);

    try {
      const trade = parseTradeRow(rowObj, i);
      if (trade) {
        trades.push(trade);
      } else {
        skippedRows++;
        // Only warn for rows that look like they should be trades
        if (rowObj.symbol || rowObj.description) {
          warnings.push(`Row ${i + 1}: Could not parse trade - ${rowObj.symbol || rowObj.description}`);
        }
      }
    } catch (err) {
      skippedRows++;
      errors.push(`Row ${i + 1}: Parse error - ${err}`);
    }
  }

  // Group multi-leg trades
  const groupedTrades = groupMultiLegTrades(trades);

  return {
    success: groupedTrades.length > 0,
    trades: groupedTrades,
    errors,
    warnings: warnings.slice(0, 10),  // Limit warnings
    stats: {
      totalRows: rows.length,
      parsedTrades: groupedTrades.length,
      skippedRows,
    },
  };
}
