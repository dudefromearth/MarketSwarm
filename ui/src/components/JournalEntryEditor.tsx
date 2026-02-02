// src/components/JournalEntryEditor.tsx
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import type { Attachment } from '../hooks/useJournal';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Highlight from '@tiptap/extension-highlight';
import { Markdown } from 'tiptap-markdown';
import type { JournalEntry, JournalTrade, Retrospective } from '../hooks/useJournal';
import TradeDetailModal from './TradeDetailModal';
import type { Trade } from './TradeLogPanel';
import { useAuth } from '../AuthWrapper';

const JOURNAL_API = 'http://localhost:3002';

// Base props shared by both modes
interface BaseEditorProps {
  loading: boolean;
  onTradesUpdated?: () => void;
}

// Tag type for the selector
interface Tag {
  id: string;
  name: string;
  description: string | null;
  is_example: boolean;
  usage_count: number;
}

// Props for daily entry mode
interface EntryModeProps extends BaseEditorProps {
  mode: 'entry';
  date: string;
  entry: JournalEntry | null;
  onSave: (content: string, isPlaybook: boolean, tags: string[]) => Promise<boolean>;
  // Trade linking
  tradesForDate: JournalTrade[];
  loadingTrades: boolean;
  onLinkTrade: (entryId: string, tradeId: string) => Promise<boolean>;
  onUnlinkTrade: (refId: string) => Promise<boolean>;
  // Initial content for new entries (e.g., trade context line)
  initialContent?: string;
}

// Props for retrospective mode
interface RetroModeProps extends BaseEditorProps {
  mode: 'retrospective';
  retroType: 'weekly' | 'monthly';
  periodStart: string;
  periodEnd: string;
  retrospective: Retrospective | null;
  onSaveRetro: (retro: {
    retro_type: 'weekly' | 'monthly';
    period_start: string;
    period_end: string;
    content: string;
    is_playbook_material: boolean;
  }) => Promise<boolean>;
}

type JournalEntryEditorProps = EntryModeProps | RetroModeProps;

const WEEKDAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

// Journal Templates - disposable scaffolding for reflection
interface JournalTemplate {
  id: string;
  name: string;
  content: string;
  category: 'daily' | 'weekly' | 'monthly' | 'all';
}

const JOURNAL_TEMPLATES: JournalTemplate[] = [
  {
    id: 'end-of-day',
    name: 'End of Day',
    category: 'daily',
    content: `## End of Day Reflection

### Market Context
How did the market behave today? Any notable moves?


### What I Did Well
What trades or decisions am I proud of?


### What I Could Improve
Where did I deviate from my plan or make mistakes?


### Key Observations
Patterns, correlations, or insights worth noting.


### Tomorrow's Focus
What will I prioritize tomorrow?

`,
  },
  {
    id: 'trade-reflection',
    name: 'Trade Reflection',
    category: 'daily',
    content: `## Trade Reflection

### Setup
What was the thesis? What signal triggered entry?


### Execution
Did I follow my plan? Any deviations?


### Outcome
What happened? Was the result aligned with the process?


### Lessons
What would I do differently? What worked?

`,
  },
  {
    id: 'weekly-retro',
    name: 'Weekly Retrospective',
    category: 'weekly',
    content: `## Weekly Retrospective

### Performance Summary
Total trades, win rate, and P&L for the week.


### Best Trade
What setup worked? Why did it succeed?


### Worst Trade
What went wrong? Was it process or luck?


### Patterns Noticed
Recurring themes, market behaviors, or personal tendencies.


### Adjustments for Next Week
What will I do differently?

`,
  },
  {
    id: 'monthly-retro',
    name: 'Monthly Retrospective',
    category: 'monthly',
    content: `## Monthly Retrospective

### Month Overview
Trading days, total trades, and net P&L.


### Goals Review
What did I set out to accomplish? Did I achieve it?


### Biggest Wins
Best trades or improvements this month.


### Biggest Lessons
Key takeaways that will shape future trading.


### Process Changes
What am I doing differently now vs. start of month?


### Next Month Focus
Primary goals and areas of improvement.

`,
  },
  {
    id: 'pre-market',
    name: 'Pre-Market Plan',
    category: 'daily',
    content: `## Pre-Market Plan

### Overnight/Globex Summary
-

### Key Levels
- Resistance:
- Support:
- POC:

### Economic Calendar
-

### Today's Bias


### Scenarios
**If bullish:**

**If bearish:**

### Risk Parameters
- Max loss:
- Position size:

`,
  },
  {
    id: 'performance-deep-dive',
    name: 'Performance Deep Dive',
    category: 'all',
    content: `## Performance Analysis

### By Strategy
Which strategies performed best/worst?


### By Time of Day
When did I trade best? Morning, afternoon, or close?


### By Market Condition
How did I perform in trending vs range-bound markets?


### Key Insights
What patterns emerged from this analysis?

`,
  },
  {
    id: 'lessons-learned',
    name: 'Lessons Learned',
    category: 'all',
    content: `## Lessons Learned

### What Worked
Strategies, setups, or behaviors that led to good outcomes.


### What Didn't Work
Mistakes, bad habits, or losing patterns to avoid.


### Rules to Add/Modify
New rules or adjustments to existing rules.


### Habits to Build
Behaviors to reinforce and practice.


### Habits to Break
Patterns to eliminate from my trading.

`,
  },
];

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const weekday = WEEKDAY_NAMES[date.getDay()];
  const monthShort = MONTH_NAMES[month - 1].slice(0, 3);
  return `${weekday} · ${monthShort} ${day}, ${year}`;
}

