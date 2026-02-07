/**
 * PositionCreateModal - Create new positions manually or from imported scripts
 *
 * Features:
 * - Build mode: Select position type and configure legs
 * - Import mode: Paste scripts from ToS, Tradier, etc.
 * - Auto-detection of script format
 * - Preview before adding to Risk Graph
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useDraggable } from '../hooks/useDraggable';
import type { PositionLeg, PositionType, CostBasisType } from '../types/riskGraph';
import { POSITION_TYPE_LABELS } from '../types/riskGraph';
import { recognizePositionType } from '../utils/positionRecognition';
import { formatLegsDisplay, formatPositionLabel } from '../utils/positionFormatting';
import StrikeDropdown from './StrikeDropdown';
import {
  parseScript,
  detectScriptFormat,
  getExampleScripts,
  SCRIPT_FORMAT_NAMES,
  type ParsedPosition,
  type ScriptFormat,
} from '../utils/scriptParsers';

const JOURNAL_API = '';

interface AvailableSymbol {
  symbol: string;
  name: string;
  enabled: boolean;
}

// Output format for created position
export interface CreatedPosition {
  symbol: string;
  legs: PositionLeg[];
  costBasis: number | null;
  costBasisType: CostBasisType;
  expiration: string;
  dte: number;
}

interface PositionCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (position: CreatedPosition) => void;
  defaultSymbol?: string;
  atmStrike?: number;  // Current ATM strike price
}

type CreateMode = 'build' | 'import';
type Direction = 'long' | 'short';

// Position type categories for organized dropdown
const POSITION_TYPE_CATEGORIES: { label: string; types: PositionType[] }[] = [
  { label: 'Basic', types: ['single', 'vertical'] },
  { label: 'Spreads', types: ['butterfly', 'bwb', 'condor'] },
  { label: 'Volatility', types: ['straddle', 'strangle', 'iron_fly', 'iron_condor'] },
  { label: 'Time', types: ['calendar', 'diagonal'] },
];

// Types that default to short (iron structures and naked premium sellers)
const SHORT_DEFAULT_TYPES: PositionType[] = [
  'iron_fly',
  'iron_condor',
  'straddle',
  'strangle',
];

// Mini risk graph SVG paths for each position type (normalized 0-24 width, 0-12 height)
// These represent the general P&L shape at expiration
const MINI_RISK_GRAPHS: Record<PositionType, { path: string; color: string }> = {
  single: {
    // Long call: flat then diagonal up
    path: 'M0,10 L12,10 L24,2',
    color: '#22c55e',
  },
  vertical: {
    // Debit spread: flat, diagonal, flat
    path: 'M0,10 L6,10 L12,4 L18,4 L24,4',
    color: '#22c55e',
  },
  butterfly: {
    // Butterfly: V shape with wings capped
    path: 'M0,8 L6,8 L12,2 L18,8 L24,8',
    color: '#3b82f6',
  },
  bwb: {
    // BWB: Asymmetric butterfly
    path: 'M0,8 L5,8 L12,2 L20,9 L24,9',
    color: '#8b5cf6',
  },
  condor: {
    // Condor: Flat top tent
    path: 'M0,8 L4,8 L8,3 L16,3 L20,8 L24,8',
    color: '#3b82f6',
  },
  straddle: {
    // Straddle: V shape
    path: 'M0,2 L12,10 L24,2',
    color: '#f59e0b',
  },
  strangle: {
    // Strangle: Wide V shape
    path: 'M0,2 L6,8 L18,8 L24,2',
    color: '#f59e0b',
  },
  iron_fly: {
    // Iron fly: Inverted tent
    path: 'M0,4 L6,4 L12,10 L18,4 L24,4',
    color: '#ef4444',
  },
  iron_condor: {
    // Iron condor: Flat bottom tent
    path: 'M0,4 L4,4 L8,9 L16,9 L20,4 L24,4',
    color: '#ef4444',
  },
  calendar: {
    // Calendar: Tent top with convex sides, single peak
    path: 'M0,10 Q2,4 12,2 Q22,4 24,10',
    color: '#06b6d4',
  },
  diagonal: {
    // Diagonal: Tent top with convex sides, two peaks
    path: 'M0,10 Q2,4 8,3 Q12,5 16,3 Q22,4 24,10',
    color: '#06b6d4',
  },
  custom: {
    path: 'M0,6 L24,6',
    color: '#6b7280',
  },
};

// Get default direction for a position type
function getDefaultDirection(type: PositionType): Direction {
  return SHORT_DEFAULT_TYPES.includes(type) ? 'short' : 'long';
}

// Default leg configurations for each position type
// Direction flips all quantities (long -> short inverts signs)
function getDefaultLegs(
  positionType: PositionType,
  baseStrike: number,
  width: number,
  expiration: string,
  right: 'call' | 'put',
  direction: Direction
): PositionLeg[] {
  // Direction multiplier: 1 for long, -1 for short
  const d = direction === 'long' ? 1 : -1;

  switch (positionType) {
    case 'single':
      return [{ strike: baseStrike, expiration, right, quantity: 1 * d }];

    case 'vertical':
      return right === 'call'
        ? [
            { strike: baseStrike, expiration, right: 'call', quantity: 1 * d },
            { strike: baseStrike + width, expiration, right: 'call', quantity: -1 * d },
          ]
        : [
            { strike: baseStrike - width, expiration, right: 'put', quantity: -1 * d },
            { strike: baseStrike, expiration, right: 'put', quantity: 1 * d },
          ];

    case 'butterfly':
    case 'bwb':
      return [
        { strike: baseStrike - width, expiration, right, quantity: 1 * d },
        { strike: baseStrike, expiration, right, quantity: -2 * d },
        { strike: baseStrike + width, expiration, right, quantity: 1 * d },
      ];

    case 'condor':
      return [
        { strike: baseStrike - width * 1.5, expiration, right, quantity: 1 * d },
        { strike: baseStrike - width * 0.5, expiration, right, quantity: -1 * d },
        { strike: baseStrike + width * 0.5, expiration, right, quantity: -1 * d },
        { strike: baseStrike + width * 1.5, expiration, right, quantity: 1 * d },
      ];

    case 'straddle':
      return [
        { strike: baseStrike, expiration, right: 'call', quantity: 1 * d },
        { strike: baseStrike, expiration, right: 'put', quantity: 1 * d },
      ];

    case 'strangle':
      return [
        { strike: baseStrike - width, expiration, right: 'put', quantity: 1 * d },
        { strike: baseStrike + width, expiration, right: 'call', quantity: 1 * d },
      ];

    case 'iron_fly':
      // Iron fly: short the ATM straddle, long the wings
      // Short iron fly = credit received (typical)
      return [
        { strike: baseStrike - width, expiration, right: 'put', quantity: 1 * d },
        { strike: baseStrike, expiration, right: 'put', quantity: -1 * d },
        { strike: baseStrike, expiration, right: 'call', quantity: -1 * d },
        { strike: baseStrike + width, expiration, right: 'call', quantity: 1 * d },
      ];

    case 'iron_condor':
      // Iron condor: short the inner strikes, long the outer wings
      return [
        { strike: baseStrike - width * 1.5, expiration, right: 'put', quantity: 1 * d },
        { strike: baseStrike - width * 0.5, expiration, right: 'put', quantity: -1 * d },
        { strike: baseStrike + width * 0.5, expiration, right: 'call', quantity: -1 * d },
        { strike: baseStrike + width * 1.5, expiration, right: 'call', quantity: 1 * d },
      ];

    case 'calendar':
    case 'diagonal':
      // For time spreads: sell near, buy far
      return [
        { strike: baseStrike, expiration, right, quantity: -1 * d },
        { strike: baseStrike, expiration, right, quantity: 1 * d },
      ];

    default:
      return [{ strike: baseStrike, expiration, right, quantity: 1 * d }];
  }
}

export default function PositionCreateModal({
  isOpen,
  onClose,
  onCreate,
  defaultSymbol = 'SPX',
  atmStrike = 5900,
}: PositionCreateModalProps) {
  const [availableSymbols, setAvailableSymbols] = useState<AvailableSymbol[]>([]);
  const [mode, setMode] = useState<CreateMode>('build');

  // Draggable modal
  const { dragHandleProps, containerStyle, isDragging } = useDraggable({
    handleSelector: '.position-create-header',
    initialCentered: true,
  });

  // Round ATM to nearest 5 for cleaner strikes
  const roundedAtm = Math.round(atmStrike / 5) * 5;

  // Build mode state
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [positionType, setPositionType] = useState<PositionType>('butterfly');
  const [direction, setDirection] = useState<Direction>('long');
  const [legs, setLegs] = useState<PositionLeg[]>([]);
  const [costBasis, setCostBasis] = useState('');
  const [costBasisType, setCostBasisType] = useState<CostBasisType>('debit');
  const [baseStrike, setBaseStrike] = useState(roundedAtm.toString());
  const [width, setWidth] = useState('20');
  const [expiration, setExpiration] = useState('');
  const [primaryRight, setPrimaryRight] = useState<'call' | 'put'>('call');

  // Vega warning for short calendars/diagonals
  const [showVegaWarning, setShowVegaWarning] = useState(false);
  const [pendingShortType, setPendingShortType] = useState<PositionType | null>(null);

  // Types that need vega warning when going short
  const VEGA_SENSITIVE_TYPES: PositionType[] = ['calendar', 'diagonal'];

  // Update direction when position type changes
  const handlePositionTypeChange = useCallback((newType: PositionType) => {
    setPositionType(newType);
    setDirection(getDefaultDirection(newType));
  }, []);

  // Handle direction change with vega warning check
  const handleDirectionChange = useCallback((newDirection: Direction) => {
    if (newDirection === 'short' && VEGA_SENSITIVE_TYPES.includes(positionType)) {
      setPendingShortType(positionType);
      setShowVegaWarning(true);
    } else {
      setDirection(newDirection);
    }
  }, [positionType]);

  // Confirm short calendar/diagonal despite vega warning
  const confirmShortVega = useCallback(() => {
    setDirection('short');
    setShowVegaWarning(false);
    setPendingShortType(null);
  }, []);

  // Cancel short calendar/diagonal
  const cancelShortVega = useCallback(() => {
    setShowVegaWarning(false);
    setPendingShortType(null);
  }, []);

  // Import mode state
  const [scriptInput, setScriptInput] = useState('');
  const [parsedPosition, setParsedPosition] = useState<ParsedPosition | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [detectedFormat, setDetectedFormat] = useState<ScriptFormat>('unknown');

  // Fetch available symbols
  useEffect(() => {
    if (isOpen) {
      fetch(`${JOURNAL_API}/api/symbols`, { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data) {
            const enabled = data.data.filter((s: AvailableSymbol) => s.enabled);
            setAvailableSymbols(enabled);
          }
        })
        .catch(err => console.error('Failed to fetch symbols:', err));

      // Set default expiration to next Friday
      const today = new Date();
      const daysUntilFriday = (5 - today.getDay() + 7) % 7 || 7;
      const nextFriday = new Date(today);
      nextFriday.setDate(today.getDate() + daysUntilFriday);
      setExpiration(nextFriday.toISOString().split('T')[0]);

      // Set base strike to ATM
      setBaseStrike(roundedAtm.toString());
    }
  }, [isOpen, roundedAtm]);

  // Generate legs when build parameters change
  useEffect(() => {
    if (mode === 'build' && expiration) {
      const strike = parseFloat(baseStrike) || 5900;
      const w = parseFloat(width) || 20;
      const newLegs = getDefaultLegs(positionType, strike, w, expiration, primaryRight, direction);
      setLegs(newLegs);
    }
  }, [mode, positionType, baseStrike, width, expiration, primaryRight, direction]);

  // Parse script when input changes
  useEffect(() => {
    if (mode === 'import' && scriptInput.trim()) {
      const detection = detectScriptFormat(scriptInput);
      setDetectedFormat(detection.format);

      const result = parseScript(scriptInput);
      if (result) {
        setParsedPosition(result);
        setParseError(null);
        setSymbol(result.symbol);
        if (result.costBasis !== undefined) {
          setCostBasis(result.costBasis.toString());
        }
        if (result.costBasisType) {
          setCostBasisType(result.costBasisType);
        }
      } else {
        setParsedPosition(null);
        setParseError('Could not parse script. Check format and try again.');
      }
    } else {
      setParsedPosition(null);
      setParseError(null);
      setDetectedFormat('unknown');
    }
  }, [mode, scriptInput]);

  // Current legs (from build or import)
  const currentLegs = mode === 'import' && parsedPosition ? parsedPosition.legs : legs;

  // Recognize position type
  const recognition = useMemo(() => {
    if (currentLegs.length === 0) {
      return { type: 'custom' as PositionType, direction: 'long' as const };
    }
    return recognizePositionType(currentLegs);
  }, [currentLegs]);

  // Format display
  const positionLabel = useMemo(() => {
    return formatPositionLabel(recognition.type, recognition.direction, currentLegs);
  }, [recognition, currentLegs]);

  const legsNotation = useMemo(() => {
    return formatLegsDisplay(currentLegs);
  }, [currentLegs]);

  // Calculate DTE
  const dte = useMemo(() => {
    if (currentLegs.length === 0) return 0;
    const expirations = currentLegs.map(l => l.expiration);
    expirations.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
    const primaryExp = expirations[0];
    if (!primaryExp) return 0;
    const expDate = new Date(primaryExp + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffTime = expDate.getTime() - today.getTime();
    return Math.max(0, Math.ceil(diffTime / (1000 * 60 * 60 * 24)));
  }, [currentLegs]);

  // Update a specific leg
  const updateLeg = useCallback((index: number, updates: Partial<PositionLeg>) => {
    setLegs(prev => {
      const newLegs = [...prev];
      newLegs[index] = { ...newLegs[index], ...updates };
      return newLegs;
    });
  }, []);

  const handleClose = useCallback(() => {
    // Reset state
    setMode('build');
    setScriptInput('');
    setParsedPosition(null);
    setParseError(null);
    onClose();
  }, [onClose]);

  const handleCreate = useCallback(() => {
    if (currentLegs.length === 0) return;

    const costBasisNum = costBasis ? parseFloat(costBasis) : null;

    // Get primary expiration
    const expirations = currentLegs.map(l => l.expiration);
    expirations.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
    const primaryExpiration = expirations[0];

    onCreate({
      symbol,
      legs: currentLegs,
      costBasis: costBasisNum,
      costBasisType,
      expiration: primaryExpiration,
      dte,
    });

    handleClose();
  }, [symbol, currentLegs, costBasis, costBasisType, dte, onCreate, handleClose]);

  const handlePasteFromClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      setScriptInput(text);
    } catch (err) {
      console.error('Failed to read clipboard:', err);
    }
  }, []);

  const isValid = () => {
    if (currentLegs.length === 0) return false;
    return currentLegs.every(leg => leg.strike > 0 && leg.expiration);
  };

  if (!isOpen) return null;

  return (
    <div className="position-create-overlay" onClick={handleClose}>
      <div
        className={`position-create-modal floating-modal ${isDragging ? 'is-dragging' : ''}`}
        onClick={e => e.stopPropagation()}
        ref={dragHandleProps.ref}
        onMouseDown={dragHandleProps.onMouseDown}
        style={containerStyle}
      >
        <div className="position-create-header draggable-handle">
          <h3>Create Position</h3>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        {/* Mode Tabs */}
        <div className="position-create-tabs">
          <button
            className={`tab-btn ${mode === 'build' ? 'active' : ''}`}
            onClick={() => setMode('build')}
          >
            Build
          </button>
          <button
            className={`tab-btn ${mode === 'import' ? 'active' : ''}`}
            onClick={() => setMode('import')}
          >
            Import Script
          </button>
        </div>

        <div className="position-create-body">
          {mode === 'build' ? (
            <>
              {/* Symbol Selection */}
              <div className="form-group">
                <label>Symbol</label>
                <select
                  value={symbol}
                  onChange={e => setSymbol(e.target.value)}
                  className="symbol-select"
                >
                  {symbol && !availableSymbols.find(s => s.symbol === symbol) && (
                    <option value={symbol}>{symbol}</option>
                  )}
                  {availableSymbols.map(s => (
                    <option key={s.symbol} value={s.symbol}>
                      {s.symbol} - {s.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Position Type Selection */}
              <div className="form-group position-type-row">
                <label>Type</label>
                <select
                  className="position-type-select"
                  value={positionType}
                  onChange={e => handlePositionTypeChange(e.target.value as PositionType)}
                >
                  {POSITION_TYPE_CATEGORIES.map(category => (
                    <optgroup key={category.label} label={category.label}>
                      {category.types.map(type => (
                        <option key={type} value={type}>
                          {POSITION_TYPE_LABELS[type]}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                <div className="position-type-display">
                  <svg
                    className={`mini-risk-graph ${direction === 'short' ? 'flipped' : ''}`}
                    viewBox="0 0 24 12"
                    width="48"
                    height="24"
                  >
                    <path
                      d={MINI_RISK_GRAPHS[positionType]?.path || MINI_RISK_GRAPHS.custom.path}
                      stroke={MINI_RISK_GRAPHS[positionType]?.color || MINI_RISK_GRAPHS.custom.color}
                      strokeWidth="1.5"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <div className="direction-toggle">
                    <button
                      type="button"
                      className={`direction-btn long ${direction === 'long' ? 'active' : ''}`}
                      onClick={() => handleDirectionChange('long')}
                    >
                      L
                    </button>
                    <button
                      type="button"
                      className={`direction-btn short ${direction === 'short' ? 'active' : ''}`}
                      onClick={() => handleDirectionChange('short')}
                    >
                      S
                    </button>
                  </div>
                  <span className="selected-type-label">
                    {direction === 'long' ? 'Long' : 'Short'} {POSITION_TYPE_LABELS[positionType]}
                  </span>
                </div>
              </div>

              {/* Quick Setup (Strike, Width, Expiration) */}
              <div className="form-group">
                <label>Quick Setup</label>
                <div className="quick-setup-row">
                  <div className="setup-field">
                    <span className="field-label">Strike</span>
                    <input
                      type="number"
                      value={baseStrike}
                      onChange={e => setBaseStrike(e.target.value)}
                      step="5"
                    />
                  </div>
                  <div className="setup-field">
                    <span className="field-label">Width</span>
                    <input
                      type="number"
                      value={width}
                      onChange={e => setWidth(e.target.value)}
                      step="5"
                    />
                  </div>
                  <div className="setup-field">
                    <span className="field-label">Exp</span>
                    <input
                      type="date"
                      value={expiration}
                      onChange={e => setExpiration(e.target.value)}
                    />
                  </div>
                  <div className="setup-field">
                    <span className="field-label">Side</span>
                    <div className="side-toggle">
                      <button
                        className={`side-btn call ${primaryRight === 'call' ? 'active' : ''}`}
                        onClick={() => setPrimaryRight('call')}
                      >
                        Call
                      </button>
                      <button
                        className={`side-btn put ${primaryRight === 'put' ? 'active' : ''}`}
                        onClick={() => setPrimaryRight('put')}
                      >
                        Put
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Legs Editor (Fine-tune) */}
              <div className="form-group legs-editor">
                <label>Legs <span className="hint">(fine-tune)</span></label>
                <div className="legs-list compact">
                  {legs.map((leg, index) => (
                    <div key={index} className="leg-row compact">
                      <select
                        className="leg-quantity"
                        value={leg.quantity}
                        onChange={e => updateLeg(index, { quantity: parseInt(e.target.value) })}
                      >
                        <option value="2">+2</option>
                        <option value="1">+1</option>
                        <option value="-1">-1</option>
                        <option value="-2">-2</option>
                      </select>
                      <StrikeDropdown
                        value={leg.strike}
                        onChange={strike => updateLeg(index, { strike })}
                        atmStrike={parseFloat(baseStrike) || 5900}
                        minStrike={4000}
                        maxStrike={7000}
                        strikeStep={5}
                        className="leg-strike-dropdown"
                      />
                      <select
                        className="leg-right"
                        value={leg.right}
                        onChange={e => updateLeg(index, { right: e.target.value as 'call' | 'put' })}
                      >
                        <option value="call">C</option>
                        <option value="put">P</option>
                      </select>
                      <input
                        type="date"
                        className="leg-expiration"
                        value={leg.expiration}
                        onChange={e => updateLeg(index, { expiration: e.target.value })}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Import Mode */}
              <div className="form-group">
                <label>
                  Paste Strategy Script
                  <button className="btn-paste" onClick={handlePasteFromClipboard}>
                    Paste from Clipboard
                  </button>
                </label>
                <textarea
                  className="script-input"
                  value={scriptInput}
                  onChange={e => setScriptInput(e.target.value)}
                  placeholder="BUY +1 BUTTERFLY SPX 100 17 JAN 25 5880/5900/5920 CALL @1.20"
                  rows={3}
                />
              </div>

              {/* Format Detection */}
              {scriptInput.trim() && (
                <div className="format-detection">
                  <span className="format-label">Detected Format:</span>
                  <span className={`format-value ${detectedFormat}`}>
                    {SCRIPT_FORMAT_NAMES[detectedFormat]}
                  </span>
                </div>
              )}

              {/* Parse Error */}
              {parseError && (
                <div className="parse-error">
                  {parseError}
                </div>
              )}

              {/* Parse Warnings */}
              {parsedPosition?.warnings && parsedPosition.warnings.length > 0 && (
                <div className="parse-warnings">
                  {parsedPosition.warnings.map((w, i) => (
                    <div key={i} className="warning">{w}</div>
                  ))}
                </div>
              )}

              {/* Parsed Result */}
              {parsedPosition && (
                <div className="parsed-result">
                  <div className="parsed-symbol">
                    <span className="label">Symbol:</span>
                    <span className="value">{parsedPosition.symbol}</span>
                  </div>
                  <div className="parsed-legs">
                    <span className="label">Legs:</span>
                    <span className="value">{formatLegsDisplay(parsedPosition.legs)}</span>
                  </div>
                  {parsedPosition.costBasis !== undefined && (
                    <div className="parsed-cost">
                      <span className="label">Cost:</span>
                      <span className={`value ${parsedPosition.costBasisType}`}>
                        {parsedPosition.costBasisType === 'credit' ? 'CR' : 'DR'} ${parsedPosition.costBasis.toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Example Scripts */}
              <div className="form-group examples">
                <label>Example Scripts</label>
                <div className="example-list">
                  {getExampleScripts().tos.slice(0, 3).map((example, i) => (
                    <button
                      key={i}
                      className="example-btn"
                      onClick={() => setScriptInput(example)}
                    >
                      {example.length > 60 ? example.slice(0, 60) + '...' : example}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Cost Basis (both modes) */}
          <div className="form-group cost-basis-group">
            <label>Cost Basis <span className="hint">(optional)</span></label>
            <div className="cost-basis-input-row">
              <div className="cost-type-toggle">
                <button
                  type="button"
                  className={`cost-type-btn debit ${costBasisType === 'debit' ? 'active' : ''}`}
                  onClick={() => setCostBasisType('debit')}
                >
                  DR
                </button>
                <button
                  type="button"
                  className={`cost-type-btn credit ${costBasisType === 'credit' ? 'active' : ''}`}
                  onClick={() => setCostBasisType('credit')}
                >
                  CR
                </button>
              </div>
              <span className="cost-basis-dollar">$</span>
              <input
                type="number"
                className="cost-basis-value"
                value={costBasis}
                onChange={e => setCostBasis(e.target.value)}
                placeholder="0.00"
                min="0"
                step="0.05"
              />
            </div>
          </div>

          {/* Preview */}
          <div className="position-preview create-preview">
            <span className="preview-label">Preview:</span>
            <div className="preview-content">
              <div className="preview-header">
                <span className="preview-symbol">{symbol}</span>
                <span className="preview-type">{positionLabel}</span>
                <span className="preview-dte">{dte}d</span>
                {costBasis && (
                  <span className={`preview-cost-basis ${costBasisType}`}>
                    {costBasisType === 'credit' ? 'CR' : 'DR'} ${costBasis}
                  </span>
                )}
              </div>
              <div className="preview-legs">{legsNotation}</div>
            </div>
          </div>
        </div>

        <div className="position-create-footer">
          <button className="btn btn-cancel" onClick={handleClose}>
            Cancel
          </button>
          <button
            className="btn btn-create"
            onClick={handleCreate}
            disabled={!isValid()}
          >
            Add Position
          </button>
        </div>
      </div>

      {/* Vega Warning Modal */}
      {showVegaWarning && (
        <div className="vega-warning-overlay" onClick={cancelShortVega}>
          <div className="vega-warning-modal" onClick={e => e.stopPropagation()}>
            <div className="vega-warning-icon">⚠️</div>
            <h4>Short {pendingShortType === 'calendar' ? 'Calendar' : 'Diagonal'} Warning</h4>
            <p>
              Short {pendingShortType === 'calendar' ? 'calendars' : 'diagonals'} are
              <strong> extra sensitive to vega</strong> (implied volatility changes).
            </p>
            <p>
              A spike in IV can cause significant losses even if the underlying
              moves in your favor. This strategy requires careful volatility management.
            </p>
            <div className="vega-warning-buttons">
              <button className="btn btn-cancel" onClick={cancelShortVega}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={confirmShortVega}>
                Do it
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
