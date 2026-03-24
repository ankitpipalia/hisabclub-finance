import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ReconciliationResponse, TaxComplianceResponse, TaxActionItem } from '../api/client';
import { ShieldAlert, Link2, RefreshCw } from 'lucide-react';

const formatAmount = (amount: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);

function severityClass(item: TaxActionItem) {
  if (item.severity === 'warning') return 'hc-badge hc-badge-warn';
  if (item.severity === 'ok') return 'hc-badge hc-badge-ok';
  return 'hc-badge hc-badge-accent';
}

export default function TaxPage() {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [taxReport, setTaxReport] = useState<TaxComplianceResponse | null>(null);
  const [reconciliations, setReconciliations] = useState<ReconciliationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [tax, rec] = await Promise.all([
        api.getTaxCompliance({ from: from || undefined, to: to || undefined }),
        api.getTransferReconciliations({
          from: from || undefined,
          to: to || undefined,
          max_gap_days: 5,
          limit: 500,
        }),
      ]);
      setTaxReport(tax);
      setReconciliations(rec);
      if (!from) setFrom(tax.period_start);
      if (!to) setTo(tax.period_end);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load tax/audit insights';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Compliance</p>
          <h1 className="hc-page-title">Tax & Audit</h1>
          <p className="hc-page-subtitle">
            New-regime tax estimate, document coverage, and transfer reconciliation.
          </p>
        </div>
        <button onClick={load} className="hc-btn hc-btn-outline">
          <RefreshCw size={14} strokeWidth={1.5} />
          Refresh
        </button>
      </header>

      <section className="hc-panel">
        <div className="hc-grid-3">
          <div>
            <label className="hc-label">From</label>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="hc-input" />
          </div>
          <div>
            <label className="hc-label">To</label>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="hc-input" />
          </div>
          <div>
            <label className="hc-label">Apply</label>
            <button onClick={load} className="hc-btn hc-btn-solid" style={{ width: '100%' }}>
              Apply Range
            </button>
          </div>
        </div>
      </section>

      {loading && <div className="hc-panel">Loading tax and reconciliation insights...</div>}

      {error && <div className="hc-msg hc-msg-danger">{error}</div>}

      {!loading && !error && taxReport && reconciliations && (
        <>
          <section className="hc-grid-4 hc-stagger">
            <div className="hc-panel">
              <p className="hc-stat-label">Estimated Taxable Income</p>
              <p className="hc-stat-value">{formatAmount(taxReport.totals.estimated_taxable_income)}</p>
            </div>
            <div className="hc-panel">
              <p className="hc-stat-label">Tax Paid</p>
              <p className="hc-stat-value">{formatAmount(taxReport.totals.tax_payments)}</p>
            </div>
            <div className="hc-panel">
              <p className="hc-stat-label">Estimated New-Regime Tax</p>
              <p className="hc-stat-value">{formatAmount(taxReport.totals.new_regime_total_tax)}</p>
            </div>
            <div className="hc-panel">
              <p className="hc-stat-label">Net Due / Refund</p>
              <p className="hc-stat-value" style={{ color: taxReport.totals.tax_due_or_refund > 0 ? 'var(--hc-accent)' : '#22c55e' }}>
                {formatAmount(Math.abs(taxReport.totals.tax_due_or_refund))}
                <span style={{ marginLeft: 8, fontSize: '0.85rem', color: 'var(--hc-muted-fg)' }}>
                  {taxReport.totals.tax_due_or_refund > 0 ? 'Due' : 'Excess Paid'}
                </span>
              </p>
            </div>
          </section>

          <section className="hc-grid-3" style={{ marginTop: '0.8rem' }}>
            <div className="hc-panel">
              <p className="hc-stat-label">Financial Year</p>
              <p className="hc-stat-value">{taxReport.tax_financial_year}</p>
            </div>
            <div className="hc-panel">
              <p className="hc-stat-label">Regime</p>
              <p className="hc-stat-value" style={{ textTransform: 'uppercase' }}>{taxReport.tax_regime}</p>
            </div>
            <div className="hc-panel">
              <p className="hc-stat-label">Unresolved Statements</p>
              <p className="hc-stat-value">{taxReport.unresolved_statement_docs}</p>
            </div>
          </section>

          <section className="hc-grid-2">
            <div className="hc-panel">
              <div className="hc-panel-head">
                <h2 className="hc-panel-title" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <ShieldAlert size={16} strokeWidth={1.5} color="var(--hc-accent)" />
                  Tax Action Items
                </h2>
              </div>
              <div className="space-y-2">
                {taxReport.action_items.map((item) => (
                  <div key={`${item.title}-${item.detail}`} className="hc-panel" style={{ background: 'transparent' }}>
                    <div className={severityClass(item)}>{item.severity}</div>
                    <p style={{ fontWeight: 600, marginTop: '0.4rem' }}>{item.title}</p>
                    <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="hc-panel">
              <h2 className="hc-panel-title">Document Coverage</h2>
              <div className="hc-grid-2" style={{ marginTop: '0.8rem' }}>
                {Object.entries(taxReport.document_coverage).map(([k, v]) => (
                  <div key={k} className="hc-badge" style={{ justifyContent: 'space-between' }}>
                    <span>{k}</span>
                    <strong>{v}</strong>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="hc-panel">
            <h2 className="hc-panel-title">New-Regime Calculation Notes</h2>
            <div style={{ marginTop: '0.8rem' }}>
              {taxReport.tax_notes.map((note) => (
                <p key={note} className="hc-panel-sub" style={{ marginTop: '0.3rem' }}>
                  {note}
                </p>
              ))}
              <p className="hc-panel-sub" style={{ marginTop: '0.6rem' }}>
                Tax before rebate: {formatAmount(taxReport.totals.new_regime_tax_before_rebate)} · Rebate: {formatAmount(taxReport.totals.new_regime_rebate)} · Cess: {formatAmount(taxReport.totals.new_regime_cess)}
              </p>
            </div>
          </section>

          <section className="hc-panel">
            <div className="hc-panel-head">
              <h2 className="hc-panel-title" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                <Link2 size={16} strokeWidth={1.5} color="var(--hc-accent)" />
                Transfer Reconciliation
              </h2>
            </div>

            <div className="hc-grid-4" style={{ marginBottom: '0.8rem' }}>
              <div className="hc-badge">Transfer txns: {reconciliations.total_transfer_transactions}</div>
              <div className="hc-badge">Matched pairs: {reconciliations.matched_pairs}</div>
              <div className="hc-badge">Match rate: {(reconciliations.match_rate * 100).toFixed(1)}%</div>
              <div className="hc-badge">Matched amount: {formatAmount(reconciliations.matched_amount)}</div>
            </div>

            <div className="hc-badge" style={{ marginBottom: '0.8rem' }}>
              Unmatched txns: {reconciliations.unmatched_transactions}
            </div>

            <div className="hc-table-wrap">
              <table className="hc-table" style={{ minWidth: 960 }}>
                <thead>
                  <tr>
                    <th>Amount</th>
                    <th>Debit Side</th>
                    <th>Credit Side</th>
                    <th>Gap</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {reconciliations.pairs.slice(0, 25).map((p, i) => (
                    <tr key={`${p.debit.id}-${p.credit.id}-${i}`}>
                      <td style={{ fontWeight: 600 }}>{formatAmount(p.amount)}</td>
                      <td>
                        <p>{p.debit.merchant_raw}</p>
                        <p className="hc-panel-sub">
                          {p.debit.transaction_date} · {p.debit.bank_name || '-'} · {p.debit.account_type || '-'}
                        </p>
                      </td>
                      <td>
                        <p>{p.credit.merchant_raw}</p>
                        <p className="hc-panel-sub">
                          {p.credit.transaction_date} · {p.credit.bank_name || '-'} · {p.credit.account_type || '-'}
                        </p>
                      </td>
                      <td>{p.day_gap}d</td>
                      <td>{(p.confidence * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                  {reconciliations.pairs.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ textAlign: 'center' }}>
                        No transfer matches for selected range.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
