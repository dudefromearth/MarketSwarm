// src/components/JournalCalendar.tsx
import { useState, useMemo } from 'react';
import type { CalendarDay } from '../hooks/useJournal';

interface JournalCalendarProps {
  year: number;
  month: number;
  days: Record<string, CalendarDay>;
  selectedDate: string | null;
  onSelectDate: (date: string) => void;
  onMonthChange: (year: number, month: number) => void;
  loading?: boolean;
}

type ViewMode = 'month' | 'week';

const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const WEEKDAYS_FULL = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];
const SESSIONS = ['Globex', 'Morning', 'Afternoon', 'Closing'] as const;

// Helper to get the start of the week (Sunday) for a given date
function getWeekStart(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  d.setDate(d.getDate() - day);
  d.setHours(0, 0, 0, 0);
  return d;
}

// Helper to format date as YYYY-MM-DD
function formatDateStr(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export default function JournalCalendar({
  year,
  month,
  days,
  selectedDate,
  onSelectDate,
  onMonthChange,
  loading = false,
}: JournalCalendarProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('month');

  // For week view, track the current week's start date
  const [weekStart, setWeekStart] = useState<Date>(() => {
    // Start with the week containing the selected date or today
    const baseDate = selectedDate ? new Date(selectedDate) : new Date();
    return getWeekStart(baseDate);
  });

  // Today's date string
  const today = new Date();
  const todayStr = formatDateStr(today);

  // Week view: get the 7 days of the current week
  const weekDays = useMemo(() => {
    const result: Date[] = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      result.push(d);
    }
    return result;
  }, [weekStart]);

  // Get week range label
  const weekLabel = useMemo(() => {
    const start = weekDays[0];
    const end = weekDays[6];
    const startMonth = MONTH_NAMES[start.getMonth()];
    const endMonth = MONTH_NAMES[end.getMonth()];

    if (start.getMonth() === end.getMonth()) {
      return `${startMonth} ${start.getDate()} - ${end.getDate()}, ${start.getFullYear()}`;
    } else if (start.getFullYear() === end.getFullYear()) {
      return `${startMonth} ${start.getDate()} - ${endMonth} ${end.getDate()}, ${start.getFullYear()}`;
    } else {
      return `${startMonth} ${start.getDate()}, ${start.getFullYear()} - ${endMonth} ${end.getDate()}, ${end.getFullYear()}`;
    }
  }, [weekDays]);

  // Month view: Get number of days in month and first day of week
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayOfWeek = new Date(year, month - 1, 1).getDay(); // 0 = Sunday

  // Build month view day cells
  const monthDayCells = useMemo(() => {
    const cells = [];

    // Empty cells before first day
    for (let i = 0; i < firstDayOfWeek; i++) {
      cells.push(
        <div key={`empty-${i}`} className="calendar-day empty" />
      );
    }

    // Day cells
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayData = days[dateStr];
      const hasEntry = dayData?.has_entry ?? false;
      const isPlaybook = dayData?.is_playbook_material ?? false;
      const isSelected = dateStr === selectedDate;
      const isToday = dateStr === todayStr;

      cells.push(
        <div
          key={dateStr}
          className={`calendar-day ${hasEntry ? 'has-entry' : ''} ${isSelected ? 'selected' : ''} ${isToday ? 'today' : ''}`}
          onClick={() => onSelectDate(dateStr)}
        >
          <span className="calendar-day-number">{day}</span>
          <span className={`calendar-dot ${hasEntry ? 'filled' : ''} ${isPlaybook ? 'playbook' : ''}`} />
        </div>
      );
    }

    return cells;
  }, [year, month, days, selectedDate, todayStr, daysInMonth, firstDayOfWeek, onSelectDate]);

  const handlePrevMonth = () => {
    if (month === 1) {
      onMonthChange(year - 1, 12);
    } else {
      onMonthChange(year, month - 1);
    }
  };

  const handleNextMonth = () => {
    if (month === 12) {
      onMonthChange(year + 1, 1);
    } else {
      onMonthChange(year, month + 1);
    }
  };

  const handlePrevWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(newStart.getDate() - 7);
    setWeekStart(newStart);
    // Update month view if week crosses into different month
    const midWeek = new Date(newStart);
    midWeek.setDate(midWeek.getDate() + 3);
    if (midWeek.getFullYear() !== year || midWeek.getMonth() + 1 !== month) {
      onMonthChange(midWeek.getFullYear(), midWeek.getMonth() + 1);
    }
  };

  const handleNextWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(newStart.getDate() + 7);
    setWeekStart(newStart);
    // Update month view if week crosses into different month
    const midWeek = new Date(newStart);
    midWeek.setDate(midWeek.getDate() + 3);
    if (midWeek.getFullYear() !== year || midWeek.getMonth() + 1 !== month) {
      onMonthChange(midWeek.getFullYear(), midWeek.getMonth() + 1);
    }
  };

  const handleToday = () => {
    const now = new Date();
    const todayYear = now.getFullYear();
    const todayMonth = now.getMonth() + 1;
    const todayDate = formatDateStr(now);

    if (year !== todayYear || month !== todayMonth) {
      onMonthChange(todayYear, todayMonth);
    }
    setWeekStart(getWeekStart(now));
    onSelectDate(todayDate);
  };

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    // Sync week view with current month/selected date when switching
    if (mode === 'week') {
      const baseDate = selectedDate ? new Date(selectedDate) : new Date(year, month - 1, 15);
      setWeekStart(getWeekStart(baseDate));
    }
  };

  // Check if a day is a weekend (Sat/Sun)
  const isWeekend = (dayOfWeek: number) => dayOfWeek === 0 || dayOfWeek === 6;

  return (
    <div className={`journal-calendar-container ${loading ? 'loading' : ''}`}>
      <div className="calendar-controls">
        <div className="view-toggle">
          <button
            className={`view-toggle-btn ${viewMode === 'month' ? 'active' : ''}`}
            onClick={() => handleViewChange('month')}
          >
            Month
          </button>
          <button
            className={`view-toggle-btn ${viewMode === 'week' ? 'active' : ''}`}
            onClick={() => handleViewChange('week')}
          >
            Week
          </button>
        </div>
        <button className="calendar-today-btn" onClick={handleToday}>Today</button>
      </div>

      {viewMode === 'month' ? (
        <>
          <div className="calendar-header">
            <button className="calendar-nav" onClick={handlePrevMonth}>&lt;</button>
            <span className="calendar-title">{MONTH_NAMES[month - 1]} {year}</span>
            <button className="calendar-nav" onClick={handleNextMonth}>&gt;</button>
          </div>

          <div className="calendar-weekdays">
            {WEEKDAYS.map((d, i) => (
              <div key={i} className="calendar-weekday">{d}</div>
            ))}
          </div>

          <div className="journal-calendar">
            {monthDayCells}
          </div>
        </>
      ) : (
        <>
          <div className="calendar-header">
            <button className="calendar-nav" onClick={handlePrevWeek}>&lt;</button>
            <span className="calendar-title">{weekLabel}</span>
            <button className="calendar-nav" onClick={handleNextWeek}>&gt;</button>
          </div>

          <div className="week-view">
            {/* Header row with day names and dates */}
            <div className="week-header">
              <div className="week-session-label" />
              {weekDays.map((d, i) => {
                const dateStr = formatDateStr(d);
                const dayData = days[dateStr];
                const hasEntry = dayData?.has_entry ?? false;
                const isSelected = dateStr === selectedDate;
                const isToday = dateStr === todayStr;
                const weekend = isWeekend(d.getDay());

                return (
                  <div
                    key={i}
                    className={`week-day-header ${isSelected ? 'selected' : ''} ${isToday ? 'today' : ''} ${weekend ? 'weekend' : ''} ${hasEntry ? 'has-entry' : ''}`}
                    onClick={() => onSelectDate(dateStr)}
                  >
                    <span className="week-day-name">{WEEKDAYS_FULL[d.getDay()]}</span>
                    <span className="week-day-date">{d.getDate()}</span>
                    {hasEntry && <span className="week-entry-dot" />}
                  </div>
                );
              })}
            </div>

            {/* Session rows */}
            {SESSIONS.map(session => (
              <div key={session} className="week-session-row">
                <div className="week-session-label">{session}</div>
                {weekDays.map((d, i) => {
                  const dateStr = formatDateStr(d);
                  const dayData = days[dateStr];
                  const hasEntry = dayData?.has_entry ?? false;
                  const isSelected = dateStr === selectedDate;
                  const weekend = isWeekend(d.getDay());

                  return (
                    <div
                      key={i}
                      className={`week-session-cell ${isSelected ? 'selected' : ''} ${weekend ? 'weekend' : ''} ${hasEntry ? 'has-entry' : ''}`}
                      onClick={() => onSelectDate(dateStr)}
                    >
                      {hasEntry && <span className="session-entry-indicator" />}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
