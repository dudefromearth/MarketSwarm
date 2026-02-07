/**
 * ThinkOrSwim Script Parser
 *
 * Parses ToS strategy notation into PositionLeg[].
 *
 * Examples:
 * BUY +1 BUTTERFLY SPX 100 17 JAN 25 5880/5900/5920 CALL @1.20
 * SELL -1 VERTICAL SPX 100 17 JAN 25 5900/5920 PUT @2.50
 * BUY +1 IRON CONDOR SPX 100 19 JAN 25 5800/5850/5950/6000 CALL/PUT @3.80
 */
/**
 * Parse month abbreviation to number (0-indexed)
 */
function parseMonth(monthStr) {
    const months = {
        'JAN': 0, 'FEB': 1, 'MAR': 2, 'APR': 3, 'MAY': 4, 'JUN': 5,
        'JUL': 6, 'AUG': 7, 'SEP': 8, 'OCT': 9, 'NOV': 10, 'DEC': 11,
    };
    return months[monthStr.toUpperCase()] ?? 0;
}
/**
 * Parse ToS expiration format: "17 JAN 25" or "17 JAN 2025"
 */
function parseTosExpiration(dateStr) {
    const match = dateStr.match(/(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2,4})/i);
    if (!match)
        return '';
    const dayStr = match[1];
    const monthStr = match[2];
    const yearStr = match[3];
    if (!dayStr || !monthStr || !yearStr)
        return '';
    const day = parseInt(dayStr);
    const month = parseMonth(monthStr);
    let year = parseInt(yearStr);
    if (year < 100) {
        year += 2000;
    }
    const date = new Date(year, month, day);
    return date.toISOString().split('T')[0] ?? '';
}
/**
 * Parse ToS components into a ParsedPosition
 */
function parseTosComponents(match, price, rawScript, warnings) {
    const action = match[1];
    const quantity = match[2];
    const strategyType = match[3];
    const symbol = match[4];
    const expirationStr = match[6];
    const strikesStr = match[7];
    const rightStr = match[8];
    if (!action || !quantity || !strategyType || !symbol || !expirationStr || !strikesStr || !rightStr) {
        return null;
    }
    const isBuy = action.toUpperCase() === 'BUY';
    const qty = Math.abs(parseInt(quantity));
    const expiration = parseTosExpiration(expirationStr);
    if (!expiration) {
        warnings.push('Could not parse expiration date');
        return null;
    }
    const strikes = strikesStr.split('/').map(s => parseFloat(s.trim()));
    const rightUpper = rightStr.toUpperCase();
    const primaryRight = rightUpper.startsWith('CALL') ? 'call' : 'put';
    const costBasisType = isBuy ? 'debit' : 'credit';
    const stratType = strategyType.toUpperCase().replace(/\s+/g, ' ').trim();
    const legs = [];
    switch (stratType) {
        case 'SINGLE':
            if (strikes.length >= 1 && strikes[0] !== undefined) {
                legs.push({
                    strike: strikes[0],
                    expiration,
                    right: primaryRight,
                    quantity: isBuy ? qty : -qty,
                });
            }
            break;
        case 'VERTICAL':
            if (strikes.length >= 2 && strikes[0] !== undefined && strikes[1] !== undefined) {
                if (primaryRight === 'call') {
                    legs.push({ strike: strikes[0], expiration, right: 'call', quantity: isBuy ? qty : -qty });
                    legs.push({ strike: strikes[1], expiration, right: 'call', quantity: isBuy ? -qty : qty });
                }
                else {
                    legs.push({ strike: strikes[0], expiration, right: 'put', quantity: isBuy ? -qty : qty });
                    legs.push({ strike: strikes[1], expiration, right: 'put', quantity: isBuy ? qty : -qty });
                }
            }
            break;
        case 'BUTTERFLY':
            if (strikes.length >= 3 && strikes[0] !== undefined && strikes[1] !== undefined && strikes[2] !== undefined) {
                legs.push({ strike: strikes[0], expiration, right: primaryRight, quantity: isBuy ? qty : -qty });
                legs.push({ strike: strikes[1], expiration, right: primaryRight, quantity: isBuy ? -2 * qty : 2 * qty });
                legs.push({ strike: strikes[2], expiration, right: primaryRight, quantity: isBuy ? qty : -qty });
            }
            break;
        case 'CONDOR':
            if (strikes.length >= 4 && strikes[0] !== undefined && strikes[1] !== undefined && strikes[2] !== undefined && strikes[3] !== undefined) {
                legs.push({ strike: strikes[0], expiration, right: primaryRight, quantity: isBuy ? qty : -qty });
                legs.push({ strike: strikes[1], expiration, right: primaryRight, quantity: isBuy ? -qty : qty });
                legs.push({ strike: strikes[2], expiration, right: primaryRight, quantity: isBuy ? -qty : qty });
                legs.push({ strike: strikes[3], expiration, right: primaryRight, quantity: isBuy ? qty : -qty });
            }
            break;
        case 'IRON CONDOR':
            if (strikes.length >= 4 && strikes[0] !== undefined && strikes[1] !== undefined && strikes[2] !== undefined && strikes[3] !== undefined) {
                legs.push({ strike: strikes[0], expiration, right: 'put', quantity: isBuy ? qty : -qty });
                legs.push({ strike: strikes[1], expiration, right: 'put', quantity: isBuy ? -qty : qty });
                legs.push({ strike: strikes[2], expiration, right: 'call', quantity: isBuy ? -qty : qty });
                legs.push({ strike: strikes[3], expiration, right: 'call', quantity: isBuy ? qty : -qty });
            }
            break;
        case 'STRADDLE':
            if (strikes.length >= 1 && strikes[0] !== undefined) {
                legs.push({ strike: strikes[0], expiration, right: 'call', quantity: isBuy ? qty : -qty });
                legs.push({ strike: strikes[0], expiration, right: 'put', quantity: isBuy ? qty : -qty });
            }
            break;
        case 'STRANGLE':
            if (strikes.length >= 2 && strikes[0] !== undefined && strikes[1] !== undefined) {
                legs.push({ strike: strikes[0], expiration, right: 'put', quantity: isBuy ? qty : -qty });
                legs.push({ strike: strikes[1], expiration, right: 'call', quantity: isBuy ? qty : -qty });
            }
            break;
        case 'CALENDAR':
        case 'DIAGONAL':
            warnings.push(`${stratType} requires multiple expirations - manual adjustment may be needed`);
            if (strikes.length >= 1 && strikes[0] !== undefined) {
                legs.push({ strike: strikes[0], expiration, right: primaryRight, quantity: isBuy ? qty : -qty });
            }
            break;
        default:
            warnings.push(`Unknown strategy type: ${stratType}`);
            for (let i = 0; i < strikes.length; i++) {
                const strike = strikes[i];
                if (strike !== undefined) {
                    legs.push({
                        strike,
                        expiration,
                        right: primaryRight,
                        quantity: i === 0 ? (isBuy ? qty : -qty) : (isBuy ? -qty : qty),
                    });
                }
            }
    }
    if (legs.length === 0) {
        return null;
    }
    return {
        symbol,
        legs,
        costBasis: price ?? undefined,
        costBasisType,
        rawScript,
        format: 'tos',
        warnings: warnings.length > 0 ? warnings : undefined,
    };
}
/**
 * Parse ThinkOrSwim strategy script
 */
