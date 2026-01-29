// src/components/LightweightPriceChart.tsx

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  LineSeries,
  CandlestickSeries,
  AreaSeries,
} from "lightweight-charts";
import type { IChartApi, UTCTimestamp } from "lightweight-charts";

export type RawSnapshot = {
  spot?: number | null;
  ts?: string;
  _index?: {
    spot?: number;
    ts?: string;
    candles_5m?: CandleData[];
    candles_15m?: CandleData[];
    candles_1h?: CandleData[];
  };
};

type CandleData = {
  t: number;  // Unix timestamp
  o: number;  // Open
  h: number;  // High
  l: number;  // Low
  c: number;  // Close
};

type Props = {
  snap: RawSnapshot | null;
  height?: number;
  title?: string;
};

type SeriesKind = "candles" | "area" | "line" | "none";
type Tf = "5m" | "15m" | "1h";

const TF_OPTIONS: Tf[] = ["5m", "15m", "1h"];

/* ========= Helpers (time) ========= */

function formatEstAxisLabelSnapped(epochSec: number): string {
  const dUtc = new Date(epochSec * 1000);
  const estString = dUtc.toLocaleString("en-US", {
    timeZone: "America/New_York",
  });
  const dEst = new Date(estString);

  let hour = dEst.getHours();
  const minute = dEst.getMinutes();

  let snappedMinute = 0;
  if (minute >= 15 && minute < 45) {
    snappedMinute = 30;
  } else if (minute >= 45) {
    snappedMinute = 0;
    hour = (hour + 1) % 24;
  } else {
    snappedMinute = 0;
  }

  const hh = hour.toString().padStart(2, "0");
  const mm = snappedMinute === 0 ? "00" : "30";
  return `${hh}:${mm}`;
}

function formatCrosshairEstLabel(time: unknown): string {
  let dUtc: Date;

  if (typeof time === "number") {
    dUtc = new Date(time * 1000);
  } else if (time && typeof time === "object" && "year" in time) {
    const t = time as { year: number; month: number; day: number };
    dUtc = new Date(Date.UTC(t.year, t.month - 1, t.day));
  } else {
    return "";
  }

  const estString = dUtc.toLocaleString("en-US", {
    timeZone: "America/New_York",
  });
  const dEst = new Date(estString);

  return dEst.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    year: "2-digit",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ========= Initial viewport helper ========= */

// Convert UTC epoch seconds to ET date parts
function toETDate(epochSec: number): { year: number; month: number; day: number; hour: number; minute: number } {
  const d = new Date(epochSec * 1000);
  const etString = d.toLocaleString("en-US", { timeZone: "America/New_York" });
  const etDate = new Date(etString);
  return {
    year: etDate.getFullYear(),
    month: etDate.getMonth(),
    day: etDate.getDate(),
    hour: etDate.getHours(),
    minute: etDate.getMinutes(),
  };
}

// Filter candles to only include today's session (9:30 AM - 4:00 PM ET)
function filterTodaySession(candles: CandleData[]): CandleData[] {
  const nowSec = Math.floor(Date.now() / 1000);
  const today = toETDate(nowSec);

  return candles.filter(c => {
    const et = toETDate(c.t);
    // Same day
    if (et.year !== today.year || et.month !== today.month || et.day !== today.day) {
      return false;
    }
    // Within session hours (9:30 AM to 4:00 PM)
    const minuteOfDay = et.hour * 60 + et.minute;
    return minuteOfDay >= 9 * 60 + 30 && minuteOfDay <= 16 * 60;
  });
}

function setTodaySessionView(chart: IChartApi, candles: CandleData[]) {
  if (candles.length === 0) {
    chart.timeScale().fitContent();
    return;
  }

  const firstTime = candles[0].t;
  const lastTime = candles[candles.length - 1].t;

  // Add some padding (5 min before start, extend to current time or end)
  const from = (firstTime - 300) as UTCTimestamp;
  const to = (lastTime + 300) as UTCTimestamp;

  chart.timeScale().setVisibleRange({ from, to });
}

/* ========= Dealer Gravity (frontend-computed) ========= */

type GravityState = {
  time: number;
  best: number;
  high: number;
  low: number;
  confidence: number; // 0..1
};

function clamp01(x: number) {
  return Math.max(0, Math.min(1, x));
}

function mean(vals: number[]): number {
  return vals.reduce((a, b) => a + b, 0) / (vals.length || 1);
}

function stdev(vals: number[]): number {
  if (vals.length < 2) return 0;
  const m = mean(vals);
  const v =
    vals.reduce((acc, x) => acc + (x - m) * (x - m), 0) / (vals.length - 1);
  return Math.sqrt(v);
}

function windowForTf(tf: Tf): number {
  switch (tf) {
    case "5m":
      return 30;
    case "15m":
      return 24;
    case "1h":
      return 20;
    default:
      return 30;
  }
}

function confidenceToFillOpacity(conf: number): number {
  const c = clamp01(conf);
  return 0.06 + c * 0.18;
}

function computeGravityFromCandles(candles: CandleData[], tf: Tf): GravityState[] {
  const n = windowForTf(tf);
  if (!candles || candles.length === 0) return [];

  const closes: number[] = [];
  const out: GravityState[] = [];

  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const t = c?.t;
    const close = c?.c;

    if (typeof t !== "number" || typeof close !== "number") continue;

    closes.push(close);
    if (closes.length > n) closes.shift();

    if (closes.length < Math.max(8, Math.floor(n * 0.5))) continue;

    const m = mean(closes);
    const sd = stdev(closes);

    const rel = m !== 0 ? sd / Math.abs(m) : 0;
    const conf = clamp01(1 - rel / 0.02);

    out.push({
      time: t,
      best: m,
      high: m + sd,
      low: m - sd,
      confidence: conf,
    });
  }

  return out;
}

