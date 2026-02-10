// src/components/MarketModeGaugeCard.tsx
// Market Mode Score gauge with animated needle

import { useEffect, useRef, useState } from "react";
import { useUserPreferences } from "../contexts/UserPreferencesContext";

type Props = {
  score: number;
};

export default function MarketModeGaugeCard({ score }: Props) {
  function normalizeScore(raw: number) {
    if (!Number.isFinite(raw)) return 50;
    if (raw >= 0 && raw <= 1) return raw * 100;
    return raw; // assume 0–100
  }

  const { resolvedTheme } = useUserPreferences();
  const isLight = resolvedTheme === 'light';

  const normalized = normalizeScore(score);
  const target = Math.max(0, Math.min(100, normalized));

  const [display, setDisplay] = useState<number>(target);
  const rafRef = useRef<number | null>(null);
  const fromRef = useRef<number>(target);
  const startRef = useRef<number>(0);

  useEffect(() => {
    const from = fromRef.current;
    const to = target;

    if (rafRef.current) cancelAnimationFrame(rafRef.current);

    const duration = 520;
    startRef.current = performance.now();
    const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

    const tick = (now: number) => {
      const t = Math.min(1, (now - startRef.current) / duration);
      const v = from + (to - from) * easeOutCubic(t);
      setDisplay(v);

      if (t < 1) rafRef.current = requestAnimationFrame(tick);
      else fromRef.current = to;
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [target]);

  const mode =
    target >= 67 ? "Expansion" : target >= 34 ? "Transition" : "Compression";

  const modeClass =
    mode === "Expansion"
      ? "mm-mode-expansion"
      : mode === "Transition"
      ? "mm-mode-transition"
      : "mm-mode-compression";

  const cx = 130;
  const cy = 140;
  const rArc = 90;

  const clampedProg = Math.max(0, Math.min(100, display));
  const angleDeg = 180 - (clampedProg / 100) * 180;
  const ang = (angleDeg * Math.PI) / 180;

  const needleLen = 74;
  const nx = cx + needleLen * Math.cos(ang);
  const ny = cy - needleLen * Math.sin(ang);

  const capR = 10;

  return (
    <div className="mm-gauge-widget">
      <div className="mm-gauge-header">
        <div className="mm-gauge-title">
          <span className="mm-gauge-title-text">Market Mode Score</span>
          <span className="mm-gauge-subtitle">Composite gamma / structure regime</span>
        </div>
        <div className="mm-gauge-mode">
          <span className="mm-gauge-mode-label">Mode</span>
          <span className={`mm-gauge-mode-pill ${modeClass}`}>{mode}</span>
        </div>
      </div>

      <div className="mm-gauge-content">
        <svg viewBox="0 0 260 190" className="mm-gauge-svg">
          <style>
            {`
              @keyframes mmSheen {
                0%   { stroke-dashoffset: 140; opacity: 0.0; }
                10%  { opacity: 0.28; }
                55%  { opacity: 0.18; }
                100% { stroke-dashoffset: 0; opacity: 0.0; }
              }
            `}
          </style>

          <defs>
            <linearGradient
              id="mmGradient"
              x1="40"
              y1="140"
              x2="220"
              y2="140"
              gradientUnits="userSpaceOnUse"
            >
              <stop offset="0%" stopColor="rgba(239,68,68,0.98)" />
              <stop offset="50%" stopColor="rgba(245,158,11,0.98)" />
              <stop offset="100%" stopColor="rgba(34,197,94,0.98)" />
            </linearGradient>

            <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="3.0" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <filter id="needleGlow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="2.0" result="nblur" />
              <feMerge>
                <feMergeNode in="nblur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Background arc */}
          <path
            d={`M ${cx - rArc} ${cy} A ${rArc} ${rArc} 0 0 1 ${cx + rArc} ${cy}`}
            fill="none"
            stroke={isLight ? "rgba(0,0,0,0.08)" : "rgba(255,255,255,0.10)"}
            strokeWidth="18"
            strokeLinecap="round"
          />

          {/* Faint gradient arc */}
          <path
            d={`M ${cx - rArc} ${cy} A ${rArc} ${rArc} 0 0 1 ${cx + rArc} ${cy}`}
            fill="none"
            stroke="url(#mmGradient)"
            strokeWidth="18"
            strokeLinecap="round"
            opacity="0.22"
          />

          {/* Active gradient arc */}
          <path
            d={`M ${cx - rArc} ${cy} A ${rArc} ${rArc} 0 0 1 ${cx + rArc} ${cy}`}
            pathLength={100}
            fill="none"
            stroke="url(#mmGradient)"
            strokeWidth="18"
            strokeLinecap="round"
            strokeDasharray={`${clampedProg} 100`}
            filter="url(#softGlow)"
          />

          {/* Animated sheen */}
          <path
            d={`M ${cx - rArc} ${cy} A ${rArc} ${rArc} 0 0 1 ${cx + rArc} ${cy}`}
            fill="none"
            stroke={isLight ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.75)"}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray="22 140"
            style={{ animation: "mmSheen 3.1s linear infinite" }}
          />

          {/* Tick marks */}
          {[
            { t: 180, thick: 2.6 },
            { t: 90, thick: 2.6 },
            { t: 0, thick: 2.6 },
          ].map((tick, idx) => {
            const rad = (tick.t * Math.PI) / 180;
            const rOuter = 72;
            const rInner = 58;
            const x1 = cx + rOuter * Math.cos(rad);
            const y1 = cy - rOuter * Math.sin(rad);
            const x2 = cx + rInner * Math.cos(rad);
            const y2 = cy - rInner * Math.sin(rad);
            return (
              <line
                key={idx}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={isLight ? "rgba(0,0,0,0.15)" : "rgba(255,255,255,0.22)"}
                strokeWidth={tick.thick}
                strokeLinecap="round"
              />
            );
          })}

          {/* Labels */}
          <text x={cx - rArc} y={cy + 20} textAnchor="middle" fontSize="11" fill={isLight ? "rgba(0,0,0,0.5)" : "rgba(244,244,245,0.72)"}>
            0
          </text>
          <text x={cx} y={22} textAnchor="middle" fontSize="11" fill={isLight ? "rgba(0,0,0,0.5)" : "rgba(244,244,245,0.72)"}>
            50
          </text>
          <text x={cx + rArc} y={cy + 20} textAnchor="middle" fontSize="11" fill={isLight ? "rgba(0,0,0,0.5)" : "rgba(244,244,245,0.72)"}>
            100
          </text>

          {/* Needle */}
          <g filter="url(#needleGlow)">
            <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={isLight ? "rgba(0,0,0,0.12)" : "rgba(255,255,255,0.18)"} strokeWidth="11" strokeLinecap="round" />
            <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={isLight ? "rgba(0,0,0,0.75)" : "rgba(255,255,255,0.92)"} strokeWidth="5.2" strokeLinecap="round" />
            <circle cx={cx} cy={cy} r={capR} fill={isLight ? "rgba(29,29,31,0.9)" : "rgba(244,244,245,0.95)"} />
            <circle cx={cx} cy={cy} r={16} fill={isLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.06)"} />
            <circle cx={cx} cy={cy} r={22} fill={isLight ? "rgba(0,0,0,0.03)" : "rgba(255,255,255,0.04)"} />
          </g>

          {/* Score display */}
          <text x={cx} y={186} textAnchor="middle" fontSize="28" fontWeight="800" fill={isLight ? "rgba(29,29,31,0.9)" : "rgba(244,244,245,0.95)"}>
            {Math.round(display)}
          </text>
        </svg>

        {/* Legend */}
        <div className="mm-gauge-legend">
          <div className="mm-gauge-legend-item">
            <span className="mm-gauge-dot compression" />
            <div>
              <span className="mm-gauge-legend-label">Compression</span>
              <span className="mm-gauge-legend-range">0–33</span>
            </div>
          </div>
          <div className="mm-gauge-legend-item">
            <span className="mm-gauge-dot transition" />
            <div>
              <span className="mm-gauge-legend-label">Transition</span>
              <span className="mm-gauge-legend-range">34–66</span>
            </div>
          </div>
          <div className="mm-gauge-legend-item">
            <span className="mm-gauge-dot expansion" />
            <div>
              <span className="mm-gauge-legend-label">Expansion</span>
              <span className="mm-gauge-legend-range">67–100</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
