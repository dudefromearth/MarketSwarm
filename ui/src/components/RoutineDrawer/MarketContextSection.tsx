/**
 * MarketContextSection - Read-only display of current market environment
 *
 * "Load the trading environment"
 */

interface SpotData {
  [symbol: string]: {
    value: number;
    ts: string;
    symbol: string;
    prevClose?: number;
    change?: number;
    changePercent?: number;
  };
}

interface MarketModeData {
  score: number;
  mode: 'compression' | 'transition' | 'expansion';
  ts?: string;
}

interface BiasLfiData {
  directional_strength: number;
  lfi_score: number;
  ts?: string;
}

interface VexyMessage {
  kind: 'epoch' | 'event';
  text: string;
  meta: Record<string, unknown>;
  ts: string;
  voice: string;
}

interface VexyData {
  epoch: VexyMessage | null;
  event: VexyMessage | null;
}

interface MarketContextSectionProps {
  spot: SpotData;
  marketMode: MarketModeData | null;
  biasLfi: BiasLfiData | null;
  vexy: VexyData | null;
}

export default function MarketContextSection({
  spot,
  marketMode,
  biasLfi,
}: MarketContextSectionProps) {
  const vix = spot['I:VIX']?.value;
  const spx = spot['I:SPX']?.value;
  const spxChange = spot['I:SPX']?.changePercent;

  const getModeClass = (mode: string | undefined) => {
    switch (mode) {
      case 'expansion':
        return 'expansion';
      case 'compression':
        return 'compression';
      case 'transition':
        return 'transition';
      default:
        return '';
    }
  };

  const getBiasLabel = (strength: number | undefined) => {
    if (strength === undefined) return { label: '-', class: 'neutral' };
    if (strength > 0.3) return { label: 'Bullish', class: 'bullish' };
    if (strength < -0.3) return { label: 'Bearish', class: 'bearish' };
    return { label: 'Neutral', class: 'neutral' };
  };

  const biasInfo = getBiasLabel(biasLfi?.directional_strength);

  return (
    <div className="routine-context-grid">
      <div className="routine-context-item">
        <div className="routine-context-label">VIX</div>
        <div className="routine-context-value">
          {vix !== undefined ? vix.toFixed(2) : '-'}
        </div>
      </div>

      <div className="routine-context-item">
        <div className="routine-context-label">SPX</div>
        <div className="routine-context-value">
          {spx !== undefined ? spx.toFixed(0) : '-'}
          {spxChange !== undefined && (
            <span style={{ fontSize: '10px', marginLeft: '4px', color: spxChange >= 0 ? '#22c55e' : '#ef4444' }}>
              {spxChange >= 0 ? '+' : ''}{spxChange.toFixed(2)}%
            </span>
          )}
        </div>
      </div>

      <div className="routine-context-item">
        <div className="routine-context-label">Market Mode</div>
        <div className={`routine-context-value ${getModeClass(marketMode?.mode)}`}>
          {marketMode?.mode ? marketMode.mode.charAt(0).toUpperCase() + marketMode.mode.slice(1) : '-'}
        </div>
      </div>

      <div className="routine-context-item">
        <div className="routine-context-label">Bias</div>
        <div className={`routine-context-value ${biasInfo.class}`}>
          {biasInfo.label}
          {biasLfi?.directional_strength !== undefined && (
            <span style={{ fontSize: '9px', marginLeft: '4px', opacity: 0.7 }}>
              ({(biasLfi.directional_strength * 100).toFixed(0)}%)
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
