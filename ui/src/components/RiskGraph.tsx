/**
 * RiskGraph - Options P&L visualization using Apache ECharts
 *
 * Core features:
 * - Expiration P&L curve (blue)
 * - Theoretical P&L curve (magenta)
 * - Pan/zoom on both axes
 * - Spot price marker
 * - Strategy strike markers
 * - Alert line visualization
 * - Auto-fit to strategies
 */

import { useRef, useMemo, useEffect, forwardRef, useImperativeHandle } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useRiskGraphCalculations, type Strategy } from '../hooks/useRiskGraphCalculations';

// Expose zoom/pan functions to parent
export interface RiskGraphHandle {
  autoFit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  panLeft: () => void;
  panRight: () => void;
}

// Symbol-specific grid intervals
const SYMBOL_GRID_CONFIG: Record<string, number> = {
  'SPX': 5,
  'NDX': 50,
  'I:SPX': 5,
  'I:NDX': 50,
};

// Alert types for visualization
export interface PriceAlertLine {
  id: string;
  price: number;
  color: string;
  label?: string;
}

export interface StrategyAlert {
  id: string;
  type: 'price' | 'debit' | 'profit_target' | 'trailing_stop' | 'ai_theta_gamma';
  targetValue: number;
  color: string;
  enabled: boolean;
}

export interface RiskGraphProps {
  strategies: Strategy[];
  spotPrice: number;
  vix: number;
  symbol: string;
  timeMachineEnabled?: boolean;
  simVolatilityOffset?: number;
  simTimeOffsetHours?: number;
  simSpotOffset?: number;
  // Alert visualization
  priceAlertLines?: PriceAlertLine[];
  alerts?: StrategyAlert[];
  // Context menu callback (for creating price lines)
  onContextMenu?: (price: number, clientX: number, clientY: number) => void;
}

