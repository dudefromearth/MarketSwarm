/**
 * VP Line Editor - Interactive tool for placing structural lines on volume profile
 *
 * Features:
 * - Display volume profile from Redis
 * - Select ticker (SPX/NDX)
 * - Click to add lines at price levels
 * - Drag lines to adjust position
 * - Mouse wheel to zoom price axis
 * - Click and drag to pan
 * - Save lines to Redis
 * - Load existing lines
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

interface VPData {
  bins: number[];
  min: number;
  max: number;
  step: number;
  symbol: string;
}

interface VolumeLine {
  price: number;
  color: string;
  weight: number;
}

interface Structures {
  volume_nodes: VolumeLine[];
  volume_wells: [number, number][];  // Shaded areas of low volume (anti-nodes)
}

const API_BASE = '/api/dealer-gravity';

const LINE_COLORS = [
  { value: '#ffff00', label: 'Yellow' },
  { value: '#3b82f6', label: 'Blue' },
  { value: '#ef4444', label: 'Red' },
  { value: '#22c55e', label: 'Green' },
];

const LINE_WEIGHTS = [
  { value: 1.5, label: 'Thin' },
  { value: 3.5, label: 'Medium' },
  { value: 5.5, label: 'Thick' },
];

const TICKERS = [
  { value: 'SPX', label: 'SPX (S&P 500)', defaultRange: [5800, 7000] },
  { value: 'NDX', label: 'NDX (Nasdaq 100)', defaultRange: [18000, 22000] },
];

export default function VPLineEditor() {
  // Ticker selection
  const [selectedTicker, setSelectedTicker] = useState('SPX');

  // VP Data
  const [vpData, setVpData] = useState<VPData | null>(null);
  const [structures, setStructures] = useState<Structures>({ volume_nodes: [], volume_wells: [] });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // View state
  const [viewMin, setViewMin] = useState(6000);
  const [viewMax, setViewMax] = useState(7000);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; viewMin: number; viewMax: number } | null>(null);

  // Line dragging - track by INDEX to avoid confusion when prices overlap
  const [draggingLineIndex, setDraggingLineIndex] = useState<number | null>(null);
  const [hoveredLine, setHoveredLine] = useState<number | null>(null);

  // Edit mode - radio button behavior, only one active at a time
  type EditMode = 'pan' | 'addLine' | 'deleteLine' | 'moveLine' | 'addWell' | 'deleteWell';
  const [editMode, setEditMode] = useState<EditMode>('pan');
  const [wellStart, setWellStart] = useState<number | null>(null);

  // Line style settings
  const [lineColor, setLineColor] = useState('#ffff00');
  const [lineWeight, setLineWeight] = useState(1.5);

  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Dimensions - fill most of the screen
  const [dimensions, setDimensions] = useState({ width: 1400, height: 800 });

  useEffect(() => {
    const updateDimensions = () => {
      setDimensions({
        width: Math.min(window.innerWidth - 40, 1800),
        height: Math.min(window.innerHeight - 200, 900),
      });
    };
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  const { width, height } = dimensions;
  const padding = { top: 30, right: 60, bottom: 50, left: 50 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Load data
  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/artifact`);
        const data = await res.json();
        if (data.success && data.data) {
          const { profile, structures: existingStructures } = data.data;
          setVpData({
            bins: profile.bins,
            min: profile.min,
            max: profile.min + profile.bins.length * profile.step,
            step: profile.step,
            symbol: selectedTicker,
          });
          if (existingStructures) {
            // Handle both old format (number[]) and new format (VolumeLine[])
            const rawNodes = existingStructures.volume_nodes || existingStructures.volumeNodes || [];
            const nodes: VolumeLine[] = rawNodes.map((n: number | VolumeLine) => {
              if (typeof n === 'number') {
                return { price: n, color: '#ffff00', weight: 1.5 };
              }
              return n;
            });
            setStructures({
              volume_nodes: nodes,
              volume_wells: existingStructures.volume_wells || [],
            });
          }
          // Set initial view based on ticker
          const ticker = TICKERS.find(t => t.value === selectedTicker);
          if (ticker) {
            setViewMin(ticker.defaultRange[0]);
            setViewMax(ticker.defaultRange[1]);
          }
        }
      } catch (err) {
        console.error('Failed to load VP data:', err);
        setMessage('Failed to load volume profile data');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [selectedTicker]);

  // Price <-> X coordinate conversion
  const priceToX = useCallback((price: number) => {
    return padding.left + ((price - viewMin) / (viewMax - viewMin)) * chartWidth;
  }, [viewMin, viewMax, chartWidth]);

  const xToPrice = useCallback((x: number) => {
    return viewMin + ((x - padding.left) / chartWidth) * (viewMax - viewMin);
  }, [viewMin, viewMax, chartWidth]);

  // Get volume at price
  const getVolumeAtPrice = useCallback((price: number) => {
    if (!vpData) return 0;
    const index = Math.floor((price - vpData.min) / vpData.step);
    if (index < 0 || index >= vpData.bins.length) return 0;
    return vpData.bins[index];
  }, [vpData]);

  // Volume profile bars - rendered from bottom up like the Risk Graph
  const volumeBars = useMemo(() => {
    if (!vpData) return [];
    const bars: { price: number; volume: number; x: number; width: number; height: number }[] = [];

    // Find max volume in view for normalization
    let maxVolInView = 0;
    for (let price = Math.floor(viewMin); price <= Math.ceil(viewMax); price += vpData.step) {
      const vol = getVolumeAtPrice(price);
      if (vol > maxVolInView) maxVolInView = vol;
    }

    for (let price = Math.floor(viewMin); price <= Math.ceil(viewMax); price += vpData.step) {
      const vol = getVolumeAtPrice(price);
      if (vol > 0) {
        const x = priceToX(price);
        const barWidth = Math.max(1, (chartWidth / (viewMax - viewMin)) * vpData.step * 0.9);
        const barHeight = maxVolInView > 0 ? (vol / maxVolInView) * chartHeight : 0;
        bars.push({
          price,
          volume: vol,
          x,
          width: barWidth,
          height: barHeight,
        });
      }
    }
    return bars;
  }, [vpData, viewMin, viewMax, priceToX, getVolumeAtPrice, chartWidth, chartHeight]);

  // Zoom function - used by wheel and buttons
  const zoom = useCallback((zoomIn: boolean, centerPrice?: number) => {
    const center = centerPrice ?? (viewMin + viewMax) / 2;
    const zoomFactor = zoomIn ? 0.8 : 1.25;
    const range = viewMax - viewMin;
    const newRange = Math.max(50, Math.min(5000, range * zoomFactor));

    const centerRatio = (center - viewMin) / range;
    const newMin = center - centerRatio * newRange;
    const newMax = center + (1 - centerRatio) * newRange;

    setViewMin(Math.max(vpData?.min || 2000, newMin));
    setViewMax(Math.min(vpData?.max || 25000, newMax));
  }, [viewMin, viewMax, vpData]);

  // Mouse wheel zoom - attach as native event to bypass passive default
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mousePrice = viewMin + ((mouseX - padding.left) / chartWidth) * (viewMax - viewMin);
      zoom(e.deltaY < 0, mousePrice);
    };

    svg.addEventListener('wheel', handleWheel, { passive: false });
    return () => svg.removeEventListener('wheel', handleWheel);
  }, [zoom, viewMin, viewMax, chartWidth]);

  // Pan handling
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return; // Left click only

    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = e.clientX - rect.left;
    const mousePrice = xToPrice(mouseX);

    const price = Math.round(mousePrice);

    // Find if clicking on a line
    const clickedLineIndex = structures.volume_nodes.findIndex(line => {
      const lineX = priceToX(line.price);
      return Math.abs(mouseX - lineX) < 8;
    });

    // Find if clicking on a well
    const clickedWellIndex = structures.volume_wells.findIndex(([start, end]) =>
      mousePrice >= start && mousePrice <= end
    );

    // Handle edit modes
    switch (editMode) {
      case 'pan':
        // Start panning
        setIsDragging(true);
        setDragStart({ x: e.clientX, viewMin, viewMax });
        return;

      case 'addLine':
        // Don't add if too close to existing line
        if (clickedLineIndex < 0) {
          const newLine: VolumeLine = { price, color: lineColor, weight: lineWeight };
          setStructures(prev => ({
            ...prev,
            volume_nodes: [...prev.volume_nodes, newLine].sort((a, b) => a.price - b.price),
          }));
          setMessage(`Added line at ${price}`);
        }
        return;

      case 'deleteLine':
        if (clickedLineIndex >= 0) {
          const deletedLine = structures.volume_nodes[clickedLineIndex];
          setStructures(prev => ({
            ...prev,
            volume_nodes: prev.volume_nodes.filter((_, i) => i !== clickedLineIndex),
          }));
          setMessage(`Deleted line at ${deletedLine.price}`);
        }
        return;

      case 'moveLine':
        if (clickedLineIndex >= 0) {
          setDraggingLineIndex(clickedLineIndex);
        }
        return;

      case 'addWell':
        if (wellStart === null) {
          setWellStart(price);
          setMessage(`Well start: ${price} - click again to set end`);
        } else {
          const newWell: [number, number] = [Math.min(wellStart, price), Math.max(wellStart, price)];
          setStructures(prev => ({
            ...prev,
            volume_wells: [...prev.volume_wells, newWell],
          }));
          setWellStart(null);
          setMessage(`Added well: ${newWell[0]} - ${newWell[1]}`);
        }
        return;

      case 'deleteWell':
        if (clickedWellIndex >= 0) {
          const [start, end] = structures.volume_wells[clickedWellIndex];
          setStructures(prev => ({
            ...prev,
            volume_wells: prev.volume_wells.filter((_, i) => i !== clickedWellIndex),
          }));
          setMessage(`Deleted well ${start}-${end}`);
        }
        return;

    }
  }, [xToPrice, priceToX, structures.volume_nodes, structures.volume_wells, editMode, wellStart, viewMin, viewMax, lineColor, lineWeight]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = e.clientX - rect.left;
    const mousePrice = xToPrice(mouseX);

    // Update hovered line (store price for comparison)
    const hoveredNode = structures.volume_nodes.find(line => {
      const lineX = priceToX(line.price);
      return Math.abs(mouseX - lineX) < 8;
    });
    setHoveredLine(hoveredNode?.price ?? null);

    // Handle line dragging - update by index, preserve color/weight
    if (draggingLineIndex !== null) {
      const newPrice = Math.round(mousePrice);
      setStructures(prev => ({
        ...prev,
        volume_nodes: prev.volume_nodes.map((line, i) =>
          i === draggingLineIndex ? { ...line, price: newPrice } : line
        ),
      }));
      // Don't update draggingLineIndex - it stays the same throughout the drag
      return;
    }

    // Handle panning
    if (isDragging && dragStart) {
      const dx = e.clientX - dragStart.x;
      const pricePerPixel = (dragStart.viewMax - dragStart.viewMin) / chartWidth;
      const priceDelta = -dx * pricePerPixel;

      const newMin = dragStart.viewMin + priceDelta;
      const newMax = dragStart.viewMax + priceDelta;

      if (newMin >= (vpData?.min || 2000) && newMax <= (vpData?.max || 25000)) {
        setViewMin(newMin);
        setViewMax(newMax);
      }
    }
  }, [isDragging, dragStart, draggingLineIndex, xToPrice, priceToX, chartWidth, vpData, structures.volume_nodes]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
    setDragStart(null);
    setDraggingLineIndex(null);
  }, []);

  // Right-click to return to pan mode
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    if (editMode !== 'pan') {
      setEditMode('pan');
      setWellStart(null);
      setMessage('Back to pan mode');
    }
  }, [editMode]);

  // Save to Redis
  const handleSave = useCallback(async () => {
    setSaving(true);
    setMessage('Saving...');

    try {
      const saveRes = await fetch(`${API_BASE}/structures`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          volume_nodes: structures.volume_nodes,
          volume_wells: structures.volume_wells,
          symbol: selectedTicker,
        }),
      });

      const result = await saveRes.json();

      if (result.success) {
        setMessage(`Saved ${structures.volume_nodes.length} lines and ${structures.volume_wells.length} wells to Redis`);
      } else {
        setMessage(`Save failed: ${result.error}`);
      }
    } catch (err) {
      console.error('Save failed:', err);
      setMessage('Save failed - check console');
    } finally {
      setSaving(false);
    }
  }, [structures, selectedTicker]);

  // Copy structures as JSON
  const handleCopy = useCallback(() => {
    const json = JSON.stringify(structures, null, 2);
    navigator.clipboard.writeText(json);
    setMessage('Copied structures JSON to clipboard');
  }, [structures]);

  // Clear all
  const handleClear = useCallback(() => {
    if (confirm('Clear all lines and wells?')) {
      setStructures({ volume_nodes: [], volume_wells: [] });
      setMessage('Cleared all structures');
    }
  }, []);

  // Reset view
  const handleResetView = useCallback(() => {
    const ticker = TICKERS.find(t => t.value === selectedTicker);
    if (ticker) {
      setViewMin(ticker.defaultRange[0]);
      setViewMax(ticker.defaultRange[1]);
    }
  }, [selectedTicker]);

  if (loading) {
    return (
      <div style={{
        padding: 40,
        color: '#e2e8f0',
        background: '#0a0a12',
        minHeight: '100vh',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}>
        Loading volume profile...
      </div>
    );
  }

  return (
    <div style={{
      padding: 20,
      color: '#e2e8f0',
      background: '#0a0a12',
      minHeight: '100vh',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 15 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>VP Line Editor</h1>

        {/* Ticker selector */}
        <select
          value={selectedTicker}
          onChange={(e) => setSelectedTicker(e.target.value)}
          style={{
            padding: '8px 12px',
            background: '#1e1e2e',
            color: '#e2e8f0',
            border: '1px solid #333',
            borderRadius: 4,
            fontSize: 14,
          }}
        >
          {TICKERS.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* Toolbar */}
      <div style={{ marginBottom: 15, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '8px 16px',
            background: '#22c55e',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: saving ? 'wait' : 'pointer',
            fontWeight: 'bold',
          }}
        >
          {saving ? 'Saving...' : 'Save to Redis'}
        </button>

        <button
          onClick={handleCopy}
          style={{
            padding: '8px 16px',
            background: '#3b82f6',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          Copy JSON
        </button>

        {/* Edit mode radio buttons */}
        <div style={{
          display: 'flex',
          gap: 2,
          background: '#1e1e2e',
          padding: 3,
          borderRadius: 6,
          border: '1px solid #333'
        }}>
          {[
            { mode: 'pan' as const, label: 'Pan', color: '#6b7280' },
            { mode: 'addLine' as const, label: '+ Line', color: '#22c55e' },
            { mode: 'deleteLine' as const, label: '− Line', color: '#ef4444' },
            { mode: 'moveLine' as const, label: '↔ Line', color: '#3b82f6' },
            { mode: 'addWell' as const, label: '+ Well', color: '#9333ea' },
            { mode: 'deleteWell' as const, label: '− Well', color: '#ef4444' },
          ].map(({ mode, label, color }) => (
            <button
              key={mode}
              onClick={() => {
                setEditMode(mode);
                setWellStart(null);
                if (mode === 'pan') {
                  setMessage('Pan mode - drag to scroll');
                } else {
                  const action = mode.startsWith('add') ? 'add' : mode.startsWith('delete') ? 'delete' : 'drag';
                  setMessage(`${label} mode - click to ${action}`);
                }
              }}
              style={{
                padding: '6px 12px',
                background: editMode === mode ? color : 'transparent',
                color: editMode === mode ? '#fff' : '#9ca3af',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: editMode === mode ? 'bold' : 'normal',
                transition: 'all 0.15s ease',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Line Color selector */}
        <div style={{
          display: 'flex',
          gap: 2,
          background: '#1e1e2e',
          padding: 3,
          borderRadius: 6,
          border: '1px solid #333',
          alignItems: 'center',
        }}>
          <span style={{ color: '#6b7280', fontSize: 11, padding: '0 4px' }}>Color:</span>
          {LINE_COLORS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setLineColor(value)}
              style={{
                width: 24,
                height: 24,
                background: value,
                border: lineColor === value ? '2px solid #fff' : '2px solid transparent',
                borderRadius: 4,
                cursor: 'pointer',
                opacity: lineColor === value ? 1 : 0.6,
              }}
              title={label}
            />
          ))}
        </div>

        {/* Line Weight selector */}
        <div style={{
          display: 'flex',
          gap: 2,
          background: '#1e1e2e',
          padding: 3,
          borderRadius: 6,
          border: '1px solid #333',
          alignItems: 'center',
        }}>
          <span style={{ color: '#6b7280', fontSize: 11, padding: '0 4px' }}>Weight:</span>
          {LINE_WEIGHTS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setLineWeight(value)}
              style={{
                padding: '4px 8px',
                background: lineWeight === value ? '#3b82f6' : 'transparent',
                color: lineWeight === value ? '#fff' : '#9ca3af',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 11,
              }}
              title={`${value}px`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Zoom controls */}
        <div style={{
          display: 'flex',
          gap: 2,
          background: '#1e1e2e',
          padding: 3,
          borderRadius: 6,
          border: '1px solid #333'
        }}>
          <button
            onClick={() => zoom(true)}
            style={{
              padding: '6px 12px',
              background: 'transparent',
              color: '#9ca3af',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 15,
              fontWeight: 'bold',
            }}
            title="Zoom In (expand price range detail)"
          >
            +
          </button>
          <button
            onClick={() => zoom(false)}
            style={{
              padding: '6px 12px',
              background: 'transparent',
              color: '#9ca3af',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 15,
              fontWeight: 'bold',
            }}
            title="Zoom Out (compress to see more range)"
          >
            −
          </button>
          <button
            onClick={handleResetView}
            style={{
              padding: '6px 12px',
              background: 'transparent',
              color: '#9ca3af',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 13,
            }}
            title="Reset to default view"
          >
            Reset
          </button>
        </div>

        <button
          onClick={handleClear}
          style={{
            padding: '8px 16px',
            background: '#374151',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          Clear All
        </button>

        <span style={{ color: '#9ca3af', marginLeft: 20 }}>
          Lines: <strong>{structures.volume_nodes.length}</strong> | Wells: <strong>{structures.volume_wells.length}</strong>
        </span>

        <span style={{ color: '#6b7280' }}>
          View: {Math.round(viewMin)} - {Math.round(viewMax)}
        </span>
      </div>

      {/* Message */}
      {message && (
        <div style={{ marginBottom: 10, padding: '8px 12px', background: '#1e1e2e', borderRadius: 4, color: '#facc15' }}>
          {message}
        </div>
      )}

      {/* Instructions */}
      <div style={{ marginBottom: 15, color: '#6b7280', fontSize: 13 }}>
        <strong>Controls:</strong> Select mode, then click to add/delete |
        Drag lines to move | +/− or scroll to zoom | Drag to pan | Right-click cancels mode
      </div>

      {/* Chart */}
      <div
        ref={containerRef}
        style={{
          border: '1px solid #1e1e2e',
          borderRadius: 4,
          background: '#0f0f1a',
          cursor: isDragging ? 'grabbing'
            : draggingLineIndex !== null ? 'ew-resize'
            : editMode === 'moveLine' && hoveredLine !== null ? 'ew-resize'
            : editMode === 'pan' ? 'grab'
            : 'crosshair',
        }}
      >
        <svg
          ref={svgRef}
          width={width}
          height={height}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onContextMenu={handleContextMenu}
        >
          {/* Background */}
          <rect x={0} y={0} width={width} height={height} fill="#0f0f1a" />

          {/* Grid lines */}
          <g opacity={0.1}>
            {Array.from({ length: 5 }, (_, i) => {
              const y = padding.top + (i / 4) * chartHeight;
              return <line key={`h-${i}`} x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#fff" />;
            })}
            {Array.from({ length: 11 }, (_, i) => {
              const x = padding.left + (i / 10) * chartWidth;
              return <line key={`v-${i}`} x1={x} y1={padding.top} x2={x} y2={height - padding.bottom} stroke="#fff" />;
            })}
          </g>

          {/* Chart area */}
          <g transform={`translate(0, ${padding.top})`}>
            {/* Volume bars - from bottom */}
            {volumeBars.map((bar, i) => (
              <rect
                key={i}
                x={bar.x - bar.width / 2}
                y={chartHeight - bar.height}
                width={bar.width}
                height={bar.height}
                fill="#3b82f6"
                opacity={0.8}
              />
            ))}

            {/* Wells */}
            {structures.volume_wells.map(([start, end], i) => {
              const x1 = priceToX(start);
              const x2 = priceToX(end);
              return (
                <rect
                  key={`well-${i}`}
                  x={Math.min(x1, x2)}
                  y={0}
                  width={Math.abs(x2 - x1)}
                  height={chartHeight}
                  fill="#ef4444"
                  opacity={0.2}
                />
              );
            })}

            {/* Volume node lines */}
            {structures.volume_nodes.map((line, index) => {
              const x = priceToX(line.price);
              const isHovered = hoveredLine === line.price || draggingLineIndex === index;
              return (
                <g key={`line-${index}`}>
                  <line
                    x1={x}
                    y1={0}
                    x2={x}
                    y2={chartHeight}
                    stroke={isHovered ? '#fff' : line.color}
                    strokeWidth={isHovered ? line.weight + 1 : line.weight}
                  />
                  {/* Price label */}
                  <text
                    x={x}
                    y={chartHeight + 15}
                    fill={isHovered ? line.color : '#6b7280'}
                    fontSize={10}
                    textAnchor="middle"
                    style={{ display: isHovered ? 'block' : 'none' }}
                  >
                    {line.price}
                  </text>
                </g>
              );
            })}

            {/* Well start marker */}
            {wellStart !== null && (
              <line
                x1={priceToX(wellStart)}
                y1={0}
                x2={priceToX(wellStart)}
                y2={chartHeight}
                stroke="#ef4444"
                strokeWidth={2}
                strokeDasharray="4,4"
              />
            )}
          </g>

          {/* X-axis (price) */}
          <g transform={`translate(0, ${height - padding.bottom + 5})`}>
            {Array.from({ length: 11 }, (_, i) => {
              const price = viewMin + (i / 10) * (viewMax - viewMin);
              const x = priceToX(price);
              return (
                <g key={i}>
                  <line x1={x} y1={-5} x2={x} y2={0} stroke="#444" />
                  <text x={x} y={15} fill="#9ca3af" fontSize={11} textAnchor="middle">
                    {Math.round(price)}
                  </text>
                </g>
              );
            })}
          </g>

          {/* Y-axis label */}
          <text
            x={15}
            y={height / 2}
            fill="#6b7280"
            fontSize={12}
            transform={`rotate(-90, 15, ${height / 2})`}
            textAnchor="middle"
          >
            Volume
          </text>

          {/* Current price indicator */}
          {hoveredLine && (
            <text
              x={width - padding.right + 5}
              y={padding.top + 20}
              fill="#ffff00"
              fontSize={14}
              fontWeight="bold"
            >
              {hoveredLine}
            </text>
          )}
        </svg>
      </div>

      {/* Summary */}
      <div style={{ marginTop: 20, padding: 15, background: '#1e1e2e', borderRadius: 4 }}>
        <div style={{ marginBottom: 10 }}>
          <strong>Lines ({structures.volume_nodes.length}):</strong>{' '}
          <span style={{ fontSize: 13 }}>
            {structures.volume_nodes.length > 0
              ? structures.volume_nodes.map(line => (
                  <span key={line.price} style={{ color: line.color, marginRight: 8 }}>
                    {line.price}
                  </span>
                ))
              : <span style={{ color: '#9ca3af' }}>None - select + Line mode and click to add</span>}
          </span>
        </div>

        {structures.volume_wells.length > 0 && (
          <div>
            <strong>Wells ({structures.volume_wells.length}):</strong>{' '}
            <span style={{ color: '#9ca3af', fontSize: 13 }}>
              {structures.volume_wells.map(([s, e]) => `${s}-${e}`).join(', ')}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
