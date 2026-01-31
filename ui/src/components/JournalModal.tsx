// src/components/JournalModal.tsx
import { useState, useEffect, useCallback } from 'react';
import { useJournal } from '../hooks/useJournal';
import JournalCalendar from './JournalCalendar';
import JournalEntryEditor from './JournalEntryEditor';
import '../styles/journal.css';

interface JournalModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedLogId: string | null;
}

export default function JournalModal({ isOpen, onClose, selectedLogId }: JournalModalProps) {
  // Initialize to current month
  const [viewMonth, setViewMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  });
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const journal = useJournal();

  // Fetch calendar when month changes or modal opens
  useEffect(() => {
    if (isOpen) {
      journal.fetchCalendar(viewMonth.year, viewMonth.month);
    }
  }, [isOpen, viewMonth.year, viewMonth.month]);

  // Fetch entry and trades when date is selected
  useEffect(() => {
    if (selectedDate) {
      journal.fetchEntry(selectedDate);
      if (selectedLogId) {
        journal.fetchTradesForDate(selectedLogId, selectedDate);
      }
    } else {
      journal.clearEntry();
    }
  }, [selectedDate, selectedLogId]);

  // Keyboard: Escape to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, onClose]);

  const handleMonthChange = useCallback((year: number, month: number) => {
    setViewMonth({ year, month });
  }, []);

  const handleSelectDate = useCallback((date: string) => {
    setSelectedDate(date);
  }, []);

  const handleSaveEntry = useCallback(async (content: string, isPlaybook: boolean): Promise<boolean> => {
    if (!selectedDate) return false;
    const success = await journal.saveEntry(selectedDate, content, isPlaybook);
    if (success) {
      // Refresh calendar to show updated dot
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

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="journal-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Journal</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="journal-content">
          <div className="journal-sidebar">
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

          <div className="journal-main">
            {selectedDate ? (
              <JournalEntryEditor
                date={selectedDate}
                entry={journal.currentEntry}
                loading={journal.loadingEntry}
                onSave={handleSaveEntry}
                tradesForDate={journal.tradesForDate}
                loadingTrades={journal.loadingTrades}
                onLinkTrade={handleLinkTrade}
                onUnlinkTrade={handleUnlinkTrade}
              />
            ) : (
              <div className="journal-empty">
                <p>Select a day to view or create an entry</p>
              </div>
            )}
          </div>
        </div>

        {journal.error && (
          <div className="journal-error">
            {journal.error}
            <button onClick={journal.clearError}>&times;</button>
          </div>
        )}
      </div>
    </div>
  );
}
