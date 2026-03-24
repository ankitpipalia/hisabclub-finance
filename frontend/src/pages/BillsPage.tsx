import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Bill } from '../api/client';
import { Receipt, CheckCircle, Clock, AlertTriangle } from 'lucide-react';

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

type FilterTab = 'all' | 'upcoming' | 'paid';

function dueBadge(daysUntilDue: number, isPaid: boolean) {
  if (isPaid) return <span className="hc-badge hc-badge-ok"><CheckCircle size={12} strokeWidth={1.5} />Paid</span>;
  if (daysUntilDue < 0) return <span className="hc-badge hc-badge-danger"><AlertTriangle size={12} strokeWidth={1.5} />Overdue {Math.abs(daysUntilDue)}d</span>;
  if (daysUntilDue <= 7) return <span className="hc-badge hc-badge-warn"><Clock size={12} strokeWidth={1.5} />Due in {daysUntilDue}d</span>;
  return <span className="hc-badge hc-badge-accent"><Clock size={12} strokeWidth={1.5} />Due in {daysUntilDue}d</span>;
}

export default function BillsPage() {
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<FilterTab>('upcoming');
  const [payingBillId, setPayingBillId] = useState<string | null>(null);
  const [payAmount, setPayAmount] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchBills = async () => {
    try {
      const res = await api.getBills();
      setBills(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load bills');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBills();
  }, []);

  const filteredBills = bills.filter((bill) => {
    if (activeTab === 'upcoming') return !bill.is_paid;
    if (activeTab === 'paid') return bill.is_paid;
    return true;
  });

  const handleMarkPaid = async (bill: Bill) => {
    if (!payAmount) return;
    setSubmitting(true);
    try {
      const updated = await api.markBillPaid(bill.id, {
        paid_amount: parseFloat(payAmount),
        paid_date: new Date().toISOString().slice(0, 10),
      });
      setBills((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
      setPayingBillId(null);
      setPayAmount('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to mark bill as paid');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading bills...</div>
      </div>
    );
  }

  const tabs: { key: FilterTab; label: string }[] = [
    { key: 'upcoming', label: 'Upcoming' },
    { key: 'paid', label: 'Paid' },
    { key: 'all', label: 'All' },
  ];

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Repayments</p>
          <h1 className="hc-page-title">Bills</h1>
          <p className="hc-page-subtitle">Track due dates and mark repayments as they happen.</p>
        </div>
      </header>

      {error && (
        <div className="hc-msg hc-msg-danger">
          <span>{error}</span>
          <button type="button" className="hc-btn hc-btn-primary" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="hc-inline-actions">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`hc-btn ${activeTab === tab.key ? 'hc-btn-solid' : 'hc-btn-ghost'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {filteredBills.length === 0 ? (
        <div className="hc-empty">
          <Receipt size={44} strokeWidth={1.5} color="var(--hc-muted-fg)" />
          <h2 style={{ marginTop: '0.7rem', fontSize: '1.35rem' }}>No bills found</h2>
          <p className="hc-page-subtitle" style={{ marginTop: '0.4rem' }}>
            {activeTab === 'upcoming'
              ? 'No upcoming dues right now.'
              : activeTab === 'paid'
              ? 'No paid bills yet.'
              : 'Upload statements to detect bill cycles.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4 hc-stagger">
          {filteredBills.map((bill) => (
            <section key={bill.id} className="hc-panel">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <div className="hc-inline-actions" style={{ gap: '0.45rem' }}>
                    <h2 className="hc-panel-title">{bill.bank_name}</h2>
                    {dueBadge(bill.days_until_due, bill.is_paid)}
                  </div>
                  {bill.account_masked && <p className="hc-panel-sub">Account: {bill.account_masked}</p>}
                  <p className="hc-panel-sub">
                    Period:{' '}
                    {new Date(bill.billing_period_start).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                    {' - '}
                    {new Date(bill.billing_period_end).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </p>
                  <p className="hc-panel-sub">
                    Due: {new Date(bill.due_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </p>
                </div>

                <div className="text-right">
                  <p style={{ fontWeight: 700, fontSize: '1.2rem' }}>{formatAmount(bill.total_due)}</p>
                  {bill.min_due !== null && <p className="hc-panel-sub">Min due: {formatAmount(bill.min_due)}</p>}
                  {bill.is_paid && bill.paid_amount !== null && (
                    <p className="hc-panel-sub" style={{ color: '#22c55e' }}>
                      Paid {formatAmount(bill.paid_amount)}
                      {bill.paid_date
                        ? ` on ${new Date(bill.paid_date).toLocaleDateString('en-IN', {
                            day: '2-digit',
                            month: 'short',
                          })}`
                        : ''}
                    </p>
                  )}
                </div>
              </div>

              {!bill.is_paid && (
                <div style={{ marginTop: '0.8rem', borderTop: '1px solid var(--hc-border)', paddingTop: '0.8rem' }}>
                  {payingBillId === bill.id ? (
                    <div className="hc-inline-actions">
                      <input
                        type="number"
                        value={payAmount}
                        onChange={(e) => setPayAmount(e.target.value)}
                        placeholder="Amount paid"
                        className="hc-input"
                        style={{ maxWidth: 220 }}
                      />
                      <button
                        onClick={() => handleMarkPaid(bill)}
                        disabled={submitting || !payAmount}
                        className="hc-btn hc-btn-solid"
                      >
                        {submitting ? 'Saving...' : 'Confirm'}
                      </button>
                      <button
                        onClick={() => {
                          setPayingBillId(null);
                          setPayAmount('');
                        }}
                        className="hc-btn hc-btn-outline"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setPayingBillId(bill.id);
                        setPayAmount(bill.total_due.toString());
                      }}
                      className="hc-btn hc-btn-primary"
                    >
                      <CheckCircle size={14} strokeWidth={1.5} />
                      Mark as Paid
                    </button>
                  )}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
