/**
 * ReadinessTagSelector - Server-backed day-texture tag pills
 *
 * Replaces the old PersonalReadiness + DayQuality chip system.
 * Tags are grouped by: sleep → focus → distractions → body → friction
 * Exclusive groups allow one selection; friction is multi-select.
 */

import type { ReadinessTag } from '../../hooks/useReadinessTags';

interface ReadinessTagSelectorProps {
  readinessTags: ReadinessTag[];
  selectedTagIds: string[];
  onToggleTag: (tagId: string, group: string) => void;
  loading: boolean;
}

const GROUP_ORDER = ['sleep', 'focus', 'distractions', 'body', 'friction'];
const GROUP_LABELS: Record<string, string> = {
  sleep: 'Sleep felt:',
  focus: 'Focus feels:',
  distractions: 'Distractions:',
  body: 'Body state:',
  friction: 'Friction:',
};

/** Strip trailing group qualifier for display (e.g. "Short Sleep" → "Short") */
function displayName(tag: ReadinessTag): string {
  const name = tag.name;
  const group = tag.group;

  // Strip " Sleep", " Distractions" suffixes for cleaner display
  if (group === 'sleep') return name.replace(/ Sleep$/, '');
  if (group === 'distractions') return name.replace(/ Distractions$/, '');
  return name;
}

export default function ReadinessTagSelector({
  readinessTags,
  selectedTagIds,
  onToggleTag,
  loading,
}: ReadinessTagSelectorProps) {
  if (loading) {
    return (
      <div className="personal-readiness">
        <div className="routine-lens-header">Personal Readiness</div>
        <div style={{ padding: '12px 0', opacity: 0.5, fontSize: 12 }}>Loading...</div>
      </div>
    );
  }

  // Group tags by group field
  const grouped = new Map<string, ReadinessTag[]>();
  for (const tag of readinessTags) {
    const list = grouped.get(tag.group) || [];
    list.push(tag);
    grouped.set(tag.group, list);
  }

  return (
    <div className="personal-readiness">
      <div className="routine-lens-header">Personal Readiness</div>

      <div className="personal-readiness-qualities">
        {GROUP_ORDER.map(group => {
          const tags = grouped.get(group);
          if (!tags || tags.length === 0) return null;

          const isFriction = group === 'friction';

          return (
            <div key={group} className="readiness-tag-row">
              <span className="readiness-tag-label">{GROUP_LABELS[group]}</span>
              <div className="readiness-tag-options">
                {tags.map(tag => (
                  <button
                    key={tag.id}
                    type="button"
                    className={`readiness-tag${isFriction ? ' friction' : ''}${selectedTagIds.includes(tag.id) ? ' selected' : ''}`}
                    onClick={() => onToggleTag(tag.id, tag.group)}
                  >
                    {displayName(tag)}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
