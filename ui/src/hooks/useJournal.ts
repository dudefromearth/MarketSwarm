// src/hooks/useJournal.ts
import { useState, useCallback } from 'react';

const JOURNAL_API = 'http://localhost:3002';

// Simplified Trade interface for journal linking
export interface JournalTrade {
  id: string;
  symbol: string;
  strategy: string;
  side: string;
  quantity: number;
  entry_time: string;
  exit_time: string | null;
  pnl_dollars: number | null;
  status: string;
}

export interface JournalEntry {
  id: string;
  user_id: number;
  entry_date: string;
  content: string | null;
  is_playbook_material: boolean;
  trade_refs: TradeRef[];
  attachments: Attachment[];
  created_at: string;
  updated_at: string;
}

export interface TradeRef {
  id: string;
  source_type: string;
  source_id: string;
  trade_id: string;
  note: string | null;
  created_at: string;
}

export interface Attachment {
  id: string;
  source_type: string;
  source_id: string;
  filename: string;
  mime_type: string | null;
  file_size: number | null;
  created_at: string;
}

export interface CalendarDay {
  has_entry: boolean;
  is_playbook_material: boolean;
}

export interface CalendarData {
  year: number;
  month: number;
  days: Record<string, CalendarDay>;
  retrospectives: {
    weekly: string[];
    monthly: string | null;
  };
}

export interface UseJournalReturn {
  // Calendar
  calendarData: CalendarData | null;
  loadingCalendar: boolean;
  fetchCalendar: (year: number, month: number) => Promise<void>;

  // Entry
  currentEntry: JournalEntry | null;
  loadingEntry: boolean;
  fetchEntry: (date: string) => Promise<void>;
  saveEntry: (date: string, content: string, isPlaybook: boolean) => Promise<boolean>;
  clearEntry: () => void;

  // Trades for linking
  tradesForDate: JournalTrade[];
  loadingTrades: boolean;
  fetchTradesForDate: (logId: string, date: string) => Promise<void>;
  linkTrade: (entryId: string, tradeId: string, note?: string) => Promise<boolean>;
  unlinkTrade: (refId: string) => Promise<boolean>;

  // Error
  error: string | null;
  clearError: () => void;
}

export function useJournal(): UseJournalReturn {
  const [calendarData, setCalendarData] = useState<CalendarData | null>(null);
  const [loadingCalendar, setLoadingCalendar] = useState(false);
  const [currentEntry, setCurrentEntry] = useState<JournalEntry | null>(null);
  const [loadingEntry, setLoadingEntry] = useState(false);
  const [tradesForDate, setTradesForDate] = useState<JournalTrade[]>([]);
  const [loadingTrades, setLoadingTrades] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCalendar = useCallback(async (year: number, month: number) => {
    setLoadingCalendar(true);
    setError(null);
    try {
      const res = await fetch(`${JOURNAL_API}/api/journal/calendar/${year}/${month}`, {
        credentials: 'include',
      });
      const data = await res.json();
      if (data.success) {
        setCalendarData(data.data);
      } else {
        setError(data.error || 'Failed to fetch calendar');
      }
    } catch (err) {
      console.error('Failed to fetch calendar:', err);
      setError('Failed to fetch calendar');
    } finally {
      setLoadingCalendar(false);
    }
  }, []);

  const fetchEntry = useCallback(async (date: string) => {
    setLoadingEntry(true);
    setError(null);
    try {
      const res = await fetch(`${JOURNAL_API}/api/journal/entries/date/${date}`, {
        credentials: 'include',
      });
      if (res.status === 404) {
        // No entry for this date - that's OK
        setCurrentEntry(null);
        return;
      }
      const data = await res.json();
      if (data.success) {
        setCurrentEntry(data.data);
      } else {
        setCurrentEntry(null);
      }
    } catch (err) {
      console.error('Failed to fetch entry:', err);
      setCurrentEntry(null);
    } finally {
      setLoadingEntry(false);
    }
  }, []);

  const saveEntry = useCallback(async (date: string, content: string, isPlaybook: boolean): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch(`${JOURNAL_API}/api/journal/entries`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entry_date: date,
          content,
          is_playbook_material: isPlaybook,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setCurrentEntry(data.data);
        return true;
      } else {
        setError(data.error || 'Failed to save entry');
        return false;
      }
    } catch (err) {
      console.error('Failed to save entry:', err);
      setError('Failed to save entry');
      return false;
    }
  }, []);

  const clearEntry = useCallback(() => {
    setCurrentEntry(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const fetchTradesForDate = useCallback(async (logId: string, date: string) => {
    if (!logId) {
      setTradesForDate([]);
      return;
    }
    setLoadingTrades(true);
    try {
      // Fetch all trades and filter by date client-side
      const res = await fetch(`${JOURNAL_API}/api/logs/${logId}/trades?limit=10000`, {
        credentials: 'include',
      });
      const data = await res.json();
      if (data.success) {
        // Filter trades that were entered on this date
        const filtered = data.data.filter((t: JournalTrade) => {
          const entryDate = t.entry_time.split('T')[0];
          return entryDate === date;
        });
        setTradesForDate(filtered);
      } else {
        setTradesForDate([]);
      }
    } catch (err) {
      console.error('Failed to fetch trades for date:', err);
      setTradesForDate([]);
    } finally {
      setLoadingTrades(false);
    }
  }, []);

  const linkTrade = useCallback(async (entryId: string, tradeId: string, note?: string): Promise<boolean> => {
    try {
      const res = await fetch(`${JOURNAL_API}/api/journal/entries/${entryId}/trades`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trade_id: tradeId, note }),
      });
      const data = await res.json();
      if (data.success) {
        // Refresh current entry to get updated trade_refs
        if (currentEntry) {
          const updated = await fetch(`${JOURNAL_API}/api/journal/entries/${entryId}`, {
            credentials: 'include',
          });
          const entryData = await updated.json();
          if (entryData.success) {
            setCurrentEntry(entryData.data);
          }
        }
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to link trade:', err);
      return false;
    }
  }, [currentEntry]);

  const unlinkTrade = useCallback(async (refId: string): Promise<boolean> => {
    try {
      const res = await fetch(`${JOURNAL_API}/api/journal/trade-refs/${refId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      const data = await res.json();
      if (data.success) {
        // Update local state to remove the ref
        if (currentEntry) {
          setCurrentEntry({
            ...currentEntry,
            trade_refs: currentEntry.trade_refs.filter(r => r.id !== refId),
          });
        }
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to unlink trade:', err);
      return false;
    }
  }, [currentEntry]);

  return {
    calendarData,
    loadingCalendar,
    fetchCalendar,
    currentEntry,
    loadingEntry,
    fetchEntry,
    saveEntry,
    clearEntry,
    tradesForDate,
    loadingTrades,
    fetchTradesForDate,
    linkTrade,
    unlinkTrade,
    error,
    clearError,
  };
}
