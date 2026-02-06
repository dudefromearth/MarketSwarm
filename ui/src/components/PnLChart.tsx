/**
 * PnLChart - Custom Canvas-based P&L chart
 *
 * Simple, no-nonsense charting:
 * - Auto-fit on load or when data changes
 * - Drag to pan
 * - Scroll to zoom
 * - Click Auto-Fit button to reset view
 */

import { useRef, useEffect, useCallback, forwardRef, useImperativeHandle, useState } from 'react';

export interface PnLPoint {
  price: number;
  pnl: number;
}

export type PriceAlertType = 'price_above' | 'price_below' | 'price_touch';

/** Backdrop render props - passed to backdrop component */
export interface BackdropRenderProps {
  /** Chart area width (excluding padding) */
  width: number;
  /** Chart area height (excluding padding) */
  height: number;
  /** Minimum price in current view (X-axis) */
  priceMin: number;
  /** Maximum price in current view (X-axis) */
  priceMax: number;
  /** Current spot price */
  spotPrice: number;
}

export interface PnLChartProps {
  expirationData: PnLPoint[];
  theoreticalData: PnLPoint[];
  spotPrice: number;
  expirationBreakevens: number[];
  theoreticalBreakevens: number[];
  strikes: number[];
  onOpenAlertDialog?: (price: number, type: PriceAlertType) => void;
  alertLines?: { price: number; color: string; label?: string }[];
  /** Optional backdrop render function - rendered behind chart */
  renderBackdrop?: (props: BackdropRenderProps) => React.ReactNode;
}

export interface PnLChartHandle {
  autoFit: () => void;
}

