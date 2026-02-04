// ui/src/contexts/TimezoneContext.tsx
// Provides user's timezone preference throughout the app

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

interface TimezoneContextValue {
  timezone: string;
  isLoading: boolean;
  setTimezone: (tz: string | null) => void;
  formatDateTime: (isoString: string, options?: Intl.DateTimeFormatOptions) => string;
  formatTime: (isoString: string) => string;
  formatDate: (isoString: string) => string;
}

const TimezoneContext = createContext<TimezoneContextValue | null>(null);

// Normalize ISO string to ensure UTC parsing
function normalizeUTC(isoString: string): string {
  if (isoString.includes('Z') || isoString.includes('+') || isoString.includes('-', 10)) {
    return isoString;
  }
  return isoString + 'Z';
}

export function TimezoneProvider({ children }: { children: ReactNode }) {
  const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [timezone, setTimezoneState] = useState<string>(detectedTimezone);
  const [isLoading, setIsLoading] = useState(true);

  // External setter - updates the timezone (null resets to browser default)
  const setTimezone = (tz: string | null) => {
    setTimezoneState(tz || detectedTimezone);
  };

  useEffect(() => {
    let cancelled = false;

    async function fetchTimezone() {
      try {
        const res = await fetch('/api/profile/me', { credentials: 'include' });
        if (res.ok && !cancelled) {
          const profile = await res.json();
          if (profile.timezone) {
            setTimezoneState(profile.timezone);
          }
          // If no timezone set, keep the browser-detected one
        }
      } catch (err) {
        // Keep browser-detected timezone on error
        console.error('Failed to fetch timezone preference:', err);
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    fetchTimezone();
    return () => { cancelled = true; };
  }, []);

  // Format a datetime string in the user's timezone
  const formatDateTime = (isoString: string, options?: Intl.DateTimeFormatOptions): string => {
    const normalizedIso = normalizeUTC(isoString);
    const date = new Date(normalizedIso);
    return date.toLocaleString('en-US', {
      timeZone: timezone,
      ...options
    });
  };

  // Format just the time portion
  const formatTime = (isoString: string): string => {
    return formatDateTime(isoString, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  // Format just the date portion
  const formatDate = (isoString: string): string => {
    return formatDateTime(isoString, {
      month: 'short',
      day: 'numeric',
      year: '2-digit'
    });
  };

  return (
    <TimezoneContext.Provider value={{ timezone, isLoading, setTimezone, formatDateTime, formatTime, formatDate }}>
      {children}
    </TimezoneContext.Provider>
  );
}

export function useTimezone(): TimezoneContextValue {
  const context = useContext(TimezoneContext);
  if (!context) {
    // Return default values if used outside provider
    const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return {
      timezone: detectedTimezone,
      isLoading: false,
      setTimezone: () => {}, // no-op outside provider
      formatDateTime: (isoString, options) => {
        const normalizedIso = normalizeUTC(isoString);
        return new Date(normalizedIso).toLocaleString('en-US', {
          timeZone: detectedTimezone,
          ...options
        });
      },
      formatTime: (isoString) => {
        const normalizedIso = normalizeUTC(isoString);
        return new Date(normalizedIso).toLocaleTimeString('en-US', {
          timeZone: detectedTimezone,
          hour: '2-digit',
          minute: '2-digit',
          hour12: true
        });
      },
      formatDate: (isoString) => {
        const normalizedIso = normalizeUTC(isoString);
        return new Date(normalizedIso).toLocaleDateString('en-US', {
          timeZone: detectedTimezone,
          month: 'short',
          day: 'numeric',
          year: '2-digit'
        });
      }
    };
  }
  return context;
}
