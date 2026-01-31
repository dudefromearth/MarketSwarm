// src/components/JournalEntryEditor.tsx
import { useState, useEffect, useCallback } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Highlight from '@tiptap/extension-highlight';
import type { JournalEntry, JournalTrade } from '../hooks/useJournal';

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

// Toolbar button component
function ToolbarButton({
  onClick,
  isActive = false,
  disabled = false,
  title,
  children,
}: {
  onClick: () => void;
  isActive?: boolean;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`toolbar-btn ${isActive ? 'active' : ''}`}
      title={title}
    >
      {children}
    </button>
  );
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
  const [isPlaybook, setIsPlaybook] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [linkingTradeId, setLinkingTradeId] = useState<string | null>(null);

  // Initialize TipTap editor
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
      }),
      Underline,
      TextAlign.configure({
        types: ['heading', 'paragraph'],
      }),
      Highlight.configure({
        multicolor: false,
      }),
    ],
    content: '',
    onUpdate: () => {
      setDirty(true);
    },
    editorProps: {
      attributes: {
        class: 'entry-content-editor',
      },
    },
  });

  // Sync form state with entry data
  useEffect(() => {
    if (editor) {
      if (entry) {
        editor.commands.setContent(entry.content || '');
        setIsPlaybook(entry.is_playbook_material);
      } else {
        editor.commands.setContent('');
        setIsPlaybook(false);
      }
      setDirty(false);
    }
  }, [entry, date, editor]);

  const handlePlaybookChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setIsPlaybook(e.target.checked);
    setDirty(true);
  };

  const handleSave = useCallback(async () => {
    if (!editor) return;
    setSaving(true);
    const content = editor.getHTML();
    const success = await onSave(content, isPlaybook);
    setSaving(false);
    if (success) {
      setDirty(false);
    }
  }, [editor, isPlaybook, onSave]);

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
  }, [dirty, saving, handleSave]);

  // Get list of already linked trade IDs
  const linkedTradeIds = new Set(entry?.trade_refs?.map(r => r.trade_id) || []);

  // Get available trades (not yet linked)
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

      {/* Rich Text Toolbar */}
      {editor && (
        <div className="editor-toolbar">
          <div className="toolbar-group">
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleBold().run()}
              isActive={editor.isActive('bold')}
              title="Bold (Cmd+B)"
            >
              <strong>B</strong>
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleItalic().run()}
              isActive={editor.isActive('italic')}
              title="Italic (Cmd+I)"
            >
              <em>I</em>
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleUnderline().run()}
              isActive={editor.isActive('underline')}
              title="Underline (Cmd+U)"
            >
              <span style={{ textDecoration: 'underline' }}>U</span>
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleStrike().run()}
              isActive={editor.isActive('strike')}
              title="Strikethrough"
            >
              <span style={{ textDecoration: 'line-through' }}>S</span>
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleHighlight().run()}
              isActive={editor.isActive('highlight')}
              title="Highlight"
            >
              <span style={{ background: '#fbbf24', color: '#000', padding: '0 2px' }}>H</span>
            </ToolbarButton>
          </div>

          <div className="toolbar-separator" />

          <div className="toolbar-group">
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
              isActive={editor.isActive('heading', { level: 1 })}
              title="Heading 1"
            >
              H1
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
              isActive={editor.isActive('heading', { level: 2 })}
              title="Heading 2"
            >
              H2
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
              isActive={editor.isActive('heading', { level: 3 })}
              title="Heading 3"
            >
              H3
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().setParagraph().run()}
              isActive={editor.isActive('paragraph')}
              title="Paragraph"
            >
              P
            </ToolbarButton>
          </div>

          <div className="toolbar-separator" />

          <div className="toolbar-group">
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleBulletList().run()}
              isActive={editor.isActive('bulletList')}
              title="Bullet List"
            >
              &bull;
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleOrderedList().run()}
              isActive={editor.isActive('orderedList')}
              title="Numbered List"
            >
              1.
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleBlockquote().run()}
              isActive={editor.isActive('blockquote')}
              title="Quote"
            >
              "
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().toggleCodeBlock().run()}
              isActive={editor.isActive('codeBlock')}
              title="Code Block"
            >
              {'</>'}
            </ToolbarButton>
          </div>

          <div className="toolbar-separator" />

          <div className="toolbar-group">
            <ToolbarButton
              onClick={() => editor.chain().focus().setTextAlign('left').run()}
              isActive={editor.isActive({ textAlign: 'left' })}
              title="Align Left"
            >
              &#8676;
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().setTextAlign('center').run()}
              isActive={editor.isActive({ textAlign: 'center' })}
              title="Align Center"
            >
              &#8596;
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().setTextAlign('right').run()}
              isActive={editor.isActive({ textAlign: 'right' })}
              title="Align Right"
            >
              &#8677;
            </ToolbarButton>
          </div>

          <div className="toolbar-separator" />

          <div className="toolbar-group">
            <ToolbarButton
              onClick={() => editor.chain().focus().setHorizontalRule().run()}
              title="Horizontal Rule"
            >
              &#8213;
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().undo().run()}
              disabled={!editor.can().undo()}
              title="Undo (Cmd+Z)"
            >
              &#8630;
            </ToolbarButton>
            <ToolbarButton
              onClick={() => editor.chain().focus().redo().run()}
              disabled={!editor.can().redo()}
              title="Redo (Cmd+Shift+Z)"
            >
              &#8631;
            </ToolbarButton>
          </div>
        </div>
      )}

      <div className="entry-body">
        <EditorContent editor={editor} className="entry-content-wrapper" />
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
