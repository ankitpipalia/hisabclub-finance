export interface Statement {
  id: string;
  pdf_id?: string | null;
  pdf_filename?: string | null;
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
  source_type: string | null;
  is_reprocess: boolean;
  reprocess_count: number;
  created_at: string;
}

export interface Transaction {
  id: string;
  transaction_date: string;
  posting_date?: string | null;
  amount: number;
  direction: string;
  transaction_nature?: string;
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
  created_at: string;
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

export interface TransactionSplitPart {
  amount: number;
  merchant_raw?: string | null;
  category_id?: string | null;
  merchant_id?: string | null;
  transaction_nature?: string | null;
  notes?: string | null;
  tags?: string[] | null;
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

export interface TransactionFilters {
  from?: string;
  to?: string;
  bank?: string;
  direction?: string;
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

export interface SmsBatchItem {
  sms_hash: string;
  sender_address: string;
  sender_id: string;
  body: string;
  sms_timestamp: string;
  classification: string;
  bank_name: string;
  account_masked: string | null;
  direction: string;
  amount: number;
  description: string;
  reference_number: string | null;
  upi_id: string | null;
  confidence: number;
}

export interface SmsBatchResponse {
  accepted: number;
  duplicates: number;
  errors: number;
}

// ─── New types for production features ───

export interface MonthlySummary {
  year_month: string;
  total_income: number;
  total_expense: number;
  net_flow: number;
  category_breakdown: Record<string, number>;
  top_merchants: { name: string; amount: number; count: number }[];
  transaction_count: number;
  vs_last_month?: { income_change: number; expense_change: number };
}

export interface TrendData {
  month: string;
  income: number;
  expense: number;
  net: number;
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

export interface BalanceSnapshot {
  id: string;
  account_id?: string | null;
  statement_id?: string | null;
  position_key: string;
  label: string;
  source_kind: string;
  entry_kind: string;
  asset_type: string;
  institution_name?: string | null;
  account_masked?: string | null;
  currency: string;
  balance: number;
  as_of_date: string;
  is_active: boolean;
  metadata_json?: Record<string, unknown> | null;
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
  latest_snapshot_date?: string | null;
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
  category_name?: string | null;
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

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  first_name?: string | null;
  last_name?: string | null;
  onboarding_completed?: boolean;
  onboarding_step?: number;
}

export interface OnboardingStatus {
  completed: boolean;
  current_step: number;
  profile_complete: boolean;
  accounts_count: number;
}

export interface Institution {
  id: string;
  name: string;
  short_name: string;
  logo_key?: string | null;
  institution_type: string;
  supported_formats: Record<string, boolean>;
  is_system: boolean;
}

export interface OnboardingAccount {
  account_type: string;
  account_number_masked?: string | null;
  nickname?: string | null;
}

export interface OnboardingBank {
  institution_name: string;
  accounts: OnboardingAccount[];
}

export interface Account {
  id: string;
  institution_id?: string | null;
  institution_name: string;
  account_type: string;
  account_number_masked?: string | null;
  nickname?: string | null;
  status: string;
  metadata_json?: Record<string, unknown> | null;
  last_statement_date?: string | null;
  opening_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountCoverageRange {
  start?: string | null;
  end?: string | null;
}

export interface AccountTreeItem extends Account {
  statement_count: number;
  total_transactions: number;
  latest_balance?: number | null;
  period_coverage: AccountCoverageRange[];
}

export interface AccountInstitutionGroup {
  institution?: Institution | null;
  institution_name: string;
  accounts: AccountTreeItem[];
}

export interface AccountStatementsSummary {
  account: Account;
  statements: Statement[];
}

export interface StatementAnnotation {
  id: string;
  parsed_transaction_id?: string | null;
  canonical_transaction_id?: string | null;
  statement_id: string;
  annotation_type: string;
  content: string;
  llm_response?: string | null;
  status: string;
  actions_json?: Record<string, unknown> | null;
  page_number?: number | null;
  created_at: string;
  updated_at: string;
}

export interface StatementReviewTransaction {
  id: string;
  canonical_transaction_id?: string | null;
  transaction_date: string;
  posting_date?: string | null;
  description_raw: string;
  amount: number;
  direction: string;
  confidence: number;
  is_quarantined: boolean;
  extraction_method: string;
  line_number?: number | null;
  page_number?: number | null;
  reviewer_user_id?: string | null;
  reviewed_at?: string | null;
  annotations: StatementAnnotation[];
}

export interface StatementReview {
  statement: Statement;
  transactions: StatementReviewTransaction[];
  annotations: StatementAnnotation[];
}

export interface ConversationThread {
  id: string;
  statement_id?: string | null;
  title: string;
  status: string;
  summary?: string | null;
  metadata_json?: Record<string, unknown> | null;
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
  metadata_json?: Record<string, unknown> | null;
  is_applied: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConversationReplyResult {
  thread: ConversationThread;
  message: ConversationMessage;
  assistant_message: ConversationMessage;
  warnings: string[];
  actions: Record<string, unknown>[];
  proposed_count: number;
  applied_count: number;
  skipped_count: number;
}

export interface TaxVerificationCheck {
  check: string;
  status: string;
  app_amount: number;
  portal_amount: number;
  gap: number;
  detail: string;
}

export interface TaxPortalData {
  id: string;
  document_artifact_id?: string | null;
  document_type: string;
  assessment_year?: string | null;
  financial_year?: string | null;
  source_name?: string | null;
  pan_masked?: string | null;
  document_date?: string | null;
  extracted_json: Record<string, unknown>;
  verification_json?: Record<string, unknown> | null;
  status: string;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaxVerificationResult {
  financial_year: string;
  tax_report: Record<string, unknown>;
  portal_data: TaxPortalData[];
  checks: TaxVerificationCheck[];
  discrepancies: TaxVerificationCheck[];
}
