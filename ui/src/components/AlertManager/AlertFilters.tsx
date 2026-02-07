/**
 * AlertFilters - View filter tabs for Alert Manager
 *
 * Filters by scope, category, and triggered status:
 * - All: Show all alerts
 * - Algo: Strategy-aware algo alerts (from algo-alerts.md)
 * - ML: Machine learning driven alerts (from ml-driven-alerts.md)
 * - Position: Tied to specific position
 * - Symbol: Market price/level alerts
 * - Portfolio: Aggregate posture alerts
 * - Workflow: Process triggers
 * - Behavioral: User pattern detection
 * - Triggered: Alerts needing attention
 */

import type { AlertScope } from '../../types/alerts';
import { getScopeStyle, ALERT_CATEGORY_STYLES } from '../../types/alerts';

// ML category color (matches ML_ALERT_CATEGORY_STYLES.opportunity_amplification for positive connotation)
const ML_FILTER_STYLE = {
  color: '#a855f7',  // Purple - learned patterns
  bgColor: 'rgba(168, 85, 247, 0.15)',
};

// View filter includes 'all', 'algo', 'ml', 'triggered' beyond scopes
export type ViewFilter = 'all' | 'algo' | 'ml' | AlertScope | 'triggered';

interface AlertFiltersProps {
  active: ViewFilter;
  onChange: (filter: ViewFilter) => void;
  counts: Record<ViewFilter, number>;
}

const FILTER_CONFIG: { value: ViewFilter; label: string; icon?: string; color?: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'algo', label: 'Algo', icon: '⚡', color: ALERT_CATEGORY_STYLES.algo.color },
  { value: 'ml', label: 'Learned', icon: '🎓', color: ML_FILTER_STYLE.color },
  { value: 'position', label: 'Position' },
  { value: 'symbol', label: 'Symbol' },
  { value: 'portfolio', label: 'Portfolio' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'behavioral', label: 'Behavioral' },
  { value: 'triggered', label: 'Triggered', icon: '!' },
];

export default function AlertFilters({ active, onChange, counts }: AlertFiltersProps) {
  return (
    <div className="alert-filters">
      {FILTER_CONFIG.map((filter) => {
        const count = counts[filter.value] || 0;
        const isTriggered = filter.value === 'triggered';
        const isAlgo = filter.value === 'algo';
        const isML = filter.value === 'ml';
        const isScope = !['all', 'triggered', 'algo', 'ml'].includes(filter.value);
        const scopeStyle = isScope ? getScopeStyle(filter.value as AlertScope) : null;

        // Determine active style
        let activeStyle: React.CSSProperties | undefined;
        if (active === filter.value) {
          if (scopeStyle) {
            activeStyle = {
              background: scopeStyle.bgColor,
              color: scopeStyle.color,
              borderColor: scopeStyle.color,
            };
          } else if (isAlgo) {
            activeStyle = {
              background: ALERT_CATEGORY_STYLES.algo.bgColor,
              color: ALERT_CATEGORY_STYLES.algo.color,
              borderColor: ALERT_CATEGORY_STYLES.algo.color,
            };
          } else if (isML) {
            activeStyle = {
              background: ML_FILTER_STYLE.bgColor,
              color: ML_FILTER_STYLE.color,
              borderColor: ML_FILTER_STYLE.color,
            };
          }
        }

        return (
          <button
            key={filter.value}
            className={`alert-filter-tab ${active === filter.value ? 'active' : ''} ${isTriggered && count > 0 ? 'urgent' : ''} ${isAlgo ? 'algo' : ''} ${isML ? 'ml' : ''}`}
            onClick={() => onChange(filter.value)}
            style={activeStyle}
          >
            {filter.icon && (
              <span className="filter-icon" style={filter.color ? { color: filter.color } : undefined}>
                {filter.icon}
              </span>
            )}
            <span className="filter-label">{filter.label}</span>
            {count > 0 && (
              <span className={`filter-count ${isTriggered ? 'urgent' : ''}`}>
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
