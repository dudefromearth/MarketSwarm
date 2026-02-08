/**
 * DayQuality - Individual quality selector row
 *
 * A single row of chip-style options for selecting a day quality.
 * Click to select, click again to deselect.
 * All selections are optional - no required inputs.
 */

interface DayQualityOption<T> {
  value: T;
  label: string;
}

interface DayQualityProps<T extends string> {
  label: string;
  options: DayQualityOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
}

export default function DayQuality<T extends string>({
  label,
  options,
  value,
  onChange,
}: DayQualityProps<T>) {
  return (
    <div className="day-quality-row">
      <span className="day-quality-label">{label}</span>
      <div className="day-quality-options">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`day-quality-chip ${value === option.value ? 'selected' : ''}`}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
