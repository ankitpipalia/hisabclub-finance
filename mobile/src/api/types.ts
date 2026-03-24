export interface Statement {
  id: string;
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
  amount: number;
  direction: string;
  merchant_raw: string;
  merchant_normalized: string | null;
  category_name: string | null;
  bank_name: string | null;
  bank_label: string | null;
  account_type: string | null;
  account_masked: string | null;
  is_recurring: boolean;
  is_anomalous: boolean;
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
