export const APP_NAME = 'HisabClub';
export const DEFAULT_WEB_URL = 'https://hisabclub-dev-web.ankit-tech.store';
export const DEFAULT_API_DOMAIN = 'hisabclub-dev-api.ankit-tech.store';
export const DEFAULT_API_URL = `https://${DEFAULT_API_DOMAIN}/api/v1`;

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

export const BANK_OPTIONS = [
  { value: '', label: 'Auto Detect' },
  { value: 'SBI', label: 'State Bank of India' },
  { value: 'HDFC', label: 'HDFC Bank' },
  { value: 'ICICI', label: 'ICICI Bank' },
  { value: 'AXIS', label: 'Axis Bank' },
  { value: 'KOTAK', label: 'Kotak Mahindra Bank' },
  { value: 'PNB', label: 'Punjab National Bank' },
  { value: 'BOB', label: 'Bank of Baroda' },
  { value: 'CANARA', label: 'Canara Bank' },
  { value: 'UNION', label: 'Union Bank of India' },
  { value: 'INDIAN', label: 'Indian Bank' },
  { value: 'BOI', label: 'Bank of India' },
  { value: 'IDBI', label: 'IDBI Bank' },
  { value: 'INDUSIND', label: 'IndusInd Bank' },
  { value: 'YES', label: 'Yes Bank' },
  { value: 'FEDERAL', label: 'Federal Bank' },
] as const;

export const BANKS = BANK_OPTIONS.map((item) => item.value).filter(Boolean) as string[];

export const DOCUMENT_TYPE_OPTIONS = [
  { value: 'auto', label: 'Auto via local LLM' },
  { value: 'bank_account', label: 'Bank account statement' },
  { value: 'credit_card', label: 'Credit card statement' },
] as const;