function formatPeriod(type: 'weekly' | 'monthly', start: string, end: string): string {
  const [startYear, startMonth, startDay] = start.split('-').map(Number);
  const [, endMonth, endDay] = end.split('-').map(Number);

  if (type === 'weekly') {
    const startStr = `${MONTH_NAMES[startMonth - 1].slice(0, 3)} ${startDay}`;
    const endStr = startMonth === endMonth
      ? `${endDay}`
      : `${MONTH_NAMES[endMonth - 1].slice(0, 3)} ${endDay}`;
    return `Week of ${startStr}–${endStr}, ${startYear}`;
  } else {
    return `${MONTH_NAMES[startMonth - 1]} ${startYear}`;
  }
}

function formatPnl(pnlCents: number | null): string {
  if (pnlCents === null) return '-';
  const dollars = pnlCents / 100;
  const sign = dollars >= 0 ? '+' : '';
  return `${sign}$${Math.abs(dollars).toFixed(0)}`;
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

export default function JournalEntryEditor(props: JournalEntryEditorProps) {
  // Auth for role-based features
  const { isAdmin } = useAuth();

  // Extract common props
  const { mode, loading, onTradesUpdated } = props;

  // Mode-specific data
  const isEntryMode = mode === 'entry';
  const date = isEntryMode ? props.date : undefined;
  const entry = isEntryMode ? props.entry : undefined;
  const onSave = isEntryMode ? props.onSave : undefined;
  const tradesForDate = isEntryMode ? props.tradesForDate : [];
  const loadingTrades = isEntryMode ? props.loadingTrades : false;
  const onLinkTrade = isEntryMode ? props.onLinkTrade : undefined;
  const onUnlinkTrade = isEntryMode ? props.onUnlinkTrade : undefined;
  const initialContent = isEntryMode ? props.initialContent : undefined;

  const retroType = !isEntryMode ? props.retroType : undefined;
  const periodStart = !isEntryMode ? props.periodStart : undefined;
  const periodEnd = !isEntryMode ? props.periodEnd : undefined;
  const retrospective = !isEntryMode ? props.retrospective : undefined;
  const onSaveRetro = !isEntryMode ? props.onSaveRetro : undefined;

  // Determine current content source
  const currentData = isEntryMode ? entry : retrospective;
  const dataKey = isEntryMode ? date : periodStart;

  const [isPlaybook, setIsPlaybook] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [linkingTradeId, setLinkingTradeId] = useState<string | null>(null);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [showTradeModal, setShowTradeModal] = useState(false);
  const [showTemplateMenu, setShowTemplateMenu] = useState(false);

  // Tags state
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [showTagSelector, setShowTagSelector] = useState(false);

  // Attachment state
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [showAttachments, setShowAttachments] = useState(true);
  const [pendingAttachments, setPendingAttachments] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Filter templates based on mode
  const availableTemplates = useMemo(() => {
    if (isEntryMode) {
      return JOURNAL_TEMPLATES.filter(t => t.category === 'daily' || t.category === 'all');
    } else if (retroType === 'weekly') {
      return JOURNAL_TEMPLATES.filter(t => t.category === 'weekly' || t.category === 'all');
    } else {
      return JOURNAL_TEMPLATES.filter(t => t.category === 'monthly' || t.category === 'all');
    }
  }, [isEntryMode, retroType]);

  // Initialize TipTap editor with Markdown support
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
      Markdown.configure({
        html: false,
        transformPastedText: true,
        transformCopiedText: true,
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

  // Sync form state with entry/retrospective data
  useEffect(() => {
    if (editor) {
      if (currentData) {
        editor.commands.setContent(currentData.content || '');
        setIsPlaybook(currentData.is_playbook_material);
      } else {
        // No existing entry - use initialContent if provided (e.g., trade context line)
        editor.commands.setContent(initialContent || '');
        setIsPlaybook(false);
        // Focus editor at end of content for immediate typing
        if (initialContent) {
          editor.commands.focus('end');
        }
      }
      setDirty(false);
    }
  }, [currentData, dataKey, editor, initialContent]);

  // Sync attachments from entry/retrospective data
  useEffect(() => {
    if (currentData && currentData.attachments) {
      setAttachments(currentData.attachments);
    } else {
      setAttachments([]);
    }
  }, [currentData, dataKey]);

  // Fetch available tags (entry mode only)
  useEffect(() => {
    if (!isEntryMode) return;

    const fetchTags = async () => {
      setTagsLoading(true);
      try {
        const res = await fetch(`${JOURNAL_API}/api/tags`, {
          credentials: 'include'
        });
        const data = await res.json();
        if (data.success) {
          setAvailableTags(data.data);
        }
      } catch (err) {
        console.error('Failed to fetch tags:', err);
      } finally {
        setTagsLoading(false);
      }
    };
    fetchTags();
  }, [isEntryMode]);

  // Sync selected tags from entry data
  useEffect(() => {
    if (isEntryMode && entry && entry.tags) {
      setSelectedTagIds(entry.tags);
    } else {
      setSelectedTagIds([]);
    }
  }, [isEntryMode, entry, dataKey]);

  // Get the source ID for attachment operations
  const attachmentSourceId = isEntryMode ? entry?.id : retrospective?.id;

  // Upload attachment to an existing entry/retrospective
  const uploadAttachment = useCallback(async (file: File, targetId?: string) => {
    const sourceId = targetId || attachmentSourceId;
    if (!sourceId) return;
    setUploadingAttachment(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const endpoint = isEntryMode
        ? `${JOURNAL_API}/api/journal/entries/${sourceId}/attachments`
        : `${JOURNAL_API}/api/journal/retrospectives/${sourceId}/attachments`;

      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });

      const result = await response.json();
      if (result.success && result.data) {
        setAttachments(prev => [...prev, result.data]);
      }
    } catch (err) {
      console.error('Failed to upload attachment:', err);
    } finally {
      setUploadingAttachment(false);
    }
  }, [attachmentSourceId, isEntryMode]);

  // Handle attachment - auto-creates entry if needed
  const handleAttachment = useCallback(async (file: File) => {
    if (attachmentSourceId) {
      // Entry exists, upload directly
      uploadAttachment(file);
    } else if (isEntryMode && onSave) {
      // No entry yet - queue attachment and save entry first
      setPendingAttachments(prev => [...prev, file]);
      const content = editor
        ? (editor.storage as unknown as Record<string, { getMarkdown: () => string }>).markdown.getMarkdown()
        : '';
      await onSave(content || '', isPlaybook, selectedTagIds);
    }
  }, [attachmentSourceId, isEntryMode, onSave, editor, isPlaybook, uploadAttachment, selectedTagIds]);

  // Upload pending attachments when entry becomes available
  useEffect(() => {
    if (attachmentSourceId && pendingAttachments.length > 0) {
      pendingAttachments.forEach(file => uploadAttachment(file, attachmentSourceId));
      setPendingAttachments([]);
    }
  }, [attachmentSourceId, pendingAttachments, uploadAttachment]);

  // Delete attachment
  const deleteAttachment = useCallback(async (attachmentId: string) => {
    try {
      const response = await fetch(`${JOURNAL_API}/api/journal/attachments/${attachmentId}`, {
        method: 'DELETE',
      });

      const result = await response.json();
      if (result.success) {
        setAttachments(prev => prev.filter(a => a.id !== attachmentId));
      }
    } catch (err) {
      console.error('Failed to delete attachment:', err);
    }
  }, []);

  // Handle file input change
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleAttachment(files[0]);
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [handleAttachment]);

  // Handle drag events
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleAttachment(files[0]);
    }
  }, [handleAttachment]);

  // Handle paste for screenshots
  const handlePaste = useCallback((e: ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          // Generate a filename for pasted images
          const ext = item.type.split('/')[1] || 'png';
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const namedFile = new File([file], `screenshot-${timestamp}.${ext}`, { type: item.type });
          handleAttachment(namedFile);
          e.preventDefault();
          break;
        }
      }
    }
  }, [handleAttachment]);

  // Register paste handler
  useEffect(() => {
    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, [handlePaste]);

  // Get thumbnail URL for image attachments
  const getAttachmentUrl = (attachmentId: string) => {
    return `${JOURNAL_API}/api/journal/attachments/${attachmentId}`;
  };

  // Check if file is an image
  const isImageAttachment = (attachment: Attachment) => {
    return attachment.mime_type?.startsWith('image/');
  };

  // Preview overlay state
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null);

  // Open preview overlay
  const openPreview = useCallback((attachment: Attachment) => {
    setPreviewAttachment(attachment);
  }, []);

  // Close preview overlay
  const closePreview = useCallback(() => {
    setPreviewAttachment(null);
  }, []);

  // Insert reference to attachment at cursor
  const insertAttachmentReference = useCallback((attachment: Attachment) => {
    if (!editor) return;
    const refText = `[📎 ${attachment.filename}]`;
    editor.chain().focus().insertContent(refText).run();
    setDirty(true);
  }, [editor]);

  const handlePlaybookChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setIsPlaybook(e.target.checked);
    setDirty(true);
  };

  const handleSave = useCallback(async () => {
    if (!editor) return;
    setSaving(true);
    const markdownStorage = (editor.storage as unknown as Record<string, { getMarkdown: () => string }>).markdown;
    const content = markdownStorage.getMarkdown();

    let success = false;
    if (isEntryMode && onSave) {
      success = await onSave(content, isPlaybook, selectedTagIds);
    } else if (!isEntryMode && onSaveRetro && retroType && periodStart && periodEnd) {
      success = await onSaveRetro({
        retro_type: retroType,
        period_start: periodStart,
        period_end: periodEnd,
        content,
        is_playbook_material: isPlaybook,
      });
    }

    setSaving(false);
    if (success) {
      setDirty(false);
    }
  }, [editor, isPlaybook, selectedTagIds, isEntryMode, onSave, onSaveRetro, retroType, periodStart, periodEnd]);

  // Tag toggle handler
  const handleToggleTag = (tagId: string) => {
    setSelectedTagIds(prev => {
      if (prev.includes(tagId)) {
        return prev.filter(id => id !== tagId);
      } else {
        return [...prev, tagId];
      }
    });
    setDirty(true);
  };

  const handleLinkTrade = async (tradeId: string) => {
    if (!entry || !onLinkTrade) return;
    setLinkingTradeId(tradeId);
    await onLinkTrade(entry.id, tradeId);
    setLinkingTradeId(null);
  };

  const handleUnlinkTrade = async (refId: string) => {
    if (!onUnlinkTrade) return;
    await onUnlinkTrade(refId);
  };

  const handleTradeClick = async (journalTrade: JournalTrade) => {
    try {
      // Fetch full trade details from API
      const response = await fetch(`${JOURNAL_API}/api/trades/${journalTrade.id}`);
      const result = await response.json();
      if (result.success && result.data) {
        setSelectedTrade(result.data);
        setShowTradeModal(true);
      }
    } catch (err) {
      console.error('Failed to fetch trade details:', err);
    }
  };

  const handleTradeModalClose = () => {
    setShowTradeModal(false);
    setSelectedTrade(null);
  };

  const handleTradeUpdated = () => {
    onTradesUpdated?.();
  };

  const handleInsertTemplate = (template: JournalTemplate) => {
    if (!editor) return;
    // Insert template content at cursor position
    editor.chain().focus().insertContent(template.content).run();
    setShowTemplateMenu(false);
    setDirty(true);
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

  // Close template menu when clicking outside
  useEffect(() => {
    if (!showTemplateMenu) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.template-dropdown-container')) {
        setShowTemplateMenu(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [showTemplateMenu]);

  // Get list of already linked trade IDs
  const linkedTradeIds = new Set(entry?.trade_refs?.map(r => r.trade_id) || []);

  // Group trades by log
  const tradesByLog = tradesForDate.reduce((acc, trade) => {
    const logName = trade.log_name || 'Unknown Log';
    if (!acc[logName]) {
      acc[logName] = [];
    }
    acc[logName].push(trade);
    return acc;
  }, {} as Record<string, typeof tradesForDate>);

  // Compute header title and entry type based on mode
  const headerTitle = isEntryMode && date
    ? formatDate(date)
    : (!isEntryMode && retroType && periodStart && periodEnd)
      ? formatPeriod(retroType, periodStart, periodEnd)
      : '';

  const entryTypeLabel = isEntryMode
    ? 'Daily'
    : retroType === 'weekly'
      ? 'Weekly Retrospective'
      : 'Monthly Retrospective';

  if (loading) {
    return (
      <div className="journal-entry-editor">
        <div className="entry-header">
          <div className="entry-time-anchor">
            <span className="entry-type-label">{entryTypeLabel}</span>
            <h3 className="entry-time-header">{headerTitle}</h3>
          </div>
        </div>
        <div className="entry-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="journal-entry-editor">
      <div className="entry-header">
        <div className="entry-time-anchor">
          <span className="entry-type-label">{entryTypeLabel}</span>
          <h3 className="entry-time-header">{headerTitle}</h3>
        </div>
        {currentData && (
          <span className="entry-meta">
            Last updated: {new Date(currentData.updated_at).toLocaleString()}
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

          <div className="toolbar-separator" />

          {/* Template Dropdown */}
          <div className="toolbar-group template-dropdown-container">
            <button
              type="button"
              className="toolbar-btn template-btn"
              onClick={() => setShowTemplateMenu(!showTemplateMenu)}
              title="Insert Template"
            >
              + Template
            </button>
            {showTemplateMenu && (
              <div className="template-menu">
                {availableTemplates.map(template => (
                  <button
                    key={template.id}
                    type="button"
                    className="template-menu-item"
                    onClick={() => handleInsertTemplate(template)}
                  >
                    {template.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Attach Button - always available in entry mode */}
          {isEntryMode && (
            <div className="toolbar-group">
              <button
                type="button"
                className="toolbar-btn attach-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadingAttachment || pendingAttachments.length > 0}
                title={attachmentSourceId ? "Attach file" : "Attach file (will auto-save entry)"}
              >
                📎{pendingAttachments.length > 0 && <span className="pending-badge">{pendingAttachments.length}</span>}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                style={{ display: 'none' }}
                onChange={handleFileSelect}
                accept="image/*,.pdf,.doc,.docx,.txt"
              />
            </div>
          )}
        </div>
      )}

      <div
        className={`entry-body ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <EditorContent editor={editor} className="entry-content-wrapper" />
        {isDragging && (
          <div className="drop-overlay">
            <span>Drop file to attach</span>
          </div>
        )}
      </div>

      {/* Tags Section - Entry mode only */}
      {isEntryMode && (
        <div className="entry-tags-section">
          <div className="tags-section-header" onClick={() => setShowTagSelector(!showTagSelector)}>
            <span className="collapse-icon">{showTagSelector ? '▼' : '▶'}</span>
            <span className="tags-label">Tags</span>
            {selectedTagIds.length > 0 && (
              <span className="tags-count">{selectedTagIds.length} selected</span>
            )}
          </div>
          {showTagSelector && (
            <div className="tags-selector">
              {tagsLoading ? (
                <div className="tags-loading">Loading tags...</div>
              ) : availableTags.length === 0 ? (
                <div className="tags-empty">No tags available. Create tags in Settings.</div>
              ) : (
                <div className="tags-grid">
                  {availableTags.map(tag => (
                    <button
                      key={tag.id}
                      className={`tag-chip ${selectedTagIds.includes(tag.id) ? 'selected' : ''}`}
                      onClick={() => handleToggleTag(tag.id)}
                      title={tag.description || tag.name}
                    >
                      {tag.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="entry-footer">
        <label className={`playbook-toggle ${!isAdmin ? 'disabled' : ''}`} title={isAdmin ? 'Mark as playbook material' : 'Coming soon'}>
          <input
            type="checkbox"
            checked={isPlaybook}
            onChange={handlePlaybookChange}
            disabled={!isAdmin}
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

      {/* Trades Section - Only show in entry mode */}
      {isEntryMode && (
      <div className="entry-trades-section">
        <div className="trades-section-header">
          <h4>Trades on This Day</h4>
          {!loadingTrades && tradesForDate.length > 0 && (
            <span className="trades-summary">
              {tradesForDate.length} trade{tradesForDate.length !== 1 ? 's' : ''}
              {' '}({tradesForDate.filter(t => t.status === 'open').length} open, {tradesForDate.filter(t => t.status === 'closed').length} closed)
            </span>
          )}
        </div>

        {loadingTrades ? (
          <div className="trades-loading">Loading trades from all logs...</div>
        ) : tradesForDate.length === 0 ? (
          <div className="no-trades">No trades existed on this day</div>
        ) : (
          <>
            {/* Show all trades grouped by log */}
            {Object.entries(tradesByLog).map(([logName, trades]) => (
              <div key={logName} className="trades-log-group">
                <span className="log-group-name">{logName}</span>
                <ul className="trade-list">
                  {trades.map(trade => {
                    const isLinked = linkedTradeIds.has(trade.id);
                    const linkedRef = entry?.trade_refs?.find(r => r.trade_id === trade.id);

                    return (
                      <li key={trade.id} className={`trade-item ${isLinked ? 'linked' : 'available'}`}>
                        <div
                          className="trade-info clickable"
                          onClick={() => handleTradeClick(trade)}
                          title="Click to view trade details"
                        >
                          <span className="trade-symbol">{trade.symbol}</span>
                          <span className="trade-dte-badge">
                            {trade.dte !== undefined ? `${trade.dte}DTE` : ''}
                          </span>
                          <span className="trade-details">
                            {trade.side} {trade.strategy} @ {formatTime(trade.entry_time)}
                          </span>
                          <span className={`trade-pnl ${trade.status === 'open' ? 'open' : (trade.pnl ?? 0) >= 0 ? 'profit' : 'loss'}`}>
                            {trade.status === 'open' ? 'OPEN' : formatPnl(trade.pnl)}
                          </span>
                        </div>
                        {entry ? (
                          isLinked && linkedRef ? (
                            <button
                              className="unlink-btn"
                              onClick={() => handleUnlinkTrade(linkedRef.id)}
                              title="Unlink from entry"
                            >
                              &times;
                            </button>
                          ) : (
                            <button
                              className="link-btn"
                              onClick={() => handleLinkTrade(trade.id)}
                              disabled={linkingTradeId === trade.id}
                              title="Link to entry"
                            >
                              {linkingTradeId === trade.id ? '...' : '+'}
                            </button>
                          )
                        ) : (
                          <span className="link-hint" title="Save entry to link trades">

                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}

            {/* Hint to save entry if no entry exists */}
            {!entry && (
              <div className="trades-link-hint">
                Save your journal entry to link these trades
              </div>
            )}
          </>
        )}
      </div>
      )}

      {/* Attachments Section - works for both entry and retrospective modes */}
      {(attachmentSourceId || (isEntryMode && pendingAttachments.length > 0)) && (
        <div className="entry-attachments-section">
          <div
            className="attachments-header"
            onClick={() => setShowAttachments(!showAttachments)}
          >
            <h4>
              <span className="collapse-icon">{showAttachments ? '▼' : '▶'}</span>
              Attachments
              {(attachments.length > 0 || pendingAttachments.length > 0) && (
                <span className="attachment-count">
                  ({attachments.length}{pendingAttachments.length > 0 ? ` + ${pendingAttachments.length} pending` : ''})
                </span>
              )}
            </h4>
            {(uploadingAttachment || pendingAttachments.length > 0) && (
              <span className="uploading-indicator">
                {pendingAttachments.length > 0 ? 'Saving entry...' : 'Uploading...'}
              </span>
            )}
          </div>

          {showAttachments && (
            <div className="attachments-content">
              {attachments.length === 0 && pendingAttachments.length === 0 ? (
                <div className="no-attachments">
                  Drag & drop files here, paste screenshots, or use the 📎 button
                </div>
              ) : (
                <>
                  <div className="attachment-tiles">
                    {/* Pending attachments (waiting for entry to be created) */}
                    {pendingAttachments.map((file, idx) => (
                      <div key={`pending-${idx}`} className="attachment-tile pending">
                        <div className="attachment-thumbnail pending-overlay">
                          {file.type.startsWith('image/') ? (
                            <img src={URL.createObjectURL(file)} alt={file.name} />
                          ) : (
                            <span className="attachment-icon">📄</span>
                          )}
                          <div className="pending-spinner" />
                        </div>
                        <span className="attachment-filename" title={file.name}>
                          {file.name.length > 20 ? file.name.slice(0, 17) + '...' : file.name}
                        </span>
                      </div>
                    ))}
                    {/* Uploaded attachments */}
                    {attachments.map(att => (
                      <div
                        key={att.id}
                        className="attachment-tile"
                        data-attachment-id={att.id}
                      >
                        {isImageAttachment(att) ? (
                          <div
                            className="attachment-thumbnail"
                            onClick={() => openPreview(att)}
                            title="Click to preview"
                          >
                            <img
                              src={getAttachmentUrl(att.id)}
                              alt={att.filename}
                            />
                          </div>
                        ) : (
                          <div
                            className="attachment-icon"
                            onClick={() => openPreview(att)}
                            title="Click to preview"
                          >
                            📄
                          </div>
                        )}
                        <span className="attachment-filename" title={att.filename}>
                          {att.filename.length > 20
                            ? att.filename.slice(0, 17) + '...'
                            : att.filename}
                        </span>
                        <div className="attachment-actions">
                          <button
                            className="attachment-ref-btn"
                            onClick={() => insertAttachmentReference(att)}
                            title="Insert reference at cursor"
                          >
                            ↗
                          </button>
                          <button
                            className="attachment-delete"
                            onClick={() => deleteAttachment(att.id)}
                            title="Delete attachment"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="attachment-snapshot-notice">
                    Attachments are snapshots and do not update.
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Trade Detail Modal - Only in entry mode */}
      {isEntryMode && (
        <TradeDetailModal
          trade={selectedTrade}
          isOpen={showTradeModal}
          onClose={handleTradeModalClose}
          onTradeUpdated={handleTradeUpdated}
        />
      )}

      {/* Attachment Preview Overlay */}
      {previewAttachment && (
        <div className="attachment-preview-overlay" onClick={closePreview}>
          <div className="attachment-preview-content" onClick={e => e.stopPropagation()}>
            <button className="preview-close" onClick={closePreview}>×</button>
            {isImageAttachment(previewAttachment) ? (
              <img
                src={getAttachmentUrl(previewAttachment.id)}
                alt={previewAttachment.filename}
                className="preview-image"
              />
            ) : (
              <div className="preview-file">
                <span className="preview-file-icon">📄</span>
                <span className="preview-file-name">{previewAttachment.filename}</span>
                <a
                  href={getAttachmentUrl(previewAttachment.id)}
                  download={previewAttachment.filename}
                  className="preview-download-btn"
                >
                  Download
                </a>
              </div>
            )}
            <div className="preview-filename">{previewAttachment.filename}</div>
          </div>
        </div>
      )}
    </div>
  );
}
