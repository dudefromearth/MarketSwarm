/**
 * AlgoAlertCreator — Form builder for creating algo alerts.
 *
 * Supports Mode A (Entry) and Mode B (Management) with:
 * - Filter builder (data source, field, operator, value, required)
 * - Trader constraints (Mode A)
 * - Position selector (Mode B)
 * - Prompt override (Advanced)
 */

import { useState, useCallback } from 'react';
import type {
  AlgoAlertMode,
  FilterCondition,
  FilterDataSource,
  FilterOperator,
  CreateAlgoAlertInput,
} from '../types/algoAlerts';
import {
  FILTER_FIELDS,
  DATA_SOURCE_LABELS,
  OPERATOR_LABELS,
} from '../types/algoAlerts';

interface FilterRow {
  id: string;
  dataSource: FilterDataSource;
  field: string;
  operator: FilterOperator;
  value: string;
  required: boolean;
}

interface AlgoAlertCreatorProps {
  onSave: (input: CreateAlgoAlertInput) => void;
  onCancel: () => void;
  positionIds?: string[];  // Available positions for Mode B
}

const DATA_SOURCES: FilterDataSource[] = [
  'gex', 'market_mode', 'bias_lfi', 'vix_regime',
  'volume_profile', 'price', 'dte', 'trade_selector',
];

const OPERATORS: FilterOperator[] = ['gt', 'lt', 'eq', 'gte', 'lte', 'between', 'in'];

let _nextId = 0;
function nextId() { return `filter-${++_nextId}`; }

