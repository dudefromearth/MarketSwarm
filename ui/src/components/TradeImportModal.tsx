/**
 * TradeImportModal - Import trades from broker CSV exports
 *
 * Supports:
 * - ThinkOrSwim (TOS) Account Statement CSV
 * - Tastytrade (planned)
 * - Interactive Brokers Flex Query (planned)
 *
 * Features:
 * - Explicit log targeting (user must select destination log)
 * - Smart recommendations for historical imports
 * - Support for archived log imports with warnings
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import * as XLSX from 'xlsx';
import {
  parseTosAccountStatement,
  parseCustomCsv,
  generateCustomTemplate,
  analyzeWithAI,
  parseWithMapping,
  recognizeStrategy,
  type ImportResult,
  type ImportedTrade,
  type Platform,
  type AIAnalysisResult,
} from '../utils/importers';

/**
 * Convert Excel/Numbers workbook to CSV text
 */
function workbookToCSV(workbook: XLSX.WorkBook): string {
  // Get first sheet
  const sheetName = workbook.SheetNames[0];
  if (!sheetName) return '';

  const sheet = workbook.Sheets[sheetName];
  return XLSX.utils.sheet_to_csv(sheet);
}

/**
 * Read file and convert to text (handles CSV, Excel, Numbers)
 */
async function readFileAsText(file: File): Promise<string> {
  const extension = file.name.split('.').pop()?.toLowerCase();

  // Excel or Numbers file
  if (['xlsx', 'xls', 'numbers'].includes(extension || '')) {
    const arrayBuffer = await file.arrayBuffer();
    const workbook = XLSX.read(arrayBuffer, { type: 'array' });
    return workbookToCSV(workbook);
  }

  // CSV or text file
  return file.text();
}

type ExtendedPlatform = Platform | 'ai';

interface LogForImport {
  id: string;
  name: string;
  description: string | null;
  lifecycleState: 'active' | 'archived' | 'retired';
  mlIncluded: boolean;
  openPositionCount: number;
  totalTradeCount: number;
  retireScheduledAt: string | null;
}

interface ImportRecommendation {
  recommend_archived: boolean;
  reason: string | null;
  target_log_state: string;
  overlap_trades: number;
}

interface TradeImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (trades: ImportedTrade[], targetLogId: string) => void;
  selectedLogId?: string | null;  // Pre-selected log (if any)
}

const PLATFORM_LABELS: Record<ExtendedPlatform, string> = {
  tos: 'ThinkOrSwim',
  tastytrade: 'Tastytrade',
  ibkr: 'Interactive Brokers',
  custom: 'Custom CSV',
  ai: 'AI Assist',
};

const PLATFORM_INFO: Record<ExtendedPlatform, { description: string; supported: boolean; instructions: string }> = {
  tos: {
    description: 'ThinkOrSwim Account Statement',
    supported: true,
    instructions: 'Export from Account Statement > Transactions as CSV',
  },
  tastytrade: {
    description: 'Tastytrade Transaction History',
    supported: false,
    instructions: 'Coming soon',
  },
  ibkr: {
    description: 'Interactive Brokers Flex Query',
    supported: false,
    instructions: 'Coming soon',
  },
  custom: {
    description: 'Use our template for any broker',
    supported: true,
    instructions: 'Download our CSV template, fill in your trades, and import',
  },
  ai: {
    description: 'AI analyzes any file format',
    supported: true,
    instructions: 'Upload CSV, Excel, or Numbers file from any broker',
  },
};

