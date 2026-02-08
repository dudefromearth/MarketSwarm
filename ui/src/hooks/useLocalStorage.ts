/**
 * useLocalStorage - Type-safe localStorage persistence
 *
 * Features:
 * - Automatic JSON serialization/deserialization
 * - Handles storage quota errors gracefully
 * - SSR-safe (returns default value if localStorage unavailable)
 * - Type-safe with generics
 */

import { useState, useCallback, useEffect } from 'react';

interface UseLocalStorageOptions<T> {
  /** If true, sync across tabs. Default: false */
  syncTabs?: boolean;
  /** Custom serializer. Default: JSON.stringify */
  serialize?: (value: T) => string;
  /** Custom deserializer. Default: JSON.parse */
  deserialize?: (value: string) => T;
}

type SetValue<T> = T | ((prevValue: T) => T);

export function useLocalStorage<T>(
  key: string,
  defaultValue: T,
  options: UseLocalStorageOptions<T> = {}
): [T, (value: SetValue<T>) => void, () => void] {
  const {
    syncTabs = false,
    serialize = JSON.stringify,
    deserialize = JSON.parse,
  } = options;

  // Get initial value from localStorage or use default
  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === 'undefined') {
      return defaultValue;
    }

    try {
      const item = localStorage.getItem(key);
      if (item === null) {
        return defaultValue;
      }
      return deserialize(item);
    } catch (error) {
      console.warn(`[useLocalStorage] Error reading key "${key}":`, error);
      return defaultValue;
    }
  });

  // Update localStorage when value changes
  const setValue = useCallback(
    (value: SetValue<T>) => {
      setStoredValue((prevValue) => {
        const newValue = value instanceof Function ? value(prevValue) : value;

        if (typeof window !== 'undefined') {
          try {
            localStorage.setItem(key, serialize(newValue));
          } catch (error) {
            // Handle quota exceeded or other storage errors
            console.warn(`[useLocalStorage] Error writing key "${key}":`, error);
          }
        }

        return newValue;
      });
    },
    [key, serialize]
  );

  // Remove from localStorage
  const removeValue = useCallback(() => {
    if (typeof window !== 'undefined') {
      try {
        localStorage.removeItem(key);
      } catch (error) {
        console.warn(`[useLocalStorage] Error removing key "${key}":`, error);
      }
    }
    setStoredValue(defaultValue);
  }, [key, defaultValue]);

  // Sync across tabs if enabled
  useEffect(() => {
    if (!syncTabs || typeof window === 'undefined') {
      return;
    }

    const handleStorageChange = (event: StorageEvent) => {
      if (event.key !== key || event.storageArea !== localStorage) {
        return;
      }

      try {
        if (event.newValue === null) {
          setStoredValue(defaultValue);
        } else {
          setStoredValue(deserialize(event.newValue));
        }
      } catch (error) {
        console.warn(`[useLocalStorage] Error syncing key "${key}":`, error);
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [key, defaultValue, deserialize, syncTabs]);

  return [storedValue, setValue, removeValue];
}

/**
 * Get current date in a specific timezone as YYYY-MM-DD
 */
export function getDateInTimezone(timezone: string = 'America/New_York'): string {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return formatter.format(now);
}

/**
 * useLocalStorageWithDailyReset - localStorage that resets daily
 *
 * Uses timezone-aware date checking (default: America/New_York)
 */
export function useLocalStorageWithDailyReset<T>(
  key: string,
  defaultValue: T,
  timezone: string = 'America/New_York'
): [T, (value: SetValue<T>) => void, () => void] {
  const dateKey = `${key}-date`;

  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === 'undefined') {
      return defaultValue;
    }

    const today = getDateInTimezone(timezone);
    const storedDate = localStorage.getItem(dateKey);

    // New day - reset
    if (storedDate !== today) {
      localStorage.setItem(dateKey, today);
      localStorage.removeItem(key);
      return defaultValue;
    }

    // Same day - try to restore
    try {
      const item = localStorage.getItem(key);
      if (item === null) {
        return defaultValue;
      }
      return JSON.parse(item);
    } catch {
      return defaultValue;
    }
  });

  const setValue = useCallback(
    (value: SetValue<T>) => {
      setStoredValue((prevValue) => {
        const newValue = value instanceof Function ? value(prevValue) : value;

        if (typeof window !== 'undefined') {
          try {
            const today = getDateInTimezone(timezone);
            localStorage.setItem(dateKey, today);
            localStorage.setItem(key, JSON.stringify(newValue));
          } catch (error) {
            console.warn(`[useLocalStorageWithDailyReset] Error writing key "${key}":`, error);
          }
        }

        return newValue;
      });
    },
    [key, dateKey, timezone]
  );

  const removeValue = useCallback(() => {
    if (typeof window !== 'undefined') {
      try {
        localStorage.removeItem(key);
        localStorage.removeItem(dateKey);
      } catch (error) {
        console.warn(`[useLocalStorageWithDailyReset] Error removing key "${key}":`, error);
      }
    }
    setStoredValue(defaultValue);
  }, [key, dateKey, defaultValue]);

  return [storedValue, setValue, removeValue];
}