export default function AlgoAlertCreator({ onSave, onCancel, positionIds }: AlgoAlertCreatorProps) {
  const [name, setName] = useState('');
  const [mode, setMode] = useState<AlgoAlertMode>('entry');
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [maxRisk, setMaxRisk] = useState('500');
  const [preferredWidth, setPreferredWidth] = useState('10');
  const [dteMin, setDteMin] = useState('0');
  const [dteMax, setDteMax] = useState('7');
  const [positionId, setPositionId] = useState('');
  const [promptOverride, setPromptOverride] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const addFilter = useCallback(() => {
    setFilters(prev => [...prev, {
      id: nextId(),
      dataSource: 'gex',
      field: FILTER_FIELDS.gex[0]?.field || '',
      operator: 'gt',
      value: '0',
      required: true,
    }]);
  }, []);

  const removeFilter = useCallback((id: string) => {
    setFilters(prev => prev.filter(f => f.id !== id));
  }, []);

  const updateFilter = useCallback((id: string, updates: Partial<FilterRow>) => {
    setFilters(prev => prev.map(f => {
      if (f.id !== id) return f;
      const updated = { ...f, ...updates };
      // Reset field when data source changes
      if (updates.dataSource && updates.dataSource !== f.dataSource) {
        const fields = FILTER_FIELDS[updates.dataSource];
        updated.field = fields?.[0]?.field || '';
      }
      return updated;
    }));
  }, []);

  const handleSave = useCallback(() => {
    if (!name.trim()) return;
    if (filters.length === 0) return;

    const input: CreateAlgoAlertInput = {
      name: name.trim(),
      mode,
      filters: filters.map(f => ({
        dataSource: f.dataSource,
        field: f.field,
        operator: f.operator,
        value: parseFilterValue(f.value, f.operator),
        required: f.required,
      })),
    };

    if (mode === 'entry') {
      input.entryConstraints = {
        maxRisk: parseFloat(maxRisk) || 500,
        preferredWidth: parseInt(preferredWidth) || 10,
        preferredDteRange: [parseInt(dteMin) || 0, parseInt(dteMax) || 7],
      };
    }

    if (mode === 'management' && positionId) {
      input.positionId = positionId;
    }

    if (promptOverride.trim()) {
      input.promptOverride = promptOverride.trim();
    }

    onSave(input);
  }, [name, mode, filters, maxRisk, preferredWidth, dteMin, dteMax, positionId, promptOverride, onSave]);

  return (
    <div className="algo-alert-creator">
      <h3>New Algo Alert</h3>

      {/* Mode Toggle */}
      <div className="mode-toggle">
        <button
          className={mode === 'entry' ? 'active' : ''}
          onClick={() => setMode('entry')}
        >
          Entry
        </button>
        <button
          className={mode === 'management' ? 'active' : ''}
          onClick={() => setMode('management')}
        >
          Management
        </button>
      </div>

      {/* Name */}
      <div className="form-row">
        <label>Name</label>
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g., Compression + Positive GEX entry"
        />
      </div>

      {/* Filter Builder */}
      <div className="filter-builder">
        <div className="filter-builder-header">
          <label>Filters (permission gates)</label>
          <button className="btn-add-filter" onClick={addFilter}>
            + Add Filter
          </button>
        </div>

        {filters.map(f => {
          const fieldOptions = FILTER_FIELDS[f.dataSource] || [];
          return (
            <div key={f.id} className="filter-row">
              <select
                value={f.dataSource}
                onChange={e => updateFilter(f.id, { dataSource: e.target.value as FilterDataSource })}
              >
                {DATA_SOURCES.map(ds => (
                  <option key={ds} value={ds}>{DATA_SOURCE_LABELS[ds]}</option>
                ))}
              </select>
              <select
                value={f.field}
                onChange={e => updateFilter(f.id, { field: e.target.value })}
              >
                {fieldOptions.map(fo => (
                  <option key={fo.field} value={fo.field} title={fo.description}>
                    {fo.label}
                  </option>
                ))}
              </select>
              <select
                value={f.operator}
                onChange={e => updateFilter(f.id, { operator: e.target.value as FilterOperator })}
              >
                {OPERATORS.map(op => (
                  <option key={op} value={op}>{OPERATOR_LABELS[op]}</option>
                ))}
              </select>
              <input
                type="text"
                value={f.value}
                onChange={e => updateFilter(f.id, { value: e.target.value })}
                style={{ width: 60 }}
                placeholder="value"
              />
              <span
                className={`required-toggle ${f.required ? 'required' : ''}`}
                onClick={() => updateFilter(f.id, { required: !f.required })}
                title={f.required ? 'Required (fail-closed on missing data)' : 'Optional (pass if data unavailable)'}
              >
                {f.required ? 'REQ' : 'OPT'}
              </span>
              <button className="btn-remove-filter" onClick={() => removeFilter(f.id)}>
                x
              </button>
            </div>
          );
        })}

        {filters.length === 0 && (
          <div className="algo-alert-empty">
            Add at least one filter gate
          </div>
        )}
      </div>

      {/* Mode A: Trader Constraints */}
      {mode === 'entry' && (
        <div className="constraints-section">
          <label>Trader Constraints</label>
          <div className="form-row-inline">
            <label>Max Risk $</label>
            <input type="number" value={maxRisk} onChange={e => setMaxRisk(e.target.value)} />
          </div>
          <div className="form-row-inline">
            <label>Width</label>
            <input type="number" value={preferredWidth} onChange={e => setPreferredWidth(e.target.value)} />
          </div>
          <div className="form-row-inline">
            <label>DTE Range</label>
            <input type="number" value={dteMin} onChange={e => setDteMin(e.target.value)} style={{ width: 40 }} />
            <span style={{ color: '#6b7280', fontSize: 10 }}>to</span>
            <input type="number" value={dteMax} onChange={e => setDteMax(e.target.value)} style={{ width: 40 }} />
          </div>
        </div>
      )}

      {/* Mode B: Position Selector */}
      {mode === 'management' && positionIds && positionIds.length > 0 && (
        <div className="form-row">
          <label>Bound Position</label>
          <select value={positionId} onChange={e => setPositionId(e.target.value)}>
            <option value="">Select position...</option>
            {positionIds.map(pid => (
              <option key={pid} value={pid}>{pid.substring(0, 8)}...</option>
            ))}
          </select>
        </div>
      )}

      {/* Advanced: Prompt Override */}
      <div style={{ marginBottom: 10 }}>
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          style={{
            fontSize: 10,
            color: '#6b7280',
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          {showAdvanced ? '- Hide Advanced' : '+ Advanced'}
        </button>
      </div>

      {showAdvanced && (
        <div className="form-row">
          <label>Prompt Override</label>
          <textarea
            value={promptOverride}
            onChange={e => setPromptOverride(e.target.value)}
            placeholder="Custom evaluation instructions (optional)"
            rows={3}
          />
        </div>
      )}

      <div className="structural-tooltip">
        Filters reflect structural alignment, not direction or outcome probability.
      </div>

      {/* Footer */}
      <div className="form-footer">
        <button className="btn-cancel" onClick={onCancel}>Cancel</button>
        <button
          className="btn-save"
          onClick={handleSave}
          disabled={!name.trim() || filters.length === 0}
        >
          Save
        </button>
      </div>
    </div>
  );
}

function parseFilterValue(raw: string, operator: FilterOperator): FilterCondition['value'] {
  if (operator === 'between') {
    const parts = raw.split(',').map(s => parseFloat(s.trim()));
    if (parts.length === 2 && parts.every(p => !isNaN(p))) {
      return parts;
    }
    return [0, 100];
  }
  if (operator === 'in' || operator === 'not_in') {
    return raw.split(',').map(s => s.trim());
  }
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  const num = parseFloat(raw);
  if (!isNaN(num)) return num;
  return raw;
}
