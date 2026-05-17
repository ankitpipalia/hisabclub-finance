import { useEffect, useState } from 'react';
import {
  Upload,
  ArrowUpRight,
  ArrowDownRight,
  CreditCard,
  Download,
  ArrowRight,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { Transaction, Statement, MonthlySummary, TrendData, Bill } from '../api/client';
import { AnomaliesPanel } from '../components/AnomaliesPanel';
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
} from 'recharts';

const PIE_COLORS = ['#ff3d00', '#f97316', '#f59e0b', '#3b82f6', '#22c55e'];

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

export default function DashboardPage() {
  const navigate = useNavigate();
  const [recentTxns, setRecentTxns] = useState<Transaction[]>([]);
  const [statements, setStatements] = useState<Statement[]>([]);
  const [loading, setLoading] = useState(true);
  const [totals, setTotals] = useState({ income: 0, expense: 0 });
  const [summary, setSummary] = useState<MonthlySummary | null>(null);
  const [trends, setTrends] = useState<TrendData[]>([]);
  const [upcomingBills, setUpcomingBills] = useState<Bill[]>([]);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [txnRes, stmtRes] = await Promise.all([
          api.getTransactions({ per_page: 10 }),
          api.getStatements(),
        ]);
        setRecentTxns(txnRes.items);
        setStatements(stmtRes.items);

        let income = 0;
        let expense = 0;
        txnRes.items.forEach((t) => {
          if (t.transaction_nature === 'income') income += t.amount;
          if (t.transaction_nature === 'expense') expense += t.amount;
        });
        setTotals({ income, expense });

        const [summaryRes, trendsRes, billsRes] = await Promise.allSettled([
          api.getMonthlySummary(),
          api.getTrends(3),
          api.getBills('upcoming'),
        ]);

        if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value);
        if (trendsRes.status === 'fulfilled') setTrends(trendsRes.value);
        if (billsRes.status === 'fulfilled') setUpcomingBills(billsRes.value.slice(0, 3));
      } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleExport = async () => {
    setExporting(true);
    try {
      await api.exportCsv();
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading dashboard...</div>
      </div>
    );
  }

  const hasData = recentTxns.length > 0;

  const categoryPieData = summary
    ? Object.entries(summary.category_breakdown ?? {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([name, value]) => ({ name, value }))
    : [];

  const trendBarData = trends.map((t) => ({
    month: t.month.slice(5),
    Income: Math.round(t.income),
    Expense: Math.round(t.expense),
  }));

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Overview</p>
          <h1 className="hc-page-title">Dashboard</h1>
          <p className="hc-page-subtitle">Your latest balances, expense mix, and payment due risk.</p>
        </div>
        <div className="hc-inline-actions">
          <button onClick={handleExport} disabled={exporting} className="hc-btn hc-btn-outline">
            <Download size={16} strokeWidth={1.5} />
            {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
          <button onClick={() => navigate('/upload')} className="hc-btn hc-btn-solid">
            <Upload size={16} strokeWidth={1.5} />
            Upload Statement
          </button>
        </div>
      </header>

      {!hasData ? (
        <div className="hc-empty">
          <CreditCard size={42} strokeWidth={1.5} color="var(--hc-muted-fg)" />
          <h2 style={{ marginTop: '0.75rem', fontSize: '1.35rem' }}>Start With Your First Statement</h2>
          <p className="hc-page-subtitle" style={{ margin: '0.6rem auto 0', maxWidth: '56ch' }}>
            Upload a credit card statement to unlock transaction parsing, category analytics, bill tracking,
            and transfer reconciliation.
          </p>
          <button
            onClick={() => navigate('/upload')}
            className="hc-btn hc-btn-primary"
            style={{ marginTop: '1rem' }}
          >
            Upload First Statement
            <ArrowRight size={16} strokeWidth={1.5} />
          </button>
        </div>
      ) : (
        <>
          <section className="hc-grid-3 hc-stagger">
            <div className="hc-panel">
              <p className="hc-stat-label">
                <ArrowDownRight size={15} strokeWidth={1.5} />
                Expenses
              </p>
              <p className="hc-stat-value">{formatAmount(totals.expense)}</p>
            </div>
            <div className="hc-panel">
              <p className="hc-stat-label">
                <ArrowUpRight size={15} strokeWidth={1.5} />
                Credits & Payments
              </p>
              <p className="hc-stat-value">{formatAmount(totals.income)}</p>
            </div>
            <div className="hc-panel">
              <p className="hc-stat-label">
                <CreditCard size={15} strokeWidth={1.5} />
                Statements
              </p>
              <p className="hc-stat-value">{statements.length}</p>
            </div>
          </section>

          <section className="hc-panel">
            <AnomaliesPanel fetchAnomalies={() => api.getAnomalies({ limit: 10 })} />
          </section>

          {(categoryPieData.length > 0 || trendBarData.length > 0) && (
            <section className="hc-grid-2">
              {categoryPieData.length > 0 && (
                <div className="hc-panel">
                  <div className="hc-panel-head">
                    <h2 className="hc-panel-title">Top Categories</h2>
                    <button onClick={() => navigate('/insights')} className="hc-btn hc-btn-primary">
                      View all
                    </button>
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={categoryPieData} cx="50%" cy="50%" outerRadius={74} dataKey="value" nameKey="name">
                        {categoryPieData.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => formatAmount(Number(value))} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-wrap gap-2" style={{ marginTop: '0.4rem' }}>
                    {categoryPieData.map((item, idx) => (
                      <span key={item.name} className="hc-badge">
                        <span
                          style={{
                            width: 8,
                            height: 8,
                            display: 'inline-block',
                            background: PIE_COLORS[idx % PIE_COLORS.length],
                          }}
                        />
                        {item.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {trendBarData.length > 0 && (
                <div className="hc-panel">
                  <div className="hc-panel-head">
                    <h2 className="hc-panel-title">Monthly Trend</h2>
                    <button onClick={() => navigate('/insights')} className="hc-btn hc-btn-primary">
                      View all
                    </button>
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={trendBarData}>
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                      <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => formatAmount(Number(value))} />
                      <Bar dataKey="Income" fill="#22c55e" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="Expense" fill="var(--hc-accent)" radius={[0, 0, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </section>
          )}

          {upcomingBills.length > 0 && (
            <section className="hc-panel">
              <div className="hc-panel-head">
                <h2 className="hc-panel-title">Upcoming Bills</h2>
                <button onClick={() => navigate('/bills')} className="hc-btn hc-btn-primary">
                  View all
                </button>
              </div>
              <div className="space-y-0">
                {upcomingBills.map((bill, idx) => (
                  <div key={bill.id} style={{ padding: '0.75rem 0', borderTop: idx ? '1px solid var(--hc-border)' : 'none' }}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p style={{ fontWeight: 600 }}>{bill.bank_name}</p>
                        <p className="hc-panel-sub">
                          Due{' '}
                          {new Date(bill.due_date).toLocaleDateString('en-IN', {
                            day: '2-digit',
                            month: 'short',
                          })}
                        </p>
                      </div>
                      <div className="text-right">
                        <p style={{ fontWeight: 600 }}>{formatAmount(bill.total_due)}</p>
                        <span
                          className={`hc-badge ${
                            bill.days_until_due < 0
                              ? 'hc-badge-danger'
                              : bill.days_until_due <= 7
                              ? 'hc-badge-warn'
                              : 'hc-badge-accent'
                          }`}
                        >
                          {bill.days_until_due < 0
                            ? `${Math.abs(bill.days_until_due)}d overdue`
                            : `${bill.days_until_due}d left`}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {statements.length > 0 && (
            <section className="hc-panel">
              <div className="hc-panel-head">
                <h2 className="hc-panel-title">Recent Statements</h2>
                <div className="hc-inline-actions">
                  <button onClick={() => navigate('/accounts')} className="hc-btn hc-btn-outline">
                    Accounts
                  </button>
                  <button onClick={() => navigate('/statements')} className="hc-btn hc-btn-primary">
                    View all
                  </button>
                </div>
              </div>
              <div className="space-y-0">
                {statements.slice(0, 5).map((statement, idx) => (
                  <div
                    key={statement.id}
                    style={{
                      padding: '0.75rem 0',
                      borderTop: idx ? '1px solid var(--hc-border)' : 'none',
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: '0.8rem',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <p style={{ fontWeight: 600 }}>
                        {statement.bank_name} · {statement.account_type}
                      </p>
                      <p className="hc-panel-sub">
                        {statement.statement_period_start
                          ? new Date(statement.statement_period_start).toLocaleDateString('en-IN', {
                              day: '2-digit',
                              month: 'short',
                              year: 'numeric',
                            })
                          : 'Unknown start'}
                        {' → '}
                        {statement.statement_period_end
                          ? new Date(statement.statement_period_end).toLocaleDateString('en-IN', {
                              day: '2-digit',
                              month: 'short',
                              year: 'numeric',
                            })
                          : 'Unknown end'}
                        {statement.account_number_masked ? ` · ${statement.account_number_masked}` : ''}
                      </p>
                    </div>
                    <div className="hc-inline-actions">
                      <span className="hc-badge">{statement.parse_status}</span>
                      <button
                        onClick={() =>
                          navigate(
                            statement.parse_status === 'parsed' || statement.parse_status === 'review_required'
                              ? `/statements/${statement.id}/review`
                              : '/statements'
                          )
                        }
                        className="hc-btn hc-btn-outline"
                      >
                        {statement.parse_status === 'parsed' || statement.parse_status === 'review_required'
                          ? 'Review'
                          : 'Open'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="hc-panel">
            <div className="hc-panel-head">
              <h2 className="hc-panel-title">Recent Transactions</h2>
              <div className="hc-inline-actions">
                <button onClick={() => navigate('/transactions')} className="hc-btn hc-btn-primary">
                  View all
                </button>
              </div>
            </div>
            <div className="space-y-0">
              {recentTxns.map((txn, idx) => (
                <div
                  key={txn.id}
                  style={{
                    padding: '0.75rem 0',
                    borderTop: idx ? '1px solid var(--hc-border)' : 'none',
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: '0.8rem',
                  }}
                >
                  <div>
                    <button
                      type="button"
                      onClick={() => navigate(`/transactions/${txn.id}`)}
                      style={{
                        fontWeight: 600,
                        background: 'transparent',
                        border: 'none',
                        padding: 0,
                        color: 'inherit',
                        cursor: 'pointer',
                      }}
                    >
                      {txn.merchant_normalized || txn.merchant_raw}
                    </button>
                    <p className="hc-panel-sub">
                      {new Date(txn.transaction_date).toLocaleDateString('en-IN', {
                        day: '2-digit',
                        month: 'short',
                      })}
                      {txn.category_name ? ` · ${txn.category_name}` : ''}
                    </p>
                  </div>
                  <p style={{ fontWeight: 600, color: txn.direction === 'credit' ? '#22c55e' : 'var(--hc-fg)' }}>
                    {txn.direction === 'credit' ? '+' : ''}
                    {formatAmount(txn.amount)}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
