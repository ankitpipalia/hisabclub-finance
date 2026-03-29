import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { DEFAULT_API_URL, STORAGE_KEYS } from './constants';

export type ThemeMode = 'auto' | 'light' | 'dark';

// Secure storage for tokens
export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(STORAGE_KEYS.TOKEN);
}

export async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(STORAGE_KEYS.TOKEN, token);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(STORAGE_KEYS.TOKEN);
  await SecureStore.deleteItemAsync(STORAGE_KEYS.REFRESH_TOKEN);
}

// Regular storage for settings
export async function getServerUrl(): Promise<string | null> {
  const stored = await AsyncStorage.getItem(STORAGE_KEYS.SERVER_URL);
  if (!stored || !stored.trim()) {
    return DEFAULT_API_URL;
  }
  return normalizeServerUrl(stored);
}

export async function setServerUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEYS.SERVER_URL, normalizeServerUrl(url));
}

export async function resetServerUrl(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEYS.SERVER_URL);
}

export async function getLastSmsSync(): Promise<number | null> {
  const val = await AsyncStorage.getItem(STORAGE_KEYS.LAST_SMS_SYNC);
  return val ? parseInt(val, 10) : null;
}

export async function setLastSmsSync(timestamp: number): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEYS.LAST_SMS_SYNC, timestamp.toString());
}

export async function getThemeMode(): Promise<ThemeMode> {
  const mode = await AsyncStorage.getItem(STORAGE_KEYS.THEME_MODE);
  if (mode === 'light' || mode === 'dark' || mode === 'auto') {
    return mode;
  }
  return 'auto';
}

export async function setThemeMode(mode: ThemeMode): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEYS.THEME_MODE, mode);
}

export function normalizeServerUrl(url: string): string {
  let value = url.trim();
  if (!value) return DEFAULT_API_URL;

  if (!/^https?:\/\//i.test(value)) {
    value = `https://${value}`;
  }

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return DEFAULT_API_URL;
  }

  parsed.hash = '';
  parsed.search = '';

  const normalizedPath = parsed.pathname.replace(/\/+$/, '');
  if (!normalizedPath || normalizedPath === '/') {
    parsed.pathname = '/api/v1';
  } else if (!normalizedPath.endsWith('/api/v1')) {
    parsed.pathname = `${normalizedPath}/api/v1`;
  } else {
    parsed.pathname = normalizedPath;
  }

  return parsed.toString().replace(/\/+$/, '');
}

export function isDefaultServerUrl(url: string | null | undefined): boolean {
  if (!url) return true;
  return normalizeServerUrl(url) === DEFAULT_API_URL;
}
