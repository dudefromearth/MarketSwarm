/**
 * RoutineSection - Collapsible section wrapper for Routine Drawer
 */

import { type ReactNode } from 'react';

interface RoutineSectionProps {
  title: string;
  icon: string;
  expanded: boolean;
  onToggle: () => void;
  badge?: number | null;
  children: ReactNode;
}

export default function RoutineSection({
  title,
  icon,
  expanded,
  onToggle,
  badge,
  children,
}: RoutineSectionProps) {
  return (
    <div className={`routine-section ${expanded ? 'expanded' : ''}`}>
      <div className="routine-section-header" onClick={onToggle}>
        <div className="routine-section-title">
          <span className="routine-section-icon">{icon}</span>
          <span>{title}</span>
          {badge != null && badge > 0 && (
            <span className="routine-section-badge">{badge}</span>
          )}
        </div>
        <span className="routine-section-chevron">▼</span>
      </div>
      <div className="routine-section-content">{children}</div>
    </div>
  );
}
