import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { DarkTheme as NavigationDarkTheme, DefaultTheme as NavigationDefaultTheme } from '@react-navigation/native';
import { MD3DarkTheme, MD3LightTheme, type MD3Theme } from 'react-native-paper';
import { useColorScheme } from 'react-native';
import {
  getThemeMode,
  setThemeMode,
  type ThemeMode,
} from '../utils/storage';

export type AppThemeColors = {
  primary: string;
  primaryDark: string;
  success: string;
  danger: string;
  warning: string;
  background: string;
  surface: string;
  text: string;
  textSecondary: string;
  border: string;
  debit: string;
  credit: string;
  tintOverlay: string;
  card: string;
};

const LIGHT_COLORS: AppThemeColors = {
  primary: '#FF3D00',
  primaryDark: '#D53200',
  success: '#1F7A42',
  danger: '#B91C1C',
  warning: '#9B6500',
  background: '#F5F4EF',
  surface: '#FFFFFF',
  text: '#101010',
  textSecondary: '#4D4D4D',
  border: '#DBD9D1',
  debit: '#101010',
  credit: '#1F7A42',
  tintOverlay: 'rgba(255, 61, 0, 0.08)',
  card: '#FFFFFF',
};

const DARK_COLORS: AppThemeColors = {
  primary: '#FF3D00',
  primaryDark: '#FF5E2E',
  success: '#4ADE80',
  danger: '#F87171',
  warning: '#FBBF24',
  background: '#0A0A0A',
  surface: '#0F0F0F',
  text: '#FAFAFA',
  textSecondary: '#A3A3A3',
  border: '#262626',
  debit: '#FAFAFA',
  credit: '#4ADE80',
  tintOverlay: 'rgba(255, 61, 0, 0.14)',
  card: '#0F0F0F',
};

type AppThemeContextValue = {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => Promise<void>;
  resolvedMode: 'light' | 'dark';
  isDark: boolean;
  colors: AppThemeColors;
  paperTheme: MD3Theme;
  navigationTheme: typeof NavigationDefaultTheme;
  ready: boolean;
};

const AppThemeContext = createContext<AppThemeContextValue | null>(null);

type Props = {
  children: React.ReactNode;
};

function createPaperTheme(colors: AppThemeColors, isDark: boolean): MD3Theme {
  const base = isDark ? MD3DarkTheme : MD3LightTheme;
  return {
    ...base,
    dark: isDark,
    roundness: 0,
    colors: {
      ...base.colors,
      primary: colors.primary,
      secondary: colors.primaryDark,
      background: colors.background,
      surface: colors.surface,
      onSurface: colors.text,
      onBackground: colors.text,
      onPrimary: '#0A0A0A',
      outline: colors.border,
      error: colors.danger,
    },
  };
}

function createNavigationTheme(colors: AppThemeColors, isDark: boolean) {
  const base = isDark ? NavigationDarkTheme : NavigationDefaultTheme;
  return {
    ...base,
    dark: isDark,
    colors: {
      ...base.colors,
      primary: colors.primary,
      background: colors.background,
      card: colors.surface,
      text: colors.text,
      border: colors.border,
      notification: colors.danger,
    },
  };
}

export function AppThemeProvider({ children }: Props) {
  const systemScheme = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>('auto');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    getThemeMode()
      .then((storedMode) => {
        if (!mounted) return;
        setModeState(storedMode);
      })
      .finally(() => {
        if (mounted) setReady(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const resolvedMode: 'light' | 'dark' = useMemo(() => {
    if (mode === 'auto') {
      return systemScheme === 'dark' ? 'dark' : 'light';
    }
    return mode;
  }, [mode, systemScheme]);

  const isDark = resolvedMode === 'dark';
  const colors = useMemo(() => (isDark ? DARK_COLORS : LIGHT_COLORS), [isDark]);
  const paperTheme = useMemo(() => createPaperTheme(colors, isDark), [colors, isDark]);
  const navigationTheme = useMemo(
    () => createNavigationTheme(colors, isDark),
    [colors, isDark],
  );

  const setMode = useCallback(async (nextMode: ThemeMode) => {
    setModeState(nextMode);
    await setThemeMode(nextMode);
  }, []);

  const value = useMemo(
    () => ({
      mode,
      setMode,
      resolvedMode,
      isDark,
      colors,
      paperTheme,
      navigationTheme,
      ready,
    }),
    [mode, setMode, resolvedMode, isDark, colors, paperTheme, navigationTheme, ready],
  );

  return <AppThemeContext.Provider value={value}>{children}</AppThemeContext.Provider>;
}

export function useAppTheme() {
  const ctx = useContext(AppThemeContext);
  if (!ctx) {
    throw new Error('useAppTheme must be used inside AppThemeProvider');
  }
  return ctx;
}
