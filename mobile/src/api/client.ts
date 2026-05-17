import { Platform } from 'react-native';
import { getToken, setToken, clearToken, getServerUrl } from '../utils/storage';
import { DEFAULT_API_URL } from '../utils/constants';
import * as FileSystem from 'expo-file-system/legacy';
import type {
  Statement,
  StatementReview,
  StatementAnnotation,
  Transaction,
  TransactionBulkUpdateResponse,
  TransactionDetail,
  TransactionListResponse,
  TransactionFilters,
  TransactionSplitPart,
  TransactionSplitResponse,
  Category,
  SmsBatchItem,
  SmsBatchResponse,
  MonthlySummary,
  TrendData,
  RecurringPattern,
  BudgetWithSpent,
  Bill,
  UserProfile,
  OnboardingStatus,
  Institution,
  OnboardingBank,
  Account,
  AccountInstitutionGroup,
  AccountStatementsSummary,
  ConversationThread,
  ConversationMessage,
  ConversationReplyResult,
  TaxPortalData,
  TaxVerificationResult,
  NetWorthOverview,
  BalanceSnapshot,
  SubscriptionOverview,
} from './types';

let _onUnauthorized: (() => void) | null = null;

// Track whether a 401-driven logout is in-flight so we don't fire the callback
// once per parallel request when the token expires mid-session.
let _unauthorizedInFlight = false;

export function setOnUnauthorized(cb: () => void) {
  _onUnauthorized = cb;
}

