/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState } from 'react';

type ThemeMode = 'light' | 'dark' | 'auto';
type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'hisabclub_theme_mode';

type ThemeContextValue = {
  mode: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setMode: (mode: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function resolveTheme(mode: ThemeMode): ResolvedTheme {
  return mode === 'auto' ? getSystemTheme() : mode;
}

function applyTheme(mode: ThemeMode): ResolvedTheme {
  const resolved = resolveTheme(mode);
  if (typeof document === 'undefined') return resolved;

  const html = document.documentElement;
  html.dataset.themeMode = mode;
  html.dataset.themeResolved = resolved;
  html.classList.toggle('theme-dark', resolved === 'dark');
  html.classList.toggle('theme-light', resolved === 'light');
  return resolved;
}

function getInitialMode(): ThemeMode {
  if (typeof window === 'undefined') return 'auto';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'auto') return stored;
  return 'auto';
}

export function initializeTheme() {
  const mode = getInitialMode();
  applyTheme(mode);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => getInitialMode());
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => getSystemTheme());
  const resolvedTheme: ResolvedTheme = mode === 'auto' ? systemTheme : mode;

  useEffect(() => {
    if (mode !== 'auto') return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setSystemTheme(getSystemTheme());
    media.addEventListener('change', onChange);
    return () => {
      media.removeEventListener('change', onChange);
    };
  }, [mode]);

  useEffect(() => {
    applyTheme(mode === 'auto' ? 'auto' : resolvedTheme);
    window.localStorage.setItem(STORAGE_KEY, mode);
  }, [mode, resolvedTheme]);

  const value = useMemo(
    () => ({
      mode,
      resolvedTheme,
      setMode: setModeState,
    }),
    [mode, resolvedTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider');
  return ctx;
}

export type { ThemeMode, ResolvedTheme };
