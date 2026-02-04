/**
 * useADI - React hook for ADI (AI Data Interface) data.
 *
 * Provides methods to fetch and export ADI snapshots.
 */

import { useState, useCallback } from 'react';

const COPILOT_BASE = '';

export type ExportFormat = 'json' | 'csv' | 'text';

export interface ADISnapshot {
  metadata: {
    timestamp_utc: string;
    symbol: string;
    session: string;
    dte?: number;
    event_flags: string[];
    schema_version: string;
    snapshot_id: string;
  };
  price_state: Record<string, unknown>;
  volatility_state: Record<string, unknown>;
  gamma_structure: Record<string, unknown>;
  auction_structure: Record<string, unknown>;
  microstructure: Record<string, unknown>;
  session_context: Record<string, unknown>;
  mel_scores: Record<string, unknown>;
  delta?: Record<string, unknown>;
  user_context?: Record<string, unknown>;
}

export interface UseADIResult {
  snapshot: ADISnapshot | null;
  loading: boolean;
  error: string | null;
  fetchSnapshot: (includeUserContext?: boolean) => Promise<ADISnapshot | null>;
  exportSnapshot: (format: ExportFormat, includeUserContext?: boolean) => Promise<string>;
  copyToClipboard: (format?: ExportFormat) => Promise<boolean>;
  downloadSnapshot: (format: ExportFormat, filename?: string) => Promise<void>;
}

export function useADI(): UseADIResult {
  const [snapshot, setSnapshot] = useState<ADISnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSnapshot = useCallback(async (includeUserContext = false): Promise<ADISnapshot | null> => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      params.set('format', 'json');
      if (includeUserContext) {
        params.set('include_user_context', 'true');
      }

      const response = await fetch(`${COPILOT_BASE}/api/adi/snapshot?${params}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setSnapshot(data);
      return data;
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to fetch ADI snapshot';
      setError(message);
      console.error('[ADI] Fetch error:', e);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const exportSnapshot = useCallback(async (
    format: ExportFormat,
    includeUserContext = false
  ): Promise<string> => {
    const params = new URLSearchParams();
    params.set('format', format);
    if (includeUserContext) {
      params.set('include_user_context', 'true');
    }

    const response = await fetch(`${COPILOT_BASE}/api/adi/snapshot?${params}`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return response.text();
  }, []);

  const copyToClipboard = useCallback(async (format: ExportFormat = 'text'): Promise<boolean> => {
    try {
      const content = await exportSnapshot(format, true);
      await navigator.clipboard.writeText(content);
      return true;
    } catch (e) {
      console.error('[ADI] Copy failed:', e);
      return false;
    }
  }, [exportSnapshot]);

  const downloadSnapshot = useCallback(async (
    format: ExportFormat,
    filename?: string
  ): Promise<void> => {
    try {
      const content = await exportSnapshot(format, true);

      const extensions: Record<ExportFormat, string> = {
        json: 'json',
        csv: 'csv',
        text: 'txt',
      };

      const mimeTypes: Record<ExportFormat, string> = {
        json: 'application/json',
        csv: 'text/csv',
        text: 'text/plain',
      };

      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const defaultFilename = `adi-snapshot-${timestamp}.${extensions[format]}`;

      const blob = new Blob([content], { type: mimeTypes[format] });
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      a.download = filename || defaultFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('[ADI] Download failed:', e);
      throw e;
    }
  }, [exportSnapshot]);

  return {
    snapshot,
    loading,
    error,
    fetchSnapshot,
    exportSnapshot,
    copyToClipboard,
    downloadSnapshot,
  };
}