export default function TradeImportModal({ isOpen, onClose, onImport, selectedLogId }: TradeImportModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [platform, setPlatform] = useState<ExtendedPlatform | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [selectedTrades, setSelectedTrades] = useState<Set<string>>(new Set());
  const [step, setStep] = useState<'select-platform' | 'upload' | 'preview' | 'ai-analyzing'>('select-platform');
  const [aiAnalysis, setAiAnalysis] = useState<AIAnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  // Log selection state
  const [availableLogs, setAvailableLogs] = useState<LogForImport[]>([]);
  const [targetLogId, setTargetLogId] = useState<string | null>(selectedLogId || null);
  const [recommendation, setRecommendation] = useState<ImportRecommendation | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch available logs when entering preview step
  useEffect(() => {
    if (step === 'preview' && result?.success) {
      fetchLogsForImport();
    }
  }, [step, result?.success]);

  // Update target log when selectedLogId prop changes
  useEffect(() => {
    if (selectedLogId && !targetLogId) {
      setTargetLogId(selectedLogId);
    }
  }, [selectedLogId]);

  // Fetch import recommendation when target log or trades change
  useEffect(() => {
    if (step === 'preview' && targetLogId && result?.trades.length) {
      fetchRecommendation();
    }
  }, [targetLogId, step, result?.trades.length]);

  const fetchLogsForImport = async () => {
    setLoadingLogs(true);
    try {
      const response = await fetch('/api/logs/for-import', {
        credentials: 'include',
      });
      const data = await response.json();
      if (data.success) {
        setAvailableLogs(data.data);
        // Auto-select if only one active log
        const activeLogs = data.data.filter((l: LogForImport) => l.lifecycleState === 'active');
        if (activeLogs.length === 1 && !targetLogId) {
          setTargetLogId(activeLogs[0].id);
        }
      }
    } catch (err) {
      console.error('[TradeImport] Failed to fetch logs:', err);
    } finally {
      setLoadingLogs(false);
    }
  };

  const fetchRecommendation = async () => {
    if (!targetLogId || !result?.trades.length) return;

    // Get date range from trades
    const dates = result.trades.map(t => t.tradeDate).sort();
    const earliestDate = dates[0];
    const latestDate = dates[dates.length - 1];

    try {
      const response = await fetch('/api/logs/import-recommendation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          target_log_id: targetLogId,
          earliest_date: earliestDate,
          latest_date: latestDate,
        }),
      });
      const data = await response.json();
      if (data.success) {
        setRecommendation(data);
      }
    } catch (err) {
      console.error('[TradeImport] Failed to fetch recommendation:', err);
    }
  };

  const handlePlatformSelect = useCallback((selected: ExtendedPlatform) => {
    if (!PLATFORM_INFO[selected].supported) return;
    setPlatform(selected);
    setStep('upload');
  }, []);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile || !platform) return;

    setFile(selectedFile);

    try {
      const text = await readFileAsText(selectedFile);

      // AI-assisted parsing
      if (platform === 'ai') {
        setAnalyzing(true);
        setStep('ai-analyzing');

        try {
          const analysis = await analyzeWithAI(text);
          setAiAnalysis(analysis);

          if (analysis.success && Object.keys(analysis.columnMapping).length > 0) {
            // Parse with AI-detected mappings
            const { trades, errors } = parseWithMapping(text, analysis.columnMapping, analysis.dateFormat);

            const parseResult: ImportResult = {
              success: trades.length > 0,
              trades: trades as ImportedTrade[],
              errors,
              warnings: analysis.notes || [],
              stats: {
                totalRows: text.split('\n').length - 1,
                parsedTrades: trades.length,
                skippedRows: errors.length,
              },
            };

            setResult(parseResult);

            if (parseResult.success) {
              setSelectedTrades(new Set(parseResult.trades.map(t => t.id)));
              setStep('preview');
            } else {
              setStep('upload');
            }
          } else {
            setResult({
              success: false,
              trades: [],
              errors: [analysis.error || 'AI could not determine the file format. Try using Custom CSV instead.'],
              warnings: [],
              stats: { totalRows: 0, parsedTrades: 0, skippedRows: 0 },
            });
            setStep('upload');
          }
        } catch (aiErr) {
          setResult({
            success: false,
            trades: [],
            errors: [`AI analysis failed: ${aiErr}. Try using Custom CSV instead.`],
            warnings: [],
            stats: { totalRows: 0, parsedTrades: 0, skippedRows: 0 },
          });
          setStep('upload');
        } finally {
          setAnalyzing(false);
        }
        return;
      }

      // Parse based on selected platform
      let parseResult: ImportResult;
      switch (platform) {
        case 'tos':
          parseResult = parseTosAccountStatement(text);
          break;
        case 'custom':
          parseResult = parseCustomCsv(text);
          break;
        default:
          parseResult = {
            success: false,
            trades: [],
            errors: [`${PLATFORM_LABELS[platform]} import not yet implemented`],
            warnings: [],
            stats: { totalRows: 0, parsedTrades: 0, skippedRows: 0 },
          };
      }

      // If parsing failed or no trades found, try AI fallback
      if (!parseResult.success || parseResult.trades.length === 0) {
        setAnalyzing(true);
        setStep('ai-analyzing');

        try {
          const analysis = await analyzeWithAI(text);
          setAiAnalysis(analysis);

          if (analysis.success && Object.keys(analysis.columnMapping).length > 0) {
            const { trades, errors } = parseWithMapping(text, analysis.columnMapping, analysis.dateFormat);

            if (trades.length > 0) {
              parseResult = {
                success: true,
                trades: trades as ImportedTrade[],
                errors,
                warnings: [
                  `Original ${PLATFORM_LABELS[platform]} parser had issues. AI detected format and found ${trades.length} trades.`,
                  ...(analysis.notes || []),
                ],
                stats: {
                  totalRows: text.split('\n').length - 1,
                  parsedTrades: trades.length,
                  skippedRows: errors.length,
                },
              };
            }
          }
        } catch (aiErr) {
          // AI fallback failed too, keep original error
          parseResult.warnings.push('AI fallback was attempted but also failed.');
        } finally {
          setAnalyzing(false);
        }
      }

      setResult(parseResult);

      // Select all trades by default
      if (parseResult.success) {
        setSelectedTrades(new Set(parseResult.trades.map(t => t.id)));
        setStep('preview');
      } else {
        setStep('upload');
      }
    } catch (err) {
      setResult({
        success: false,
        trades: [],
        errors: [`Failed to read file: ${err}`],
        warnings: [],
        stats: { totalRows: 0, parsedTrades: 0, skippedRows: 0 },
      });
    }
  }, [platform]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && fileInputRef.current) {
      const dt = new DataTransfer();
      dt.items.add(droppedFile);
      fileInputRef.current.files = dt.files;
      fileInputRef.current.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, []);

  const toggleTrade = useCallback((id: string) => {
    setSelectedTrades(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (!result) return;
    if (selectedTrades.size === result.trades.length) {
      setSelectedTrades(new Set());
    } else {
      setSelectedTrades(new Set(result.trades.map(t => t.id)));
    }
  }, [result, selectedTrades]);

  const handleImport = useCallback(() => {
    if (!result || !targetLogId) return;
    const tradesToImport = result.trades.filter(t => selectedTrades.has(t.id));
    onImport(tradesToImport, targetLogId);
    handleClose();
  }, [result, selectedTrades, targetLogId, onImport]);

  const handleClose = useCallback(() => {
    setFile(null);
    setPlatform(null);
    setResult(null);
    setSelectedTrades(new Set());
    setAiAnalysis(null);
    setAnalyzing(false);
    setAvailableLogs([]);
    setTargetLogId(selectedLogId || null);
    setRecommendation(null);
    setStep('select-platform');
    onClose();
  }, [onClose, selectedLogId]);

  const handleBack = useCallback(() => {
    if (step === 'preview' || step === 'ai-analyzing') {
      setFile(null);
      setResult(null);
      setSelectedTrades(new Set());
      setAiAnalysis(null);
      setAnalyzing(false);
      setStep('upload');
    } else if (step === 'upload') {
      setPlatform(null);
      setStep('select-platform');
    }
  }, [step]);

  const downloadTemplate = useCallback(() => {
    const template = generateCustomTemplate();
    const blob = new Blob([template], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'trade-import-template.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  const formatLeg = (leg: ImportedTrade['legs'][0]) => {
    const sign = leg.quantity > 0 ? '+' : '';
    return `${sign}${leg.quantity} ${leg.symbol} ${leg.expiration} ${leg.strike} ${leg.type.toUpperCase()}`;
  };

  if (!isOpen) return null;

  return (
    <div className="trade-import-overlay" onClick={handleClose}>
      <div className="trade-import-modal" onClick={e => e.stopPropagation()}>
        <div className="trade-import-header">
          <h3>Import Trades</h3>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        <div className="trade-import-body">
          {step === 'select-platform' && (
            <div className="platform-selection">
              <div className="platform-prompt">Select your broker platform:</div>
              <div className="platform-grid">
                {(Object.keys(PLATFORM_INFO) as ExtendedPlatform[]).map((p) => (
                  <div
                    key={p}
                    className={`platform-card ${PLATFORM_INFO[p].supported ? '' : 'disabled'} ${p === 'ai' ? 'ai-card' : ''}`}
                    onClick={() => handlePlatformSelect(p)}
                  >
                    {p === 'ai' && <div className="ai-badge">AI</div>}
                    <div className="platform-name">{PLATFORM_LABELS[p]}</div>
                    <div className="platform-desc">{PLATFORM_INFO[p].description}</div>
                    {PLATFORM_INFO[p].supported ? (
                      <div className={`platform-status ${p === 'ai' ? 'ai-status' : 'supported'}`}>
                        {p === 'ai' ? 'Auto-Detect' : 'Supported'}
                      </div>
                    ) : (
                      <div className="platform-status coming-soon">Coming Soon</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 'ai-analyzing' && (
            <div className="ai-analyzing">
              <div className="ai-spinner"></div>
              <div className="ai-status-text">AI is analyzing your file...</div>
              <div className="ai-substatus">Detecting columns and format</div>
            </div>
          )}

          {step === 'upload' && platform && (
            <>
              <div className="platform-selected">
                <span className="platform-label">Importing from:</span>
                <span className="platform-value">{PLATFORM_LABELS[platform]}</span>
              </div>
              <div className="import-instructions">
                {PLATFORM_INFO[platform].instructions}
              </div>

              {platform === 'custom' && (
                <div className="template-section">
                  <button className="btn btn-template" onClick={downloadTemplate}>
                    Download CSV Template
                  </button>
                  <div className="template-help">
                    <div className="template-columns">
                      <strong>Required columns:</strong> date, symbol, expiration, strike, type, quantity, price
                    </div>
                    <div className="template-columns">
                      <strong>Optional:</strong> time, commission, fees, effect
                    </div>
                    <div className="template-note">
                      Legs with the same date+time are grouped into a single trade.
                      Use negative quantity for short positions.
                    </div>
                  </div>
                </div>
              )}

              <div
                className="file-drop-zone"
                onDragOver={e => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.txt,.xlsx,.xls,.numbers"
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                />
                <div className="drop-icon">📁</div>
                <div className="drop-text">
                  {platform === 'ai'
                    ? 'Drop CSV, Excel, or Numbers file here'
                    : 'Drop CSV file here or click to browse'
                  }
                </div>
              </div>
            </>
          )}

          {result && !result.success && (
            <div className="import-errors">
              {result.errors.map((err, i) => (
                <div key={i} className="error-item">
                  <span className="error-icon">⚠️</span>
                  {err}
                </div>
              ))}
            </div>
          )}

          {step === 'preview' && result?.success && (
            <>
              {/* Log Selection */}
              <div className="log-selection-section">
                <div className="log-selection-header">
                  <span className="log-selection-label">Import to:</span>
                  {loadingLogs && <span className="loading-indicator">Loading...</span>}
                </div>

                {availableLogs.length > 0 ? (
                  <div className="log-selection-grid">
                    {availableLogs.map(log => {
                      const isRetiring = log.lifecycleState === 'archived' && !!log.retireScheduledAt;
                      const isSelectable = !isRetiring;

                      return (
                      <div
                        key={log.id}
                        className={`log-option ${targetLogId === log.id ? 'selected' : ''} ${log.lifecycleState} ${isRetiring ? 'retiring' : ''}`}
                        onClick={() => isSelectable && setTargetLogId(log.id)}
                        style={{ cursor: isSelectable ? 'pointer' : 'not-allowed', opacity: isRetiring ? 0.5 : 1 }}
                        title={isRetiring ? 'This log is scheduled for retirement and cannot receive imports' : undefined}
                      >
                        <div className="log-option-header">
                          <span className="log-name">{log.name}</span>
                          <span className={`log-state-badge ${log.lifecycleState} ${isRetiring ? 'retiring' : ''}`}>
                            {isRetiring ? 'Retiring' : log.lifecycleState === 'active' ? 'Active' : 'Archived'}
                          </span>
                        </div>
                        {log.description && (
                          <div className="log-description">{log.description}</div>
                        )}
                        <div className="log-meta">
                          <span>{log.totalTradeCount} trades</span>
                          {log.openPositionCount > 0 && (
                            <span className="open-positions">{log.openPositionCount} open</span>
                          )}
                          {!log.mlIncluded && (
                            <span className="ml-excluded">ML excluded</span>
                          )}
                        </div>
                      </div>
                      );
                    })}
                  </div>
                ) : !loadingLogs ? (
                  <div className="no-logs-warning">
                    No trade logs available. Create a log first.
                  </div>
                ) : null}

                {/* Archived log warning */}
                {targetLogId && availableLogs.find(l => l.id === targetLogId)?.lifecycleState === 'archived' && (
                  <div className="archived-log-notice">
                    <span className="notice-icon">ℹ️</span>
                    This log is archived. Imported trades will not affect live alerts or learning unless the log is reactivated.
                  </div>
                )}

                {/* Import recommendation */}
                {recommendation?.recommend_archived && recommendation.reason && (
                  <div className="import-recommendation">
                    <span className="recommendation-icon">💡</span>
                    <div className="recommendation-content">
                      <div className="recommendation-text">{recommendation.reason}</div>
                      <div className="recommendation-hint">
                        Would you like to place it in a separate archived log?
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="import-summary">
                <div className="summary-item">
                  <span className="label">Platform:</span>
                  <span className="value">{platform ? PLATFORM_LABELS[platform] : 'Unknown'}</span>
                </div>
                <div className="summary-item">
                  <span className="label">File:</span>
                  <span className="value">{file?.name}</span>
                </div>
                <div className="summary-item">
                  <span className="label">Trades Found:</span>
                  <span className="value">{result.trades.length}</span>
                </div>
                <div className="summary-item">
                  <span className="label">Selected:</span>
                  <span className="value">{selectedTrades.size}</span>
                </div>
              </div>

              {result.warnings.length > 0 && (
                <div className="import-warnings">
                  {result.warnings.slice(0, 5).map((warn, i) => (
                    <div key={i} className="warning-item">
                      <span className="warning-icon">ℹ️</span>
                      {warn}
                    </div>
                  ))}
                  {result.warnings.length > 5 && (
                    <div className="warning-more">
                      +{result.warnings.length - 5} more warnings
                    </div>
                  )}
                </div>
              )}

              <div className="trades-list">
                <div className="trades-header">
                  <label className="select-all">
                    <input
                      type="checkbox"
                      checked={selectedTrades.size === result.trades.length}
                      onChange={toggleAll}
                    />
                    Select All
                  </label>
                </div>

                <div className="trades-scroll">
                  {result.trades.map(trade => {
                    const strategy = recognizeStrategy(trade.legs);
                    const strategyLabel = strategy.type === 'butterfly' ? 'BF' :
                                         strategy.type === 'vertical' ? 'VS' :
                                         strategy.type === 'iron_condor' ? 'IC' :
                                         strategy.type === 'straddle' ? 'STR' :
                                         strategy.type === 'strangle' ? 'STRG' :
                                         strategy.type === 'single' ? 'SGL' : '?';
                    return (
                      <div
                        key={trade.id}
                        className={`trade-row ${selectedTrades.has(trade.id) ? 'selected' : ''}`}
                        onClick={() => toggleTrade(trade.id)}
                      >
                        <input
                          type="checkbox"
                          checked={selectedTrades.has(trade.id)}
                          onChange={() => toggleTrade(trade.id)}
                        />
                        <div className="trade-info">
                          <div className="trade-header-row">
                            <span className="trade-date">{trade.tradeDate}</span>
                            <span className={`strategy-badge ${strategy.type}`}>
                              {strategyLabel} {strategy.strike}{strategy.width > 0 ? `/${strategy.width}` : ''} {strategy.side.charAt(0).toUpperCase()}
                            </span>
                          </div>
                          <div className="trade-legs">
                            {trade.legs.map((leg, i) => (
                              <span key={i} className={`leg ${leg.quantity > 0 ? 'long' : 'short'}`}>
                                {formatLeg(leg)}
                              </span>
                            ))}
                          </div>
                          <div className="trade-price">
                            ${Math.abs(trade.totalPrice / 100).toFixed(2)}
                            <span className={`effect ${trade.positionEffect}`}>{trade.positionEffect}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="trade-import-footer">
          {step === 'select-platform' && (
            <button className="btn btn-cancel" onClick={handleClose}>
              Cancel
            </button>
          )}

          {step === 'upload' && (
            <>
              <button className="btn btn-back" onClick={handleBack}>
                ← Back
              </button>
              <button className="btn btn-cancel" onClick={handleClose}>
                Cancel
              </button>
            </>
          )}

          {step === 'preview' && (
            <>
              <button className="btn btn-back" onClick={handleBack}>
                ← Back
              </button>
              <button
                className="btn btn-import"
                onClick={handleImport}
                disabled={selectedTrades.size === 0 || !targetLogId}
                title={!targetLogId ? 'Select a target log' : undefined}
              >
                Import {selectedTrades.size} Trade{selectedTrades.size !== 1 ? 's' : ''}
                {targetLogId && availableLogs.length > 0 && (
                  <span className="import-target">
                    → {availableLogs.find(l => l.id === targetLogId)?.name}
                  </span>
                )}
              </button>
            </>
          )}
        </div>
      </div>

      <style>{`
        .trade-import-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .trade-import-modal {
          background: #1a1a2e;
          border: 1px solid #333;
          border-radius: 8px;
          width: 600px;
          max-width: 90vw;
          max-height: 80vh;
          display: flex;
          flex-direction: column;
        }

        .trade-import-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-bottom: 1px solid #333;
        }

        .trade-import-header h3 {
          margin: 0;
          font-size: 18px;
          color: #e2e8f0;
        }

        .close-btn {
          background: none;
          border: none;
          color: #666;
          font-size: 24px;
          cursor: pointer;
          padding: 0;
          line-height: 1;
        }

        .close-btn:hover {
          color: #fff;
        }

        .trade-import-body {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
        }

        .platform-selection {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .platform-prompt {
          font-size: 14px;
          color: #9ca3af;
          text-align: center;
        }

        .platform-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
        }

        .platform-card {
          background: #0f0f1a;
          border: 1px solid #333;
          border-radius: 8px;
          padding: 16px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .platform-card:hover:not(.disabled) {
          border-color: #3b82f6;
          background: rgba(59, 130, 246, 0.1);
        }

        .platform-card.disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .platform-name {
          font-size: 15px;
          font-weight: 600;
          color: #e2e8f0;
          margin-bottom: 4px;
        }

        .platform-desc {
          font-size: 12px;
          color: #666;
          margin-bottom: 8px;
        }

        .platform-status {
          font-size: 11px;
          font-weight: 500;
          padding: 2px 8px;
          border-radius: 4px;
          display: inline-block;
        }

        .platform-status.supported {
          background: rgba(74, 222, 128, 0.2);
          color: #4ade80;
        }

        .platform-status.coming-soon {
          background: rgba(156, 163, 175, 0.2);
          color: #9ca3af;
        }

        .platform-card.ai-card {
          border-color: #8b5cf6;
          background: rgba(139, 92, 246, 0.1);
          position: relative;
        }

        .platform-card.ai-card:hover {
          border-color: #a78bfa;
          background: rgba(139, 92, 246, 0.2);
        }

        .ai-badge {
          position: absolute;
          top: -8px;
          right: -8px;
          background: linear-gradient(135deg, #8b5cf6, #6366f1);
          color: white;
          font-size: 10px;
          font-weight: 700;
          padding: 2px 8px;
          border-radius: 10px;
        }

        .platform-status.ai-status {
          background: rgba(139, 92, 246, 0.2);
          color: #a78bfa;
        }

        .ai-analyzing {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 60px 20px;
          text-align: center;
        }

        .ai-spinner {
          width: 48px;
          height: 48px;
          border: 3px solid #333;
          border-top-color: #8b5cf6;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin-bottom: 20px;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .ai-status-text {
          font-size: 16px;
          color: #e2e8f0;
          margin-bottom: 8px;
        }

        .ai-substatus {
          font-size: 13px;
          color: #666;
        }

        .platform-selected {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          background: #0f0f1a;
          border-radius: 6px;
          margin-bottom: 12px;
        }

        .platform-label {
          font-size: 12px;
          color: #666;
        }

        .platform-value {
          font-size: 14px;
          font-weight: 500;
          color: #3b82f6;
        }

        .import-instructions {
          font-size: 13px;
          color: #9ca3af;
          margin-bottom: 16px;
          padding: 12px;
          background: rgba(59, 130, 246, 0.1);
          border: 1px solid rgba(59, 130, 246, 0.2);
          border-radius: 6px;
        }

        .template-section {
          margin-bottom: 16px;
          padding: 16px;
          background: #0f0f1a;
          border: 1px solid #333;
          border-radius: 6px;
        }

        .btn-template {
          background: #3b82f6;
          color: #fff;
          border: none;
          padding: 8px 16px;
          border-radius: 6px;
          font-size: 13px;
          cursor: pointer;
          margin-bottom: 12px;
        }

        .btn-template:hover {
          background: #2563eb;
        }

        .template-help {
          font-size: 12px;
          color: #9ca3af;
        }

        .template-columns {
          margin-bottom: 6px;
        }

        .template-columns strong {
          color: #e2e8f0;
        }

        .template-note {
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid #333;
          font-style: italic;
          color: #666;
        }

        .file-drop-zone {
          border: 2px dashed #444;
          border-radius: 8px;
          padding: 40px;
          text-align: center;
          cursor: pointer;
          transition: all 0.2s;
        }

        .file-drop-zone:hover {
          border-color: #3b82f6;
          background: rgba(59, 130, 246, 0.1);
        }

        .drop-icon {
          font-size: 48px;
          margin-bottom: 16px;
        }

        .drop-text {
          font-size: 16px;
          color: #e2e8f0;
          margin-bottom: 8px;
        }

        .supported-platforms {
          font-size: 12px;
          color: #666;
        }

        .import-errors {
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.3);
          border-radius: 6px;
          padding: 12px;
          margin-bottom: 16px;
        }

        .error-item {
          color: #f87171;
          font-size: 13px;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .import-warnings {
          background: rgba(250, 204, 21, 0.1);
          border: 1px solid rgba(250, 204, 21, 0.3);
          border-radius: 6px;
          padding: 12px;
          margin-bottom: 16px;
        }

        .warning-item {
          color: #fbbf24;
          font-size: 12px;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .warning-more {
          color: #666;
          font-size: 11px;
          margin-top: 8px;
        }

        .import-summary {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
          margin-bottom: 16px;
          padding: 12px;
          background: #0f0f1a;
          border-radius: 6px;
        }

        .summary-item {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .summary-item .label {
          font-size: 11px;
          color: #666;
          text-transform: uppercase;
        }

        .summary-item .value {
          font-size: 14px;
          color: #e2e8f0;
        }

        .trades-list {
          border: 1px solid #333;
          border-radius: 6px;
          overflow: hidden;
        }

        .trades-header {
          padding: 8px 12px;
          background: #0f0f1a;
          border-bottom: 1px solid #333;
        }

        .select-all {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: #9ca3af;
          cursor: pointer;
        }

        .trades-scroll {
          max-height: 300px;
          overflow-y: auto;
        }

        .trade-row {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px;
          border-bottom: 1px solid #222;
          cursor: pointer;
          transition: background 0.15s;
        }

        .trade-row:hover {
          background: rgba(59, 130, 246, 0.1);
        }

        .trade-row.selected {
          background: rgba(59, 130, 246, 0.15);
        }

        .trade-row:last-child {
          border-bottom: none;
        }

        .trade-info {
          flex: 1;
          min-width: 0;
        }

        .trade-header-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 4px;
        }

        .trade-date {
          font-size: 12px;
          color: #666;
        }

        .strategy-badge {
          font-size: 11px;
          font-weight: 600;
          padding: 2px 8px;
          border-radius: 4px;
          background: #333;
          color: #9ca3af;
        }

        .strategy-badge.butterfly {
          background: rgba(139, 92, 246, 0.2);
          color: #a78bfa;
        }

        .strategy-badge.vertical {
          background: rgba(59, 130, 246, 0.2);
          color: #60a5fa;
        }

        .strategy-badge.iron_condor {
          background: rgba(234, 179, 8, 0.2);
          color: #fbbf24;
        }

        .strategy-badge.single {
          background: rgba(107, 114, 128, 0.2);
          color: #9ca3af;
        }

        .trade-legs {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 4px;
        }

        .leg {
          font-size: 12px;
          font-family: monospace;
          padding: 2px 6px;
          border-radius: 3px;
        }

        .leg.long {
          background: rgba(74, 222, 128, 0.2);
          color: #4ade80;
        }

        .leg.short {
          background: rgba(248, 113, 113, 0.2);
          color: #f87171;
        }

        .trade-price {
          font-size: 13px;
          color: #e2e8f0;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .trade-price .effect {
          font-size: 10px;
          text-transform: uppercase;
          padding: 2px 6px;
          border-radius: 3px;
          background: #333;
          color: #9ca3af;
        }

        .trade-price .effect.open {
          background: rgba(74, 222, 128, 0.2);
          color: #4ade80;
        }

        .trade-price .effect.close {
          background: rgba(248, 113, 113, 0.2);
          color: #f87171;
        }

        .trade-import-footer {
          display: flex;
          justify-content: flex-end;
          gap: 12px;
          padding: 16px 20px;
          border-top: 1px solid #333;
        }

        .btn {
          padding: 8px 16px;
          border-radius: 6px;
          font-size: 14px;
          cursor: pointer;
          border: none;
        }

        .btn-cancel, .btn-back {
          background: #333;
          color: #e2e8f0;
        }

        .btn-import {
          background: #3b82f6;
          color: #fff;
        }

        .btn-import:disabled {
          background: #333;
          color: #666;
          cursor: not-allowed;
        }

        .btn:hover:not(:disabled) {
          filter: brightness(1.1);
        }

        /* Log Selection Styles */
        .log-selection-section {
          margin-bottom: 16px;
          padding-bottom: 16px;
          border-bottom: 1px solid #333;
        }

        .log-selection-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
        }

        .log-selection-label {
          font-size: 14px;
          font-weight: 600;
          color: #e2e8f0;
        }

        .loading-indicator {
          font-size: 12px;
          color: #666;
        }

        .log-selection-grid {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 200px;
          overflow-y: auto;
        }

        .log-option {
          padding: 12px;
          background: #0f0f1a;
          border: 1px solid #333;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s;
        }

        .log-option:hover {
          border-color: #555;
        }

        .log-option.selected {
          border-color: #3b82f6;
          background: rgba(59, 130, 246, 0.1);
        }

        .log-option.archived {
          opacity: 0.8;
        }

        .log-option-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 4px;
        }

        .log-name {
          font-size: 14px;
          font-weight: 500;
          color: #e2e8f0;
        }

        .log-state-badge {
          font-size: 10px;
          padding: 2px 8px;
          border-radius: 10px;
          font-weight: 600;
        }

        .log-state-badge.active {
          background: rgba(34, 197, 94, 0.2);
          color: #4ade80;
        }

        .log-state-badge.archived {
          background: rgba(156, 163, 175, 0.2);
          color: #9ca3af;
        }

        .log-state-badge.retiring {
          background: rgba(239, 68, 68, 0.2);
          color: #f87171;
        }

        .log-option.retiring {
          border-color: rgba(239, 68, 68, 0.3);
          background: rgba(239, 68, 68, 0.05);
        }

        .log-option.retiring:hover {
          border-color: rgba(239, 68, 68, 0.4);
          cursor: not-allowed;
        }

        .log-description {
          font-size: 12px;
          color: #9ca3af;
          margin-bottom: 4px;
        }

        .log-meta {
          display: flex;
          gap: 12px;
          font-size: 11px;
          color: #666;
        }

        .log-meta .open-positions {
          color: #f59e0b;
        }

        .log-meta .ml-excluded {
          color: #9ca3af;
        }

        .no-logs-warning {
          padding: 16px;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.3);
          border-radius: 6px;
          color: #f87171;
          font-size: 13px;
          text-align: center;
        }

        .archived-log-notice {
          display: flex;
          gap: 8px;
          padding: 10px 12px;
          background: rgba(59, 130, 246, 0.1);
          border: 1px solid rgba(59, 130, 246, 0.2);
          border-radius: 6px;
          margin-top: 12px;
          font-size: 12px;
          color: #93c5fd;
        }

        .notice-icon {
          flex-shrink: 0;
        }

        .import-recommendation {
          display: flex;
          gap: 10px;
          padding: 12px;
          background: rgba(251, 191, 36, 0.1);
          border: 1px solid rgba(251, 191, 36, 0.2);
          border-radius: 6px;
          margin-top: 12px;
        }

        .recommendation-icon {
          flex-shrink: 0;
          font-size: 16px;
        }

        .recommendation-content {
          flex: 1;
        }

        .recommendation-text {
          font-size: 13px;
          color: #fcd34d;
          margin-bottom: 4px;
        }

        .recommendation-hint {
          font-size: 12px;
          color: #9ca3af;
        }

        .import-target {
          margin-left: 8px;
          font-size: 11px;
          opacity: 0.8;
        }

        /* Light theme */
        [data-theme="light"] .trade-import-overlay {
          background: rgba(0, 0, 0, 0.2);
          backdrop-filter: blur(2px);
        }

        [data-theme="light"] .trade-import-modal {
          background: #ffffff;
          border-color: #d1d1d6;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
        }

        [data-theme="light"] .trade-import-header {
          border-bottom-color: #e5e5ea;
          background: rgba(0, 0, 0, 0.02);
        }

        [data-theme="light"] .trade-import-header h3 {
          color: #1d1d1f;
        }

        [data-theme="light"] .close-btn {
          color: #86868b;
        }

        [data-theme="light"] .close-btn:hover {
          color: #1d1d1f;
        }

        [data-theme="light"] .platform-prompt {
          color: #6e6e73;
        }

        [data-theme="light"] .platform-card {
          background: #f5f5f7;
          border-color: #d1d1d6;
        }

        [data-theme="light"] .platform-card:hover:not(.disabled) {
          border-color: #007aff;
          background: rgba(0, 122, 255, 0.06);
        }

        [data-theme="light"] .platform-name {
          color: #1d1d1f;
        }

        [data-theme="light"] .platform-desc {
          color: #86868b;
        }

        [data-theme="light"] .platform-card.ai-card {
          background: rgba(139, 92, 246, 0.06);
        }

        [data-theme="light"] .platform-card.ai-card:hover {
          background: rgba(139, 92, 246, 0.1);
        }

        [data-theme="light"] .ai-spinner {
          border-color: #d1d1d6;
        }

        [data-theme="light"] .ai-status-text {
          color: #1d1d1f;
        }

        [data-theme="light"] .ai-substatus {
          color: #86868b;
        }

        [data-theme="light"] .platform-selected {
          background: #f5f5f7;
        }

        [data-theme="light"] .platform-label {
          color: #86868b;
        }

        [data-theme="light"] .import-instructions {
          color: #6e6e73;
          background: rgba(0, 122, 255, 0.06);
          border-color: rgba(0, 122, 255, 0.15);
        }

        [data-theme="light"] .template-section {
          background: #f5f5f7;
          border-color: #d1d1d6;
        }

        [data-theme="light"] .btn-template {
          background: #007aff;
        }

        [data-theme="light"] .btn-template:hover {
          background: #0066d6;
        }

        [data-theme="light"] .template-help {
          color: #6e6e73;
        }

        [data-theme="light"] .template-columns strong {
          color: #1d1d1f;
        }

        [data-theme="light"] .template-note {
          border-top-color: #e5e5ea;
          color: #86868b;
        }

        [data-theme="light"] .file-drop-zone {
          border-color: #d1d1d6;
        }

        [data-theme="light"] .file-drop-zone:hover {
          border-color: #007aff;
          background: rgba(0, 122, 255, 0.04);
        }

        [data-theme="light"] .drop-text {
          color: #1d1d1f;
        }

        [data-theme="light"] .supported-platforms {
          color: #86868b;
        }

        [data-theme="light"] .import-summary {
          background: #f5f5f7;
        }

        [data-theme="light"] .summary-item .label {
          color: #86868b;
        }

        [data-theme="light"] .summary-item .value {
          color: #1d1d1f;
        }

        [data-theme="light"] .trades-list {
          border-color: #d1d1d6;
        }

        [data-theme="light"] .trades-header {
          background: #f5f5f7;
          border-bottom-color: #d1d1d6;
        }

        [data-theme="light"] .select-all {
          color: #6e6e73;
        }

        [data-theme="light"] .trade-row {
          border-bottom-color: #e5e5ea;
        }

        [data-theme="light"] .trade-row:hover {
          background: rgba(0, 122, 255, 0.04);
        }

        [data-theme="light"] .trade-row.selected {
          background: rgba(0, 122, 255, 0.08);
        }

        [data-theme="light"] .trade-date {
          color: #86868b;
        }

        [data-theme="light"] .strategy-badge {
          background: #e5e5ea;
          color: #6e6e73;
        }

        [data-theme="light"] .trade-price {
          color: #1d1d1f;
        }

        [data-theme="light"] .trade-price .effect {
          background: #e5e5ea;
          color: #6e6e73;
        }

        [data-theme="light"] .trade-import-footer {
          border-top-color: #e5e5ea;
        }

        [data-theme="light"] .btn-cancel,
        [data-theme="light"] .btn-back {
          background: #e5e5ea;
          color: #1d1d1f;
        }

        [data-theme="light"] .btn-import {
          background: #007aff;
        }

        [data-theme="light"] .btn-import:disabled {
          background: #e5e5ea;
          color: #aeaeb2;
        }

        [data-theme="light"] .log-selection-section {
          border-bottom-color: #e5e5ea;
        }

        [data-theme="light"] .log-selection-label {
          color: #1d1d1f;
        }

        [data-theme="light"] .loading-indicator {
          color: #86868b;
        }

        [data-theme="light"] .log-option {
          background: #f5f5f7;
          border-color: #d1d1d6;
        }

        [data-theme="light"] .log-option:hover {
          border-color: #aeaeb2;
        }

        [data-theme="light"] .log-option.selected {
          border-color: #007aff;
          background: rgba(0, 122, 255, 0.06);
        }

        [data-theme="light"] .log-name {
          color: #1d1d1f;
        }

        [data-theme="light"] .log-description {
          color: #6e6e73;
        }

        [data-theme="light"] .log-meta {
          color: #86868b;
        }

        [data-theme="light"] .warning-more {
          color: #86868b;
        }

        [data-theme="light"] .archived-log-notice {
          background: rgba(0, 122, 255, 0.06);
          border-color: rgba(0, 122, 255, 0.15);
          color: #007aff;
        }

        /* Light scrollbar */
        [data-theme="light"] .trades-scroll::-webkit-scrollbar-thumb {
          background: #c7c7cc;
        }

        [data-theme="light"] .trades-scroll::-webkit-scrollbar-thumb:hover {
          background: #aeaeb2;
        }

        [data-theme="light"] .log-selection-grid::-webkit-scrollbar-thumb {
          background: #c7c7cc;
        }

        [data-theme="light"] .log-selection-grid::-webkit-scrollbar-thumb:hover {
          background: #aeaeb2;
        }
      `}</style>
    </div>
  );
}
