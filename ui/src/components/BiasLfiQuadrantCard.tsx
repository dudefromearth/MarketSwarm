// src/components/BiasLfiQuadrantCard.tsx
// Liquidity-Intent Map (LIM) quadrant visualization

type Props = {
  directional_strength: number;
  lfi_score: number;
};

export default function BiasLfiQuadrantCard({
  directional_strength,
  lfi_score,
}: Props) {
  const bias = Math.max(-100, Math.min(100, directional_strength || 0));
  const lfi = Math.max(0, Math.min(100, lfi_score || 0));

  const xPct = (bias + 100) / 2;
  const yPct = lfi;

  const biasLabel =
    (bias > 0 ? "+" : bias < 0 ? "−" : "") + Math.abs(Math.round(bias));
  const lfiLabel = Math.round(lfi);

  const BUBBLE_SIZE = 56;

  const liquidityXLabel = bias >= 0 ? "Supportive" : "Hostile";
  const liquidityXValue = (bias >= 0 ? "+" : "−") + Math.abs(Math.round(bias));
  const liquidityYLabel = lfi >= 50 ? "Absorbing" : "Accelerating";

  // Determine quadrant for bubble coloring
  const quadrant =
    bias < 0 && lfi >= 50 ? "tl" :  // Pin/Mean Reversion (cyan)
    bias >= 0 && lfi >= 50 ? "tr" : // False Breakout Risk (purple)
    bias < 0 && lfi < 50 ? "bl" :   // Downside Acceleration (red)
    "br";                           // Air-Pocket Expansion (green)

  return (
    <div className="lim-widget">
      <div className="lim-header">
        <div className="lim-title">
          <span className="lim-title-text">Liquidity–Intent Map</span>
          <span className="lim-subtitle">How liquidity responds to price</span>
        </div>
        <div className="lim-values">
          <span>Bias: {biasLabel}</span>
          <span>LFI: {lfiLabel}</span>
        </div>
      </div>

      <div className="lim-quadrant-container">
        {/* Y-axis label */}
        <div className="lim-y-label">
          <span>L</span>
          <span>F</span>
          <span>I</span>
        </div>

        {/* Main quadrant area */}
        <div className="lim-quadrant">
          {/* Y-axis values */}
          <div className="lim-y-axis">
            <span className="lim-y-val top">100</span>
            <span className="lim-y-val mid">50</span>
            <span className="lim-y-val bot">0</span>
          </div>

          {/* Quadrant grid */}
          <div className="lim-grid">
            {/* Background gradient */}
            <div className="lim-grid-bg" />

            {/* Center lines */}
            <div className="lim-center-v" />
            <div className="lim-center-h" />

            {/* Quadrant labels */}
            <div className="lim-label tl">
              <div className="lim-label-title">Pin / Mean Reversion</div>
              <div className="lim-label-desc">Liquidity contains price</div>
            </div>
            <div className="lim-label tr">
              <div className="lim-label-title">False Breakout Risk</div>
              <div className="lim-label-desc">Moves need confirmation</div>
            </div>
            <div className="lim-label bl">
              <div className="lim-label-title">Downside Acceleration</div>
              <div className="lim-label-desc">Liquidity amplifies selling</div>
            </div>
            <div className="lim-label br">
              <div className="lim-label-title">Air-Pocket Expansion</div>
              <div className="lim-label-desc">Price can travel quickly</div>
            </div>

            {/* X-axis values */}
            <div className="lim-x-axis">
              <span className="lim-x-val left">−100</span>
              <span className="lim-x-val mid">0</span>
              <span className="lim-x-val right">+100</span>
            </div>

            {/* Floating bubble */}
            <div
              className={`lim-bubble ${quadrant}`}
              style={{
                left: `${xPct}%`,
                top: `${100 - yPct}%`,
                width: BUBBLE_SIZE,
                height: BUBBLE_SIZE,
              }}
            >
              <div className="lim-bubble-content">
                <div className="lim-bubble-label">{liquidityXLabel}</div>
                <div className="lim-bubble-value">{liquidityXValue}</div>
                <div className="lim-bubble-lfi">
                  {liquidityYLabel} ({lfiLabel})
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom label */}
      <div className="lim-bottom-label">
        ← Hostile to price | Supportive of price →
      </div>
    </div>
  );
}
