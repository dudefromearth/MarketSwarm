// src/components/JournalCalendar.tsx
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

const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export default function JournalCalendar({
  year,
  month,
  days,
  selectedDate,
  onSelectDate,
  onMonthChange,
  loading = false,
}: JournalCalendarProps) {
  // Get number of days in month and first day of week
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayOfWeek = new Date(year, month - 1, 1).getDay(); // 0 = Sunday

  // Build day cells
  const dayCells = [];

  // Empty cells before first day
  for (let i = 0; i < firstDayOfWeek; i++) {
    dayCells.push(
      <div key={`empty-${i}`} className="calendar-day empty" />
    );
  }

  // Day cells
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const dayData = days[dateStr];
    const hasEntry = dayData?.has_entry ?? false;
    const isPlaybook = dayData?.is_playbook_material ?? false;
    const isSelected = dateStr === selectedDate;
    const isToday = dateStr === todayStr;

    dayCells.push(
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

  const handleToday = () => {
    const now = new Date();
    const todayYear = now.getFullYear();
    const todayMonth = now.getMonth() + 1;
    const todayDate = `${todayYear}-${String(todayMonth).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

    if (year !== todayYear || month !== todayMonth) {
      onMonthChange(todayYear, todayMonth);
    }
    onSelectDate(todayDate);
  };

  return (
    <div className={`journal-calendar-container ${loading ? 'loading' : ''}`}>
      <div className="calendar-header">
        <button className="calendar-nav" onClick={handlePrevMonth}>&lt;</button>
        <span className="calendar-title">{MONTH_NAMES[month - 1]} {year}</span>
        <button className="calendar-nav" onClick={handleNextMonth}>&gt;</button>
      </div>

      <button className="calendar-today-btn" onClick={handleToday}>Today</button>

      <div className="calendar-weekdays">
        {WEEKDAYS.map((d, i) => (
          <div key={i} className="calendar-weekday">{d}</div>
        ))}
      </div>

      <div className="journal-calendar">
        {dayCells}
      </div>
    </div>
  );
}
