import { useState, useEffect, useCallback, useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';

export type ChangelogArea = 'risk-graph' | 'routine' | 'dealer-gravity' | 'journal' | 'process' | 'general';
export type ChangelogEntryType = 'feature' | 'enhancement' | 'fix' | 'change';

export interface ChangelogEntry {
  id: string;
  area: ChangelogArea;
  title: string;
  description: string;
  type: ChangelogEntryType;
}

export interface ChangelogVersion {
  version: string;
  date: string;
  entries: ChangelogEntry[];
}

interface ChangelogData {
  versions: ChangelogVersion[];
}

export function useChangelog() {
  const [data, setData] = useState<ChangelogData | null>(null);
  const [loading, setLoading] = useState(true);
  const [seenIds, setSeenIds] = useLocalStorage<string[]>('fotw-changelog-seen', []);

  useEffect(() => {
    fetch(`/changelog.json?t=${Date.now()}`)
      .then(res => res.json())
      .then((json: ChangelogData) => {
        setData(json);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  const versions = data?.versions ?? [];

  const allEntries = useMemo(
    () => versions.flatMap(v => v.entries),
    [versions]
  );

  const latestVersion = versions.length > 0 ? versions[0].version : '0.0.0';

  const isEntrySeen = useCallback(
    (id: string) => seenIds.includes(id),
    [seenIds]
  );

  const unseenCount = useMemo(
    () => allEntries.filter(e => !seenIds.includes(e.id)).length,
    [allEntries, seenIds]
  );

  const unseenCountForArea = useCallback(
    (area: ChangelogArea) =>
      allEntries.filter(e => e.area === area && !seenIds.includes(e.id)).length,
    [allEntries, seenIds]
  );

  const hasUnseenForArea = useCallback(
    (area: ChangelogArea) => unseenCountForArea(area) > 0,
    [unseenCountForArea]
  );

  const markSeen = useCallback(
    (id: string) => {
      setSeenIds(prev => prev.includes(id) ? prev : [...prev, id]);
    },
    [setSeenIds]
  );

  const markAllSeen = useCallback(
    () => {
      const allIds = allEntries.map(e => e.id);
      setSeenIds(allIds);
    },
    [allEntries, setSeenIds]
  );

  const entriesForArea = useCallback(
    (area: ChangelogArea) =>
      versions
        .map(v => ({
          ...v,
          entries: v.entries.filter(e => e.area === area),
        }))
        .filter(v => v.entries.length > 0),
    [versions]
  );

  return {
    versions,
    loading,
    unseenCount,
    unseenCountForArea,
    hasUnseenForArea,
    markSeen,
    markAllSeen,
    isEntrySeen,
    entriesForArea,
    latestVersion,
  };
}
