// src/components/VixRegimeCard.tsx
// VIX Regime widget showing volatility regime and strategy recommendations

type Props = {
  vix: number | null;
  ts?: string;
};

export default function VixRegimeCard({ vix, ts }: Props) {
  const vixValue = typeof vix === "number" ? vix : 14.67;

  const lowerCut = 17;
  const upperCut = 32;
  const hardMax = 40;

  let regime: "ZombieLand" | "Goldilocks" | "Chaos" = "ZombieLand";
  let nextBoundaryLabel = `${(lowerCut - vixValue).toFixed(2)} pts to ${lowerCut}`;
  if (vixValue >= lowerCut && vixValue < upperCut) {
    regime = "Goldilocks";
    const distToLower = vixValue - lowerCut;
    const distToUpper = upperCut - vixValue;
    nextBoundaryLabel =
      distToLower < distToUpper
        ? `${distToLower.toFixed(2)} pts above ${lowerCut}`
        : `${distToUpper.toFixed(2)} pts below ${upperCut}`;
  } else if (vixValue >= upperCut) {
    regime = "Chaos";
    nextBoundaryLabel = `${(vixValue - upperCut).toFixed(2)} pts above ${upperCut}`;
  }

  const clampedVix = Math.min(Math.max(vixValue, 0), hardMax);
  let markerTopPct = 0;

  if (clampedVix < lowerCut) {
    const local = clampedVix / lowerCut;
    const zoneStart = 100 - 33.333;
    const zoneSpan = 33.333;
    markerTopPct = zoneStart + (1 - local) * zoneSpan;
  } else if (clampedVix < upperCut) {
    const local = (clampedVix - lowerCut) / (upperCut - lowerCut);
    const zoneStart = 100 - 66.666;
    const zoneSpan = 33.333;
    markerTopPct = zoneStart + (1 - local) * zoneSpan;
  } else {
    const local = (clampedVix - upperCut) / (hardMax - upperCut || 1);
    const zoneStart = 0;
    const zoneSpan = 33.333;
    markerTopPct = zoneStart + (1 - Math.min(local, 1)) * zoneSpan;
  }

  const chaosActive = regime === "Chaos";
  const goldActive = regime === "Goldilocks";
  const zombieActive = regime === "ZombieLand";

  const guideRows = [
    {
      id: "Chaos" as const,
      title: "Chaos zone",
      range: "VIX \u2265 32",
      widthGuide: "50+ wide flies / hedges",
      dteGuide: "Focus: 0-1 DTE, defensive structures",
      colorClass: "vix-color-chaos",
    },
    {
      id: "Goldilocks" as const,
      title: "Goldilocks",
      range: "VIX ~17-32",
      widthGuide: "30-50 wide, classic OTM flies",
      dteGuide: "Focus: 0-1 DTE (OTM / Batman), 0-2 DTE runners",
      colorClass: "vix-color-goldilocks",
    },
    {
      id: "ZombieLand" as const,
      title: "ZombieLand",
      range: "VIX ~12-17",
      widthGuide: "30-20 wide, narrower flies",
      dteGuide: "Focus: 0-1 DTE, 0-3 DTE, smaller sizes",
      colorClass: "vix-color-zombie",
    },
  ];

  return (
    <div className="vix-regime-card">
      <div className="vix-regime-header">
        <div className="vix-regime-title">VIX Playbook</div>
        <div className="vix-regime-value">VIX: {vixValue.toFixed(2)}</div>
        <div className="vix-regime-meta">
          Regime:{" "}
          <span className={`vix-regime-label ${regime.toLowerCase()}`}>
            {regime}
          </span>
          <br />
          <span className="vix-regime-boundary">{nextBoundaryLabel}</span>
          {ts && <div className="vix-regime-ts">as of {ts}</div>}
        </div>
      </div>

      <div className="vix-regime-content">
        {/* Thermometer strip */}
        <div className="vix-thermometer">
          <div className={`vix-zone chaos ${chaosActive ? "active" : ""}`}>
            <span className="vix-zone-label">Chaos</span>
            <div className="vix-zone-boundary">
              <span className="vix-boundary-value">{upperCut}</span>
            </div>
          </div>

          <div className={`vix-zone goldilocks ${goldActive ? "active" : ""}`}>
            <span className="vix-zone-label">Goldilocks</span>
            <div className="vix-zone-boundary">
              <span className="vix-boundary-value">{lowerCut}</span>
            </div>
          </div>

          <div className={`vix-zone zombie ${zombieActive ? "active" : ""}`}>
            <span className="vix-zone-label">ZombieLand</span>
          </div>

          {/* Current VIX marker */}
          <div className="vix-marker" style={{ top: `${markerTopPct}%` }}>
            <div className="vix-marker-line" />
            <span className="vix-marker-value">{vixValue.toFixed(1)}</span>
          </div>
        </div>

        {/* Strategy guide */}
        <div className="vix-guide">
          {guideRows.map((row) => {
            const active = row.id === regime;
            return (
              <div
                key={row.id}
                className={`vix-guide-row ${active ? "active" : ""}`}
              >
                <div className={`vix-guide-title ${row.colorClass}`}>
                  {row.title}{" "}
                  <span className="vix-guide-range">({row.range})</span>
                </div>
                <div className="vix-guide-detail">
                  <span className="vix-guide-label">Fly width: </span>
                  <span className={row.colorClass}>{row.widthGuide}</span>
                </div>
                <div className="vix-guide-detail vix-guide-dte">
                  {row.dteGuide}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
