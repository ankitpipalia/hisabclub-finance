const API_BASE = '/api/v1';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('hisabclub_token');
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('hisabclub_token', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('hisabclub_token');
  }

  isAuthenticated(): boolean {
    return this.token !== null;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string> || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
      });
    } catch {
      throw new ApiError(
        0,
        'Could not reach backend server. Verify API availability and try again.',
      );
    }

    if (response.status === 401) {
      this.clearToken();
      window.location.href = '/login';
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

  private async requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string> || {}),
    };
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
    if (response.status === 401) {
      this.clearToken();
      window.location.href = '/login';
      throw new ApiError(401, 'Unauthorized');
    }
    if (!response.ok) {
      const message = await response.text().catch(() => 'File request failed');
      throw new ApiError(response.status, message || 'File request failed');
    }
    return response.blob();
  }

  // For raw responses (CSV export)
  private async requestRaw(path: string): Promise<Response> {
    const headers: Record<string, string> = {};
    if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
    return fetch(`${API_BASE}${path}`, { headers });
  }

  // Auth
  async setup(data: {
    email: string;
    display_name: string;
    password: string;
    first_name?: string;
    last_name?: string;
    date_of_birth?: string;
    pan_number?: string;
  }) {
    const result = await this.request<{ access_token: string; refresh_token: string }>(
      '/auth/setup',
      { method: 'POST', body: JSON.stringify(data) }
    );
    this.setToken(result.access_token);
    return result;
  }

  async register(data: {
    email: string;
    display_name: string;
    password: string;
    first_name?: string;
    last_name?: string;
    date_of_birth?: string;
    pan_number?: string;
  }) {
    const result = await this.request<{ access_token: string; refresh_token: string }>(
      '/auth/register',
      { method: 'POST', body: JSON.stringify(data) }
    );
    this.setToken(result.access_token);
    return result;
  }

  async login(email: string, password: string) {
    const result = await this.request<{ access_token: string; refresh_token: string }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) }
    );
    this.setToken(result.access_token);
    return result;
  }

  async requestPasswordReset(email: string) {
    return this.request<ForgotPasswordResponse>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  async resetPassword(token: string, newPassword: string) {
    return this.request<MessageResponse>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  }

  async changePassword(currentPassword: string, newPassword: string) {
    return this.request<MessageResponse>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
  }

  async clearMyData(currentPassword: string, confirmation: string) {
    return this.request<ClearUserDataResponse>('/auth/clear-data', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        confirmation,
      }),
    });
  }

  async getMe() {
    return this.request<UserProfile>('/auth/me');
  }

  async getOnboardingStatus() {
    return this.request<OnboardingStatus>('/auth/onboarding/status');
  }

  async updateOnboardingProfile(data: {
    first_name?: string;
    last_name?: string;
    date_of_birth?: string;
    pan_number?: string;
  }) {
    return this.request<UserProfile>('/auth/onboarding/profile', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async saveOnboardingBanks(data: { banks: OnboardingBank[] }) {
    return this.request<MessageResponse>('/auth/onboarding/banks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async completeOnboarding() {
    return this.request<OnboardingStatus>('/auth/onboarding/complete', {
      method: 'POST',
    });
  }

  // Upload
  async uploadPdf(
    file: File,
    password?: string,
    bankHint?: string,
    accountTypeHint?: string,
    documentTypeHint?: string,
    forceReprocess: boolean = false,
  ) {
    const formData = new FormData();
    formData.append('file', file);
    if (password) formData.append('password', password);
    if (bankHint) formData.append('bank_hint', bankHint);
    if (accountTypeHint && accountTypeHint !== 'auto') {
      formData.append('account_type_hint', accountTypeHint);
    }
    if (documentTypeHint) formData.append('document_type_hint', documentTypeHint);
    if (forceReprocess) formData.append('force_reprocess', 'true');
    return this.request<UploadResponse>(
      '/upload/pdf',
      { method: 'POST', body: formData }
    );
  }

  async uploadPdfs(
    items: Array<{
      file: File;
      password?: string;
      bank_hint?: string;
      account_type_hint?: string;
      document_type_hint?: string;
      force_reprocess?: boolean;
    }>,
  ) {
    const formData = new FormData();
    const itemPayload: Array<Record<string, unknown>> = [];
    for (const item of items) {
      formData.append('files', item.file);
      itemPayload.push({
        password: item.password || undefined,
        bank_hint: item.bank_hint || undefined,
        account_type_hint: item.account_type_hint || undefined,
        document_type_hint: item.document_type_hint || undefined,
        force_reprocess: Boolean(item.force_reprocess),
      });
    }
    formData.append('items_json', JSON.stringify(itemPayload));
    return this.request<BulkUploadResponse>(
      '/upload/pdfs',
      { method: 'POST', body: formData },
    );
  }

  async getUploadStatus(pdfId: string) {
    return this.request<UploadStatusResponse>(`/upload/${pdfId}/status`);
  }

  async getRecentUploads(limit: number = 20) {
    return this.request<UploadReviewItem[]>(`/upload/recent?limit=${limit}`);
  }

  // Statements
  async getStatements(params?: { bank?: string }) {
    const query = new URLSearchParams();
    if (params?.bank) query.set('bank', params.bank);
    const qs = query.toString();
    return this.request<{ items: Statement[]; total: number }>(
      `/statements${qs ? `?${qs}` : ''}`
    );
  }

  async getStatementIntegrity(statementId: string) {
    return this.request<StatementIntegrityResponse>(`/statements/${statementId}/integrity`);
  }

  async getStatementPdf(statementId: string) {
    return this.requestBlob(`/statements/${statementId}/pdf`);
  }

  async getStatementReview(statementId: string) {
    return this.request<StatementReview>(`/statements/${statementId}/review`);
  }

  async annotateStatementTransaction(
    statementId: string,
    txnId: string,
    payload: {
      annotation_type: string;
      content: string;
      page_number?: number;
      apply_changes?: boolean;
    },
  ) {
    return this.request<StatementAnnotation>(`/statements/${statementId}/transactions/${txnId}/annotate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async verifyStatementTransaction(statementId: string, txnId: string) {
    return this.request<MessageResponse>(`/statements/${statementId}/transactions/${txnId}/verify`, {
      method: 'POST',
    });
  }

  async bulkVerifyStatement(statementId: string) {
    return this.request<MessageResponse>(`/statements/${statementId}/bulk-verify`, {
      method: 'POST',
    });
  }

  async rereviewStatement(statementId: string) {
    return this.request<Statement>(`/statements/${statementId}/re-review`, {
      method: 'POST',
    });
  }

  async deleteStatement(statementId: string) {
    return this.request<MessageResponse>(`/statements/${statementId}`, {
      method: 'DELETE',
    });
  }

  // Transactions
  async getTransactions(params?: TransactionFilters) {
    const query = new URLSearchParams();
    if (params?.from) query.set('from', params.from);
    if (params?.to) query.set('to', params.to);
    if (params?.bank) query.set('bank', params.bank);
    if (params?.direction) query.set('direction', params.direction);
    if (params?.nature) query.set('nature', params.nature);
    if (params?.search) query.set('search', params.search);
    if (params?.page) query.set('page', params.page.toString());
    if (params?.per_page) query.set('per_page', params.per_page.toString());
    const qs = query.toString();
    return this.request<TransactionListResponse>(
      `/transactions${qs ? `?${qs}` : ''}`
    );
  }

  async autoCategorizeUncategorized(limit: number = 300) {
    return this.request<{ scanned: number; updated: number }>(
      `/transactions/auto-categorize-uncategorized?limit=${limit}`,
      { method: 'POST' }
    );
  }

  async reclassifyTransferPayments(params?: {
    days?: number;
    limit?: number;
    max_gap_days?: number;
    use_llm?: boolean;
  }) {
    const query = new URLSearchParams();
    if (params?.days !== undefined) query.set('days', String(params.days));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.max_gap_days !== undefined) {
      query.set('max_gap_days', String(params.max_gap_days));
    }
    if (params?.use_llm !== undefined) query.set('use_llm', String(params.use_llm));
    const qs = query.toString();
    return this.request<ReclassifyTransferResponse>(
      `/transactions/reclassify-transfer-payments${qs ? `?${qs}` : ''}`,
      { method: 'POST' },
    );
  }

  async reconcileUpiFailures(params?: {
    days?: number;
    max_gap_days?: number;
    limit?: number;
  }) {
    const query = new URLSearchParams();
    if (params?.days !== undefined) query.set('days', String(params.days));
    if (params?.max_gap_days !== undefined) query.set('max_gap_days', String(params.max_gap_days));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString();
    return this.request<UpiReconcileResponse>(
      `/transactions/reconcile-upi-failures${qs ? `?${qs}` : ''}`,
      { method: 'POST' },
    );
  }

  async updateTransaction(txnId: string, data: Record<string, unknown>) {
    return this.request<Transaction>(`/transactions/${txnId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async getTransactionDetail(txnId: string) {
    return this.request<TransactionDetail>(`/transactions/${txnId}/detail`);
  }

  async bulkUpdateTransactions(payload: {
    transaction_ids: string[];
    category_id?: string | null;
    merchant_id?: string | null;
    transaction_nature?: string | null;
    notes?: string | null;
    tags?: string[] | null;
    is_excluded?: boolean | null;
  }) {
    return this.request<TransactionBulkUpdateResponse>('/transactions/bulk-update', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async splitTransaction(
    txnId: string,
    payload: {
      parts: Array<{
        amount: number;
        merchant_raw?: string | null;
        category_id?: string | null;
        merchant_id?: string | null;
        transaction_nature?: string | null;
        notes?: string | null;
        tags?: string[] | null;
      }>;
      exclude_original?: boolean;
    },
  ) {
    return this.request<TransactionSplitResponse>(`/transactions/${txnId}/split`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // Categories
  async getCategories() {
    return this.request<Category[]>('/categories');
  }

  // Merchants
  async getMerchants(search?: string) {
    const qs = search ? `?search=${encodeURIComponent(search)}` : '';
    return this.request<Merchant[]>(`/merchants${qs}`);
  }

  // ─── Insights ───
  async getMonthlySummary(month?: string) {
    const qs = month ? `?year_month=${month}` : '';
    return this.request<MonthlySummary>(`/insights/monthly-summary${qs}`);
  }

  async getTrends(months: number = 6) {
    const result = await this.request<TrendData[] | TrendResponse>(
      `/insights/trends?months=${months}`
    );
    // Backward/forward compatible: endpoint may return either raw list or wrapped payload.
    if (Array.isArray(result)) return result;
    return Array.isArray(result.data) ? result.data : [];
  }

  async getRecurring() {
    return this.request<RecurringPattern[]>('/insights/recurring');
  }

  async getAnomalies(params?: {
    window_days?: number;
    history_days?: number;
    sigma?: number;
    limit?: number;
  }) {
    const query = new URLSearchParams();
    if (params?.window_days) query.set('window_days', String(params.window_days));
    if (params?.history_days) query.set('history_days', String(params.history_days));
    if (params?.sigma) query.set('sigma', String(params.sigma));
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return this.request<AnomalyResponse>(`/insights/anomalies${qs ? `?${qs}` : ''}`);
  }

  async listTransferMatches(params?: { status?: string; limit?: number }) {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return this.request<TransferMatchListResponse>(`/transfers${qs ? `?${qs}` : ''}`);
  }

  async resolveTransferMatch(
    matchId: string,
    decision: 'confirm' | 'reject',
  ) {
    return this.request<TransferMatch>(`/transfers/${matchId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    });
  }

  async getNetWorthOverview(months: number = 12) {
    return this.request<NetWorthOverview>(`/net-worth/overview?months=${months}`);
  }

  async createManualNetWorthSnapshot(payload: {
    label: string;
    entry_kind: 'asset' | 'liability';
    asset_type: string;
    balance: number;
    as_of_date: string;
    institution_name?: string | null;
    account_masked?: string | null;
    currency?: string;
    metadata_json?: Record<string, unknown> | null;
    position_key?: string | null;
  }) {
    return this.request<BalanceSnapshot>('/net-worth/manual-snapshots', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async deleteManualNetWorthSnapshot(snapshotId: string) {
    return this.request<BalanceSnapshot>(`/net-worth/manual-snapshots/${snapshotId}`, {
      method: 'DELETE',
    });
  }

  async getSubscriptions() {
    return this.request<SubscriptionOverview>('/subscriptions');
  }

  async getTransferReconciliations(params?: {
    from?: string;
    to?: string;
    max_gap_days?: number;
    limit?: number;
  }) {
    const query = new URLSearchParams();
    if (params?.from) query.set('from', params.from);
    if (params?.to) query.set('to', params.to);
    if (params?.max_gap_days !== undefined) {
      query.set('max_gap_days', String(params.max_gap_days));
    }
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString();
    return this.request<ReconciliationResponse>(`/insights/reconciliations${qs ? `?${qs}` : ''}`);
  }

  async getTaxCompliance(params?: { from?: string; to?: string }) {
    const query = new URLSearchParams();
    if (params?.from) query.set('from', params.from);
    if (params?.to) query.set('to', params.to);
    const qs = query.toString();
    return this.request<TaxComplianceResponse>(`/insights/tax-compliance${qs ? `?${qs}` : ''}`);
  }

  async assistantChat(payload: AssistantChatRequest) {
    return this.request<AssistantChatResponse>('/assistant/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getAccounts() {
    return this.request<Account[]>('/accounts');
  }

  async getAccountsTree() {
    return this.request<AccountInstitutionGroup[]>('/accounts/tree');
  }

  async getInstitutions() {
    return this.request<Institution[]>('/accounts/institutions');
  }

  async createAccount(payload: {
    institution_name: string;
    account_type: string;
    account_number_masked?: string;
    nickname?: string;
    metadata_json?: Record<string, unknown>;
  }) {
    return this.request<Account>('/accounts', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async updateAccount(accountId: string, payload: {
    nickname?: string | null;
    status?: string;
    metadata_json?: Record<string, unknown>;
  }) {
    return this.request<Account>(`/accounts/${accountId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  async closeAccount(accountId: string) {
    return this.request<Account>(`/accounts/${accountId}`, {
      method: 'DELETE',
    });
  }

  async getAccountStatements(accountId: string) {
    return this.request<AccountStatementsSummary>(`/accounts/${accountId}/statements`);
  }

  async getConversations() {
    return this.request<ConversationThread[]>('/conversations');
  }

  async createConversation(payload: {
    title: string;
    statement_id?: string | null;
    initial_message?: string;
  }) {
    return this.request<ConversationThread>('/conversations', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getConversationMessages(threadId: string) {
    return this.request<ConversationMessage[]>(`/conversations/${threadId}/messages`);
  }

  async replyConversation(threadId: string, payload: { message: string; apply_changes?: boolean }) {
    return this.request<ConversationReplyResult>(`/conversations/${threadId}/reply`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getConversationPendingCount() {
    return this.request<{ pending_count: number }>('/conversations/pending-count');
  }

  async resolveConversation(threadId: string) {
    return this.request<{ resolved: boolean; thread: ConversationThread }>(`/conversations/${threadId}/resolve`, {
      method: 'POST',
    });
  }

  async uploadTaxPortalDocument(
    file: File,
    documentType: string,
    financialYear?: string,
    password?: string,
    forceReprocess: boolean = false,
  ) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);
    if (financialYear) formData.append('financial_year', financialYear);
    if (password) formData.append('password', password);
    if (forceReprocess) formData.append('force_reprocess', 'true');
    return this.request<TaxPortalUploadResult>('/tax/upload-portal-document', {
      method: 'POST',
      body: formData,
    });
  }

  async getTaxVerification(financialYear: string) {
    return this.request<TaxVerificationResult>(`/tax/verification/${encodeURIComponent(financialYear)}`);
  }

  async getTaxPortalData(financialYear: string) {
    return this.request<TaxPortalData[]>(`/tax/portal-data/${encodeURIComponent(financialYear)}`);
  }

  async getTaxDiscrepancies(financialYear: string) {
    return this.request<TaxVerificationCheck[]>(`/tax/discrepancies/${encodeURIComponent(financialYear)}`);
  }

  // ─── Budgets ───
  async getBudgets() {
    const res = await this.request<{ items: BudgetWithSpent[]; total: number }>('/budgets');
    return res.items;
  }

  async createBudget(data: { category_id?: string; amount_limit: number; period: string }) {
    return this.request<BudgetWithSpent>('/budgets', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteBudget(id: string) {
    return this.request<void>(`/budgets/${id}`, { method: 'DELETE' });
  }

  // ─── Bills ───
  async getBills(status?: string) {
    const qs = status ? `?status=${status}` : '';
    const res = await this.request<{ items: Bill[]; total: number }>(`/bills${qs}`);
    return res.items;
  }

  async markBillPaid(id: string, data: { paid_amount: number; paid_date: string }) {
    return this.request<Bill>(`/bills/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_paid: true, ...data }),
    });
  }

  // ─── Export ───
  async exportCsv(params?: { from?: string; to?: string }) {
    const query = new URLSearchParams();
    if (params?.from) query.set('from', params.from);
    if (params?.to) query.set('to', params.to);
    const qs = query.toString();
    const res = await this.requestRaw(`/export/csv${qs ? `?${qs}` : ''}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hisabclub-transactions-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ─── Gmail ───
  async connectGmail() {
    return this.request<{ auth_url: string }>('/gmail/connect', { method: 'POST' });
  }

  async getGmailAllowlist() {
    return this.request<GmailAllowlistAccount[]>('/gmail/allowlist');
  }

  async updateGmailAllowlist(accountId: string, senders: string[]) {
    return this.request<GmailAllowlistAccount>(`/gmail/allowlist?account_id=${encodeURIComponent(accountId)}`, {
      method: 'PUT',
      body: JSON.stringify({ senders }),
    });
  }

  async syncGmail() {
    return this.request<GmailSyncResult>('/gmail/sync', {
      method: 'POST',
    });
  }

  // ─── Local Imports ───
  async importFolder(data: FolderImportRequest) {
    return this.request<FolderImportResponse>('/imports/folder', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getDocumentArtifacts(params?: { status?: string; doc_type?: string; limit?: number }) {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.doc_type) query.set('doc_type', params.doc_type);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return this.request<{ items: DocumentArtifact[]; total: number }>(
      `/imports/artifacts${qs ? `?${qs}` : ''}`
    );
  }

  async getArtifactPdf(artifactId: string) {
    return this.requestBlob(`/imports/artifacts/${artifactId}/file`);
  }

  async getParserSupportQueue(limit: number = 200) {
    return this.request<ParserSupportQueueResponse>(`/imports/parser-support-queue?limit=${limit}`);
  }

  async getReviewTasks(statusFilter: string = 'open', limit: number = 50) {
    const query = new URLSearchParams();
    if (statusFilter) query.set('status', statusFilter);
    query.set('limit', String(limit));
    return this.request<ReviewTask[]>(`/reviews/tasks?${query.toString()}`);
  }

  async resolveReviewTask(taskId: string, action: 'promote' | 'ignore', reasonCode?: string) {
    return this.request<ResolveReviewTaskResult>(`/reviews/tasks/${taskId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        reason_code: reasonCode ?? null,
      }),
    });
  }
}

// ─── Types ───

export interface Statement {
  id: string;
  pdf_id: string | null;
  pdf_filename: string | null;
  bank_name: string;
  account_type: string;
  account_number_masked: string | null;
  statement_period_start: string | null;
  statement_period_end: string | null;
  due_date: string | null;
  total_amount_due: number | null;
  min_amount_due: number | null;
  credit_limit: number | null;
  parse_status: string;
  transaction_count: number | null;
  expected_row_count: number | null;
  extracted_row_count: number | null;
  promoted_row_count: number | null;
  quarantined_row_count: number | null;
  yield_rate: number | null;
  source_type: string | null;
  is_reprocess: boolean;
  reprocess_count: number;
  created_at: string;
}

export interface StatementAnnotation {
  id: string;
  parsed_transaction_id: string | null;
  canonical_transaction_id: string | null;
  statement_id: string;
  annotation_type: string;
  content: string;
  llm_response: string | null;
  status: string;
  actions_json: Record<string, unknown> | null;
  page_number: number | null;
  created_at: string;
  updated_at: string;
}

export interface StatementReviewTransaction {
  id: string;
  canonical_transaction_id: string | null;
  transaction_date: string;
  posting_date: string | null;
  description_raw: string;
  amount: number;
  direction: string;
  confidence: number;
  is_quarantined: boolean;
  extraction_method: string;
  line_number: number | null;
  page_number: number | null;
  reviewer_user_id: string | null;
  reviewed_at: string | null;
  annotations: StatementAnnotation[];
}

export interface StatementReview {
  statement: Statement;
  transactions: StatementReviewTransaction[];
  annotations: StatementAnnotation[];
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  onboarding_completed: boolean;
  onboarding_step: number;
}

export interface OnboardingStatus {
  completed: boolean;
  current_step: number;
  profile_complete: boolean;
  accounts_count: number;
}

export interface OnboardingBankAccount {
  account_type: string;
  account_number_masked?: string | null;
  nickname?: string | null;
}

export interface OnboardingBank {
  institution_name: string;
  accounts: OnboardingBankAccount[];
}

export interface Institution {
  id: string;
  name: string;
  short_name: string;
  logo_key: string | null;
  institution_type: string;
  supported_formats: Record<string, boolean>;
  is_system: boolean;
}

export interface Account {
  id: string;
  institution_id: string | null;
  institution_name: string;
  account_type: string;
  account_number_masked: string | null;
  nickname: string | null;
  status: string;
  metadata_json: Record<string, unknown> | null;
  last_statement_date: string | null;
  opening_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountCoverageRange {
  start: string | null;
  end: string | null;
}

export interface AccountTreeItem extends Account {
  statement_count: number;
  total_transactions: number;
  latest_balance: number | null;
  period_coverage: AccountCoverageRange[];
}

export interface AccountInstitutionGroup {
  institution: Institution | null;
  institution_name: string;
  accounts: AccountTreeItem[];
}

export interface AccountStatementsSummary {
  account: Account;
  statements: Statement[];
}

export interface ForgotPasswordResponse {
  message: string;
  delivery: string;
  preview_url: string | null;
}

export interface UploadReviewItem {
  pdf_id: string;
  file_name: string;
  status: string;
  message: string;
  bank_name: string | null;
  account_type: string | null;
  parser_used: string | null;
  transaction_count: number | null;
  created_at: string | null;
}

export interface MessageResponse {
  message: string;
}

export interface ClearUserDataResponse {
  message: string;
  deleted_rows: Record<string, number>;
  deleted_files: number;
  deleted_directories: number;
  file_delete_errors: number;
}

export interface StatementIntegrityResponse {
  statement_id: string;
  account_type: string;
  status: string;
  transaction_count: number;
  debit_total: number;
  credit_total: number;
  net_activity: number;
  total_amount_due: number | null;
  min_amount_due: number | null;
  previous_balance: number | null;
  closing_balance: number | null;
  expected_closing_balance: number | null;
  due_gap: number | null;
  closing_balance_gap: number | null;
  tolerance_due: number;
  tolerance_balance: number;
  llm_status: string | null;
  llm_confidence: number | null;
  llm_reason: string | null;
  notes: string[];
}

export interface Transaction {
  id: string;
  transaction_date: string;
  posting_date?: string | null;
  amount: number;
  direction: string;
  transaction_nature: string;
  currency?: string;
  merchant_raw: string;
  merchant_normalized: string | null;
  category_id?: string | null;
  category_name: string | null;
  bank_name: string | null;
  bank_label: string | null;
  account_type: string | null;
  account_masked: string | null;
  is_recurring: boolean;
  is_anomalous: boolean;
  is_excluded?: boolean;
  notes: string | null;
  tags: string[] | null;
  created_at?: string;
}

export interface TransactionListResponse {
  items: Transaction[];
  total: number;
  page: number;
  per_page: number;
}

export interface TransactionBulkUpdateResponse {
  updated_count: number;
  items: Transaction[];
}

export interface TransactionSplitResponse {
  original_transaction: Transaction;
  created_transactions: Transaction[];
}

export interface TransactionSource {
  parsed_txn_id: string;
  statement_id: string | null;
  source_type: string;
  description_raw: string;
  confidence: number;
  extraction_method: string;
  match_method: string;
  is_primary: boolean;
}

export interface TransactionOverride {
  id: string;
  field_name: string;
  old_value: string | null;
  new_value: string;
  override_reason: string | null;
  created_at: string;
}

export interface TransactionDetail {
  transaction: Transaction;
  sources: TransactionSource[];
  overrides: TransactionOverride[];
  split_parent: Transaction | null;
  split_children: Transaction[];
}

export interface ReclassifyTransferResponse {
  scanned: number;
  updated: number;
  matched_credit_card_pairs: number;
  llm_checked: number;
  llm_promoted: number;
}

export interface UpiReconcileResponse {
  scanned: number;
  matched_pairs: number;
  updated_transactions: number;
}

export interface ReviewTask {
  id: string;
  statement_id: string;
  task_type: string;
  status: string;
  reason_code: string;
  title: string;
  details: string | null;
  payload_json: Record<string, unknown> | null;
  resolved_by_user_id: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResolveReviewTaskResult {
  task: ReviewTask;
  promoted_count: number;
  ignored_count: number;
}

export interface TransactionFilters {
  from?: string;
  to?: string;
  bank?: string;
  direction?: string;
  nature?: string;
  search?: string;
  page?: number;
  per_page?: number;
}

export interface Category {
  id: string;
  name: string;
  parent_id: string | null;
  icon: string;
  color: string;
  is_system: boolean;
}

export interface Merchant {
  id: string;
  name: string;
  name_normalized: string;
  category_id: string | null;
  merchant_type: string | null;
}

export interface MonthlySummary {
  year_month: string;
  total_income: number;
  total_expense: number;
  net_flow: number;
  category_breakdown: Record<string, number>;
  top_merchants: { name: string; amount: number; count: number }[];
  transaction_count: number;
  vs_last_month?: number | { income_change?: number; expense_change?: number } | null;
}

export interface TrendData {
  month: string;
  income: number;
  expense: number;
  net: number;
  category_breakdown: Record<string, number>;
}

export interface TrendResponse {
  months: number;
  data: TrendData[];
}

export interface RecurringPattern {
  id: string;
  description_pattern: string;
  merchant_name: string | null;
  typical_amount: number;
  frequency: string;
  next_expected: string | null;
  category_name: string | null;
  is_active: boolean;
}

export interface AnomalyTransaction {
  transaction_id: string;
  transaction_date: string;
  amount: string;
  merchant: string;
  category_id: string | null;
  category_name: string | null;
  bank_name: string | null;
  reason: 'category_spike' | 'new_large_merchant';
  detail: string;
  expected_mean: string | null;
  expected_max: string | null;
  deviation_ratio: number | null;
}

export interface AnomalyResponse {
  items: AnomalyTransaction[];
  total: number;
}

export interface TransferLeg {
  transaction_id: string;
  transaction_date: string;
  amount: string;
  bank_name: string | null;
  account_masked: string | null;
  direction: string;
  description: string;
}

export interface TransferMatch {
  id: string;
  match_type: string;
  confidence: number;
  resolution_status: 'auto' | 'confirmed' | 'rejected' | string;
  matched_at: string;
  debit_leg: TransferLeg;
  credit_leg: TransferLeg;
}

export interface TransferMatchListResponse {
  items: TransferMatch[];
  total: number;
}

export interface ReconciliationTransaction {
  id: string;
  transaction_date: string;
  amount: number;
  direction: string;
  transaction_nature: string;
  merchant_raw: string;
  bank_name: string | null;
  account_type: string | null;
  account_masked: string | null;
  source_files: string[];
}

export interface ReconciliationPair {
  amount: number;
  day_gap: number;
  confidence: number;
  reasoning: string;
  debit: ReconciliationTransaction;
  credit: ReconciliationTransaction;
}

export interface ReconciliationResponse {
  total_transfer_transactions: number;
  matched_pairs: number;
  unmatched_transactions: number;
  matched_amount: number;
  match_rate: number;
  pairs: ReconciliationPair[];
  unmatched: ReconciliationTransaction[];
}

export interface TaxComplianceTotals {
  total_income: number;
  salary_income: number;
  interest_income: number;
  dividend_income: number;
  other_income: number;
  total_expense: number;
  tax_payments: number;
  investment_outflow: number;
  transfer_internal: number;
  estimated_taxable_income: number;
  new_regime_tax_before_rebate: number;
  new_regime_rebate: number;
  new_regime_tax_after_rebate: number;
  new_regime_cess: number;
  new_regime_total_tax: number;
  new_regime_rebate_threshold: number;
  tax_due_or_refund: number;
  documented_interest_income: number;
  documented_interest_tds: number;
  documented_tax_payments: number;
  documented_fd_principal: number;
  documented_fd_interest: number;
  documented_ppf_contribution: number;
  documented_ppf_interest: number;
  documented_ppf_closing_balance: number;
  savings_account_count: number;
}

export interface TaxActionItem {
  severity: string;
  title: string;
  detail: string;
}

export interface TaxComplianceCashItem {
  transaction_id: string;
  transaction_date: string;
  amount: number;
  merchant_raw: string;
  bank_name: string | null;
  account_type: string | null;
}

export interface TaxSavingsAccount {
  bank_name: string;
  account_masked: string | null;
  statement_count: number;
  interest_income: number;
}

export interface TaxLinkageCheck {
  check: string;
  status: string;
  ledger_amount: number;
  document_amount: number;
  gap: number;
  detail: string;
}

export interface TaxComplianceResponse {
  period_start: string;
  period_end: string;
  tax_regime: string;
  tax_financial_year: string;
  totals: TaxComplianceTotals;
  document_coverage: Record<string, number>;
  unresolved_statement_docs: number;
  high_value_cash_expenses: TaxComplianceCashItem[];
  savings_accounts: TaxSavingsAccount[];
  linkage_checks: TaxLinkageCheck[];
  document_amounts: Record<string, number>;
  action_items: TaxActionItem[];
  tax_notes: string[];
}

export interface BudgetWithSpent {
  id: string;
  category_id: string | null;
  category_name: string | null;
  amount_limit: number;
  period: string;
  is_active: boolean;
  spent_amount: number;
  remaining: number;
  percentage_used: number;
}

export interface Bill {
  id: string;
  bank_name: string;
  account_masked: string | null;
  billing_period_start: string;
  billing_period_end: string;
  due_date: string;
  total_due: number;
  min_due: number | null;
  is_paid: boolean;
  paid_amount: number | null;
  paid_date: string | null;
  days_until_due: number;
}

export interface GmailAllowlistAccount {
  account_id: string;
  provider_email: string | null;
  senders: string[];
}

export interface GmailSyncResult {
  emails_found: number;
  pdfs_saved: number;
  provider_email: string | null;
  error: string | null;
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

export interface DocumentArtifact {
  id: string;
  file_path: string;
  file_name: string;
  file_ext: string;
  doc_type: string;
  doc_subtype: string | null;
  bank_hint: string | null;
  status: string;
  parse_message: string | null;
  discovered_at: string;
  processed_at: string | null;
}

export interface ParserSupportQueueItem {
  bank_hint: string | null;
  doc_type: string;
  reason: string;
  count: number;
  sample_files: string[];
  sample_message: string | null;
  last_seen: string | null;
}

export interface ParserSupportQueueResponse {
  total: number;
  items: ParserSupportQueueItem[];
}

export interface UploadResponse {
  pdf_id: string;
  document_id?: string | null;
  status: string;
  message: string;
  bank_name?: string | null;
  account_type?: string | null;
  parser_used?: string | null;
}

export interface BulkUploadResultItem {
  file_name: string;
  pdf_id: string;
  document_id?: string | null;
  status: string;
  message: string;
  bank_name?: string | null;
  account_type?: string | null;
}

export interface BulkUploadResponse {
  total: number;
  success_count: number;
  reviewing_count: number;
  duplicate_count: number;
  failed_count: number;
  items: BulkUploadResultItem[];
}

export interface UploadStatusResponse {
  pdf_id: string;
  document_id?: string | null;
  status: string;
  message: string;
  statement_id?: string | null;
  transaction_count?: number | null;
  bank_name?: string | null;
  error?: string | null;
}

export interface AssistantChatRequest {
  message: string;
  apply_changes?: boolean;
  max_candidates?: number;
}

export interface AssistantActionResult {
  action: string;
  transaction_id: string;
  status: string;
  detail: string;
  before?: string | null;
  after?: string | null;
}

export interface AssistantChatResponse {
  reply: string;
  proposed_count: number;
  applied_count: number;
  skipped_count: number;
  warnings: string[];
  actions: AssistantActionResult[];
}

export interface ConversationThread {
  id: string;
  statement_id: string | null;
  title: string;
  status: string;
  summary: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  pending_question_count: number;
}

export interface ConversationMessage {
  id: string;
  thread_id: string;
  role: string;
  content: string;
  message_index: number;
  metadata_json: Record<string, unknown> | null;
  is_applied: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConversationReplyResult {
  thread: ConversationThread;
  message: ConversationMessage;
  assistant_message: ConversationMessage;
  warnings: string[];
  actions: AssistantActionResult[];
  proposed_count: number;
  applied_count: number;
  skipped_count: number;
}

export interface TaxPortalData {
  id: string;
  document_artifact_id: string | null;
  document_type: string;
  assessment_year: string | null;
  financial_year: string | null;
  source_name: string | null;
  pan_masked: string | null;
  document_date: string | null;
  extracted_json: Record<string, unknown>;
  verification_json: Record<string, unknown> | null;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaxVerificationCheck {
  check: string;
  status: string;
  app_amount: number;
  portal_amount: number;
  gap: number;
  detail: string;
}

export interface TaxVerificationResult {
  financial_year: string;
  tax_report: TaxComplianceResponse;
  portal_data: TaxPortalData[];
  checks: TaxVerificationCheck[];
  discrepancies: TaxVerificationCheck[];
}

export interface TaxPortalUploadResult {
  artifact_id: string;
  portal_data_id: string;
  document_type: string;
  financial_year: string | null;
  message: string;
}

export interface BalanceSnapshot {
  id: string;
  account_id: string | null;
  statement_id: string | null;
  position_key: string;
  label: string;
  source_kind: string;
  entry_kind: string;
  asset_type: string;
  institution_name: string | null;
  account_masked: string | null;
  currency: string;
  balance: number;
  as_of_date: string;
  is_active: boolean;
  metadata_json: Record<string, unknown> | null;
}

export interface NetWorthHistoryPoint {
  as_of_date: string;
  assets: number;
  liabilities: number;
  net_worth: number;
}

export interface NetWorthTotals {
  assets: number;
  liabilities: number;
  net_worth: number;
  positions_count: number;
  manual_positions_count: number;
  latest_snapshot_date: string | null;
}

export interface NetWorthOverview {
  totals: NetWorthTotals;
  history: NetWorthHistoryPoint[];
  positions: BalanceSnapshot[];
  manual_snapshots: BalanceSnapshot[];
}

export interface SubscriptionItem {
  id: string;
  merchant_name: string;
  description_pattern: string;
  category_name: string | null;
  typical_amount: number;
  amount_variance: number;
  frequency: string;
  expected_day: number;
  last_seen_date: string;
  next_expected: string;
  is_active: boolean;
  annual_cost_estimate: number;
  monthly_cost_equivalent: number;
  status: string;
  days_until_due: number;
}

export interface SubscriptionSummary {
  active_count: number;
  total_monthly_estimate: number;
  total_annual_estimate: number;
  overdue_count: number;
}

export interface SubscriptionOverview {
  summary: SubscriptionSummary;
  items: SubscriptionItem[];
}

export const api = new ApiClient();
