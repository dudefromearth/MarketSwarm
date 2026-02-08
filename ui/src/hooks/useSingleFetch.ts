/**
 * useSingleFetch - Fetch once when a condition becomes true
 *
 * Common pattern for drawer/panel components that need to fetch data
 * once when opened, but not on subsequent re-renders.
 *
 * Features:
 * - Fetches once when `shouldFetch` transitions from false to true
 * - Resets fetch flag when `shouldFetch` becomes false (allows re-fetch on next open)
 * - Provides loading state and refetch capability
 * - Handles errors gracefully
 */

import { useState, useEffect, useRef, useCallback } from 'react';

interface UseSingleFetchOptions {
  /** If true, errors are logged to console. Default: true */
  logErrors?: boolean;
}

interface UseSingleFetchResult<T> {
  /** The fetched data, or null if not yet fetched or error occurred */
  data: T | null;
  /** True while fetch is in progress */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Manually trigger a refetch */
  refetch: () => void;
}

export function useSingleFetch<T>(
  shouldFetch: boolean,
  fetchFn: () => Promise<T>,
  options: UseSingleFetchOptions = {}
): UseSingleFetchResult<T> {
  const { logErrors = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasFetchedRef = useRef(false);
  const wasTrueRef = useRef(false);
  const fetchFnRef = useRef(fetchFn);

  // Keep fetchFn ref updated
  fetchFnRef.current = fetchFn;

  const doFetch = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await fetchFnRef.current();
      setData(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Fetch failed';
      setError(message);
      if (logErrors) {
        console.error('[useSingleFetch] Error:', err);
      }
    } finally {
      setLoading(false);
    }
  }, [logErrors]);

  // Fetch when shouldFetch transitions from false to true (and hasn't fetched yet)
  useEffect(() => {
    if (shouldFetch && !wasTrueRef.current && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      doFetch();
    }
    wasTrueRef.current = shouldFetch;
  }, [shouldFetch, doFetch]);

  // Reset fetch flag when shouldFetch becomes false
  useEffect(() => {
    if (!shouldFetch) {
      hasFetchedRef.current = false;
    }
  }, [shouldFetch]);

  const refetch = useCallback(() => {
    hasFetchedRef.current = false;
    doFetch();
    hasFetchedRef.current = true;
  }, [doFetch]);

  return { data, loading, error, refetch };
}
