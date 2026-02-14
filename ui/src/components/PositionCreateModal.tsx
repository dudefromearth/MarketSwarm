/**
 * PositionCreateModal - Create or edit positions
 *
 * Features:
 * - Build mode: Select position type and configure legs
 * - Import mode: Paste scripts from ToS, Tradier, etc.
 * - Edit mode: Modify existing positions (legs, cost basis)
 * - Auto-detection of script format
 * - Preview before adding to Risk Graph
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useDraggable } from '../hooks/useDraggable';
import type { PositionLeg, PositionType, PositionDirection, CostBasisType } from '../types/riskGraph';
import { POSITION_TYPE_LABELS } from '../types/riskGraph';
import { recognizePositionType, strategyToLegs } from '../utils/positionRecognition';
import { formatLegsDisplay, formatPositionLabel } from '../utils/positionFormatting';
import { useSymbolConfig, getCurrentExpiration, getNextExpiration } from '../utils/symbolConfig';
import {
  parseScript,
  detectScriptFormat,
  getExampleScripts,
  SCRIPT_FORMAT_NAMES,
  type ParsedPosition,
  type ScriptFormat,
} from '../utils/scriptParsers';
import { generateTosScript } from '../utils/tosGenerator';
import StrikeDropdown from './StrikeDropdown';

// Output format for created position
export interface CreatedPosition {
  symbol: string;
  legs: PositionLeg[];
  costBasis: number | null;
  costBasisType: CostBasisType;
  expiration: string;
  dte: number;
}

export interface PositionPrefill {
  positionType: PositionType;
  baseStrike: number;
  width: number;
  primaryRight: 'call' | 'put';
  expiration: string;       // YYYY-MM-DD
  costBasis?: number | null;
  symbol?: string;
}

// Legacy strategy data format (for backward compatibility with edit mode)
export interface StrategyData {
  id: string;
  strategy: 'butterfly' | 'vertical' | 'single';
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  expiration: string;
  debit: number | null;
  symbol?: string;
  legs?: PositionLeg[];
  positionType?: PositionType;
  direction?: PositionDirection;
  costBasis?: number | null;
  costBasisType?: CostBasisType;
}

interface PositionCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (position: CreatedPosition) => void;
  onSave?: (strategy: StrategyData) => void;
  editStrategy?: StrategyData | null;
  defaultSymbol?: string;
  atmStrike?: number;  // Current ATM strike price (fallback for primary underlying)
  spotData?: Record<string, { value: number; [key: string]: any }>;
  prefill?: PositionPrefill | null;
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

// Strategies that are naturally credit when traded in their default direction
const CREDIT_DEFAULT_TYPES: PositionType[] = [
  'iron_fly',
  'iron_condor',
  'straddle',
  'strangle',
  'calendar',
  'diagonal',
];

// Determine default cost basis type based on strategy + direction
function getDefaultCostBasisType(type: PositionType, dir: Direction): CostBasisType {
  const isNaturalCredit = CREDIT_DEFAULT_TYPES.includes(type);
  // Natural credit strategies in their default (short) direction are credits;
  // flipping direction flips the credit/debit nature.
  // Calendars/diagonals default long but are still credits.
  if (type === 'calendar' || type === 'diagonal') {
    return dir === 'long' ? 'credit' : 'debit';
  }
  return isNaturalCredit && dir === 'short' ? 'credit' : 'debit';
}

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
    // Calendar: Tent top with concave sides, single peak
    path: 'M0,10 Q7,10 12,2 Q17,10 24,10',
    color: '#06b6d4',
  },
  diagonal: {
    // Diagonal: Tent top with concave sides, two peaks
    path: 'M0,10 Q5,10 8,3 Q12,6 16,3 Q19,10 24,10',
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

// Format date to YYYY-MM-DD
function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

// Default leg configurations for each position type
// Direction flips all quantities (long -> short inverts signs)
function getDefaultLegs(
  positionType: PositionType,
  baseStrike: number,
  width: number,
  expiration: string,
  right: 'call' | 'put',
  direction: Direction,
  expirationPattern: 'daily' | 'weekly' | 'monthly' = 'daily'
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
      // Iron fly base (long direction): long ATM straddle, short wings (debit)
      // Short direction (default): short ATM straddle, long wings (credit)
      return [
        { strike: baseStrike - width, expiration, right: 'put', quantity: -1 * d },
        { strike: baseStrike, expiration, right: 'put', quantity: 1 * d },
        { strike: baseStrike, expiration, right: 'call', quantity: 1 * d },
        { strike: baseStrike + width, expiration, right: 'call', quantity: -1 * d },
      ];

    case 'iron_condor':
      // Iron condor base (long direction): long inner strikes, short wings (debit)
      // Short direction (default): short inner strikes, long wings (credit)
      return [
        { strike: baseStrike - width * 1.5, expiration, right: 'put', quantity: -1 * d },
        { strike: baseStrike - width * 0.5, expiration, right: 'put', quantity: 1 * d },
        { strike: baseStrike + width * 0.5, expiration, right: 'call', quantity: 1 * d },
        { strike: baseStrike + width * 1.5, expiration, right: 'call', quantity: -1 * d },
      ];

    case 'calendar':
    case 'diagonal': {
      // For time spreads: sell near (current exp), buy far (next exp)
      const nearExp = expiration;
      const farExp = formatDate(getNextExpiration(new Date(expiration + 'T00:00:00'), expirationPattern));
      // Diagonal uses different strikes; calendar uses same strike
      const farStrike = positionType === 'diagonal' ? baseStrike + width : baseStrike;
      return [
        { strike: baseStrike, expiration: nearExp, right, quantity: -1 * d },
        { strike: farStrike, expiration: farExp, right, quantity: 1 * d },
      ];
    }

    default:
      return [{ strike: baseStrike, expiration, right, quantity: 1 * d }];
  }
}

export default function PositionCreateModal({
  isOpen,
  onClose,
  onCreate,
  onSave,
  editStrategy,
  defaultSymbol = 'SPX',
  atmStrike = 5900,
  spotData,
  prefill,
}: PositionCreateModalProps) {
  const isEditMode = editStrategy != null;
  const { symbols: availableSymbols, getConfig } = useSymbolConfig();
  const [mode, setMode] = useState<CreateMode>('build');

  // Fetch all spot prices once when modal opens (REST baseline)
  const [fetchedSpot, setFetchedSpot] = useState<Record<string, { value: number }>>({});
  useEffect(() => {
    if (isOpen) {
      fetch('/api/models/spot', { credentials: 'include' })
        .then(r => r.json())
        .then(d => {
          if (d.success && d.data) setFetchedSpot(d.data);
        })
        .catch(() => {});
    }
  }, [isOpen]);

  // Merge: live SSE spotData overlays on top of fetched baseline
  const allSpot = useMemo(() => {
    return { ...fetchedSpot, ...spotData };
  }, [fetchedSpot, spotData]);

  // Draggable modal
  const { dragHandleProps, containerStyle, isDragging } = useDraggable({
    handleSelector: '.position-create-header',
    initialCentered: true,
  });

  // Build mode state
  const [symbol, setSymbol] = useState(defaultSymbol);

  // Fetch real market strikes for the selected symbol
  const [availableStrikes, setAvailableStrikes] = useState<number[]>([]);
  useEffect(() => {
    if (!isOpen) return;
    const spotKey = getConfig(symbol).spotKey;
    fetch(`/api/options/strikes/${encodeURIComponent(spotKey)}`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => {
        if (d.success && Array.isArray(d.strikes) && d.strikes.length > 0) {
          setAvailableStrikes(d.strikes);
        } else {
          setAvailableStrikes([]);
        }
      })
      .catch(() => setAvailableStrikes([]));
  }, [isOpen, symbol, getConfig]);
  const [positionType, setPositionType] = useState<PositionType>('butterfly');
  const [direction, setDirection] = useState<Direction>('long');
  const [legs, setLegs] = useState<PositionLeg[]>([]);
  const [costBasis, setCostBasis] = useState('');
  const [costBasisType, setCostBasisType] = useState<CostBasisType>('debit');

  // Config-driven values from Symbol Config Registry
  const symbolConfig = useMemo(() => getConfig(symbol), [symbol, getConfig]);
  const { strikeIncrement, defaultWidth, expirationPattern } = symbolConfig;

  // Per-symbol ATM: resolve from merged spot data (fetched + live SSE)
  const symbolAtm = useMemo(() => {
    const key = symbolConfig.spotKey;
    const val = allSpot[key]?.value;
    if (val && val > 0) return val;
    return atmStrike || 5900;
  }, [symbol, allSpot, atmStrike, symbolConfig.spotKey]);

  const roundedAtm = Math.round(symbolAtm / strikeIncrement) * strikeIncrement;

  const [baseStrike, setBaseStrike] = useState(roundedAtm.toString());
  const [width, setWidth] = useState(defaultWidth.toString());
  const [expiration, setExpiration] = useState('');
  const [primaryRight, setPrimaryRight] = useState<'call' | 'put'>('call');
  const [positionQty, setPositionQty] = useState(1);

  // Vega warning for short calendars/diagonals
  const [showVegaWarning, setShowVegaWarning] = useState(false);
  const [pendingShortType, setPendingShortType] = useState<PositionType | null>(null);

  // Skip flag: when direction or expiration changes via user action, the in-place
  // update handles legs directly — the generation effect should not overwrite.
  const skipRegenRef = useRef(false);

  // Types that need vega warning when going short
  const VEGA_SENSITIVE_TYPES: PositionType[] = ['calendar', 'diagonal'];

  // Time spread types (used later after recognition is computed)
  const TIME_SPREAD_TYPES: PositionType[] = ['calendar', 'diagonal'];

  // Update direction when position type changes (full regeneration via effect)
  const handlePositionTypeChange = useCallback((newType: PositionType) => {
    setPositionType(newType);
    const newDir = getDefaultDirection(newType);
    setDirection(newDir);
    if (!costBasis) setCostBasisType(getDefaultCostBasisType(newType, newDir));
  }, [costBasis]);

  // Handle multiplier change — scale all leg quantities proportionally
  const handleMultiplierChange = useCallback((newMultiplier: number) => {
    const oldMultiplier = positionQty;
    if (oldMultiplier === newMultiplier || oldMultiplier === 0) {
      setPositionQty(newMultiplier);
      return;
    }
    setPositionQty(newMultiplier);
    // Re-scale: divide out old multiplier, multiply by new
    setLegs(prev => prev.map(leg => {
      const baseQty = leg.quantity / oldMultiplier;
      return { ...leg, quantity: Math.round(baseQty * newMultiplier) };
    }));
    skipRegenRef.current = true;
  }, [positionQty]);

  // Handle direction change — flip existing leg qty signs in place
  const handleDirectionChange = useCallback((newDirection: Direction) => {
    if (newDirection === 'short' && VEGA_SENSITIVE_TYPES.includes(positionType)) {
      setPendingShortType(positionType);
      setShowVegaWarning(true);
    } else {
      if (newDirection !== direction) {
        skipRegenRef.current = true;
        setLegs(prev => prev.map(leg => ({ ...leg, quantity: -leg.quantity })));
      }
      setDirection(newDirection);
      if (!costBasis) setCostBasisType(getDefaultCostBasisType(positionType, newDirection));
    }
  }, [positionType, direction, costBasis]);

  // Confirm short calendar/diagonal despite vega warning — flip leg qty signs
  const confirmShortVega = useCallback(() => {
    skipRegenRef.current = true;
    setLegs(prev => prev.map(leg => ({ ...leg, quantity: -leg.quantity })));
    setDirection('short');
    if (!costBasis) setCostBasisType(getDefaultCostBasisType(pendingShortType || positionType, 'short'));
    setShowVegaWarning(false);
    setPendingShortType(null);
  }, [costBasis, pendingShortType, positionType]);

  // Cancel short calendar/diagonal
  const cancelShortVega = useCallback(() => {
    setShowVegaWarning(false);
    setPendingShortType(null);
  }, []);

  // Handle expiration change — update all leg expirations in place
  const handleExpirationChange = useCallback((newExp: string) => {
    skipRegenRef.current = true;
    setExpiration(newExp);
    setLegs(prev => prev.map(leg => ({ ...leg, expiration: newExp })));
  }, []);

  // Import mode state
  const [scriptInput, setScriptInput] = useState('');
  const [parsedPosition, setParsedPosition] = useState<ParsedPosition | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [detectedFormat, setDetectedFormat] = useState<ScriptFormat>('unknown');

  // Reset strike, width, and expiration when symbol changes (dynamic ATM + config per symbol)
  useEffect(() => {
    if (isEditMode) return; // Don't reset in edit mode
    setBaseStrike(roundedAtm.toString());
    setWidth(defaultWidth.toString());
    setExpiration(formatDate(getCurrentExpiration(expirationPattern)));
  }, [symbol, roundedAtm, defaultWidth, expirationPattern, isEditMode]);

  // Set initial values when modal opens
  useEffect(() => {
    if (isOpen && !isEditMode) {
      setExpiration(formatDate(getCurrentExpiration(expirationPattern)));
      setBaseStrike(roundedAtm.toString());
    }
  }, [isOpen, roundedAtm, expirationPattern, isEditMode]);

  // Apply prefill values when modal opens with prefill data
  useEffect(() => {
    if (isOpen && prefill && !isEditMode) {
      setMode('build');
      if (prefill.symbol) setSymbol(prefill.symbol);
      setPositionType(prefill.positionType as PositionType);
      setDirection(getDefaultDirection(prefill.positionType as PositionType));
      setBaseStrike(prefill.baseStrike.toString());
      setWidth(prefill.width.toString());
      setPrimaryRight(prefill.primaryRight);
      setExpiration(prefill.expiration);
      if (prefill.costBasis != null) {
        setCostBasis(Math.abs(prefill.costBasis).toFixed(2));
        setCostBasisType(prefill.costBasis < 0 ? 'credit' : 'debit');
      } else {
        setCostBasis('');
        const dir = getDefaultDirection(prefill.positionType as PositionType);
        setCostBasisType(getDefaultCostBasisType(prefill.positionType as PositionType, dir));
      }
    }
  }, [isOpen, prefill, isEditMode]);

  // Populate form when editing an existing strategy
  useEffect(() => {
    if (isOpen && editStrategy) {
      setMode('build');
      setSymbol(editStrategy.symbol || 'SPX');

      if (editStrategy.legs && editStrategy.legs.length > 0) {
        setLegs([...editStrategy.legs]);
      } else {
        const derivedLegs = strategyToLegs(
          editStrategy.strategy,
          editStrategy.side,
          editStrategy.strike,
          editStrategy.width,
          editStrategy.expiration
        );
        setLegs(derivedLegs);
      }

      const basis = editStrategy.costBasis ?? editStrategy.debit ?? null;
      setCostBasis(basis !== null ? Number(basis).toFixed(2) : '');
      setCostBasisType(editStrategy.costBasisType || 'debit');
    }
  }, [isOpen, editStrategy]);

  // Generate legs when build parameters change (create mode only)
  // Direction and expiration changes are handled in-place by their own handlers;
  // skipRegenRef prevents this effect from overwriting those updates.
  useEffect(() => {
    if (isEditMode) return; // Don't auto-generate in edit mode
    if (skipRegenRef.current) {
      skipRegenRef.current = false;
      return;
    }
    if (mode === 'build' && expiration) {
      const strike = parseFloat(baseStrike) || 5900;
      const w = parseFloat(width) || defaultWidth;
      const baseLegs = getDefaultLegs(positionType, strike, w, expiration, primaryRight, direction, expirationPattern);
      // Apply multiplier to base leg quantities
      const newLegs = positionQty > 1
        ? baseLegs.map(leg => ({ ...leg, quantity: leg.quantity * positionQty }))
        : baseLegs;
      setLegs(newLegs);
    }
  }, [mode, positionType, baseStrike, width, expiration, primaryRight, direction, expirationPattern, defaultWidth, isEditMode, positionQty]);

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
          setCostBasis(Number(result.costBasis).toFixed(2));
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

  // Recognize position type from current legs
  const recognition = useMemo(() => {
    if (currentLegs.length === 0) {
      return { type: 'custom' as PositionType, direction: 'long' as const, isSymmetric: true };
    }
    return recognizePositionType(currentLegs);
  }, [currentLegs]);

  // Time spreads have per-leg expirations; all others share the first leg's expiration
  const isTimespread = TIME_SPREAD_TYPES.includes(isEditMode ? recognition.type : positionType);

  // In edit mode, derive type/direction from recognition
  const displayPositionType = isEditMode ? recognition.type : positionType;
  const displayDirection = isEditMode ? recognition.direction : direction;
  const isAsymmetric = recognition.isSymmetric === false;

  // Format display - use user's selection in build mode, inferred in import/edit mode
  const positionLabel = useMemo(() => {
    if (mode === 'build' && !isEditMode) {
      return formatPositionLabel(positionType, direction, currentLegs);
    }
    return formatPositionLabel(recognition.type, recognition.direction, currentLegs);
  }, [mode, isEditMode, positionType, direction, recognition, currentLegs]);

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

  // Update a specific leg. When updating expiration on leg 0 for non-timespreads,
  // propagate the new expiration to all other legs.
  const updateLeg = useCallback((index: number, updates: Partial<PositionLeg>) => {
    setLegs(prev => {
      const newLegs = [...prev];
      newLegs[index] = { ...newLegs[index], ...updates };
      // Propagate expiration from first leg to all others (except timespreads)
      if (index === 0 && updates.expiration && !isTimespread) {
        for (let i = 1; i < newLegs.length; i++) {
          newLegs[i] = { ...newLegs[i], expiration: updates.expiration };
        }
      }
      return newLegs;
    });
  }, [isTimespread]);

  const handleClose = useCallback(() => {
    // Reset state
    setMode('build');
    setScriptInput('');
    setParsedPosition(null);
    setParseError(null);
    setPositionQty(1);
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
  }, [symbol, currentLegs, costBasis, costBasisType, dte, positionQty, onCreate, handleClose]);

  // Save handler for edit mode (derives legacy fields from legs for backward compat)
  const handleSave = useCallback(() => {
    if (!editStrategy || legs.length === 0 || !onSave) return;

    const costBasisNum = costBasis ? parseFloat(costBasis) : null;

    // Calculate center strike and width for legacy compatibility
    const sortedLegs = [...legs].sort((a, b) => a.strike - b.strike);
    const strikes = sortedLegs.map(l => l.strike);

    let centerStrike = strikes[0];
    let legWidth = 0;

    if (legs.length === 3) {
      centerStrike = strikes[1];
      legWidth = strikes[1] - strikes[0];
    } else if (legs.length === 2) {
      centerStrike = strikes[0];
      legWidth = strikes[1] - strikes[0];
    } else if (legs.length === 4) {
      centerStrike = Math.round((strikes[1] + strikes[2]) / 2);
      legWidth = strikes[1] - strikes[0];
    }

    // Get primary expiration
    const expirations = legs.map(l => l.expiration);
    expirations.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
    const primaryExpiration = expirations[0];

    // Determine side from dominant leg type
    const calls = legs.filter(l => l.right === 'call').length;
    const puts = legs.filter(l => l.right === 'put').length;
    const side: 'call' | 'put' = calls >= puts ? 'call' : 'put';

    // Map position type back to legacy strategy type
    let legacyStrategy: 'butterfly' | 'vertical' | 'single' = 'single';
    if (['butterfly', 'bwb'].includes(recognition.type)) {
      legacyStrategy = 'butterfly';
    } else if (['vertical', 'calendar', 'diagonal'].includes(recognition.type)) {
      legacyStrategy = 'vertical';
    }

    onSave({
      id: editStrategy.id,
      symbol,
      strategy: legacyStrategy,
      side,
      strike: centerStrike,
      width: legWidth,
      dte,
      expiration: primaryExpiration,
      debit: costBasisNum,
      costBasis: costBasisNum,
      costBasisType,
      legs,
      positionType: recognition.type,
      direction: recognition.direction,
    });

    handleClose();
  }, [editStrategy, symbol, legs, costBasis, costBasisType, dte, recognition, onSave, handleClose]);

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
          <h3>{isEditMode ? 'Edit Position' : 'Create Position'}</h3>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        <div className="position-create-body">
          {mode === 'build' ? (
            <>
              {/* Symbol + Strategy Row */}
              <div className="form-group symbol-strategy-row">
                <div className="symbol-field">
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
                <div className="strategy-field">
                  <label>Strategy</label>
                {isEditMode ? (
                  <div className="position-type-display">
                    <span className={`position-type-badge ${displayPositionType}`}>
                      {positionLabel}
                    </span>
                    {isAsymmetric && (
                      <span className="position-asym-warning">
                        Asymmetric wing widths
                      </span>
                    )}
                  </div>
                ) : (
                  <>
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
                          Buy
                        </button>
                        <button
                          type="button"
                          className={`direction-btn short ${direction === 'short' ? 'active' : ''}`}
                          onClick={() => handleDirectionChange('short')}
                        >
                          Sell
                        </button>
                      </div>
                      <span className="selected-type-label">
                        {direction === 'long' ? 'Buy' : 'Sell'} {POSITION_TYPE_LABELS[positionType]}
                      </span>
                    </div>
                  </>
                )}
                </div>
              </div>

              {/* Legs Editor */}
              <div className="form-group legs-editor">
                <label>Legs</label>
                <div className="legs-list">
                  {/* Column headers */}
                  <div className="leg-row leg-header">
                    <span className="leg-index"></span>
                    <span className="leg-col-label leg-quantity">QTY</span>
                    <span className="leg-col-label leg-strike">STRIKE</span>
                    <span className="leg-col-label leg-right">TYPE</span>
                    <span className="leg-col-label leg-expiration">EXPIRATION</span>
                    <span className="leg-col-label leg-cost-basis">
                      <span className={costBasisType}>{costBasisType === 'credit' ? 'CREDIT' : 'DEBIT'}</span>
                    </span>
                    <span className="leg-col-label leg-qty-field">POS</span>
                  </div>
                  {legs.map((leg, index) => (
                    <div key={index} className="leg-row">
                      <span className="leg-index">Leg {index + 1}:</span>

                      <input
                        type="number"
                        className="leg-quantity"
                        value={leg.quantity}
                        onChange={e => updateLeg(index, { quantity: parseInt(e.target.value) || 0 })}
                        min="-999"
                        max="999"
                        step="1"
                      />

                      <StrikeDropdown
                        value={leg.strike}
                        onChange={strike => updateLeg(index, { strike })}
                        atmStrike={roundedAtm}
                        strikes={availableStrikes.length > 0 ? availableStrikes : undefined}
                        minStrike={roundedAtm - symbolConfig.strikeRange}
                        maxStrike={roundedAtm + symbolConfig.strikeRange}
                        strikeStep={strikeIncrement}
                        className="leg-strike"
                      />

                      <select
                        className="leg-right"
                        value={leg.right}
                        onChange={e => updateLeg(index, { right: e.target.value as 'call' | 'put' })}
                      >
                        <option value="call">Call</option>
                        <option value="put">Put</option>
                      </select>

                      {/* Show expiration on first leg always; on other legs only for timespreads */}
                      {(index === 0 || isTimespread) && (
                        <input
                          type="date"
                          className="leg-expiration"
                          value={leg.expiration}
                          onChange={e => updateLeg(index, { expiration: e.target.value })}
                        />
                      )}

                      {/* Cost basis + QTY on first leg row only */}
                      {index === 0 && (
                        <>
                          <input
                            type="text"
                            inputMode="decimal"
                            className={`cost-basis-inline ${costBasis ? costBasisType : ''}`}
                            value={costBasis}
                            onChange={e => {
                              const val = e.target.value;
                              if (val === '' || val === '-' || /^-?\d*\.?\d{0,2}$/.test(val)) {
                                setCostBasis(val);
                                const num = parseFloat(val);
                                if (!isNaN(num)) {
                                  setCostBasisType(num < 0 ? 'credit' : 'debit');
                                }
                              }
                            }}
                            onBlur={() => {
                              if (costBasis) {
                                const num = parseFloat(costBasis);
                                if (!isNaN(num)) setCostBasis(num.toFixed(2));
                              }
                            }}
                            placeholder="0.00"
                          />
                          <input
                            type="number"
                            className="position-qty-input"
                            value={positionQty}
                            onChange={e => handleMultiplierChange(Math.max(1, Math.min(999, parseInt(e.target.value) || 1)))}
                            min="1"
                            max="999"
                            step="1"
                          />
                        </>
                      )}
                    </div>
                  ))}
                </div>

                {/* Type change warning (edit mode) */}
                {isEditMode && recognition.type === 'custom' && legs.length > 1 && (
                  <div className="type-change-warning">
                    Structure not recognized. Adjust legs to match a known pattern.
                  </div>
                )}
              </div>

              {/* Preview + Action Buttons */}
              <div className="preview-actions-row">
                <div className="position-preview create-preview">
                  <span className="preview-label">Preview:</span>
                  <div className="preview-content">
                    <div className="preview-header">
                      <span className="preview-symbol">{symbol}</span>
                      <span className="preview-type">{positionLabel}</span>
                      <span className="preview-dte">{dte}d</span>
                      {costBasis && (
                        <span className={`preview-cost-basis ${costBasisType}`}>
                          ${parseFloat(costBasis).toFixed(2)} {costBasisType === 'credit' ? 'CREDIT' : 'DEBIT'}
                        </span>
                      )}
                    </div>
                    <div className="preview-legs">{legsNotation}</div>
                  </div>
                </div>
                <div className="action-buttons">
                  <button
                    className={`btn ${isEditMode ? 'btn-save' : 'btn-create'}`}
                    onClick={isEditMode ? handleSave : handleCreate}
                    disabled={!isValid()}
                  >
                    {isEditMode ? 'Save Changes' : 'Add to Risk Graph'}
                  </button>
                  {!isEditMode && (
                    <button
                      className="btn btn-import-export"
                      onClick={() => setMode(mode === 'import' ? 'build' : 'import')}
                    >
                      {mode === 'import' ? 'Back to Build' : 'Import / Export'}
                    </button>
                  )}
                  <button className="btn btn-cancel" onClick={handleClose}>
                    Cancel
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* TOS Export */}
              {currentLegs.length > 0 && (
                <div className="form-group tos-export-group">
                  <label>Export</label>
                  <div className="tos-output">
                    <code>{generateTosScript({ symbol, legs: currentLegs, costBasis: costBasis ? parseFloat(costBasis) : null })}</code>
                    <button
                      className="btn-copy-tos"
                      onClick={async () => {
                        const script = generateTosScript({ symbol, legs: currentLegs, costBasis: costBasis ? parseFloat(costBasis) : null });
                        await navigator.clipboard.writeText(script);
                        const btn = document.querySelector('.btn-copy-tos');
                        if (btn) { btn.textContent = 'Copied!'; setTimeout(() => { btn.textContent = 'Copy'; }, 2000); }
                      }}
                    >
                      Copy
                    </button>
                  </div>
                </div>
              )}

              {/* Import */}
              <div className="form-group">
                <label>
                  Import Script
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
                        ${parsedPosition.costBasis.toFixed(2)} {parsedPosition.costBasisType === 'credit' ? 'Credit' : 'Debit'}
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

          {/* Cost Basis for import mode only */}
          {mode === 'import' && (
            <div className="form-group cost-basis-group">
              <label>Cost Basis <span className="hint">(optional)</span></label>
              <div className="cost-basis-input-row">
                <input
                  type="text"
                  inputMode="decimal"
                  className="cost-basis-value"
                  value={costBasis}
                  onChange={e => {
                    const val = e.target.value;
                    if (val === '' || val === '-' || /^-?\d*\.?\d{0,2}$/.test(val)) {
                      setCostBasis(val);
                      const num = parseFloat(val);
                      if (!isNaN(num)) {
                        setCostBasisType(num < 0 ? 'credit' : 'debit');
                      }
                    }
                  }}
                  onBlur={() => {
                    if (costBasis) {
                      const num = parseFloat(costBasis);
                      if (!isNaN(num)) setCostBasis(num.toFixed(2));
                    }
                  }}
                  placeholder="0.00"
                  step="0.05"
                />
                <span className={`cost-basis-label ${costBasisType}`}>
                  {costBasisType === 'credit' ? 'CREDIT' : 'DEBIT'}
                </span>
              </div>
            </div>
          )}
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
