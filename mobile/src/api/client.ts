import { getToken, setToken, clearToken, getServerUrl } from '../utils/storage';
import { DEFAULT_API_URL } from '../utils/constants';
import type {
  Statement,
  Transaction,
  TransactionListResponse,
  TransactionFilters,
  Category,
  SmsBatchItem,
  SmsBatchResponse,
  MonthlySummary,
  TrendData,
  RecurringPattern,
  BudgetWithSpent,
  Bill,
} from './types';

let _onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(cb: () => void) {
  _onUnauthorized = cb;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function getBaseUrl(): Promise<string> {
  const url = await getServerUrl();
  // Return stored URL only if it's non-empty, otherwise use default
  return (url && url.trim()) ? url.trim() : DEFAULT_API_URL;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const baseUrl = await getBaseUrl();
  const token = await getToken();

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(
      0,
      'Could not reach backend server. Verify the server URL and ensure backend is running.',
    );
  }

  if (response.status === 401) {
    await clearToken();
    _onUnauthorized?.();
    throw new ApiError(401, 'Unauthorized');
  }

  if (!response.ok) {
    let detail = 'Request failed';
    const raw = await response.text().catch(() => '');
    if (raw && raw.trim()) {
      const normalized = raw.trim();
      const isHtml =
        normalized.startsWith('<!DOCTYPE html') ||
        normalized.startsWith('<html') ||
        normalized.includes('<html');
      if (isHtml) {
        detail = `Upstream gateway returned HTML error page (HTTP ${response.status}). Please retry.`;
        throw new ApiError(response.status, detail);
      }
      try {
        const parsed = JSON.parse(normalized);
        if (parsed && typeof parsed.detail === 'string') {
          detail = parsed.detail;
        } else {
          detail = normalized.slice(0, 300);
        }
      } catch {
        detail = normalized.slice(0, 300);
      }
    } else if (response.status >= 500) {
      detail = 'Backend server is temporarily unavailable. Please try again.';
    }
    throw new ApiError(response.status, detail);
  }

  return response.json();
}

// Auth
export async function setup(data: { email: string; display_name: string; password: string }) {
  const result = await request<{ access_token: string; refresh_token: string }>(
    '/auth/setup',
    { method: 'POST', body: JSON.stringify(data) },
  );
  await setToken(result.access_token);
  return result;
}

export async function login(email: string, password: string) {
  const result = await request<{ access_token: string; refresh_token: string }>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
  );
  await setToken(result.access_token);
  return result;
}

