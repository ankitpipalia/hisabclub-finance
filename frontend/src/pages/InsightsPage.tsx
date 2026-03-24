import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { MonthlySummary, TrendData, RecurringPattern } from '../api/client';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { ArrowUpRight, ArrowDownRight, TrendingUp, RefreshCw } from 'lucide-react';

const PIE_COLORS = [
  '#ff3d00', '#f97316', '#f59e0b', '#3b82f6', '#22c55e',
  '#14b8a6', '#ef4444', '#8b5cf6', '#84cc16', '#06b6d4',
];

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

export default function InsightsPage() {
  const [summary, setSummary] = useState<MonthlySummary | null>(null);
  const [trends, setTrends] = useState<TrendData[]>([]);
  const [recurring, setRecurring] = useState<RecurringPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [summaryRes, trendsRes, recurringRes] = await Promise.all([
          api.getMonthlySummary(),
          api.getTrends(6),
          api.getRecurring(),
        ]);
        setSummary(summaryRes);
        setTrends(trendsRes);
        setRecurring(recurringRes);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load insights');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading insights...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="hc-page">
        <div className="hc-msg hc-msg-danger">{error}</div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="hc-page">
        <div className="hc-empty">
          <TrendingUp size={44} strokeWidth={1.5} color="var(--hc-muted-fg)" />
          <h2 style={{ marginTop: '0.7rem', fontSize: '1.35rem' }}>No data yet</h2>
          <p className="hc-page-subtitle" style={{ marginTop: '0.4rem' }}>
            Upload statements to generate spending and income insights.
          </p>
        </div>
      </div>
    );
  }

  const categoryData = Object.entries(summary.category_breakdown ?? {}).map(([name, value]) => ({
    name,
    value,
  }));

  const incomeChange =
    typeof summary.vs_last_month === 'object' && summary.vs_last_month
      ? summary.vs_last_month.income_change
      : undefined;
  const expenseChange =
    typeof summary.vs_last_month === 'number'
      ? summary.vs_last_month
      : summary.vs_last_month?.expense_change;

  const trendChartData = trends.map((t) => ({
    month: t.month.slice(2).replace('-', '/'),
    Income: Math.round(t.income),
    Expense: Math.round(t.expense),
  }));

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Analytics</p>
          <h1 className="hc-page-title">Insights</h1>
          <p className="hc-page-subtitle">Understand category drift, recurring charges, and cashflow movement.</p>
        </div>
      </header>

      <section className="hc-grid-4 hc-stagger">
        <div className="hc-panel">
          <p className="hc-stat-label">
            <ArrowUpRight size={15} strokeWidth={1.5} />
            Income
          </p>
          <p className="hc-stat-value">{formatAmount(summary.total_income)}</p>
          {incomeChange !== undefined && (
            <p className="hc-panel-sub" style={{ color: incomeChange >= 0 ? '#22c55e' : 'var(--hc-accent)' }}>
              {incomeChange >= 0 ? '+' : ''}
              {incomeChange.toFixed(1)}% vs last month
            </p>
          )}
        </div>

        <div className="hc-panel">
          <p className="hc-stat-label">
            <ArrowDownRight size={15} strokeWidth={1.5} />
            Expenses
          </p>
          <p className="hc-stat-value">{formatAmount(summary.total_expense)}</p>
          {expenseChange !== undefined && (
            <p className="hc-panel-sub" style={{ color: expenseChange <= 0 ? '#22c55e' : 'var(--hc-accent)' }}>
              {expenseChange >= 0 ? '+' : ''}
              {expenseChange.toFixed(1)}% vs last month
            </p>
          )}
        </div>

        <div className="hc-panel">
          <p className="hc-stat-label">
            <TrendingUp size={15} strokeWidth={1.5} />
            Net Flow
          </p>
          <p className="hc-stat-value" style={{ color: summary.net_flow >= 0 ? '#22c55e' : 'var(--hc-accent)' }}>
            {formatAmount(summary.net_flow)}
          </p>
        </div>

        <div className="hc-panel">
          <p className="hc-stat-label">Transactions</p>
          <p className="hc-stat-value">{summary.transaction_count}</p>
          <p className="hc-panel-sub">{summary.year_month}</p>
        </div>
      </section>

      <section className="hc-grid-2">
        <div className="hc-panel">
          <h2 className="hc-panel-title">Category Breakdown</h2>
          {categoryData.length === 0 ? (
            <p className="hc-panel-sub" style={{ marginTop: '0.8rem' }}>No category data available</p>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={categoryData}
                  cx="50%"
                  cy="50%"
                  outerRadius={95}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                >
                  {categoryData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => formatAmount(Number(value))} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="hc-panel">
          <h2 className="hc-panel-title">Monthly Trend (6 months)</h2>
          {trendChartData.length === 0 ? (
            <p className="hc-panel-sub" style={{ marginTop: '0.8rem' }}>No trend data available</p>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={trendChartData}>
                <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value) => formatAmount(Number(value))} />
                <Legend />
                <Bar dataKey="Income" fill="#22c55e" radius={[0, 0, 0, 0]} />
                <Bar dataKey="Expense" fill="var(--hc-accent)" radius={[0, 0, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      <section className="hc-panel">
        <div className="hc-panel-head">
          <div>
            <h2 className="hc-panel-title">Recurring Transactions</h2>
            <p className="hc-panel-sub">Subscriptions and regular payments detected from transaction history.</p>
          </div>
        </div>

        {recurring.length === 0 ? (
          <p className="hc-panel-sub">No recurring transactions detected yet.</p>
        ) : (
          <div>
            {recurring.map((item, idx) => (
              <div
                key={item.id}
                style={{
                  padding: '0.75rem 0',
                  borderTop: idx ? '1px solid var(--hc-border)' : 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.8rem',
                  flexWrap: 'wrap',
                }}
              >
                <div>
                  <p style={{ fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                    <RefreshCw size={14} strokeWidth={1.5} color="var(--hc-accent)" />
                    {item.merchant_name || item.description_pattern}
                  </p>
                  <p className="hc-panel-sub">
                    {item.frequency}
                    {item.category_name ? ` · ${item.category_name}` : ''}
                    {item.next_expected
                      ? ` · Next: ${new Date(item.next_expected).toLocaleDateString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                        })}`
                      : ''}
                  </p>
                </div>
                <div className="text-right">
                  <p style={{ fontWeight: 600 }}>{formatAmount(item.typical_amount)}</p>
                  <span className={`hc-badge ${item.is_active ? 'hc-badge-ok' : 'hc-badge-warn'}`}>
                    {item.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
