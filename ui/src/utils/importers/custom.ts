/**
 * Custom CSV Format Parser
 *
 * A simple, user-fillable format for importing trades from any broker.
 *
 * Expected columns:
 * date,time,symbol,expiration,strike,type,quantity,price,commission,fees,effect
 *
 * Example:
 * date,time,symbol,expiration,strike,type,quantity,price,commission,fees,effect
 * 2025-02-07,10:30:00,SPX,2025-02-07,6000,call,1,2.50,0.65,0.14,open
 * 2025-02-07,10:30:00,SPX,2025-02-07,6010,call,-2,1.75,0.65,0.14,open
 * 2025-02-07,10:30:00,SPX,2025-02-07,6020,call,1,1.00,0.65,0.14,open
 *
 * Notes:
 * - Legs with the same date+time are grouped into a single trade
 * - quantity: positive = long, negative = short
 * - type: "call" or "put"
 * - effect: "open" or "close"
 * - price: per-contract price in dollars
 */

import type { ImportedTrade, ImportedLeg, ImportResult } from './index';

interface CustomRow {
  date: string;
  time: string;
  symbol: string;
  expiration: string;
  strike: string;
  type: string;
  quantity: string;
  price: string;
  commission: string;
  fees: string;
  effect: string;
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
 * Normalize header names
 */
function normalizeHeader(header: string): keyof CustomRow | null {
  const h = header.toLowerCase().trim();

  const mappings: Record<string, keyof CustomRow> = {
    'date': 'date',
    'trade_date': 'date',
    'trade date': 'date',
    'time': 'time',
    'trade_time': 'time',
    'trade time': 'time',
    'symbol': 'symbol',
    'underlying': 'symbol',
    'expiration': 'expiration',
    'exp': 'expiration',
    'exp_date': 'expiration',
    'expiry': 'expiration',
    'strike': 'strike',
    'strike_price': 'strike',
    'type': 'type',
    'option_type': 'type',
    'call_put': 'type',
    'call/put': 'type',
    'quantity': 'quantity',
    'qty': 'quantity',
    'contracts': 'quantity',
    'price': 'price',
    'fill_price': 'price',
    'premium': 'price',
    'commission': 'commission',
    'comm': 'commission',
    'fees': 'fees',
    'fee': 'fees',
    'effect': 'effect',
    'position_effect': 'effect',
    'open_close': 'effect',
  };

  return mappings[h] || null;
}

/**
 * Parse custom CSV format
 */
export function parseCustomCsv(content: string): ImportResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const trades: ImportedTrade[] = [];

  const lines = content.split(/\r?\n/).filter(line => line.trim());

  if (lines.length < 2) {
    return {
      success: false,
      trades: [],
      errors: ['File must contain a header row and at least one data row'],
      warnings: [],
      stats: { totalRows: 0, parsedTrades: 0, skippedRows: 0 },
    };
  }

  // Parse header
  const headerLine = lines[0];
  const headers = parseCSVLine(headerLine);
  const columnMap: Map<number, keyof CustomRow> = new Map();

  headers.forEach((h, i) => {
    const normalized = normalizeHeader(h);
    if (normalized) {
      columnMap.set(i, normalized);
    }
  });

  // Check required columns
  const requiredColumns: (keyof CustomRow)[] = ['date', 'symbol', 'expiration', 'strike', 'type', 'quantity', 'price'];
  const foundColumns = new Set(columnMap.values());
  const missingColumns = requiredColumns.filter(c => !foundColumns.has(c));

  if (missingColumns.length > 0) {
    return {
      success: false,
      trades: [],
      errors: [`Missing required columns: ${missingColumns.join(', ')}`],
      warnings: [],
      stats: { totalRows: lines.length - 1, parsedTrades: 0, skippedRows: lines.length - 1 },
    };
  }

  // Parse data rows and group by date+time
  const legGroups: Map<string, { row: CustomRow; lineNum: number }[]> = new Map();
  let skippedRows = 0;

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const values = parseCSVLine(line);
    const row: Partial<CustomRow> = {};

    columnMap.forEach((colName, colIndex) => {
      row[colName] = values[colIndex] || '';
    });

    // Validate required fields
    if (!row.date || !row.symbol || !row.expiration || !row.strike || !row.type || !row.quantity || !row.price) {
      warnings.push(`Row ${i + 1}: Missing required fields, skipping`);
      skippedRows++;
      continue;
    }

    // Create group key
    const groupKey = `${row.date}-${row.time || '00:00:00'}`;

    if (!legGroups.has(groupKey)) {
      legGroups.set(groupKey, []);
    }
    legGroups.get(groupKey)!.push({ row: row as CustomRow, lineNum: i + 1 });
  }

  // Convert leg groups to trades
  let tradeIndex = 0;
  for (const [groupKey, legs] of legGroups) {
    try {
      const firstLeg = legs[0].row;

      const importedLegs: ImportedLeg[] = legs.map(({ row }) => ({
        symbol: row.symbol.toUpperCase(),
        expiration: row.expiration,
        strike: parseFloat(row.strike),
        type: row.type.toLowerCase().includes('put') ? 'put' : 'call',
        quantity: parseInt(row.quantity),
        price: parseFloat(row.price),
      }));

      // Calculate totals
      let totalPrice = 0;
      let totalCommission = 0;
      let totalFees = 0;

      for (const { row } of legs) {
        const qty = parseInt(row.quantity);
        const price = parseFloat(row.price);
        totalPrice += price * qty * 100; // Convert to cents
        totalCommission += parseFloat(row.commission || '0');
        totalFees += parseFloat(row.fees || '0');
      }

      const trade: ImportedTrade = {
        id: `custom-${firstLeg.date}-${tradeIndex}`,
        platform: 'custom',
        tradeDate: firstLeg.date,
        tradeTime: firstLeg.time || undefined,
        symbol: firstLeg.symbol.toUpperCase(),
        legs: importedLegs,
        totalPrice,
        commission: totalCommission,
        fees: totalFees,
        positionEffect: (firstLeg.effect?.toLowerCase() || 'open').includes('close') ? 'close' : 'open',
      };

      trades.push(trade);
      tradeIndex++;
    } catch (err) {
      const lineNums = legs.map(l => l.lineNum).join(', ');
      errors.push(`Rows ${lineNums}: Failed to parse trade - ${err}`);
      skippedRows += legs.length;
    }
  }

  return {
    success: trades.length > 0,
    trades,
    errors,
    warnings: warnings.slice(0, 10),
    stats: {
      totalRows: lines.length - 1,
      parsedTrades: trades.length,
      skippedRows,
    },
  };
}

/**
 * Generate a CSV template for users to fill out
 */
export function generateCustomTemplate(): string {
  const header = 'date,time,symbol,expiration,strike,type,quantity,price,commission,fees,effect';
  const example1 = '2025-02-07,10:30:00,SPX,2025-02-07,6000,call,1,2.50,0.65,0.14,open';
  const example2 = '2025-02-07,10:30:00,SPX,2025-02-07,6010,call,-2,1.75,0.65,0.14,open';
  const example3 = '2025-02-07,10:30:00,SPX,2025-02-07,6020,call,1,1.00,0.65,0.14,open';
  const comment = '# Delete example rows above and add your trades. Legs with same date+time are grouped together.';

  return `${header}\n${example1}\n${example2}\n${example3}\n${comment}`;
}
