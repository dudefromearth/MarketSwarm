/** Map position symbols to spot data keys */
const INDEX_MAP: Record<string, string> = {
  'SPX': 'I:SPX',
  'SPXW': 'I:SPX',
  'NDXP': 'I:NDX',
  'NDX': 'I:NDX',
  'VIX': 'I:VIX',
  'RUT': 'I:RUT',
  'XSP': 'I:XSP',
};

export function resolveSpotKey(positionSymbol: string): string {
  return INDEX_MAP[positionSymbol] || positionSymbol;
}

export function getSpotForSymbol(
  symbol: string,
  spotData: Record<string, { value: number }>,
  fallback: number
): number {
  return spotData[resolveSpotKey(symbol)]?.value || fallback;
}
