/**
 * TosImportModal - Import ToS scripts to create strategies
 *
 * Accepts ToS order scripts for:
 * - Butterflies
 * - Verticals
 * - Singles
 */

import { useState, useCallback } from 'react';
import { parseTosScript, validateStrategy, type ParsedStrategy } from '../utils/tosParser';

interface TosImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (strategy: ParsedStrategy) => void;
}

export default function TosImportModal({ isOpen, onClose, onImport }: TosImportModalProps) {
  const [script, setScript] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ParsedStrategy | null>(null);

  const handleScriptChange = useCallback((value: string) => {
    setScript(value);
    setError(null);
    setPreview(null);

    if (!value.trim()) return;

    const result = parseTosScript(value);
    if (result.success && result.strategy) {
      const validationError = validateStrategy(result.strategy);
      if (validationError) {
        setError(validationError);
      } else {
        setPreview(result.strategy);
      }
    } else {
      setError(result.error || 'Failed to parse script');
    }
  }, []);

  const handleImport = useCallback(() => {
    if (!preview) return;
    onImport(preview);
    setScript('');
    setPreview(null);
    setError(null);
    onClose();
  }, [preview, onImport, onClose]);

  const handleClose = useCallback(() => {
    setScript('');
    setPreview(null);
    setError(null);
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div className="tos-import-overlay" onClick={handleClose}>
      <div className="tos-import-modal" onClick={e => e.stopPropagation()}>
        <div className="tos-import-header">
          <h3>Import ToS Script</h3>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        <div className="tos-import-body">
          <div className="script-input-section">
            <label>Paste ToS Order Script</label>
            <textarea
              value={script}
              onChange={e => handleScriptChange(e.target.value)}
              placeholder="BUY +1 BUTTERFLY SPX 100 (Weeklys) 31 JAN 26 5990/6000/6010 CALL @2.50"
              rows={3}
              autoFocus
            />
            <div className="supported-formats">
              <span>Supported:</span> Butterfly, Vertical, Single
            </div>
          </div>

          {error && (
            <div className="parse-error">
              <span className="error-icon">!</span>
              {error}
            </div>
          )}

          {preview && (
            <div className="strategy-preview">
              <h4>Parsed Strategy</h4>
              <div className="preview-grid">
                <div className="preview-item">
                  <span className="label">Type</span>
                  <span className="value type">{preview.strategy}</span>
                </div>
                <div className="preview-item">
                  <span className="label">Side</span>
                  <span className={`value side ${preview.side}`}>{preview.side}</span>
                </div>
                <div className="preview-item">
                  <span className="label">Strike</span>
                  <span className="value">{preview.strike}</span>
                </div>
                {preview.width > 0 && (
                  <div className="preview-item">
                    <span className="label">Width</span>
                    <span className="value">{preview.width}</span>
                  </div>
                )}
                <div className="preview-item">
                  <span className="label">Expiration</span>
                  <span className="value">{preview.expiration}</span>
                </div>
                <div className="preview-item">
                  <span className="label">DTE</span>
                  <span className="value">{preview.dte}</span>
                </div>
                <div className="preview-item">
                  <span className="label">Debit</span>
                  <span className="value price">
                    {preview.debit !== null ? `$${preview.debit.toFixed(2)}` : '-'}
                  </span>
                </div>
              </div>

              {/* Show strategy legs */}
              <div className="strategy-legs-preview">
                {preview.strategy === 'butterfly' && (
                  <>
                    <div className="leg buy">Buy 1x {preview.strike - preview.width} {preview.side}</div>
                    <div className="leg sell">Sell 2x {preview.strike} {preview.side}</div>
                    <div className="leg buy">Buy 1x {preview.strike + preview.width} {preview.side}</div>
                  </>
                )}
                {preview.strategy === 'vertical' && (
                  <>
                    <div className="leg buy">Buy 1x {preview.strike} {preview.side}</div>
                    <div className="leg sell">
                      Sell 1x {preview.side === 'call'
                        ? preview.strike + preview.width
                        : preview.strike - preview.width} {preview.side}
                    </div>
                  </>
                )}
                {preview.strategy === 'single' && (
                  <div className="leg buy">Buy 1x {preview.strike} {preview.side}</div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="tos-import-footer">
          <button className="btn btn-cancel" onClick={handleClose}>
            Cancel
          </button>
          <button
            className="btn btn-import"
            onClick={handleImport}
            disabled={!preview}
          >
            Add to Risk Graph
          </button>
        </div>
      </div>
    </div>
  );
}
