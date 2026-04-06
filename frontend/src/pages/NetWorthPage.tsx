import { useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Gem, Landmark, ShieldAlert, Trash2 } from 'lucide-react';

import { api } from '../api/client';
import type { FormEvent } from 'react';
import type { BalanceSnapshot, NetWorthHistoryPoint, NetWorthOverview } from '../api/client';

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

const todayIso = () => new Date().toISOString().slice(0, 10);

type ManualFormState = {
  label: string;
  entry_kind: 'asset' | 'liability';
  asset_type: string;
  balance: string;
  as_of_date: string;
  institution_name: string;
  account_masked: string;
};

const initialFormState: ManualFormState = {
  label: '',
  entry_kind: 'asset',
  asset_type: 'cash',
  balance: '',
  as_of_date: todayIso(),
  institution_name: '',
  account_masked: '',
};

export default function NetWorthPage() {
  const [overview, setOverview] = useState<NetWorthOverview | null>(null);
  const [months, setMonths] = useState(12);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<ManualFormState>(initialFormState);

  const loadOverview = async (selectedMonths: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getNetWorthOverview(selectedMonths);
      setOverview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load net worth data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview(months);
  }, [months]);

  const historyChartData = useMemo(
    () =>
      (overview?.history ?? []).map((point: NetWorthHistoryPoint) => ({
        ...point,
        label: new Date(point.as_of_date).toLocaleDateString('en-IN', {
          day: '2-digit',
          month: 'short',
        }),
      })),
    [overview],
  );

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.label.trim() || !form.balance.trim()) {
      setError('Label and balance are required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createManualNetWorthSnapshot({
        label: form.label.trim(),
        entry_kind: form.entry_kind,
        asset_type: form.asset_type.trim() || 'other_asset',
        balance: Number(form.balance),
        as_of_date: form.as_of_date,
        institution_name: form.institution_name.trim() || undefined,
        account_masked: form.account_masked.trim() || undefined,
      });
      setForm(initialFormState);
      await loadOverview(months);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save manual position.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (snapshot: BalanceSnapshot) => {
    try {
      await api.deleteManualNetWorthSnapshot(snapshot.id);
      await loadOverview(months);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete manual position.');
    }
  };

  if (loading && !overview) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading net worth view...</div>
      </div>
    );
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Balance Sheet</p>
          <h1 className="hc-page-title">Net Worth</h1>
          <p className="hc-page-subtitle">
            Statement balances and manual assets/liabilities rolled into one running view.
          </p>
        </div>
        <label className="hc-field" style={{ minWidth: 170 }}>
          <span className="hc-label">History Window</span>
          <select
            className="hc-input"
            value={months}
            onChange={(event) => setMonths(Number(event.target.value))}
          >
            {[6, 12, 24, 36].map((value) => (
              <option key={value} value={value}>
                Last {value} months
              </option>
            ))}
          </select>
        </label>
      </header>

      {error && <div className="hc-msg hc-msg-danger">{error}</div>}

      <section className="hc-grid-4 hc-stagger">
        <div className="hc-panel">
          <p className="hc-stat-label">
            <Gem size={15} strokeWidth={1.5} />
            Net Worth
          </p>
          <p
            className="hc-stat-value"
            style={{ color: (overview?.totals.net_worth ?? 0) >= 0 ? '#22c55e' : 'var(--hc-accent)' }}
          >
            {formatAmount(overview?.totals.net_worth ?? 0)}
          </p>
          <p className="hc-panel-sub">
            Latest snapshot {overview?.totals.latest_snapshot_date ?? 'not available'}
          </p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">Assets</p>
          <p className="hc-stat-value">{formatAmount(overview?.totals.assets ?? 0)}</p>
          <p className="hc-panel-sub">{overview?.totals.positions_count ?? 0} active positions</p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">
            <ShieldAlert size={15} strokeWidth={1.5} />
            Liabilities
          </p>
          <p className="hc-stat-value">{formatAmount(overview?.totals.liabilities ?? 0)}</p>
          <p className="hc-panel-sub">Cards and manual liabilities</p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">
            <Landmark size={15} strokeWidth={1.5} />
            Manual Positions
          </p>
          <p className="hc-stat-value">{overview?.totals.manual_positions_count ?? 0}</p>
          <p className="hc-panel-sub">Tracked alongside statement balances</p>
        </div>
      </section>

      <section className="hc-grid-2">
        <div className="hc-panel">
          <h2 className="hc-panel-title">History</h2>
          {!historyChartData.length ? (
            <p className="hc-panel-sub" style={{ marginTop: '0.8rem' }}>
              No balance snapshots yet. Upload statements or add a manual position.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={historyChartData}>
                <CartesianGrid stroke="var(--hc-border)" strokeDasharray="4 4" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value) => formatAmount(Number(value))} />
                <Line type="monotone" dataKey="assets" stroke="#22c55e" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="liabilities" stroke="#ef4444" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="net_worth" stroke="var(--hc-accent)" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="hc-panel">
          <h2 className="hc-panel-title">Add Manual Position</h2>
          <p className="hc-panel-sub">
            Use this for cash, gold, loans, private assets, or anything not represented by a parsed statement.
          </p>
          <form onSubmit={handleSubmit} style={{ marginTop: '1rem', display: 'grid', gap: '0.85rem' }}>
            <label className="hc-field">
              <span className="hc-label">Label</span>
              <input
                className="hc-input"
                value={form.label}
                onChange={(event) => setForm((prev) => ({ ...prev, label: event.target.value }))}
                placeholder="Emergency Fund"
              />
            </label>
            <div className="hc-grid-2" style={{ gap: '0.85rem' }}>
              <label className="hc-field">
                <span className="hc-label">Entry Kind</span>
                <select
                  className="hc-input"
                  value={form.entry_kind}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, entry_kind: event.target.value as 'asset' | 'liability' }))
                  }
                >
                  <option value="asset">Asset</option>
                  <option value="liability">Liability</option>
                </select>
              </label>
              <label className="hc-field">
                <span className="hc-label">Asset Type</span>
                <input
                  className="hc-input"
                  value={form.asset_type}
                  onChange={(event) => setForm((prev) => ({ ...prev, asset_type: event.target.value }))}
                  placeholder="cash, gold, loan"
                />
              </label>
            </div>
            <div className="hc-grid-2" style={{ gap: '0.85rem' }}>
              <label className="hc-field">
                <span className="hc-label">Balance</span>
                <input
                  className="hc-input"
                  inputMode="decimal"
                  value={form.balance}
                  onChange={(event) => setForm((prev) => ({ ...prev, balance: event.target.value }))}
                  placeholder="250000"
                />
              </label>
              <label className="hc-field">
                <span className="hc-label">As Of</span>
                <input
                  className="hc-input"
                  type="date"
                  value={form.as_of_date}
                  onChange={(event) => setForm((prev) => ({ ...prev, as_of_date: event.target.value }))}
                />
              </label>
            </div>
            <div className="hc-grid-2" style={{ gap: '0.85rem' }}>
              <label className="hc-field">
                <span className="hc-label">Institution Name</span>
                <input
                  className="hc-input"
                  value={form.institution_name}
                  onChange={(event) => setForm((prev) => ({ ...prev, institution_name: event.target.value }))}
                  placeholder="HDFC Bank"
                />
              </label>
              <label className="hc-field">
                <span className="hc-label">Account Masked</span>
                <input
                  className="hc-input"
                  value={form.account_masked}
                  onChange={(event) => setForm((prev) => ({ ...prev, account_masked: event.target.value }))}
                  placeholder="XX1234"
                />
              </label>
            </div>
            <button type="submit" className="hc-btn hc-btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Add Position'}
            </button>
          </form>
        </div>
      </section>

      <section className="hc-grid-2">
        <div className="hc-panel">
          <h2 className="hc-panel-title">Current Positions</h2>
          {!overview?.positions.length ? (
            <p className="hc-panel-sub">No active positions found.</p>
          ) : (
            <div>
              {overview.positions.map((position, index) => (
                <div
                  key={position.id}
                  style={{
                    padding: '0.9rem 0',
                    borderTop: index ? '1px solid var(--hc-border)' : 'none',
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: '0.9rem',
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <p style={{ fontWeight: 600 }}>{position.label}</p>
                    <p className="hc-panel-sub">
                      {position.entry_kind} · {position.asset_type}
                      {position.institution_name ? ` · ${position.institution_name}` : ''}
                      {position.account_masked ? ` · ${position.account_masked}` : ''}
                      {` · ${new Date(position.as_of_date).toLocaleDateString('en-IN')}`}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ fontWeight: 700 }}>{formatAmount(position.balance)}</p>
                    <span className={`hc-badge ${position.entry_kind === 'asset' ? 'hc-badge-ok' : 'hc-badge-warn'}`}>
                      {position.source_kind}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="hc-panel">
          <h2 className="hc-panel-title">Manual Snapshot Log</h2>
          {!overview?.manual_snapshots.length ? (
            <p className="hc-panel-sub">No manual positions added yet.</p>
          ) : (
            <div>
              {overview.manual_snapshots.map((snapshot, index) => (
                <div
                  key={snapshot.id}
                  style={{
                    padding: '0.85rem 0',
                    borderTop: index ? '1px solid var(--hc-border)' : 'none',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '0.9rem',
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <p style={{ fontWeight: 600 }}>{snapshot.label}</p>
                    <p className="hc-panel-sub">
                      {snapshot.entry_kind} · {snapshot.asset_type} ·{' '}
                      {new Date(snapshot.as_of_date).toLocaleDateString('en-IN')}
                    </p>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <p style={{ fontWeight: 700 }}>{formatAmount(snapshot.balance)}</p>
                    <button
                      type="button"
                      className="hc-btn hc-btn-ghost"
                      onClick={() => void handleDelete(snapshot)}
                      title="Delete manual snapshot"
                    >
                      <Trash2 size={16} strokeWidth={1.5} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