export async function requestPasswordReset(email: string) {
  return request<{
    message: string;
    delivery: string;
    preview_url: string | null;
  }>('/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(token: string, newPassword: string) {
  return request<{ message: string }>('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function changePassword(currentPassword: string, newPassword: string) {
  return request<{ message: string }>('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

export async function clearMyData(currentPassword: string, confirmation: string) {
  return request<{
    message: string;
    deleted_rows: Record<string, number>;
    deleted_files: number;
    deleted_directories: number;
    file_delete_errors: number;
  }>('/auth/clear-data', {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      confirmation,
    }),
  });
}

export async function getMe() {
  return request<{ id: string; email: string; display_name: string }>('/auth/me');
}

// Upload
export async function uploadPdf(
  fileUri: string,
  fileName: string,
  password?: string,
  bankHint?: string,
  accountTypeHint?: string,
  documentTypeHint?: string,
  forceReprocess: boolean = false,
) {
  const formData = new FormData();
  formData.append('file', {
    uri: fileUri,
    name: fileName,
    type: inferUploadMimeType(fileName),
  } as any);
  if (password) formData.append('password', password);
  if (bankHint) formData.append('bank_hint', bankHint);
  if (accountTypeHint && accountTypeHint !== 'auto') {
    formData.append('account_type_hint', accountTypeHint);
  }
  if (documentTypeHint) {
    formData.append('document_type_hint', documentTypeHint);
  }
  if (forceReprocess) formData.append('force_reprocess', 'true');

  return request<{
    pdf_id: string;
    document_id?: string | null;
    status: string;
    message: string;
    bank_name?: string | null;
    account_type?: string | null;
    parser_used?: string | null;
  }>(
    '/upload/pdf',
    { method: 'POST', body: formData },
  );
}

function inferUploadMimeType(fileName: string): string {
  const lowerName = fileName.toLowerCase();
  if (lowerName.endsWith('.csv')) return 'text/csv';
  if (lowerName.endsWith('.xlsx')) {
    return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  }
  if (lowerName.endsWith('.xls')) return 'application/vnd.ms-excel';
  return 'application/pdf';
}

export async function getRecentUploads(limit: number = 20) {
  return request<Array<{
    pdf_id: string;
    file_name: string;
    status: string;
    message: string;
    bank_name?: string | null;
    account_type?: string | null;
    parser_used?: string | null;
    transaction_count?: number | null;
    created_at?: string | null;
  }>>(`/upload/recent?limit=${limit}`);
}

export interface FolderImportRequest {
  folder_path: string;
  parse_supported?: boolean;
  dry_run?: boolean;
  force_reprocess?: boolean;
  max_files?: number;
  password_map?: Record<string, string>;
}

export interface FolderImportResponse {
  discovered: number;
  ingested: number;
  parsed: number;
  skipped: number;
  failed: number;
  by_doc_type: Record<string, number>;
  messages: string[];
}

export async function importFolder(data: FolderImportRequest) {
  return request<FolderImportResponse>('/imports/folder', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Statements
export async function getStatements(params?: { bank?: string }) {
  const query = new URLSearchParams();
  if (params?.bank) query.set('bank', params.bank);
  const qs = query.toString();
  return request<{ items: Statement[]; total: number }>(`/statements${qs ? `?${qs}` : ''}`);
}

export async function rereviewStatement(statementId: string) {
  return request<Statement>(`/statements/${statementId}/re-review`, {
    method: 'POST',
  });
}

export async function deleteStatement(statementId: string) {
  return request<{ message: string }>(`/statements/${statementId}`, {
    method: 'DELETE',
  });
}

// Transactions
export async function getTransactions(params?: TransactionFilters) {
  const query = new URLSearchParams();
  if (params?.from) query.set('from', params.from);
  if (params?.to) query.set('to', params.to);
  if (params?.bank) query.set('bank', params.bank);
  if (params?.direction) query.set('direction', params.direction);
  if (params?.search) query.set('search', params.search);
  if (params?.page) query.set('page', params.page.toString());
  if (params?.per_page) query.set('per_page', params.per_page.toString());
  const qs = query.toString();
  return request<TransactionListResponse>(`/transactions${qs ? `?${qs}` : ''}`);
}

export async function autoCategorizeUncategorized(limit: number = 300) {
  return request<{ scanned: number; updated: number }>(
    `/transactions/auto-categorize-uncategorized?limit=${limit}`,
    { method: 'POST' },
  );
}

export async function updateTransaction(txnId: string, data: Record<string, any>) {
  return request<Transaction>(`/transactions/${txnId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

// Categories
export async function getCategories() {
  return request<Category[]>('/categories');
}

// SMS
export async function syncSmsBatch(deviceId: string, items: SmsBatchItem[]) {
  return request<SmsBatchResponse>('/sms/batch', {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId, items }),
  });
}

// ─── Insights ───
export async function getMonthlySummary(month?: string) {
  const qs = month ? `?month=${month}` : '';
  return request<MonthlySummary>(`/insights/monthly-summary${qs}`);
}

export async function getTrends(months: number = 6) {
  return request<TrendData[]>(`/insights/trends?months=${months}`);
}

export async function getRecurring() {
  return request<RecurringPattern[]>('/insights/recurring');
}

// ─── Budgets ───
export async function getBudgets() {
  const res = await request<{ items: BudgetWithSpent[]; total: number }>('/budgets');
  return res.items;
}

export async function createBudget(data: { category_id?: string; amount_limit: number; period: string }) {
  return request<BudgetWithSpent>('/budgets', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ─── Bills ───
export async function getBills(status?: string) {
  const qs = status ? `?status=${status}` : '';
  const res = await request<{ items: Bill[]; total: number }>(`/bills${qs}`);
  return res.items;
}

export async function markBillPaid(id: string, data: { paid_amount: number; paid_date: string }) {
  return request<Bill>(`/bills/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ is_paid: true, ...data }),
  });
}

// Health check (for testing server connection)
export async function testConnection(): Promise<boolean> {
  try {
    const baseUrl = await getBaseUrl();
    const healthUrl = baseUrl.replace(/\/api\/v1\/?$/, '/health');
    const res = await fetch(healthUrl, { method: 'GET', headers: { 'Accept': 'application/json' } });
    return res.ok;
  } catch {
    return false;
  }
}