async function handleUnauthorized() {
  if (_unauthorizedInFlight) {
    return;
  }
  _unauthorizedInFlight = true;
  try {
    await clearToken();
    _onUnauthorized?.();
  } finally {
    // Allow a future 401 to drive logout again once we're back at the
    // login screen and a new token has been issued.
    setTimeout(() => {
      _unauthorizedInFlight = false;
    }, 1500);
  }
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
  const raw = (url && url.trim()) ? url.trim() : DEFAULT_API_URL;
  // Android emulator can't reach the host machine via "localhost" — it must
  // use the special-cased 10.0.2.2 alias. iOS simulator and physical devices
  // resolve localhost normally. We only rewrite when running on Android.
  if (Platform.OS === 'android') {
    return raw.replace(/(https?:\/\/)(localhost|127\.0\.0\.1)/i, '$110.0.2.2');
  }
  return raw;
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
    await handleUnauthorized();
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

async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const baseUrl = await getBaseUrl();
  const token = await getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${baseUrl}${path}`, { ...options, headers });
  if (response.status === 401) {
    await handleUnauthorized();
    throw new ApiError(401, 'Unauthorized');
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => 'File request failed');
    throw new ApiError(response.status, detail || 'File request failed');
  }
  return response.blob();
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

export async function register(data: {
  email: string;
  display_name: string;
  password: string;
  first_name?: string;
  last_name?: string;
  date_of_birth?: string;
  pan_number?: string;
}) {
  const result = await request<{ access_token: string; refresh_token: string }>(
    '/auth/register',
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
  return request<UserProfile>('/auth/me');
}

export async function getOnboardingStatus() {
  return request<OnboardingStatus>('/auth/onboarding/status');
}

export async function updateOnboardingProfile(data: {
  first_name?: string;
  last_name?: string;
  date_of_birth?: string;
  pan_number?: string;
}) {
  return request<UserProfile>('/auth/onboarding/profile', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function saveOnboardingBanks(data: { banks: OnboardingBank[] }) {
  return request<{ message: string }>('/auth/onboarding/banks', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function completeOnboarding() {
  return request<OnboardingStatus>('/auth/onboarding/complete', {
    method: 'POST',
  });
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

export async function getStatementReview(statementId: string) {
  return request<StatementReview>(`/statements/${statementId}/review`);
}

export async function annotateStatementTransaction(
  statementId: string,
  txnId: string,
  data: {
    annotation_type: string;
    content: string;
    page_number?: number;
    apply_changes?: boolean;
  },
) {
  return request<StatementAnnotation>(`/statements/${statementId}/transactions/${txnId}/annotate`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function verifyStatementTransaction(statementId: string, txnId: string) {
  return request<{ message: string }>(`/statements/${statementId}/transactions/${txnId}/verify`, {
    method: 'POST',
  });
}

export async function bulkVerifyStatement(statementId: string) {
  return request<{ message: string }>(`/statements/${statementId}/bulk-verify`, {
    method: 'POST',
  });
}

export async function getStatementPdf(statementId: string) {
  return requestBlob(`/statements/${statementId}/pdf`);
}

export async function downloadStatementPdfToCache(statementId: string, fileName?: string) {
  const baseUrl = await getBaseUrl();
  const token = await getToken();
  if (!token) {
    throw new ApiError(401, 'Unauthorized');
  }
  const directory = `${FileSystem.cacheDirectory}statements/`;
  await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
  const targetName = (fileName || `statement-${statementId}.pdf`).replace(/[^a-zA-Z0-9._-]/g, '_');
  const localUri = `${directory}${targetName}`;
  const result = await FileSystem.downloadAsync(`${baseUrl}/statements/${statementId}/pdf`, localUri, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return result.uri;
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

export async function getTransactionDetail(txnId: string) {
  return request<TransactionDetail>(`/transactions/${txnId}/detail`);
}

export async function bulkUpdateTransactions(payload: {
  transaction_ids: string[];
  category_id?: string | null;
  merchant_id?: string | null;
  transaction_nature?: string | null;
  notes?: string | null;
  tags?: string[] | null;
  is_excluded?: boolean | null;
}) {
  return request<TransactionBulkUpdateResponse>('/transactions/bulk-update', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function splitTransaction(
  txnId: string,
  payload: {
    parts: TransactionSplitPart[];
    exclude_original?: boolean;
  },
) {
  return request<TransactionSplitResponse>(`/transactions/${txnId}/split`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// Categories
export async function getCategories() {
  return request<Category[]>('/categories');
}

// Accounts
export async function getAccounts() {
  return request<Account[]>('/accounts');
}

export async function getAccountsTree() {
  return request<AccountInstitutionGroup[]>('/accounts/tree');
}

export async function getInstitutions() {
  return request<Institution[]>('/accounts/institutions');
}

export async function createAccount(data: {
  institution_name: string;
  account_type: string;
  account_number_masked?: string;
  nickname?: string;
  metadata_json?: Record<string, unknown>;
}) {
  return request<Account>('/accounts', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getAccountStatements(accountId: string) {
  return request<AccountStatementsSummary>(`/accounts/${accountId}/statements`);
}

// Conversations
export async function getConversations() {
  return request<ConversationThread[]>('/conversations');
}

export async function createConversation(data: {
  title: string;
  statement_id?: string;
  initial_message?: string;
}) {
  return request<ConversationThread>('/conversations', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getConversationMessages(threadId: string) {
  return request<ConversationMessage[]>(`/conversations/${threadId}/messages`);
}

export async function replyConversation(
  threadId: string,
  data: { message: string; apply_changes?: boolean },
) {
  return request<ConversationReplyResult>(`/conversations/${threadId}/reply`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function resolveConversation(threadId: string) {
  return request<{ thread: ConversationThread; resolved: boolean }>(`/conversations/${threadId}/resolve`, {
    method: 'POST',
  });
}

export async function getConversationPendingCount() {
  return request<{ pending_count: number }>('/conversations/pending-count');
}

// Tax
export async function getTaxVerification(financialYear: string) {
  return request<TaxVerificationResult>(`/tax/verification/${encodeURIComponent(financialYear)}`);
}

export async function getTaxPortalData(financialYear: string) {
  return request<TaxPortalData[]>(`/tax/portal-data/${encodeURIComponent(financialYear)}`);
}

export async function getTaxDiscrepancies(financialYear: string) {
  return request<TaxVerificationResult['discrepancies']>(`/tax/discrepancies/${encodeURIComponent(financialYear)}`);
}

export async function uploadTaxPortalDocument(
  fileUri: string,
  fileName: string,
  documentType: string,
  financialYear?: string,
  password?: string,
  forceReprocess: boolean = false,
) {
  const formData = new FormData();
  formData.append('file', {
    uri: fileUri,
    name: fileName,
    type: inferUploadMimeType(fileName),
  } as any);
  formData.append('document_type', documentType);
  if (financialYear) formData.append('financial_year', financialYear);
  if (password) formData.append('password', password);
  if (forceReprocess) formData.append('force_reprocess', 'true');
  return request<{
    artifact_id: string;
    portal_data_id: string;
    document_type: string;
    financial_year?: string | null;
    message: string;
  }>('/tax/upload-portal-document', {
    method: 'POST',
    body: formData,
  });
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

export async function getNetWorthOverview(months: number = 12) {
  return request<NetWorthOverview>(`/net-worth/overview?months=${months}`);
}

export async function createManualNetWorthSnapshot(data: {
  label: string;
  entry_kind: 'asset' | 'liability';
  asset_type: string;
  balance: number;
  as_of_date: string;
  institution_name?: string;
  account_masked?: string;
  currency?: string;
  metadata_json?: Record<string, unknown>;
  position_key?: string;
}) {
  return request<BalanceSnapshot>('/net-worth/manual-snapshots', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteManualNetWorthSnapshot(snapshotId: string) {
  return request<BalanceSnapshot>(`/net-worth/manual-snapshots/${snapshotId}`, {
    method: 'DELETE',
  });
}

export async function getSubscriptions() {
  return request<SubscriptionOverview>('/subscriptions');
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
