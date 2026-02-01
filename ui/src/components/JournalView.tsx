// src/components/JournalView.tsx
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useJournal } from '../hooks/useJournal';
import { useAuth } from '../AuthWrapper';
import JournalCalendar from './JournalCalendar';
import JournalEntryEditor from './JournalEntryEditor';
import type { TradeReflectionContext } from './TradeLogPanel';
import '../styles/journal.css';

interface JournalViewProps {
  onClose: () => void;
  onOpenPlaybook?: () => void;
  tradeContext?: TradeReflectionContext | null;
}

type Tab = 'entries' | 'retrospectives';
type RetroType = 'weekly' | 'monthly';

// Helper to get week start (Monday) for a date
function getWeekStart(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday
  d.setDate(diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

// Helper to get week end (Sunday) for a date
function getWeekEnd(start: Date): Date {
  const d = new Date(start);
  d.setDate(d.getDate() + 6);
  return d;
}

// Helper to format date as YYYY-MM-DD
function formatDateISO(date: Date): string {
  return date.toISOString().split('T')[0];
}

// Helper to get month start
function getMonthStart(year: number, month: number): Date {
  return new Date(year, month - 1, 1);
}

// Helper to get month end
function getMonthEnd(year: number, month: number): Date {
  return new Date(year, month, 0);
}

export default function JournalView({ onClose, onOpenPlaybook, tradeContext }: JournalViewProps) {
  // Auth for role-based features
  const { isAdmin } = useAuth();

  // Tab state
  const [activeTab, setActiveTab] = useState<Tab>('entries');

  // Calendar/entries state
  const [viewMonth, setViewMonth] = useState(() => {
    // If trade context provided, use trade's close date for the view month
    if (tradeContext?.closeDate) {
      const closeDate = new Date(tradeContext.closeDate);
      return { year: closeDate.getFullYear(), month: closeDate.getMonth() + 1 };
    }
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  });
  const [selectedDate, setSelectedDate] = useState<string | null>(() => {
    // If trade context provided, anchor to trade's close date
    if (tradeContext?.closeDate) {
      return formatDateISO(new Date(tradeContext.closeDate));
    }
    // Auto-select today's date - tools should come up to meet the trader
    return formatDateISO(new Date());
  });

  // Generate minimal context line for trade-based reflection
  const tradeContextLine = useMemo(() => {
    if (!tradeContext) return null;
    const strategyLabel = tradeContext.strategy === 'butterfly' ? 'Butterfly'
      : tradeContext.strategy === 'vertical' ? 'Vertical'
      : tradeContext.strategy === 'single' ? 'Single'
      : tradeContext.strategy || 'Trade';
    const sideLabel = tradeContext.side?.charAt(0).toUpperCase() + tradeContext.side?.slice(1) || '';
    const strikeDisplay = tradeContext.width
      ? `${tradeContext.strike}/${tradeContext.width}w`
      : `${tradeContext.strike}`;
    return `Trade: ${tradeContext.symbol} ${sideLabel} ${strategyLabel} · ${strikeDisplay} · Closed\n\n`;
  }, [tradeContext]);

  // Retrospectives state
  const [retroType, setRetroType] = useState<RetroType>('weekly');
  const [selectedPeriod, setSelectedPeriod] = useState<{ start: string; end: string } | null>(null);

  const journal = useJournal();

  // Generate available periods for retrospectives
  const availablePeriods = useMemo(() => {
    const periods: { start: string; end: string; label: string }[] = [];
    const now = new Date();

    if (retroType === 'weekly') {
      // Last 8 weeks
      for (let i = 0; i < 8; i++) {
        const weekStart = getWeekStart(new Date(now.getTime() - i * 7 * 24 * 60 * 60 * 1000));
        const weekEnd = getWeekEnd(weekStart);
        const startStr = formatDateISO(weekStart);
        const endStr = formatDateISO(weekEnd);
        const label = i === 0 ? 'This Week' : i === 1 ? 'Last Week' : `${weekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
        periods.push({ start: startStr, end: endStr, label });
      }
    } else {
      // Last 6 months
      for (let i = 0; i < 6; i++) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        const monthStart = getMonthStart(d.getFullYear(), d.getMonth() + 1);
        const monthEnd = getMonthEnd(d.getFullYear(), d.getMonth() + 1);
        const startStr = formatDateISO(monthStart);
        const endStr = formatDateISO(monthEnd);
        const label = i === 0 ? 'This Month' : monthStart.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
        periods.push({ start: startStr, end: endStr, label });
      }
    }

    return periods;
  }, [retroType]);

  // Fetch calendar when month changes
  useEffect(() => {
    if (activeTab === 'entries') {
      journal.fetchCalendar(viewMonth.year, viewMonth.month);
    }
  }, [activeTab, viewMonth.year, viewMonth.month]);

  // Fetch entry and trades when date is selected
  useEffect(() => {
    if (activeTab === 'entries' && selectedDate) {
      journal.fetchEntry(selectedDate);
      journal.fetchTradesForDate(selectedDate);
    } else if (activeTab === 'entries') {
      journal.clearEntry();
    }
  }, [activeTab, selectedDate]);

  // Fetch retrospective when period is selected
  useEffect(() => {
    if (activeTab === 'retrospectives' && selectedPeriod) {
      journal.fetchRetrospective(retroType, selectedPeriod.start);
    } else if (activeTab === 'retrospectives') {
      journal.clearRetrospective();
    }
  }, [activeTab, retroType, selectedPeriod]);

  // Select first period by default when switching to retrospectives
  useEffect(() => {
    if (activeTab === 'retrospectives' && !selectedPeriod && availablePeriods.length > 0) {
      setSelectedPeriod({ start: availablePeriods[0].start, end: availablePeriods[0].end });
    }
  }, [activeTab, availablePeriods]);

  // Reset period when retro type changes
  useEffect(() => {
    if (availablePeriods.length > 0) {
      setSelectedPeriod({ start: availablePeriods[0].start, end: availablePeriods[0].end });
    }
  }, [retroType]);

  const handleMonthChange = useCallback((year: number, month: number) => {
    setViewMonth({ year, month });
  }, []);

  const handleSelectDate = useCallback((date: string) => {
    setSelectedDate(date);
  }, []);

  const handleSaveEntry = useCallback(async (content: string, isPlaybook: boolean, tags: string[]): Promise<boolean> => {
    if (!selectedDate) return false;
    const success = await journal.saveEntry(selectedDate, content, isPlaybook, tags);
    if (success) {
      journal.fetchCalendar(viewMonth.year, viewMonth.month);
    }
    return success;
  }, [selectedDate, viewMonth.year, viewMonth.month, journal]);

  const handleLinkTrade = useCallback(async (entryId: string, tradeId: string): Promise<boolean> => {
    return journal.linkTrade(entryId, tradeId);
  }, [journal]);

  const handleUnlinkTrade = useCallback(async (refId: string): Promise<boolean> => {
    return journal.unlinkTrade(refId);
  }, [journal]);

  const handleSaveRetrospective = useCallback(async (retro: {
    retro_type: 'weekly' | 'monthly';
    period_start: string;
    period_end: string;
    content: string;
    is_playbook_material: boolean;
  }): Promise<boolean> => {
    return journal.saveRetrospective(retro);
  }, [journal]);

  return (
    <div className="journal-view">
      <div className="journal-view-header">
        <h2>Journal</h2>
        <div className="journal-tabs">
          <button
            className={`journal-tab ${activeTab === 'entries' ? 'active' : ''}`}
            onClick={() => setActiveTab('entries')}
          >
            Entries
          </button>
          <button
            className={`journal-tab retro-tab ${activeTab === 'retrospectives' ? 'active' : ''}`}
            onClick={() => setActiveTab('retrospectives')}
          >
            ✨ Retrospectives
          </button>
        </div>
        <div className="journal-header-actions">
          {onOpenPlaybook && (
            <button
              className={`btn-playbook-link ${!isAdmin ? 'disabled' : ''}`}
              onClick={isAdmin ? onOpenPlaybook : undefined}
              disabled={!isAdmin}
              title={isAdmin ? 'Open Playbook' : 'Coming soon'}
            >
              Playbook
            </button>
          )}
          <button className="btn-back-to-trades" onClick={onClose}>
            ← Back to Trades
          </button>
        </div>
      </div>

      {/* Loop Indicator - Journal is where Reflection happens */}
      <div className="improvement-loop-indicator">
        <span className="loop-stage">Discovery</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage">Analysis</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage">Action</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage current">Reflection</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage">Distillation</span>
      </div>

      <div className="journal-content">
        {activeTab === 'entries' ? (
          <div className="journal-entries-layout">
            <div className="journal-calendar-section">
              <JournalCalendar
                year={viewMonth.year}
                month={viewMonth.month}
                days={journal.calendarData?.days || {}}
                selectedDate={selectedDate}
                onSelectDate={handleSelectDate}
                onMonthChange={handleMonthChange}
                loading={journal.loadingCalendar}
              />
            </div>

            <div className="journal-editor-section">
              {selectedDate ? (
                <JournalEntryEditor
                  mode="entry"
                  date={selectedDate}
                  entry={journal.currentEntry}
                  loading={journal.loadingEntry}
                  onSave={handleSaveEntry}
                  tradesForDate={journal.tradesForDate}
                  loadingTrades={journal.loadingTrades}
                  onLinkTrade={handleLinkTrade}
                  onUnlinkTrade={handleUnlinkTrade}
                  onTradesUpdated={() => journal.fetchTradesForDate(selectedDate)}
                  initialContent={tradeContextLine || undefined}
                />
              ) : (
                <div className="journal-empty">
                  <p>Select a day to view or create an entry</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="journal-entries-layout">
            <div className="journal-retro-nav">
              <div className="retro-type-toggle">
                <button
                  className={`retro-type-btn ${retroType === 'weekly' ? 'active' : ''}`}
                  onClick={() => setRetroType('weekly')}
                >
                  Weekly
                </button>
                <button
                  className={`retro-type-btn ${retroType === 'monthly' ? 'active' : ''}`}
                  onClick={() => setRetroType('monthly')}
                >
                  Monthly
                </button>
              </div>

              <div className="retro-periods">
                {availablePeriods.map(period => (
                  <button
                    key={period.start}
                    className={`retro-period-btn ${selectedPeriod?.start === period.start ? 'active' : ''}`}
                    onClick={() => setSelectedPeriod({ start: period.start, end: period.end })}
                  >
                    {period.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="journal-editor-section">
              {selectedPeriod ? (
                <JournalEntryEditor
                  mode="retrospective"
                  retroType={retroType}
                  periodStart={selectedPeriod.start}
                  periodEnd={selectedPeriod.end}
                  retrospective={journal.currentRetrospective}
                  loading={journal.loadingRetrospective}
                  onSaveRetro={handleSaveRetrospective}
                />
              ) : (
                <div className="journal-empty">
                  <p>Select a period to view or create a retrospective</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {journal.error && (
        <div className="journal-error">
          {journal.error}
          <button onClick={journal.clearError}>&times;</button>
        </div>
      )}
    </div>
  );
}
