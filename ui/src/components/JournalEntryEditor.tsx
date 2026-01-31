// src/components/JournalEntryEditor.tsx
import { useState, useEffect } from 'react';
import type { JournalEntry, JournalTrade, TradeRef } from '../hooks/useJournal';

interface JournalEntryEditorProps {
  date: string;
  entry: JournalEntry | null;
  loading: boolean;
  onSave: (content: string, isPlaybook: boolean) => Promise<boolean>;
  // Trade linking
  tradesForDate: JournalTrade[];
  loadingTrades: boolean;
  onLinkTrade: (entryId: string, tradeId: string) => Promise<boolean>;
  onUnlinkTrade: (refId: string) => Promise<boolean>;
}

const WEEKDAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const weekday = WEEKDAY_NAMES[date.getDay()];
  const monthName = MONTH_NAMES[month - 1];
  return `${weekday}, ${monthName} ${day}, ${year}`;
}

function formatPnl(pnl: number | null): string {
  if (pnl === null) return '-';
  const sign = pnl >= 0 ? '+' : '';
  return `${sign}$${pnl.toFixed(0)}`;
}

function formatTime(isoTime: string): string {
  const date = new Date(isoTime);
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

export default function JournalEntryEditor({
  date,
  entry,
  loading,
  onSave,
  tradesForDate,
  loadingTrades,
  onLinkTrade,
  onUnlinkTrade,
}: JournalEntryEditorProps) {
  const [content, setContent] = useState('');
  const [isPlaybook, setIsPlaybook] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [linkingTradeId, setLinkingTradeId] = useState<string | null>(null);

  // Sync form state with entry data
  useEffect(() => {
    if (entry) {
      setContent(entry.content || '');
      setIsPlaybook(entry.is_playbook_material);
    } else {
      setContent('');
      setIsPlaybook(false);
    }
    setDirty(false);
  }, [entry, date]);

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value);
    setDirty(true);
  };

  const handlePlaybookChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setIsPlaybook(e.target.checked);
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    const success = await onSave(content, isPlaybook);
    setSaving(false);
    if (success) {
      setDirty(false);
    }
  };

  const handleLinkTrade = async (tradeId: string) => {
    if (!entry) return;
    setLinkingTradeId(tradeId);
    await onLinkTrade(entry.id, tradeId);
    setLinkingTradeId(null);
  };

  const handleUnlinkTrade = async (refId: string) => {
    await onUnlinkTrade(refId);
  };

  // Keyboard shortcut: Cmd/Ctrl + S to save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (dirty && !saving) {
          handleSave();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [dirty, saving, content, isPlaybook]);

  // Get list of already linked trade IDs
  const linkedTradeIds = new Set(entry?.trade_refs?.map(r => r.trade_id) || []);

  // Separate trades into linked and available
  const linkedTrades = tradesForDate.filter(t => linkedTradeIds.has(t.id));
  const availableTrades = tradesForDate.filter(t => !linkedTradeIds.has(t.id));

  if (loading) {
    return (
      <div className="journal-entry-editor">
        <div className="entry-header">
          <h3>{formatDate(date)}</h3>
        </div>
        <div className="entry-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="journal-entry-editor">
      <div className="entry-header">
        <h3>{formatDate(date)}</h3>
        {entry && (
          <span className="entry-meta">
            Last updated: {new Date(entry.updated_at).toLocaleString()}
          </span>
        )}
      </div>

      <div className="entry-body">
        <textarea
          className="entry-content"
          value={content}
          onChange={handleContentChange}
          placeholder="What happened today? What did you learn?"
          autoFocus
        />
      </div>

      <div className="entry-footer">
        <label className="playbook-toggle">
          <input
            type="checkbox"
            checked={isPlaybook}
            onChange={handlePlaybookChange}
          />
          <span>Playbook Material</span>
        </label>

        <div className="entry-actions">
          {dirty && <span className="unsaved-indicator">Unsaved changes</span>}
          <button
            className="save-btn"
            onClick={handleSave}
            disabled={saving || !dirty}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {/* Trades Section */}
      <div className="entry-trades-section">
        <h4>Trades</h4>

        {/* Linked Trades */}
        {entry && entry.trade_refs && entry.trade_refs.length > 0 && (
          <div className="linked-trades">
            <span className="trades-label">Linked</span>
            <ul className="trade-list">
              {entry.trade_refs.map(ref => {
                const trade = tradesForDate.find(t => t.id === ref.trade_id);
                return (
                  <li key={ref.id} className="trade-item linked">
                    <div className="trade-info">
                      <span className="trade-symbol">{trade?.symbol || ref.trade_id.slice(0, 8)}</span>
                      {trade && (
                        <>
                          <span className="trade-details">
                            {trade.side} {trade.strategy} @ {formatTime(trade.entry_time)}
                          </span>
                          <span className={`trade-pnl ${(trade.pnl_dollars ?? 0) >= 0 ? 'profit' : 'loss'}`}>
                            {formatPnl(trade.pnl_dollars)}
                          </span>
                        </>
                      )}
                    </div>
                    <button
                      className="unlink-btn"
                      onClick={() => handleUnlinkTrade(ref.id)}
                      title="Unlink trade"
                    >
                      &times;
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Available Trades to Link */}
        {entry && availableTrades.length > 0 && (
          <div className="available-trades">
            <span className="trades-label">Available</span>
            <ul className="trade-list">
              {availableTrades.map(trade => (
                <li key={trade.id} className="trade-item available">
                  <div className="trade-info">
                    <span className="trade-symbol">{trade.symbol}</span>
                    <span className="trade-details">
                      {trade.side} {trade.strategy} @ {formatTime(trade.entry_time)}
                    </span>
                    <span className={`trade-pnl ${(trade.pnl_dollars ?? 0) >= 0 ? 'profit' : 'loss'}`}>
                      {formatPnl(trade.pnl_dollars)}
                    </span>
                  </div>
                  <button
                    className="link-btn"
                    onClick={() => handleLinkTrade(trade.id)}
                    disabled={linkingTradeId === trade.id}
                    title="Link trade"
                  >
                    {linkingTradeId === trade.id ? '...' : '+'}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* No trades message */}
        {!loadingTrades && tradesForDate.length === 0 && (
          <div className="no-trades">No trades on this day</div>
        )}

        {/* Must save first message */}
        {!entry && tradesForDate.length > 0 && (
          <div className="no-trades">Save entry first to link trades</div>
        )}

        {loadingTrades && (
          <div className="no-trades">Loading trades...</div>
        )}
      </div>

      {entry && entry.attachments && entry.attachments.length > 0 && (
        <div className="entry-attachments">
          <h4>Attachments</h4>
          <ul>
            {entry.attachments.map(att => (
              <li key={att.id}>
                {att.filename}
                {att.file_size && <span className="att-size"> ({Math.round(att.file_size / 1024)}KB)</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
