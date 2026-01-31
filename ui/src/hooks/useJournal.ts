// src/hooks/useJournal.ts
import { useState, useCallback } from 'react';

const JOURNAL_API = 'http://localhost:3002';

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

  // Error
  error: string | null;
  clearError: () => void;
}

export function useJournal(): UseJournalReturn {
  const [calendarData, setCalendarData] = useState<CalendarData | null>(null);
  const [loadingCalendar, setLoadingCalendar] = useState(false);
  const [currentEntry, setCurrentEntry] = useState<JournalEntry | null>(null);
  const [loadingEntry, setLoadingEntry] = useState(false);
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

  return {
    calendarData,
    loadingCalendar,
    fetchCalendar,
    currentEntry,
    loadingEntry,
    fetchEntry,
    saveEntry,
    clearEntry,
    error,
    clearError,
  };
}