interface ViewState {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

const PADDING = { top: 40, right: 20, bottom: 50, left: 60 };

const PnLChart = forwardRef<PnLChartHandle, PnLChartProps>(({
  expirationData,
  theoreticalData,
  spotPrice,
  expirationBreakevens,
  theoreticalBreakevens,
  strikes,
  onOpenAlertDialog,
  alertLines = [],
  renderBackdrop,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // View state (what portion of data is visible)
  const viewState = useRef<ViewState>({ xMin: 0, xMax: 100, yMin: -100, yMax: 100 });

  // Drag state
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const viewAtDragStart = useRef<ViewState | null>(null);
  const isXAxisDrag = useRef(false); // True when dragging on X-axis to zoom
  const isYAxisDrag = useRef(false); // True when dragging on Y-axis to zoom
  const [cursorStyle, setCursorStyle] = useState('grab');
  const [axisZoomHint, setAxisZoomHint] = useState<'x' | 'y' | null>(null);
  const [crosshair, setCrosshair] = useState<{ x: number; y: number } | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; price: number } | null>(null);

  // Backdrop dimensions and view state - updated on draw
  const [backdropProps, setBackdropProps] = useState<BackdropRenderProps | null>(null);

  // Calculate bounds that fit all data + breakevens + spot with padding
  // Break-even span (trade width) should fill 2/3 of chart width
  const calculateFitBounds = useCallback((): ViewState => {
    if (expirationData.length === 0) {
      return { xMin: spotPrice - 50, xMax: spotPrice + 50, yMin: -100, yMax: 100 };
    }

    // Collect all Y points
    const allY = [
      ...expirationData.map(p => p.pnl),
      ...theoreticalData.map(p => p.pnl),
      0, // Always include zero line
    ];

    const yMin = Math.min(...allY);
    const yMax = Math.max(...allY);
    const yRange = yMax - yMin || 100;

    // Trade width is defined by ALL break-evens (expiration + theoretical/real-time)
    // Theoretical break-evens are typically wider
    const allBreakevens = [...expirationBreakevens, ...theoreticalBreakevens];

    let tradeMin: number, tradeMax: number;

    if (allBreakevens.length >= 2) {
      tradeMin = Math.min(...allBreakevens);
      tradeMax = Math.max(...allBreakevens);
    } else if (allBreakevens.length === 1) {
      // Single break-even - center around it with strikes
      const be = allBreakevens[0];
      const strikeSpan = strikes.length > 0
        ? Math.max(...strikes) - Math.min(...strikes)
        : 50;
      tradeMin = be - strikeSpan;
      tradeMax = be + strikeSpan;
    } else {
      // No break-evens - use strikes
      tradeMin = Math.min(...strikes, spotPrice);
      tradeMax = Math.max(...strikes, spotPrice);
    }

    const tradeWidth = tradeMax - tradeMin || 100;
    const tradeCenter = (tradeMin + tradeMax) / 2;

    // Trade width should fill 2/3 of chart, so total chart = tradeWidth * 1.5
    const chartWidth = tradeWidth * 1.5;

    return {
      xMin: tradeCenter - chartWidth / 2,
      xMax: tradeCenter + chartWidth / 2,
      yMin: yMin - yRange * 0.1,
      yMax: yMax + yRange * 0.1,
    };
  }, [expirationData, theoreticalData, expirationBreakevens, theoreticalBreakevens, strikes, spotPrice]);

  // Auto-fit view to data
  const autoFit = useCallback(() => {
    viewState.current = calculateFitBounds();
    draw();
  }, [calculateFitBounds]);

  // Expose autoFit to parent
  useImperativeHandle(ref, () => ({ autoFit }));

  // Convert data coordinates to canvas pixels
  const toCanvasX = useCallback((price: number, width: number): number => {
    const { xMin, xMax } = viewState.current;
    const chartWidth = width - PADDING.left - PADDING.right;
    return PADDING.left + ((price - xMin) / (xMax - xMin)) * chartWidth;
  }, []);

  const toCanvasY = useCallback((pnl: number, height: number): number => {
    const { yMin, yMax } = viewState.current;
    const chartHeight = height - PADDING.top - PADDING.bottom;
    return PADDING.top + ((yMax - pnl) / (yMax - yMin)) * chartHeight;
  }, []);

  // Convert canvas pixels to data coordinates
  const toDataX = useCallback((canvasX: number, width: number): number => {
    const { xMin, xMax } = viewState.current;
    const chartWidth = width - PADDING.left - PADDING.right;
    return xMin + ((canvasX - PADDING.left) / chartWidth) * (xMax - xMin);
  }, []);

  const toDataY = useCallback((canvasY: number, height: number): number => {
    const { yMin, yMax } = viewState.current;
    const chartHeight = height - PADDING.top - PADDING.bottom;
    return yMax - ((canvasY - PADDING.top) / chartHeight) * (yMax - yMin);
  }, []);

  // Draw the chart
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    // Skip drawing if container has no dimensions yet
    if (width < 50 || height < 50) return;

    // Handle high DPI displays
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);

    const { xMin, xMax, yMin, yMax } = viewState.current;

    // Update backdrop props for external render
    const chartWidth = width - PADDING.left - PADDING.right;
    const chartHeight = height - PADDING.top - PADDING.bottom;
    setBackdropProps({
      width: chartWidth,
      height: chartHeight,
      priceMin: xMin,
      priceMax: xMax,
      spotPrice,
    });

    // Clear - fill axis areas, leave chart area for backdrop to show
    ctx.fillStyle = '#0a0a0a';
    // Top padding
    ctx.fillRect(0, 0, width, PADDING.top);
    // Bottom padding
    ctx.fillRect(0, height - PADDING.bottom, width, PADDING.bottom);
    // Left padding
    ctx.fillRect(0, PADDING.top, PADDING.left, chartHeight);
    // Right padding
    ctx.fillRect(width - PADDING.right, PADDING.top, PADDING.right, chartHeight);

    // Chart area background (semi-transparent if backdrop exists)
    if (renderBackdrop) {
      ctx.fillStyle = 'rgba(10, 10, 10, 0.85)'; // Semi-transparent to let backdrop show
    } else {
      ctx.fillStyle = '#0a0a0a';
    }
    ctx.fillRect(PADDING.left, PADDING.top, chartWidth, chartHeight);

    // Draw grid
    ctx.strokeStyle = '#1a1a1a';
    ctx.lineWidth = 1;

    // Y grid lines and labels
    const yRange = yMax - yMin;
    const yStep = calculateNiceStep(yRange, 6);
    const yStart = Math.ceil(yMin / yStep) * yStep;

    ctx.font = '10px monospace';
    ctx.fillStyle = '#555';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    for (let y = yStart; y <= yMax; y += yStep) {
      const canvasY = toCanvasY(y, height);
      if (canvasY >= PADDING.top && canvasY <= height - PADDING.bottom) {
        ctx.beginPath();
        ctx.moveTo(PADDING.left, canvasY);
        ctx.lineTo(width - PADDING.right, canvasY);
        ctx.stroke();

        const label = y >= 0 ? `+$${y.toFixed(0)}` : `-$${Math.abs(y).toFixed(0)}`;
        ctx.fillText(label, PADDING.left - 5, canvasY);
      }
    }

    // X grid lines and labels
    const xRange = xMax - xMin;
    const xStep = calculateNiceStep(xRange, 10);
    const xStart = Math.ceil(xMin / xStep) * xStep;

    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';

    for (let x = xStart; x <= xMax; x += xStep) {
      const canvasX = toCanvasX(x, width);
      if (canvasX >= PADDING.left && canvasX <= width - PADDING.right) {
        ctx.beginPath();
        ctx.moveTo(canvasX, PADDING.top);
        ctx.lineTo(canvasX, height - PADDING.bottom);
        ctx.stroke();

        ctx.fillText(x.toFixed(0), canvasX, height - PADDING.bottom + 5);
      }
    }

    // Draw zero line (more prominent)
    const zeroY = toCanvasY(0, height);
    if (zeroY >= PADDING.top && zeroY <= height - PADDING.bottom) {
      ctx.strokeStyle = '#333';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(PADDING.left, zeroY);
      ctx.lineTo(width - PADDING.right, zeroY);
      ctx.stroke();
    }

    // Draw spot price line
    const spotX = toCanvasX(spotPrice, width);
    if (spotX >= PADDING.left && spotX <= width - PADDING.right) {
      ctx.strokeStyle = '#fbbf24';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(spotX, PADDING.top);
      ctx.lineTo(spotX, height - PADDING.bottom);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label
      ctx.fillStyle = '#fbbf24';
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(spotPrice.toFixed(0), spotX, PADDING.top - 5);
    }

    // Draw strike markers
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 1;
    strikes.forEach(strike => {
      const x = toCanvasX(strike, width);
      if (x >= PADDING.left && x <= width - PADDING.right) {
        ctx.beginPath();
        ctx.moveTo(x, zeroY - 8);
        ctx.lineTo(x, zeroY + 8);
        ctx.stroke();
      }
    });

    // Draw expiration breakeven markers (blue, matches expiration curve)
    ctx.fillStyle = '#3b82f6';
    ctx.font = '9px monospace';
    expirationBreakevens.forEach(be => {
      const x = toCanvasX(be, width);
      if (x >= PADDING.left && x <= width - PADDING.right) {
        ctx.beginPath();
        ctx.arc(x, zeroY, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillText(`${be.toFixed(0)}`, x, zeroY + 12);
      }
    });

    // Draw theoretical breakeven markers (magenta, matches theoretical curve)
    ctx.fillStyle = '#e879f9';
    theoreticalBreakevens.forEach(be => {
      const x = toCanvasX(be, width);
      if (x >= PADDING.left && x <= width - PADDING.right) {
        ctx.beginPath();
        ctx.arc(x, zeroY, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillText(`${be.toFixed(0)}`, x, zeroY - 12);
      }
    });

    // Draw expiration P&L curve
    if (expirationData.length > 1) {
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      ctx.beginPath();

      let started = false;
      expirationData.forEach(point => {
        const x = toCanvasX(point.price, width);
        const y = toCanvasY(point.pnl, height);

        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();

      // Fill area (green above zero, red below)
      ctx.globalAlpha = 0.1;
      expirationData.forEach((point, i) => {
        if (i === 0) return;
        const prev = expirationData[i - 1];
        const x1 = toCanvasX(prev.price, width);
        const x2 = toCanvasX(point.price, width);
        const y1 = toCanvasY(prev.pnl, height);
        const y2 = toCanvasY(point.pnl, height);

        ctx.fillStyle = point.pnl >= 0 ? '#4ade80' : '#f87171';
        ctx.beginPath();
        ctx.moveTo(x1, zeroY);
        ctx.lineTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.lineTo(x2, zeroY);
        ctx.closePath();
        ctx.fill();
      });
      ctx.globalAlpha = 1;
    }

    // Draw theoretical P&L curve
    if (theoreticalData.length > 1) {
      ctx.strokeStyle = '#e879f9';
      ctx.lineWidth = 2;
      ctx.beginPath();

      let started = false;
      theoreticalData.forEach(point => {
        const x = toCanvasX(point.price, width);
        const y = toCanvasY(point.pnl, height);

        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
    }

    // Draw alert lines
    alertLines.forEach(alert => {
      const x = toCanvasX(alert.price, width);
      if (x >= PADDING.left && x <= width - PADDING.right) {
        ctx.strokeStyle = alert.color;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, PADDING.top);
        ctx.lineTo(x, height - PADDING.bottom);
        ctx.stroke();
        ctx.setLineDash([]);

        // Label
        if (alert.label) {
          ctx.fillStyle = alert.color;
          ctx.font = '9px monospace';
          ctx.textAlign = 'center';
          ctx.fillText(alert.label, x, PADDING.top - 5);
        }
      }
    });

    // Draw current P&L at spot indicator
    if (theoreticalData.length > 0) {
      // Find P&L at spot price
      let pnlAtSpot: number | null = null;
      for (let i = 1; i < theoreticalData.length; i++) {
        const prev = theoreticalData[i - 1];
        const curr = theoreticalData[i];
        if (spotPrice >= prev.price && spotPrice <= curr.price) {
          const t = (spotPrice - prev.price) / (curr.price - prev.price);
          pnlAtSpot = prev.pnl + t * (curr.pnl - prev.pnl);
          break;
        }
      }

      if (pnlAtSpot !== null && spotX >= PADDING.left && spotX <= width - PADDING.right) {
        const pnlY = toCanvasY(pnlAtSpot, height);
        if (pnlY >= PADDING.top && pnlY <= height - PADDING.bottom) {
          // Draw marker
          ctx.fillStyle = pnlAtSpot >= 0 ? '#4ade80' : '#f87171';
          ctx.beginPath();
          ctx.arc(spotX, pnlY, 6, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = '#fff';
          ctx.lineWidth = 2;
          ctx.stroke();

          // Draw P&L value label
          const labelText = `${pnlAtSpot >= 0 ? '+' : ''}$${pnlAtSpot.toFixed(0)}`;
          ctx.font = 'bold 11px monospace';
          const metrics = ctx.measureText(labelText);
          const labelPadding = 4;
          const labelX = spotX + 10;
          const labelY = pnlY;

          ctx.fillStyle = pnlAtSpot >= 0 ? '#166534' : '#991b1b';
          ctx.beginPath();
          ctx.roundRect(
            labelX - labelPadding,
            labelY - 8,
            metrics.width + labelPadding * 2,
            16,
            3
          );
          ctx.fill();

          ctx.fillStyle = '#fff';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText(labelText, labelX, labelY);
        }
      }
    }

    // Draw legend (bottom-left corner, compact)
    ctx.font = '10px monospace';
    const legendX = PADDING.left + 10;
    const legendY = height - PADDING.bottom - 30;

    ctx.fillStyle = '#3b82f6';
    ctx.fillRect(legendX, legendY, 16, 2);
    ctx.fillStyle = '#666';
    ctx.textAlign = 'left';
    ctx.fillText('At Expiry', legendX + 20, legendY + 3);

    ctx.fillStyle = '#e879f9';
    ctx.fillRect(legendX, legendY + 12, 16, 2);
    ctx.fillStyle = '#666';
    ctx.fillText('Real-Time', legendX + 20, legendY + 15);

  }, [expirationData, theoreticalData, spotPrice, expirationBreakevens, theoreticalBreakevens, strikes, alertLines, toCanvasX, toCanvasY, renderBackdrop]);

  // Calculate nice step size for axis labels
  function calculateNiceStep(range: number, targetSteps: number): number {
    const roughStep = range / targetSteps;
    const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
    const normalized = roughStep / magnitude;

    let niceStep;
    if (normalized <= 1) niceStep = 1;
    else if (normalized <= 2) niceStep = 2;
    else if (normalized <= 5) niceStep = 5;
    else niceStep = 10;

    return niceStep * magnitude;
  }

  // Mouse handlers for pan/zoom
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const height = container.clientHeight;

    // Check if clicking in X-axis zone (bottom area) or Y-axis zone (left area)
    isXAxisDrag.current = mouseY > height - PADDING.bottom;
    isYAxisDrag.current = mouseX < PADDING.left && mouseY < height - PADDING.bottom;

    if (isXAxisDrag.current) {
      setAxisZoomHint('x');
    } else if (isYAxisDrag.current) {
      setAxisZoomHint('y');
    } else {
      setAxisZoomHint(null);
    }

    isDragging.current = true;
    dragStart.current = { x: e.clientX, y: e.clientY };
    viewAtDragStart.current = { ...viewState.current };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging.current || !viewAtDragStart.current || !containerRef.current) return;

    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;
    const chartWidth = width - PADDING.left - PADDING.right;
    const chartHeight = height - PADDING.top - PADDING.bottom;

    const { xMin, xMax, yMin, yMax } = viewAtDragStart.current;
    const xRange = xMax - xMin;
    const yRange = yMax - yMin;

    if (isXAxisDrag.current) {
      // Dragging on X-axis: zoom X
      // Drag right = wider (zoom out), drag left = narrower (zoom in)
      const zoomFactor = 1 - (dx / chartWidth) * 2;
      const xCenter = (xMin + xMax) / 2;
      const newXRange = xRange * zoomFactor;
      viewState.current = {
        ...viewAtDragStart.current,
        xMin: xCenter - newXRange / 2,
        xMax: xCenter + newXRange / 2,
      };
    } else if (isYAxisDrag.current) {
      // Dragging on Y-axis: zoom Y
      // Drag up = taller (expand), drag down = shorter (contract)
      const zoomFactor = 1 + (dy / chartHeight) * 2;
      const yCenter = (yMin + yMax) / 2;
      const newYRange = yRange * zoomFactor;
      viewState.current = {
        ...viewAtDragStart.current,
        yMin: yCenter - newYRange / 2,
        yMax: yCenter + newYRange / 2,
      };
    } else {
      // Normal drag: pan
      const xShift = -(dx / chartWidth) * xRange;
      const yShift = (dy / chartHeight) * yRange;

      viewState.current = {
        xMin: xMin + xShift,
        xMax: xMax + xShift,
        yMin: yMin + yShift,
        yMax: yMax + yShift,
      };
    }

    draw();
  }, [draw]);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    isXAxisDrag.current = false;
    isYAxisDrag.current = false;
    viewAtDragStart.current = null;
    setCursorStyle('grab');
    setAxisZoomHint(null);
  }, []);

