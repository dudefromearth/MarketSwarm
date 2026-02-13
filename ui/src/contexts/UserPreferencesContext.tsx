// ui/src/contexts/UserPreferencesContext.tsx
// Client-side display preferences: theme, text size, indicator panel visibility

import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { useLocalStorage } from '../hooks/useLocalStorage';

export type ThemeMode = 'dark' | 'light' | 'auto';
export type TextSize = 'compact' | 'normal' | 'comfortable';
export type ContrastLevel = 'low' | 'normal' | 'high';

interface UserPreferencesContextValue {
  theme: ThemeMode;
  setTheme: (t: ThemeMode) => void;
  resolvedTheme: 'dark' | 'light';
  textSize: TextSize;
  setTextSize: (s: TextSize) => void;
  contrast: ContrastLevel;
  setContrast: (c: ContrastLevel) => void;
  indicatorPanelsVisible: boolean;
  setIndicatorPanelsVisible: (v: boolean) => void;
}

const UserPreferencesContext = createContext<UserPreferencesContextValue | null>(null);

function getSystemTheme(): 'dark' | 'light' {
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function UserPreferencesProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useLocalStorage<ThemeMode>('ms-pref-theme', 'dark', { syncTabs: true });
  const [textSize, setTextSize] = useLocalStorage<TextSize>('ms-pref-text-size', 'normal', { syncTabs: true });
  const [contrast, setContrast] = useLocalStorage<ContrastLevel>('ms-pref-contrast', 'normal', { syncTabs: true });
  const [indicatorPanelsVisible, setIndicatorPanelsVisible] = useLocalStorage<boolean>('ms-pref-indicators-visible', false, { syncTabs: true });

  // For auto mode, we need to track the system preference reactively
  const [systemTheme, setSystemTheme] = useLocalStorage<'dark' | 'light'>('ms-pref-system-theme', getSystemTheme());

  const resolvedTheme: 'dark' | 'light' = theme === 'auto' ? systemTheme : theme;

  // Listen to system theme changes for auto mode
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      setSystemTheme(e.matches ? 'dark' : 'light');
    };
    // Set initial value
    setSystemTheme(mq.matches ? 'dark' : 'light');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [setSystemTheme]);

  // Apply theme and text-size to document
  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
  }, [resolvedTheme]);

  useEffect(() => {
    document.documentElement.dataset.textSize = textSize;
  }, [textSize]);

  useEffect(() => {
    document.documentElement.dataset.contrast = contrast;
  }, [contrast]);

  // Range slider filled-track: set --range-pct on every input[type="range"]
  useEffect(() => {
    const updatePct = (el: HTMLInputElement) => {
      const min = parseFloat(el.min) || 0;
      const max = parseFloat(el.max) || 100;
      const val = parseFloat(el.value);
      const pct = ((val - min) / (max - min)) * 100;
      el.style.setProperty('--range-pct', `${pct}%`);
    };

    const onInput = (e: Event) => {
      const t = e.target as HTMLInputElement;
      if (t?.type === 'range') updatePct(t);
    };

    // Init all existing range inputs
    document.querySelectorAll<HTMLInputElement>('input[type="range"]').forEach(updatePct);

    document.addEventListener('input', onInput);

    // Watch for dynamically added range inputs
    const obs = new MutationObserver((mutations) => {
      for (const m of mutations) {
        m.addedNodes.forEach((node) => {
          if (node instanceof HTMLElement) {
            if (node.matches?.('input[type="range"]')) updatePct(node as HTMLInputElement);
            node.querySelectorAll<HTMLInputElement>('input[type="range"]').forEach(updatePct);
          }
        });
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });

    return () => {
      document.removeEventListener('input', onInput);
      obs.disconnect();
    };
  }, []);

  return (
    <UserPreferencesContext.Provider value={{
      theme, setTheme, resolvedTheme,
      textSize, setTextSize,
      contrast, setContrast,
      indicatorPanelsVisible, setIndicatorPanelsVisible,
    }}>
      {children}
    </UserPreferencesContext.Provider>
  );
}

export function useUserPreferences(): UserPreferencesContextValue {
  const context = useContext(UserPreferencesContext);
  if (!context) {
    throw new Error('useUserPreferences must be used within a UserPreferencesProvider');
  }
  return context;
}
