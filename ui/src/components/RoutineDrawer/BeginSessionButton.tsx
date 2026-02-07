/**
 * BeginSessionButton - "Enter Market" button to release to Action Surface
 */

interface BeginSessionButtonProps {
  isRoutineComplete: boolean;
  onBegin: () => void;
}

export default function BeginSessionButton({ isRoutineComplete, onBegin }: BeginSessionButtonProps) {
  return (
    <div className="routine-begin-session">
      <button
        className="routine-begin-btn"
        onClick={onBegin}
        disabled={!isRoutineComplete}
      >
        Enter Market
      </button>
      {!isRoutineComplete && (
        <div className="routine-begin-hint">
          Complete all sections to begin
        </div>
      )}
    </div>
  );
}
