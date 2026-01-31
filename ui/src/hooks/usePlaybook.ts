// src/hooks/usePlaybook.ts
import { useState, useCallback } from 'react';

const JOURNAL_API = 'http://localhost:3002';

export interface PlaybookEntry {
  id: string;
  user_id: number;
  title: string;
  entry_type: 'pattern' | 'rule' | 'warning' | 'filter' | 'constraint';
  description: string;
  status: 'draft' | 'active' | 'retired';
  created_at: string;
  updated_at: string;
  sources?: PlaybookSourceRef[];
  source_count?: number;
}

export interface PlaybookSourceRef {
  id: string;
  playbook_entry_id: string;
  source_type: 'entry' | 'retrospective' | 'trade';
  source_id: string;
  note: string | null;
  created_at: string;
}

export interface FlaggedMaterial {
  entries: Array<{
    id: string;
    entry_date: string;
    content: string;
    created_at: string;
    updated_at: string;
  }>;
  retrospectives: Array<{
    id: string;
    retro_type: 'weekly' | 'monthly';
    period_start: string;
    period_end: string;
    content: string;
    created_at: string;
    updated_at: string;
  }>;
}

export interface UsePlaybookReturn {
  // Entries
  entries: PlaybookEntry[];
  loadingEntries: boolean;
  fetchEntries: (filters?: {
    type?: string;
    status?: string;
    search?: string;
  }) => Promise<void>;

  // Current entry
  currentEntry: PlaybookEntry | null;
  loadingEntry: boolean;
  fetchEntry: (id: string) => Promise<void>;
  clearEntry: () => void;

  // CRUD
  createEntry: (data: {
    title: string;
    entry_type: string;
    description: string;
    status?: string;
    sources?: Array<{
      source_type: string;
      source_id: string;
      note?: string;
    }>;
  }) => Promise<PlaybookEntry | null>;
  updateEntry: (id: string, updates: Partial<PlaybookEntry>) => Promise<boolean>;
  deleteEntry: (id: string) => Promise<boolean>;

  // Sources
  addSource: (entryId: string, source: {
    source_type: string;
    source_id: string;
    note?: string;
  }) => Promise<boolean>;
  removeSource: (sourceId: string) => Promise<boolean>;

  // Flagged material
  flaggedMaterial: FlaggedMaterial | null;
  loadingFlagged: boolean;
  fetchFlaggedMaterial: () => Promise<void>;

  // Error
  error: string | null;
  clearError: () => void;
}

