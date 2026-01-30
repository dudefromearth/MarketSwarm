/**
 * ADIPanel - AI Data Interface export panel.
 *
 * Provides buttons to:
 * - Copy snapshot to clipboard (for Vexy)
 * - Download as JSON, CSV, or Text
 * - Preview current snapshot
 */

import { useState } from 'react';
import { useADI, type ExportFormat } from '../hooks/useADI';

interface ADIPanelProps {
  compact?: boolean;
}

export default function ADIPanel({ compact = false }: ADIPanelProps) {
  const { loading, copyToClipboard, downloadSnapshot, fetchSnapshot, snapshot } = useADI();
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState<string>('');

  const handleCopy = async () => {
    const success = await copyToClipboard('text');
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = async (format: ExportFormat) => {
    await downloadSnapshot(format);
  };

  const handlePreview = async () => {
    const snap = await fetchSnapshot(true);
    if (snap) {
      setPreviewContent(JSON.stringify(snap, null, 2));
      setShowPreview(true);
    }
  };

  if (compact) {
    return (
      <div className="adi-panel-compact">
        <button
          className="adi-copy-btn"
          onClick={handleCopy}
          disabled={loading}
          title="Copy snapshot to clipboard for Vexy"
        >
          {copied ? '✓ Copied' : '📋 Copy to Vexy'}
        </button>
        <div className="adi-download-dropdown">
          <button className="adi-download-btn" title="Download snapshot">
            ⬇ Export
          </button>
          <div className="adi-dropdown-content">
            <button onClick={() => handleDownload('json')}>JSON</button>
            <button onClick={() => handleDownload('csv')}>CSV</button>
            <button onClick={() => handleDownload('text')}>Text</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="adi-panel">
      <div className="adi-panel-header">
        <h4>AI Data Interface</h4>
        <span className="adi-schema-version">v1.0</span>
      </div>

      <div className="adi-panel-content">
        <p className="adi-description">
          Export market structure data for AI analysis.
          Copy to clipboard and paste into Vexy or other AI assistants.
        </p>

        <div className="adi-actions">
          {/* Copy to Clipboard */}
          <button
            className={`adi-action-btn adi-copy-main ${copied ? 'copied' : ''}`}
            onClick={handleCopy}
            disabled={loading}
          >
            {copied ? '✓ Copied to Clipboard' : '📋 Copy to Vexy'}
          </button>

          {/* Download Options */}
          <div className="adi-download-section">
            <span className="adi-download-label">Download:</span>
            <div className="adi-download-buttons">
              <button
                className="adi-format-btn"
                onClick={() => handleDownload('json')}
                disabled={loading}
                title="JSON - Structured data for AI parsing"
              >
                JSON
              </button>
              <button
                className="adi-format-btn"
                onClick={() => handleDownload('csv')}
                disabled={loading}
                title="CSV - For spreadsheet analysis"
              >
                CSV
              </button>
              <button
                className="adi-format-btn"
                onClick={() => handleDownload('text')}
                disabled={loading}
                title="Text - Human-readable format"
              >
                TXT
              </button>
            </div>
          </div>

          {/* Preview */}
          <button
            className="adi-preview-btn"
            onClick={handlePreview}
            disabled={loading}
          >
            👁 Preview Snapshot
          </button>
        </div>

        {/* Last snapshot info */}
        {snapshot && (
          <div className="adi-snapshot-info">
            <span className="adi-snapshot-id">
              ID: {snapshot.metadata.snapshot_id}
            </span>
            <span className="adi-snapshot-time">
              {new Date(snapshot.metadata.timestamp_utc).toLocaleTimeString()}
            </span>
          </div>
        )}
      </div>

      {/* Preview Modal */}
      {showPreview && (
        <div className="adi-preview-overlay" onClick={() => setShowPreview(false)}>
          <div className="adi-preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="adi-preview-header">
              <h4>ADI Snapshot Preview</h4>
              <button onClick={() => setShowPreview(false)}>×</button>
            </div>
            <pre className="adi-preview-content">
              {previewContent}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