const RiskGraph = forwardRef<RiskGraphHandle, RiskGraphProps>(({
  strategies,
  spotPrice,
  vix,
  symbol,
  timeMachineEnabled = false,
  simVolatilityOffset = 0,
  simTimeOffsetHours = 0,
  simSpotOffset = 0,
  priceAlertLines = [],
  alerts = [],
  onContextMenu,
}, ref) => {
  const chartRef = useRef<ReactECharts>(null);
  const gridInterval = SYMBOL_GRID_CONFIG[symbol] || 5;

  // Zoom/pan control functions
  const getZoomState = () => {
    const chart = chartRef.current?.getEchartsInstance();
    if (!chart) return { start: 0, end: 100 };
    const option = chart.getOption() as { dataZoom?: Array<{ start?: number; end?: number }> };
    const dz = option.dataZoom?.[0];
    return { start: dz?.start ?? 0, end: dz?.end ?? 100 };
  };

  const zoomIn = () => {
    const { start, end } = getZoomState();
    const range = end - start;
    const newRange = Math.max(10, range * 0.7); // Zoom in 30%
    const center = (start + end) / 2;
    const newStart = Math.max(0, center - newRange / 2);
    const newEnd = Math.min(100, center + newRange / 2);
    chartRef.current?.getEchartsInstance()?.dispatchAction({
      type: 'dataZoom', start: newStart, end: newEnd
    });
  };

  const zoomOut = () => {
    const { start, end } = getZoomState();
    const range = end - start;
    const newRange = Math.min(100, range * 1.4); // Zoom out 40%
    const center = (start + end) / 2;
    const newStart = Math.max(0, center - newRange / 2);
    const newEnd = Math.min(100, center + newRange / 2);
    chartRef.current?.getEchartsInstance()?.dispatchAction({
      type: 'dataZoom', start: newStart, end: newEnd
    });
  };

  const panLeft = () => {
    const { start, end } = getZoomState();
    const range = end - start;
    const shift = range * 0.2; // Pan 20% of visible range
    const newStart = Math.max(0, start - shift);
    const newEnd = newStart + range;
    chartRef.current?.getEchartsInstance()?.dispatchAction({
      type: 'dataZoom', start: newStart, end: Math.min(100, newEnd)
    });
  };

  const panRight = () => {
    const { start, end } = getZoomState();
    const range = end - start;
    const shift = range * 0.2; // Pan 20% of visible range
    const newEnd = Math.min(100, end + shift);
    const newStart = newEnd - range;
    chartRef.current?.getEchartsInstance()?.dispatchAction({
      type: 'dataZoom', start: Math.max(0, newStart), end: newEnd
    });
  };

  const autoFit = () => {
    chartRef.current?.getEchartsInstance()?.dispatchAction({
      type: 'dataZoom', start: 0, end: 100
    });
  };

  // Auto-fit when strategy count changes
  const strategyCount = strategies.filter(s => s.visible).length;
  const prevStrategyCount = useRef(strategyCount);
  useEffect(() => {
    if (strategyCount !== prevStrategyCount.current) {
      // Strategy added or removed - auto-fit after a brief delay for chart to update
      const timer = setTimeout(() => autoFit(), 50);
      prevStrategyCount.current = strategyCount;
      return () => clearTimeout(timer);
    }
  }, [strategyCount]);

  // Expose zoom/pan functions to parent
  useImperativeHandle(ref, () => ({
    autoFit,
    zoomIn,
    zoomOut,
    panLeft,
    panRight,
  }));

  // Simulated spot
  const effectiveSpot = timeMachineEnabled && simSpotOffset !== 0
    ? spotPrice + simSpotOffset
    : spotPrice;

  // Calculate P&L data
  const data = useRiskGraphCalculations({
    strategies,
    spotPrice,
    vix,
    timeMachineEnabled,
    simVolatilityOffset,
    simTimeOffsetHours,
  });

  // Convert to ECharts format
  const expirationData = useMemo(() =>
    data.expirationPoints.map(p => [p.price, p.pnl]),
    [data.expirationPoints]
  );

  const theoreticalData = useMemo(() =>
    data.theoreticalPoints.map(p => [p.price, p.pnl]),
    [data.theoreticalPoints]
  );

  // Strike markers
  const strikeMarkers = useMemo(() => {
    return strategies.filter(s => s.visible).flatMap(strat => {
      if (strat.strategy === 'butterfly') {
        return [strat.strike - strat.width, strat.strike, strat.strike + strat.width];
      } else if (strat.strategy === 'vertical') {
        return [strat.strike, strat.side === 'call' ? strat.strike + strat.width : strat.strike - strat.width];
      }
      return [strat.strike];
    });
  }, [strategies]);

  // Build chart option
  const option: EChartsOption = useMemo(() => {
    const hasData = data.expirationPoints.length > 0;

    // Calculate X bounds: include all data, break-evens, and spot with padding
    const allBreakevens = [...data.expirationBreakevens, ...data.theoreticalBreakevens];
    const xPoints = [data.minPrice, data.maxPrice, spotPrice, ...allBreakevens];
    const xMin = Math.min(...xPoints);
    const xMax = Math.max(...xPoints);
    const xRange = xMax - xMin || 100;
    const xPadding = xRange * 0.08; // 8% padding on each side
    const chartXMin = xMin - xPadding;
    const chartXMax = xMax + xPadding;

    // Calculate Y bounds: always include zero, fit all P&L with padding
    const yMin = Math.min(data.minPnL, 0);
    const yMax = Math.max(data.maxPnL, 0);
    const yRange = yMax - yMin || 100;
    const yPadding = yRange * 0.1; // 10% padding
    const chartYMin = yMin - yPadding;
    const chartYMax = yMax + yPadding;

    // Tick height as percentage of P&L range
    const pnlRange = data.maxPnL - data.minPnL || 100;
    const tickHeight = pnlRange * 0.04; // 4% of range

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const markLines: any[] = [
      // Zero line (horizontal)
      {
        yAxis: 0,
        lineStyle: { color: '#333', type: 'solid', width: 1 },
        label: { show: false },
      },
    ];

    // Spot price - tick at zero line
    markLines.push([
      { coord: [spotPrice, -tickHeight], symbol: 'none' },
      { coord: [spotPrice, tickHeight], symbol: 'none', lineStyle: { color: '#fbbf24', type: 'solid', width: 1 }, label: { formatter: spotPrice.toFixed(0), color: '#fbbf24', fontSize: 9, position: 'end' } },
    ]);

    // Sim spot tick (if different)
    if (timeMachineEnabled && simSpotOffset !== 0) {
      markLines.push([
        { coord: [effectiveSpot, -tickHeight], symbol: 'none' },
        { coord: [effectiveSpot, tickHeight], symbol: 'none', lineStyle: { color: '#f97316', type: 'solid', width: 1 }, label: { formatter: 'SIM', color: '#f97316', fontSize: 8, position: 'end' } },
      ]);
    }

    // Strike markers - ticks at zero line
    strikeMarkers.forEach(strike => {
      markLines.push([
        { coord: [strike, -tickHeight * 0.6], symbol: 'none' },
        { coord: [strike, tickHeight * 0.6], symbol: 'none', lineStyle: { color: '#f59e0b', type: 'solid', width: 1 } },
      ]);
    });

    // Price alert lines (user-defined vertical lines)
    priceAlertLines.forEach(alert => {
      markLines.push([
        { coord: [alert.price, data.minPnL - pnlRange * 0.1], symbol: 'none' },
        {
          coord: [alert.price, data.maxPnL + pnlRange * 0.1],
          symbol: 'none',
          lineStyle: { color: alert.color, type: 'solid', width: 1 },
          label: {
            formatter: alert.price.toFixed(0),
            color: '#fff',
            backgroundColor: alert.color,
            padding: [2, 4],
            borderRadius: 2,
            fontSize: 9,
            position: 'start',
          },
        },
      ]);
    });

    // Strategy alerts (price type only - vertical lines at target price)
    alerts.filter(a => a.enabled && a.type === 'price').forEach(alert => {
      markLines.push([
        { coord: [alert.targetValue, data.minPnL - pnlRange * 0.1], symbol: 'none' },
        {
          coord: [alert.targetValue, data.maxPnL + pnlRange * 0.1],
          symbol: 'none',
          lineStyle: { color: alert.color, type: 'dashed', width: 1 },
          label: {
            formatter: alert.targetValue.toFixed(0),
            color: '#fff',
            backgroundColor: alert.color,
            padding: [2, 4],
            borderRadius: 2,
            fontSize: 9,
            position: 'start',
          },
        },
      ]);
    });

    return {
      animation: false,
      backgroundColor: '#0a0a0a',

      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', crossStyle: { color: '#555' } },
        backgroundColor: 'rgba(15, 15, 15, 0.95)',
        borderColor: '#333',
        textStyle: { color: '#e5e5e5', fontSize: 11 },
        formatter: (params: unknown) => {
          const p = params as Array<{ data: [number, number]; seriesName: string; color: string }>;
          if (!p?.length) return '';
          const price = p[0].data[0];
          let html = `<div style="color:#888;margin-bottom:4px;">$${price.toFixed(2)}</div>`;
          p.forEach(item => {
            const pnl = item.data[1];
            const color = pnl >= 0 ? '#4ade80' : '#f87171';
            html += `<div>${item.seriesName}: <span style="color:${color}">$${pnl >= 0 ? '+' : ''}${pnl.toFixed(0)}</span></div>`;
          });
          return html;
        },
      },

      legend: {
        data: ['Expiration', 'Current'],
        top: 6,
        right: 12,
        textStyle: { color: '#555', fontSize: 10 },
        itemWidth: 16,
        itemHeight: 2,
      },

      grid: { left: 55, right: 15, top: 35, bottom: 55 },

      xAxis: {
        type: 'value',
        min: hasData ? chartXMin : spotPrice - 50,
        max: hasData ? chartXMax : spotPrice + 50,
        axisLine: { lineStyle: { color: '#333' } },
        axisLabel: { color: '#555', fontSize: 9, formatter: (v: number) => v.toFixed(0) },
        splitLine: { lineStyle: { color: '#1a1a1a' } },
        interval: gridInterval,
      },

      yAxis: {
        type: 'value',
        min: hasData ? chartYMin : -100,
        max: hasData ? chartYMax : 100,
        axisLine: { lineStyle: { color: '#333' } },
        axisLabel: { color: '#555', fontSize: 9, formatter: (v: number) => `$${v >= 0 ? '+' : ''}${v.toFixed(0)}` },
        splitLine: { lineStyle: { color: '#1a1a1a' } },
      },

      dataZoom: [
        // X-axis zoom/pan: scroll = zoom (compress strikes), drag = pan
        {
          type: 'inside',
          xAxisIndex: 0,
          filterMode: 'none',
          zoomOnMouseWheel: true,       // Scroll to zoom X (compress/expand strikes)
          moveOnMouseMove: true,        // Drag to pan
          moveOnMouseWheel: false,
          preventDefaultMouseMove: true,
        },
        // Y-axis zoom: Shift+scroll
        {
          type: 'inside',
          yAxisIndex: 0,
          filterMode: 'none',
          zoomOnMouseWheel: 'shift',   // Shift+scroll to zoom Y
          moveOnMouseMove: false,
          moveOnMouseWheel: false,
        },
        // Slider for quick navigation
        {
          type: 'slider',
          xAxisIndex: 0,
          height: 24,
          bottom: 4,
          borderColor: '#333',
          backgroundColor: '#0d0d0d',
          fillerColor: 'rgba(59,130,246,0.2)',
          handleStyle: { color: '#3b82f6', borderColor: '#3b82f6' },
          handleSize: '80%',
          textStyle: { color: '#555', fontSize: 8 },
          dataBackground: {
            lineStyle: { color: '#3b82f6', width: 1 },
            areaStyle: { color: 'rgba(59,130,246,0.1)' },
          },
          selectedDataBackground: {
            lineStyle: { color: '#3b82f6', width: 1 },
            areaStyle: { color: 'rgba(59,130,246,0.2)' },
          },
          brushSelect: false,
          showDetail: false,
        },
      ],

      series: [
        {
          name: 'Expiration',
          type: 'line',
          data: expirationData,
          symbol: 'none',
          lineStyle: { color: '#3b82f6', width: 2 },
          areaStyle: {
            color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(74,222,128,0.15)' },
                { offset: 0.5, color: 'transparent' },
                { offset: 1, color: 'rgba(248,113,113,0.15)' },
              ],
            },
            origin: 0,
          },
          markLine: { silent: true, symbol: 'none', data: markLines },
        },
        {
          name: 'Current',
          type: 'line',
          data: theoreticalData,
          symbol: 'none',
          lineStyle: { color: '#e879f9', width: 2 },
        },
      ],
    };
  }, [data, expirationData, theoreticalData, spotPrice, effectiveSpot, gridInterval, strikeMarkers, timeMachineEnabled, simSpotOffset, priceAlertLines, alerts]);

  // Handle chart events
  const onEvents = useMemo(() => ({
    contextmenu: (params: { event?: { event?: MouseEvent }; data?: [number, number] }) => {
      if (onContextMenu && params.event?.event) {
        const event = params.event.event;
        event.preventDefault();

        // Get the chart instance and convert pixel to data coordinates
        const chart = chartRef.current?.getEchartsInstance();
        if (chart) {
          const pointInPixel = [event.offsetX, event.offsetY];
          const pointInGrid = chart.convertFromPixel({ seriesIndex: 0 }, pointInPixel);
          if (pointInGrid) {
            const price = pointInGrid[0];
            onContextMenu(price, event.clientX, event.clientY);
          }
        }
      }
    },
  }), [onContextMenu]);

  return (
    <div className="risk-graph" style={{ height: '100%', width: '100%', position: 'relative' }}>
      <ReactECharts
        ref={chartRef}
        option={option}
        style={{ height: '100%', width: '100%' }}
        opts={{ renderer: 'canvas' }}
        notMerge={false}
        onEvents={onEvents}
      />
    </div>
  );
});

RiskGraph.displayName = 'RiskGraph';

export default RiskGraph;

// Re-export Strategy type from hook
export { type Strategy };