  // Context menu handler
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();

    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Only show context menu in chart area
    const inChartArea = mouseX >= PADDING.left && mouseX <= width - PADDING.right &&
                        mouseY >= PADDING.top && mouseY <= height - PADDING.bottom;

    if (inChartArea) {
      const price = toDataX(mouseX, width);
      setContextMenu({ x: e.clientX - rect.left, y: e.clientY - rect.top, price });
      setCrosshair(null);
    }
  }, [toDataX]);

  // Close context menu
  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  // Handle alert creation from context menu - opens dialog
  const handleCreateAlert = useCallback((type: PriceAlertType) => {
    if (contextMenu && onOpenAlertDialog) {
      onOpenAlertDialog(contextMenu.price, type);
    }
    setContextMenu(null);
  }, [contextMenu, onOpenAlertDialog]);

  // Update cursor and crosshair based on mouse position
  const handleMouseHover = useCallback((e: React.MouseEvent) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Check if in chart area for crosshair
    const inChartArea = mouseX >= PADDING.left && mouseX <= width - PADDING.right &&
                        mouseY >= PADDING.top && mouseY <= height - PADDING.bottom;

    if (inChartArea && !isDragging.current) {
      setCrosshair({ x: mouseX, y: mouseY });
    } else {
      setCrosshair(null);
    }

    if (isDragging.current) return;

    // X-axis zone = bottom area
    if (mouseY > height - PADDING.bottom) {
      setCursorStyle('ew-resize');
    // Y-axis zone = left area
    } else if (mouseX < PADDING.left) {
      setCursorStyle('ns-resize');
    } else {
      setCursorStyle('crosshair');
    }
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();

    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const width = container.clientWidth;
    const height = container.clientHeight;

    // Zoom factor
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;

    // Get mouse position in data coordinates
    const dataX = toDataX(mouseX, width);
    const dataY = toDataY(mouseY, height);

    const { xMin, xMax, yMin, yMax } = viewState.current;

    // Zoom around mouse position
    if (e.shiftKey) {
      // Shift+scroll: zoom Y only
      const newYMin = dataY - (dataY - yMin) * zoomFactor;
      const newYMax = dataY + (yMax - dataY) * zoomFactor;
      viewState.current.yMin = newYMin;
      viewState.current.yMax = newYMax;
    } else {
      // Normal scroll: zoom X only
      const newXMin = dataX - (dataX - xMin) * zoomFactor;
      const newXMax = dataX + (xMax - dataX) * zoomFactor;
      viewState.current.xMin = newXMin;
      viewState.current.xMax = newXMax;
    }

    draw();
  }, [draw, toDataX, toDataY]);

  // Auto-fit ONLY when strategies change (strikes array changes), not on price updates
  const strategyHash = strikes.join(',');
  const prevStrategyHash = useRef<string | null>(null);

  useEffect(() => {
    if (strategyHash !== prevStrategyHash.current) {
      autoFit();
      prevStrategyHash.current = strategyHash;
      // Also trigger a delayed autoFit in case container wasn't measured yet
      const timer = setTimeout(() => autoFit(), 50);
      return () => clearTimeout(timer);
    }
  }, [strategyHash, autoFit]);

  // Handle resize - both window and container
  useEffect(() => {
    const handleResize = () => draw();
    window.addEventListener('resize', handleResize);

    // Also observe container resize - call autoFit on first resize to set proper bounds
    const container = containerRef.current;
    let resizeObserver: ResizeObserver | null = null;
    let hasInitialSize = false;
    if (container) {
      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (entry && entry.contentRect.width > 0 && entry.contentRect.height > 0) {
          if (!hasInitialSize) {
            // First time we have valid dimensions - do full autoFit
            hasInitialSize = true;
            autoFit();
          } else {
            draw();
          }
        }
      });
      resizeObserver.observe(container);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
    };
  }, [draw, autoFit]);

  // Initial draw - with a small delay to ensure container is measured
  useEffect(() => {
    autoFit();
    // Redraw after a short delay to ensure layout is complete
    const timer = setTimeout(() => autoFit(), 100);
    return () => clearTimeout(timer);
  }, [autoFit]);

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%', minHeight: '300px', position: 'relative' }}
    >
      {/* Backdrop layer - renders behind the canvas */}
      {renderBackdrop && backdropProps && (
        <div
          style={{
            position: 'absolute',
            top: PADDING.top,
            left: PADDING.left,
            width: backdropProps.width,
            height: backdropProps.height,
            pointerEvents: 'none',
            zIndex: 0,
          }}
        >
          {renderBackdrop(backdropProps)}
        </div>
      )}
      <canvas
        ref={canvasRef}
        style={{ display: 'block', cursor: cursorStyle, position: 'relative', zIndex: 1, background: 'transparent' }}
        onMouseDown={(e) => { handleMouseDown(e); setCursorStyle('grabbing'); closeContextMenu(); }}
        onMouseMove={(e) => { handleMouseMove(e); if (!isDragging.current) handleMouseHover(e); }}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => { handleMouseUp(); setCrosshair(null); }}
        onWheel={handleWheel}
        onContextMenu={handleContextMenu}
      />
      {/* Temporary preview line when context menu is open */}
      {contextMenu && containerRef.current && (
        <div style={{
          position: 'absolute',
          left: contextMenu.x,
          top: PADDING.top,
          width: 2,
          height: containerRef.current.clientHeight - PADDING.top - PADDING.bottom,
          background: 'repeating-linear-gradient(to bottom, #f59e0b 0px, #f59e0b 4px, transparent 4px, transparent 8px)',
          pointerEvents: 'none',
          opacity: 0.8,
        }} />
      )}

      {/* Context Menu */}
      {contextMenu && (
        <div
          style={{
            position: 'absolute',
            left: contextMenu.x,
            top: contextMenu.y,
            background: '#1a1a1a',
            border: '1px solid #333',
            borderRadius: '6px',
            padding: '4px 0',
            minWidth: '180px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            zIndex: 100,
          }}
          onMouseLeave={closeContextMenu}
        >
          <div style={{
            padding: '6px 12px',
            borderBottom: '1px solid #333',
            color: '#888',
            fontSize: '11px',
          }}>
            Alert at {contextMenu.price.toFixed(0)}
          </div>
          <button
            onClick={() => handleCreateAlert('price_above')}
            style={{
              display: 'block',
              width: '100%',
              padding: '8px 12px',
              background: 'transparent',
              border: 'none',
              color: '#fff',
              fontSize: '12px',
              textAlign: 'left',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#2a2a2a'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            🔔 Alert when price rises above
          </button>
          <button
            onClick={() => handleCreateAlert('price_below')}
            style={{
              display: 'block',
              width: '100%',
              padding: '8px 12px',
              background: 'transparent',
              border: 'none',
              color: '#fff',
              fontSize: '12px',
              textAlign: 'left',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#2a2a2a'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            🔔 Alert when price falls below
          </button>
          <button
            onClick={() => handleCreateAlert('price_touch')}
            style={{
              display: 'block',
              width: '100%',
              padding: '8px 12px',
              background: 'transparent',
              border: 'none',
              color: '#fff',
              fontSize: '12px',
              textAlign: 'left',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#2a2a2a'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            🔔 Alert when price touches
          </button>
        </div>
      )}

      {axisZoomHint === 'x' && (
        <div style={{
          position: 'absolute',
          bottom: PADDING.bottom / 2,
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(59, 130, 246, 0.9)',
          color: '#fff',
          padding: '4px 12px',
          borderRadius: '4px',
          fontSize: '12px',
          fontWeight: 'bold',
          pointerEvents: 'none',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          <span>◀ Narrower</span>
          <span style={{ color: 'rgba(255,255,255,0.5)' }}>|</span>
          <span>Wider ▶</span>
        </div>
      )}
      {axisZoomHint === 'y' && (
        <div style={{
          position: 'absolute',
          left: PADDING.left / 2,
          top: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'rgba(59, 130, 246, 0.9)',
          color: '#fff',
          padding: '8px 6px',
          borderRadius: '4px',
          fontSize: '11px',
          fontWeight: 'bold',
          pointerEvents: 'none',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px',
          whiteSpace: 'nowrap',
        }}>
          <span>▲ Taller</span>
          <span style={{ color: 'rgba(255,255,255,0.5)' }}>—</span>
          <span>▼ Shorter</span>
        </div>
      )}
      {crosshair && containerRef.current && (() => {
        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;
        const price = toDataX(crosshair.x, width);

        // Find P&L values from curves at this price
        const findPnLAtPrice = (data: PnLPoint[], targetPrice: number): number | null => {
          if (data.length < 2) return null;
          for (let i = 1; i < data.length; i++) {
            const prev = data[i - 1];
            const curr = data[i];
            if (targetPrice >= prev.price && targetPrice <= curr.price) {
              // Linear interpolation
              const t = (targetPrice - prev.price) / (curr.price - prev.price);
              return prev.pnl + t * (curr.pnl - prev.pnl);
            }
          }
          return null;
        };

        const expirationPnL = findPnLAtPrice(expirationData, price);
        const theoreticalPnL = findPnLAtPrice(theoreticalData, price);

        const expirationY = expirationPnL !== null ? toCanvasY(expirationPnL, height) : null;
        const theoreticalY = theoreticalPnL !== null ? toCanvasY(theoreticalPnL, height) : null;

        return (
          <>
            {/* Vertical line */}
            <div style={{
              position: 'absolute',
              left: crosshair.x,
              top: PADDING.top,
              width: 1,
              height: height - PADDING.top - PADDING.bottom,
              borderLeft: '1px dashed rgba(150, 150, 150, 0.6)',
              pointerEvents: 'none',
            }} />
            {/* Horizontal line at expiration P&L */}
            {expirationY !== null && (
              <div style={{
                position: 'absolute',
                left: PADDING.left,
                top: expirationY,
                width: width - PADDING.left - PADDING.right,
                height: 1,
                borderTop: '1px dashed rgba(59, 130, 246, 0.6)',
                pointerEvents: 'none',
              }} />
            )}
            {/* Horizontal line at theoretical P&L */}
            {theoreticalY !== null && (
              <div style={{
                position: 'absolute',
                left: PADDING.left,
                top: theoreticalY,
                width: width - PADDING.left - PADDING.right,
                height: 1,
                borderTop: '1px dashed rgba(232, 121, 249, 0.6)',
                pointerEvents: 'none',
              }} />
            )}
            {/* X-axis label (price) */}
            <div style={{
              position: 'absolute',
              left: crosshair.x,
              top: height - PADDING.bottom + 2,
              transform: 'translateX(-50%)',
              background: '#3b82f6',
              color: '#fff',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '10px',
              fontWeight: 'bold',
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
            }}>
              {price.toFixed(0)}
            </div>
            {/* Y-axis label - Expiration P&L (blue) */}
            {expirationPnL !== null && expirationY !== null && (
              <div style={{
                position: 'absolute',
                left: 2,
                top: expirationY,
                transform: 'translateY(-50%)',
                background: '#3b82f6',
                color: '#fff',
                padding: '2px 6px',
                borderRadius: '3px',
                fontSize: '10px',
                fontWeight: 'bold',
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                zIndex: 1,
              }}>
                {expirationPnL >= 0 ? '+' : ''}{expirationPnL.toFixed(0)}
              </div>
            )}
            {/* Y-axis label - Theoretical P&L (magenta) - on top */}
            {theoreticalPnL !== null && theoreticalY !== null && (
              <div style={{
                position: 'absolute',
                left: 2,
                top: theoreticalY,
                transform: 'translateY(-50%)',
                background: '#e879f9',
                color: '#fff',
                padding: '2px 6px',
                borderRadius: '3px',
                fontSize: '10px',
                fontWeight: 'bold',
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                zIndex: 2,
              }}>
                {theoreticalPnL >= 0 ? '+' : ''}{theoreticalPnL.toFixed(0)}
              </div>
            )}
          </>
        );
      })()}
    </div>
  );
});

PnLChart.displayName = 'PnLChart';

export default PnLChart;