export function usePlaybook(): UsePlaybookReturn {
  const [entries, setEntries] = useState<PlaybookEntry[]>([]);
  const [loadingEntries, setLoadingEntries] = useState(false);

  const [currentEntry, setCurrentEntry] = useState<PlaybookEntry | null>(null);
  const [loadingEntry, setLoadingEntry] = useState(false);

  const [flaggedMaterial, setFlaggedMaterial] = useState<FlaggedMaterial | null>(null);
  const [loadingFlagged, setLoadingFlagged] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);
  const clearEntry = useCallback(() => setCurrentEntry(null), []);

  const fetchEntries = useCallback(async (filters?: {
    type?: string;
    status?: string;
    search?: string;
  }) => {
    setLoadingEntries(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filters?.type) params.set('type', filters.type);
      if (filters?.status) params.set('status', filters.status);
      if (filters?.search) params.set('search', filters.search);

      const url = `${JOURNAL_API}/api/playbook/entries${params.toString() ? '?' + params : ''}`;
      const response = await fetch(url);
      const result = await response.json();

      if (result.success) {
        setEntries(result.data);
      } else {
        setError(result.error || 'Failed to fetch playbook entries');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoadingEntries(false);
    }
  }, []);

  const fetchEntry = useCallback(async (id: string) => {
    setLoadingEntry(true);
    setError(null);
    try {
      const response = await fetch(`${JOURNAL_API}/api/playbook/entries/${id}`);
      const result = await response.json();

      if (result.success) {
        setCurrentEntry(result.data);
      } else {
        setError(result.error || 'Failed to fetch playbook entry');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoadingEntry(false);
    }
  }, []);

  const createEntry = useCallback(async (data: {
    title: string;
    entry_type: string;
    description: string;
    status?: string;
    sources?: Array<{
      source_type: string;
      source_id: string;
      note?: string;
    }>;
  }): Promise<PlaybookEntry | null> => {
    setError(null);
    try {
      const response = await fetch(`${JOURNAL_API}/api/playbook/entries`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await response.json();

      if (result.success) {
        return result.data;
      } else {
        setError(result.error || 'Failed to create playbook entry');
        return null;
      }
    } catch (err) {
      setError('Failed to connect to server');
      return null;
    }
  }, []);

  const updateEntry = useCallback(async (id: string, updates: Partial<PlaybookEntry>): Promise<boolean> => {
    setError(null);
    try {
      const response = await fetch(`${JOURNAL_API}/api/playbook/entries/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      const result = await response.json();

      if (result.success) {
        setCurrentEntry(result.data);
        return true;
      } else {
        setError(result.error || 'Failed to update playbook entry');
        return false;
      }
    } catch (err) {
      setError('Failed to connect to server');
      return false;
    }
  }, []);

  const deleteEntry = useCallback(async (id: string): Promise<boolean> => {
    setError(null);
    try {
      const response = await fetch(`${JOURNAL_API}/api/playbook/entries/${id}`, {
        method: 'DELETE',
      });
      const result = await response.json();

      if (result.success) {
        setEntries(prev => prev.filter(e => e.id !== id));
        if (currentEntry?.id === id) {
          setCurrentEntry(null);
        }
        return true;
      } else {
        setError(result.error || 'Failed to delete playbook entry');
        return false;
      }
    } catch (err) {
      setError('Failed to connect to server');
      return false;
    }
  }, [currentEntry]);

  const addSource = useCallback(async (entryId: string, source: {
    source_type: string;
    source_id: string;
    note?: string;
  }): Promise<boolean> => {
    setError(null);
    try {
      const response = await fetch(`${JOURNAL_API}/api/playbook/entries/${entryId}/sources`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(source),
      });
      const result = await response.json();

      if (result.success) {
        // Refresh current entry to get updated sources
        if (currentEntry?.id === entryId) {
          await fetchEntry(entryId);
        }
        return true;
      } else {
        setError(result.error || 'Failed to add source');
        return false;
      }
    } catch (err) {
      setError('Failed to connect to server');
      return false;
    }
  }, [currentEntry, fetchEntry]);

  const removeSource = useCallback(async (sourceId: string): Promise<boolean> => {
    setError(null);
    try {
      const response = await fetch(`${JOURNAL_API}/api/playbook/sources/${sourceId}`, {
        method: 'DELETE',
      });
      const result = await response.json();

      if (result.success) {
        // Update current entry sources
        if (currentEntry) {
          setCurrentEntry(prev => prev ? {
            ...prev,
            sources: prev.sources?.filter(s => s.id !== sourceId)
          } : null);
        }
        return true;
      } else {
        setError(result.error || 'Failed to remove source');
        return false;
      }
    } catch (err) {
      setError('Failed to connect to server');
      return false;
    }
  }, [currentEntry]);

  const fetchFlaggedMaterial = useCallback(async () => {
    setLoadingFlagged(true);
    setError(null);
    try {
      const response = await fetch(`${JOURNAL_API}/api/playbook/flagged-material`);
      const result = await response.json();

      if (result.success) {
        setFlaggedMaterial(result.data);
      } else {
        setError(result.error || 'Failed to fetch flagged material');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setLoadingFlagged(false);
    }
  }, []);

  return {
    entries,
    loadingEntries,
    fetchEntries,
    currentEntry,
    loadingEntry,
    fetchEntry,
    clearEntry,
    createEntry,
    updateEntry,
    deleteEntry,
    addSource,
    removeSource,
    flaggedMaterial,
    loadingFlagged,
    fetchFlaggedMaterial,
    error,
    clearError,
  };
}