export function parseTosScript(script) {
    const trimmed = script.trim();
    const warnings = [];
    // Main pattern with price
    const mainPattern = /^(BUY|SELL)\s+([+-]?\d+)\s+(.+?)\s+([A-Z]+)\s+(\d+)\s*(?:\([^)]+\))?\s*(\d{1,2}\s+[A-Z]{3}\s+\d{2,4})\s+([\d/]+)\s+(CALL|PUT|CALL\/PUT|PUT\/CALL)\s*@\s*([\d.]+)$/i;
    const match = trimmed.match(mainPattern);
    if (!match) {
        // Try simpler pattern without price
        const simplePattern = /^(BUY|SELL)\s+([+-]?\d+)\s+(.+?)\s+([A-Z]+)\s+(\d+)\s*(?:\([^)]+\))?\s*(\d{1,2}\s+[A-Z]{3}\s+\d{2,4})\s+([\d/]+)\s+(CALL|PUT|CALL\/PUT|PUT\/CALL)/i;
        const simpleMatch = trimmed.match(simplePattern);
        if (!simpleMatch) {
            return null;
        }
        return parseTosComponents(simpleMatch, null, trimmed, warnings);
    }
    const priceStr = match[9];
    const price = priceStr ? parseFloat(priceStr) : null;
    return parseTosComponents(match, price, trimmed, warnings);
}
/**
 * Get example ToS scripts for testing/demo
 */
export function getTosExamples() {
    return [
        'BUY +1 BUTTERFLY SPX 100 17 JAN 25 5880/5900/5920 CALL @1.20',
        'SELL -1 VERTICAL SPX 100 17 JAN 25 5900/5920 PUT @2.50',
        'BUY +1 IRON CONDOR SPX 100 19 JAN 25 5800/5850/5950/6000 CALL/PUT @3.80',
        'BUY +1 STRADDLE SPX 100 17 JAN 25 5900 CALL/PUT @10.00',
    ];
}
//# sourceMappingURL=tos.js.map