import { useEffect, useState } from 'react';
import { RefreshCw, Repeat, TriangleAlert } from 'lucide-react';

import { api } from '../api/client';
import type { SubscriptionOverview } from '../api/client';

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

const statusTone = (status: string) => {
  if (status === 'overdue') return 'hc-badge-warn';
  if (status === 'upcoming') return 'hc-badge-info';
  if (status === 'scheduled') return 'hc-badge-ok';
  return 'hc-badge';
};

export default function SubscriptionsPage() {
  const [overview, setOverview] = useState<SubscriptionOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async (isRefresh: boolean = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const result = await api.getSubscriptions();
      setOverview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load subscriptions.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading subscriptions...</div>
      </div>
    );
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Recurring Spend</p>
          <h1 className="hc-page-title">Subscriptions</h1>
          <p className="hc-page-subtitle">
            Recurring merchant patterns computed from your canonical expense history.
          </p>
        </div>
        <button
          type="button"
          className="hc-btn hc-btn-ghost"
          onClick={() => void loadData(true)}
          disabled={refreshing}
        >
          <RefreshCw size={16} strokeWidth={1.5} />
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </header>

      {error && <div className="hc-msg hc-msg-danger">{error}</div>}

      <section className="hc-grid-4 hc-stagger">
        <div className="hc-panel">
          <p className="hc-stat-label">
            <Repeat size={15} strokeWidth={1.5} />
            Active Patterns
          </p>
          <p className="hc-stat-value">{overview?.summary.active_count ?? 0}</p>
          <p className="hc-panel-sub">Recurring expenses currently tracked</p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">Monthly Estimate</p>
          <p className="hc-stat-value">{formatAmount(overview?.summary.total_monthly_estimate ?? 0)}</p>
          <p className="hc-panel-sub">Monthly equivalent across all frequencies</p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">Annual Estimate</p>
          <p className="hc-stat-value">{formatAmount(overview?.summary.total_annual_estimate ?? 0)}</p>
          <p className="hc-panel-sub">Full-year recurring burden</p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">
            <TriangleAlert size={15} strokeWidth={1.5} />
            Overdue
          </p>
          <p className="hc-stat-value">{overview?.summary.overdue_count ?? 0}</p>
          <p className="hc-panel-sub">Expected charges that already slipped past due date</p>
        </div>
      </section>

      <section className="hc-panel">
        <div className="hc-panel-head">
          <div>
            <h2 className="hc-panel-title">Detected Recurring Charges</h2>
            <p className="hc-panel-sub">
              This list is derived from recurring expense patterns, not hard-coded vendors.
            </p>
          </div>
        </div>

        {!overview?.items.length ? (
          <p className="hc-panel-sub">No recurring charges detected yet.</p>
        ) : (
          <div>
            {overview.items.map((item, index) => (
              <div
                key={item.id}
                style={{
                  padding: '0.95rem 0',
                  borderTop: index ? '1px solid var(--hc-border)' : 'none',
                  display: 'grid',
                  gridTemplateColumns: 'minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr)',
                  gap: '0.85rem',
                  alignItems: 'center',
                }}
              >
                <div>
                  <p style={{ fontWeight: 700 }}>{item.merchant_name}</p>
                  <p className="hc-panel-sub">
                    {item.category_name ? `${item.category_name} · ` : ''}
                    {item.frequency} · last seen {new Date(item.last_seen_date).toLocaleDateString('en-IN')}
                  </p>
                </div>
                <div>
                  <p style={{ fontWeight: 600 }}>{formatAmount(item.typical_amount)}</p>
                  <p className="hc-panel-sub">
                    Monthly equivalent {formatAmount(item.monthly_cost_equivalent)}
                  </p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <p className="hc-panel-sub" style={{ marginBottom: '0.35rem' }}>
                    Next expected {new Date(item.next_expected).toLocaleDateString('en-IN')}
                  </p>
                  <span className={`hc-badge ${statusTone(item.status)}`}>{item.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