function getCandlesForTf(idx: RawSnapshot['_index'], tf: Tf): CandleData[] | undefined {
  if (!idx) return undefined;
  switch (tf) {
    case "5m":
      return idx.candles_5m;
    case "15m":
      return idx.candles_15m;
    case "1h":
      return idx.candles_1h;
    default:
      return idx.candles_5m;
  }
}

/* ========= Component ========= */

export default function LightweightPriceChart({
  snap,
  height = 280,
  title = "Dealer Gravity",
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null);

  const lastTsRef = useRef<string | null>(null);
  const lastSpotRef = useRef<number | null>(null);
  const hasInitializedRef = useRef(false);
  const seriesKindRef = useRef<SeriesKind>("none");

  const lastCandleRef = useRef<{
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
  } | null>(null);

  const [tf, setTf] = useState<Tf>("5m");

  // Prevent "random reset" by avoiding repeated setData calls when nothing changed
  const lastHistKeyRef = useRef<string>("");

  // ===== Gravity series refs =====
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gravityBestRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gravityHighRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gravityLowRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gravityCloudRef = useRef<any>(null); // Single cloud that floats above/below based on gravity direction

  // cache for gravity
  const gravityCacheRef = useRef<Map<number, number>>(new Map());

  // latest values for legend
  const [gravityLast, setGravityLast] = useState<{
    best: number | null;
    high: number | null;
    low: number | null;
    conf: number | null;
  }>({ best: null, high: null, low: null, conf: null });

  const GRAVITY = {
    best: "rgba(56,189,248,0.95)",   // cyan
    high: "rgba(34,197,94,0.95)",    // green
    low: "rgba(244,114,182,0.95)",   // pink
    fillBase: "rgba(148,163,184,",
  };

  const getBucketSeconds = (tfVal: Tf): number => {
    switch (tfVal) {
      case "5m":
        return 5 * 60;
      case "15m":
        return 15 * 60;
      case "1h":
        return 60 * 60;
      default:
        return 5 * 60;
    }
  };

  /* ========= CREATE CHART + SERIES (once) ========= */
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(148,163,184,1)",
      },
      grid: {
        vertLines: { color: "rgba(51,65,85,0.3)" },
        horzLines: { color: "rgba(51,65,85,0.3)" },
      },
      rightPriceScale: { borderColor: "rgba(30,41,59,1)" },
      timeScale: {
        borderColor: "rgba(30,41,59,1)",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: { mode: 1 },
      localization: {
        timeFormatter: (time: unknown) => formatCrosshairEstLabel(time),
      },
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let series: any = null;
    let kind: SeriesKind = "none";

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (typeof (chart as any).addSeries === "function") {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        series = (chart as any).addSeries(CandlestickSeries, {
          upColor: "#22c55e",
          downColor: "#ef4444",
          borderUpColor: "#22c55e",
          borderDownColor: "#ef4444",
          wickUpColor: "#22c55e",
          wickDownColor: "#ef4444",
          priceLineVisible: true,
          lastValueVisible: false,
          priceLineColor: "rgba(16,185,129,0.85)",
        });
        kind = "candles";
      } catch {
        try {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          series = (chart as any).addSeries(AreaSeries, {
            lineColor: "rgba(56,189,248,1)",
            topColor: "rgba(56,189,248,0.45)",
            bottomColor: "rgba(56,189,248,0.03)",
            lineWidth: 2,
            priceLineVisible: true,
            lastValueVisible: false,
            priceLineColor: "rgba(16,185,129,0.85)",
          });
          kind = "area";
        } catch {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          series = (chart as any).addSeries(LineSeries, {
            color: "rgba(56,189,248,1)",
            lineWidth: 2,
            priceLineVisible: true,
            lastValueVisible: false,
            priceLineColor: "rgba(16,185,129,0.85)",
          });
          kind = "line";
        }
      }
    } else {
      console.error("[LW] chart.addSeries is not a function");
      series = null;
      kind = "none";
    }

    // ===== Gravity overlays =====
    try {
      // Floating cloud - positioned above or below based on gravity direction
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      gravityCloudRef.current = (chart as any).addSeries(AreaSeries, {
        lineWidth: 0,
        lineColor: "transparent",
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        topColor: "rgba(56,189,248,0.25)",    // Cyan cloud color
        bottomColor: "rgba(56,189,248,0.05)", // Fades out
      });

      // High band line (green)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      gravityHighRef.current = (chart as any).addSeries(LineSeries, {
        color: GRAVITY.high,
        lineWidth: 2,
        lineType: 0,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: true,
        title: "",
      });

      // Low band line (pink)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      gravityLowRef.current = (chart as any).addSeries(LineSeries, {
        color: GRAVITY.low,
        lineWidth: 2,
        lineType: 0,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: true,
        title: "",
      });

      // Best guess line (cyan) - on top
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      gravityBestRef.current = (chart as any).addSeries(LineSeries, {
        color: GRAVITY.best,
        lineWidth: 3,
        lineType: 0,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: true,
        title: "",
      });
    } catch (e) {
      console.warn("[LW] Gravity overlays failed to init:", e);
      gravityCloudRef.current = null;
      gravityHighRef.current = null;
      gravityLowRef.current = null;
      gravityBestRef.current = null;
    }

    seriesRef.current = series;
    seriesKindRef.current = kind;
    chartRef.current = chart;

    const handleResize = () => {
      if (!containerRef.current || !chartRef.current) return;
      const { width } = containerRef.current.getBoundingClientRect();
      chartRef.current.applyOptions({ width });
    };

    handleResize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (chartRef.current) chartRef.current.remove();

      chartRef.current = null;
      seriesRef.current = null;
      seriesKindRef.current = "none";
      hasInitializedRef.current = false;
      lastTsRef.current = null;
      lastSpotRef.current = null;
      lastCandleRef.current = null;
      lastHistKeyRef.current = "";

      gravityBestRef.current = null;
      gravityHighRef.current = null;
      gravityLowRef.current = null;
      gravityCloudRef.current = null;
      gravityCacheRef.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height]);

  /* ========= UPDATE AXIS LOCALIZATION WHEN TF CHANGES ========= */
  useEffect(() => {
    if (!chartRef.current) return;

    hasInitializedRef.current = false;
    lastCandleRef.current = null;
    lastHistKeyRef.current = "";
    gravityCacheRef.current.clear();
    setGravityLast({ best: null, high: null, low: null, conf: null });

    chartRef.current.applyOptions({
      timeScale: {
        secondsVisible: false,
        tickMarkFormatter: (time: unknown) => {
          let epochSec: number;

          if (typeof time === "number") {
            epochSec = time;
          } else if (time && typeof time === "object" && "year" in time) {
            const t = time as { year: number; month: number; day: number };
            epochSec = Date.UTC(t.year, t.month - 1, t.day) / 1000;
          } else {
            return "";
          }

          const dUtc = new Date(epochSec * 1000);
          const estString = dUtc.toLocaleString("en-US", {
            timeZone: "America/New_York",
          });
          const dEst = new Date(estString);

          const hour = dEst.getHours();
          const minute = dEst.getMinutes();

          if (hour === 9 && minute >= 25 && minute <= 35) {
            return dEst.toLocaleDateString("en-US", { day: "2-digit" });
          }

          return formatEstAxisLabelSnapped(epochSec);
        },
      },
    });
  }, [tf]);

  /* ========= LOAD HISTORICAL CANDLES (respect TF) ========= */
  useEffect(() => {
    if (!snap || !snap._index) return;
    if (!seriesRef.current || !chartRef.current) return;

    const idx = snap._index;
    const allCandles = getCandlesForTf(idx, tf);
    if (!allCandles || !Array.isArray(allCandles) || allCandles.length === 0) return;

    // Filter to today's session only
    const candles = filterTodaySession(allCandles);
    if (candles.length === 0) return;

    const lastT = candles[candles.length - 1]?.t;
    const histKey = `${tf}:${candles.length}:${typeof lastT === "number" ? lastT : "na"}`;
    if (histKey === lastHistKeyRef.current) return;
    lastHistKeyRef.current = histKey;

    const kind = seriesKindRef.current;

    if (kind === "candles") {
      const formatted = candles.map((c) => ({
        time: c.t,
        open: c.o,
        high: c.h,
        low: c.l,
        close: c.c,
      }));
      seriesRef.current.setData(formatted);
      if (formatted.length > 0) {
        lastCandleRef.current = formatted[formatted.length - 1];
      }
    } else if (kind === "area" || kind === "line") {
      const formatted = candles.map((c) => ({
        time: c.t,
        value: c.c,
      }));
      seriesRef.current.setData(formatted);
      lastCandleRef.current = null;
    } else {
      return;
    }

    const gravity = computeGravityFromCandles(candles, tf);

    if (
      gravityBestRef.current &&
      gravityHighRef.current &&
      gravityLowRef.current &&
      gravityCloudRef.current
    ) {
      const bestData = gravity.map((g) => ({ time: g.time, value: g.best }));
      const highData = gravity.map((g) => ({ time: g.time, value: g.high }));
      const lowData = gravity.map((g) => ({ time: g.time, value: g.low }));

      // Cloud position: floats above or below best based on gravity pull direction
      // If price > best, gravity pulls DOWN (cloud below best)
      // If price < best, gravity pulls UP (cloud above best)
      const cloudData = gravity.map((g, i) => {
        const priceAtTime = candles[Math.min(i + windowForTf(tf), candles.length - 1)]?.c || g.best;
        const pullDown = priceAtTime > g.best; // Price above gravity = pulling down
        const spread = g.high - g.low;
        // Position cloud above or below the best line with some offset
        const cloudValue = pullDown
          ? g.best - spread * 0.6  // Cloud below (gravity pulling down)
          : g.best + spread * 0.6; // Cloud above (gravity pulling up)
        return { time: g.time, value: cloudValue };
      });

      // Set line data
      gravityBestRef.current.setData(bestData);
      gravityHighRef.current.setData(highData);
      gravityLowRef.current.setData(lowData);

      // Set cloud data
      gravityCloudRef.current.setData(cloudData);

      const last = gravity[gravity.length - 1];
      const lastCandle = candles[candles.length - 1];
      if (last && lastCandle) {
        const op = confidenceToFillOpacity(last.confidence);
        const pullDown = lastCandle.c > last.best;

        // Color based on direction: cyan for up pull, pink for down pull
        const cloudColor = pullDown
          ? "rgba(244,114,182," // Pink - gravity pulling down
          : "rgba(56,189,248,"; // Cyan - gravity pulling up

        gravityCloudRef.current.applyOptions({
          topColor: `${cloudColor}${op})`,
          bottomColor: `${cloudColor}${op * 0.15})`,
        });

        setGravityLast({
          best: last.best,
          high: last.high,
          low: last.low,
          conf: last.confidence,
        });
      }
    }

    gravityCacheRef.current.clear();
    for (const c of candles) {
      if (typeof c?.t === "number" && typeof c?.c === "number") {
        gravityCacheRef.current.set(c.t, c.c);
      }
    }

    if (!hasInitializedRef.current) {
      // Set view to today's trading session
      setTodaySessionView(chartRef.current, candles);
      hasInitializedRef.current = true;
    }
  }, [snap?._index, tf]);

  /* ========= LIVE UPDATES (spot, bucketed per TF) ========= */
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return;
    if (!snap) return;

    const hasIndex =
      !!snap._index && snap._index.spot != null && !!snap._index.ts;

    const spot = hasIndex
      ? (snap._index!.spot as number)
      : (snap.spot as number | null);

    const ts = hasIndex ? snap._index!.ts : snap.ts;
    if (spot == null || !ts) return;

    if (lastTsRef.current === ts && lastSpotRef.current === spot) return;
    lastTsRef.current = ts!;
    lastSpotRef.current = spot;

    const tSec = Math.floor(new Date(ts).getTime() / 1000);
    const bucketSeconds = getBucketSeconds(tf);
    const bucketStart = Math.floor(tSec / bucketSeconds) * bucketSeconds;
    const kind = seriesKindRef.current;

    if (kind === "candles") {
      const last = lastCandleRef.current;

      if (!last || bucketStart > last.time) {
        const newCandle = {
          time: bucketStart,
          open: spot,
          high: spot,
          low: spot,
          close: spot,
        };
        seriesRef.current.update(newCandle);
        lastCandleRef.current = newCandle;
      } else if (bucketStart === last.time) {
        const updated = {
          time: last.time,
          open: last.open,
          high: Math.max(last.high, spot),
          low: Math.min(last.low, spot),
          close: spot,
        };
        seriesRef.current.update(updated);
        lastCandleRef.current = updated;
      }
    } else if (kind === "area" || kind === "line") {
      seriesRef.current.update({
        time: bucketStart,
        value: spot,
      });
    } else {
      return;
    }

    if (
      gravityBestRef.current &&
      gravityHighRef.current &&
      gravityLowRef.current &&
      gravityCloudRef.current
    ) {
      gravityCacheRef.current.set(bucketStart, spot);

      const entries = Array.from(gravityCacheRef.current.entries()).sort(
        (a, b) => a[0] - b[0]
      );

      const n = windowForTf(tf);
      const recent = entries.slice(Math.max(0, entries.length - n));
      const closes = recent.map(([, c]) => c);

      if (closes.length >= Math.max(8, Math.floor(n * 0.5))) {
        const m = mean(closes);
        const sd = stdev(closes);
        const rel = m !== 0 ? sd / Math.abs(m) : 0;
        const conf = clamp01(1 - rel / 0.02);

        const highVal = m + sd;
        const lowVal = m - sd;
        const spread = highVal - lowVal;

        // Update lines
        gravityBestRef.current.update({ time: bucketStart, value: m });
        gravityHighRef.current.update({ time: bucketStart, value: highVal });
        gravityLowRef.current.update({ time: bucketStart, value: lowVal });

        // Cloud position based on gravity direction
        const pullDown = spot > m; // Price above gravity = pulling down
        const cloudValue = pullDown
          ? m - spread * 0.6  // Cloud below
          : m + spread * 0.6; // Cloud above

        gravityCloudRef.current.update({ time: bucketStart, value: cloudValue });

        // Adjust cloud color and opacity based on direction and confidence
        const op = confidenceToFillOpacity(conf);
        const cloudColor = pullDown
          ? "rgba(244,114,182," // Pink - gravity pulling down
          : "rgba(56,189,248,"; // Cyan - gravity pulling up

        gravityCloudRef.current.applyOptions({
          topColor: `${cloudColor}${op})`,
          bottomColor: `${cloudColor}${op * 0.15})`,
        });

        setGravityLast({ best: m, high: highVal, low: lowVal, conf });
      }
    }
  }, [snap, snap?._index?.ts, snap?._index?.spot, tf]);

  const gBest = gravityLast.best;
  const gHigh = gravityLast.high;
  const gLow = gravityLast.low;

  return (
    <div className="dealer-gravity-lw">
      <div className="dg-lw-header">
        <span className="dg-lw-title">{title}</span>
        <div className="dg-lw-controls">
          <div className="dg-lw-timeframes">
            {TF_OPTIONS.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => setTf(opt)}
                className={`dg-lw-tf-btn ${opt === tf ? 'active' : ''}`}
              >
                {opt}
              </button>
            ))}
          </div>
          <div className="dg-lw-legend">
            <span className="dg-lw-legend-item best">
              <span className="dg-lw-dot"></span>
              Best {gBest != null ? gBest.toFixed(2) : "—"}
            </span>
            <span className="dg-lw-legend-item high">
              <span className="dg-lw-dot"></span>
              High {gHigh != null ? gHigh.toFixed(2) : "—"}
            </span>
            <span className="dg-lw-legend-item low">
              <span className="dg-lw-dot"></span>
              Low {gLow != null ? gLow.toFixed(2) : "—"}
            </span>
          </div>
        </div>
      </div>
      <div
        ref={containerRef}
        className="dg-lw-chart"
        style={{ height: `${height}px` }}
      />
    </div>
  );
}
