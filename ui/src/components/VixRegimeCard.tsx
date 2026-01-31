// src/components/VixRegimeCard.tsx
// VIX Regime widget showing volatility regime and strategy recommendations

type Props = {
  vix: number | null;
  ts?: string;
};

export default function VixRegimeCard({ vix, ts }: Props) {
  const vixValue = typeof vix === "number" ? vix : 14.67;

  // Time-based detection for special conditions
  const currentHour = new Date().getHours();
  const isAfternoon = currentHour >= 14;

  const lowerCut = 17;
  const upperCut = 32;
  const batmanCut = 40;
  const hardMax = 50;

  // Determine regime and special conditions
  let regime: "ZombieLand" | "Goldilocks" | "Chaos" = "ZombieLand";
  let specialCondition: string | null = null;
  let specialIcon: string = "";

  if (vixValue >= upperCut) {
    regime = "Chaos";
    if (vixValue >= batmanCut) {
      specialCondition = "BATMAN";
      specialIcon = "🦇";
    }
  } else if (vixValue >= lowerCut) {
    regime = "Goldilocks";
  } else {
    regime = "ZombieLand";
    if (vixValue <= 15 && !isAfternoon) {
      specialCondition = "TIMEWARP";
      specialIcon = "⏰";
    } else if (isAfternoon) {
      specialCondition = "GAMMA SCALP";
      specialIcon = "⚡";
    }
  }

  // Distance to boundary
  let nextBoundaryLabel = "";
  if (vixValue < lowerCut) {
    nextBoundaryLabel = `${(lowerCut - vixValue).toFixed(1)} to Goldilocks`;
  } else if (vixValue < upperCut) {
    const distToLower = vixValue - lowerCut;
    const distToUpper = upperCut - vixValue;
    nextBoundaryLabel = distToLower < distToUpper
      ? `${distToLower.toFixed(1)} above Zombie`
      : `${distToUpper.toFixed(1)} to Chaos`;
  } else {
    nextBoundaryLabel = `${(vixValue - upperCut).toFixed(1)} into Chaos`;
  }

  const clampedVix = Math.min(Math.max(vixValue, 10), hardMax);
  let markerTopPct = 0;

  if (clampedVix < lowerCut) {
    const local = (clampedVix - 10) / (lowerCut - 10);
    markerTopPct = 100 - (local * 33.333);
  } else if (clampedVix < upperCut) {
    const local = (clampedVix - lowerCut) / (upperCut - lowerCut);
    markerTopPct = 66.666 - (local * 33.333);
  } else {
    const local = (clampedVix - upperCut) / (hardMax - upperCut);
    markerTopPct = 33.333 - (Math.min(local, 1) * 33.333);
  }

  const chaosActive = regime === "Chaos";
  const goldActive = regime === "Goldilocks";
  const zombieActive = regime === "ZombieLand";

  const guideRows = [
    {
      id: "Chaos" as const,
      title: "Chaos",
      range: "VIX ≥32",
      widthGuide: "50+w flies",
      debitGuide: "$2.50-6.50",
      dteGuide: "0 DTE",
      special: vixValue >= batmanCut ? "🦇 Batman: bracket spot" : null,
      colorClass: "vix-color-chaos",
    },
    {
      id: "Goldilocks" as const,
      title: "Goldilocks",
      range: "VIX 17-32",
      widthGuide: vixValue <= 23 ? "30-40w" : "40-50w",
      debitGuide: vixValue <= 23 ? "$1.50-4" : "$2-5",
      dteGuide: "0-1 DTE",
      special: null,
      colorClass: "vix-color-goldilocks",
    },
    {
      id: "ZombieLand" as const,
      title: "ZombieLand",
      range: "VIX ≤17",
      widthGuide: isAfternoon ? "10-20w" : "20-30w",
      debitGuide: isAfternoon ? "<$2" : "$1-3",
      dteGuide: vixValue <= 15 && !isAfternoon ? "1-2 DTE" : "0-1 DTE",
      special: specialCondition && regime === "ZombieLand" ? `${specialIcon} ${specialCondition}` : null,
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
          {specialCondition && (
            <span className="vix-special-badge">{specialIcon} {specialCondition}</span>
          )}
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
            <span className="vix-zone-label">Zombie</span>
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
                  <span className="vix-guide-label">Fly: </span>
                  <span className={row.colorClass}>{row.widthGuide}</span>
                  <span className="vix-guide-label"> • Debit: </span>
                  <span>{row.debitGuide}</span>
                </div>
                <div className="vix-guide-detail vix-guide-dte">
                  {row.dteGuide}
                  {row.special && (
                    <span className="vix-guide-special"> • {row.special}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
