export const APP_NAME = 'HisabClub';
export const DEFAULT_API_URL = 'http://localhost:8000/api/v1';

export const STORAGE_KEYS = {
  TOKEN: 'hisabclub_token',
  REFRESH_TOKEN: 'hisabclub_refresh_token',
  SERVER_URL: 'hisabclub_server_url',
  LAST_SMS_SYNC: 'hisabclub_last_sms_sync',
  THEME_MODE: 'hisabclub_theme_mode',
};

export const COLORS = {
  primary: '#2563EB',
  primaryDark: '#1D4ED8',
  success: '#16A34A',
  danger: '#DC2626',
  warning: '#D97706',
  background: '#F9FAFB',
  surface: '#FFFFFF',
  text: '#111827',
  textSecondary: '#6B7280',
  border: '#E5E7EB',
  debit: '#111827',
  credit: '#16A34A',
};

export const BANKS = ['HDFC', 'AXIS', 'SBI', 'ICICI', 'KOTAK'] as const;
