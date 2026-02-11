/**
 * useReadinessTags - Server-backed readiness state via day-texture tags
 *
 * Replaces the old localStorage-based PersonalReadiness/Friction system.
 * Tags are stored on the Journal entry for the current day, making them
 * persistent, queryable, and available to Vexy.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const JOURNAL_API = '';

export interface ReadinessTag {
  id: string;
  name: string;
  category: string;
  group: string;
  system: boolean;
}

// Groups where only one tag can be selected at a time
const EXCLUSIVE_GROUPS = new Set(['sleep', 'focus', 'distractions', 'body']);

/**
 * Get current date in America/New_York timezone as YYYY-MM-DD
 */
function getTodayET(): string {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return formatter.format(now);
}

interface JournalEntryData {
  id: string;
  content: string | null;
  is_playbook_material: boolean;
  tags: string[];
}

export function useReadinessTags() {
  const [readinessTags, setReadinessTags] = useState<ReadinessTag[]>([]);
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const currentEntryRef = useRef<JournalEntryData | null>(null);
  const readinessTagIdsRef = useRef<Set<string>>(new Set());
  const savingRef = useRef(false);

  // Fetch tags and today's entry on mount
  useEffect(() => {
    let cancelled = false;

    const init = async () => {
      setLoading(true);
      try {
        // Fetch day-texture tags
        const tagsRes = await fetch(`${JOURNAL_API}/api/tags?category=day-texture`, {
          credentials: 'include',
        });
        const tagsData = await tagsRes.json();

        if (cancelled) return;

        if (tagsData.success) {
          const tags: ReadinessTag[] = tagsData.data;
          setReadinessTags(tags);
          readinessTagIdsRef.current = new Set(tags.map(t => t.id));
        }

        // Fetch today's journal entry
        const today = getTodayET();
        const entryRes = await fetch(`${JOURNAL_API}/api/journal/entries/date/${today}`, {
          credentials: 'include',
        });

        if (cancelled) return;

        if (entryRes.ok) {
          const entryData = await entryRes.json();
          if (entryData.success && entryData.data) {
            const entry = entryData.data;
            currentEntryRef.current = {
              id: entry.id,
              content: entry.content,
              is_playbook_material: entry.is_playbook_material,
              tags: entry.tags || [],
            };
            // Extract day-texture tag IDs from entry
            const dayTextureIds = (entry.tags || []).filter(
              (id: string) => readinessTagIdsRef.current.has(id)
            );
            setSelectedTagIds(dayTextureIds);
          }
        } else if (entryRes.status === 404) {
          currentEntryRef.current = null;
          setSelectedTagIds([]);
        }
      } catch (err) {
        console.error('Failed to init readiness tags:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    init();
    return () => { cancelled = true; };
  }, []);

  const toggleReadinessTag = useCallback(async (tagId: string, group: string) => {
    if (savingRef.current) return;
    savingRef.current = true;

    try {
      const isExclusive = EXCLUSIVE_GROUPS.has(group);

      setSelectedTagIds(prev => {
        let next: string[];

        if (isExclusive) {
          // Find all tag IDs in the same group
          const groupTagIds = readinessTags
            .filter(t => t.group === group)
            .map(t => t.id);

          // Remove all tags in this group
          const withoutGroup = prev.filter(id => !groupTagIds.includes(id));

          // Toggle: if already selected, just remove; otherwise add
          if (prev.includes(tagId)) {
            next = withoutGroup;
          } else {
            next = [...withoutGroup, tagId];
          }
        } else {
          // Multi-select (friction): simple toggle
          if (prev.includes(tagId)) {
            next = prev.filter(id => id !== tagId);
          } else {
            next = [...prev, tagId];
          }
        }

        // Persist asynchronously
        const entryData = currentEntryRef.current;
        const existingNonReadinessTags = (entryData?.tags || []).filter(
          (id: string) => !readinessTagIdsRef.current.has(id)
        );
        const fullTagList = [...existingNonReadinessTags, ...next];

        const today = getTodayET();
        fetch(`${JOURNAL_API}/api/journal/entries`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entry_date: today,
            content: entryData?.content ?? null,
            is_playbook_material: entryData?.is_playbook_material ?? false,
            tags: fullTagList,
          }),
        })
          .then(res => res.json())
          .then(data => {
            if (data.success && data.data) {
              currentEntryRef.current = {
                id: data.data.id,
                content: data.data.content,
                is_playbook_material: data.data.is_playbook_material,
                tags: data.data.tags || [],
              };
            }
          })
          .catch(err => console.error('Failed to save readiness tags:', err))
          .finally(() => { savingRef.current = false; });

        return next;
      });
    } catch {
      savingRef.current = false;
    }
  }, [readinessTags]);

  const getDayTextureContext = useCallback((): Record<string, string> => {
    const context: Record<string, string> = {};
    for (const tagId of selectedTagIds) {
      const tag = readinessTags.find(t => t.id === tagId);
      if (tag) {
        context[tag.group] = tag.name;
      }
    }
    return context;
  }, [selectedTagIds, readinessTags]);

  return {
    readinessTags,
    selectedTagIds,
    toggleReadinessTag,
    loading,
    getDayTextureContext,
  };
}
