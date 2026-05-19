import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type {
  ReconciliationResponse,
  TaxActionItem,
  TaxComplianceResponse,
  TaxPortalData,
  TaxVerificationCheck,
  TaxVerificationResult,
} from '../api/client';
import { ShieldAlert, Link2, RefreshCw } from 'lucide-react';
import RegimeComparator from '../components/tax/RegimeComparator';

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

type FinancialYearOption = {
  key: string;
  label: string;
  from: string;
  to: string;
};

function buildFinancialYearOptions(previousCount: number): FinancialYearOption[] {
  const today = new Date();
  const runningStartYear =
    today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
  const options: FinancialYearOption[] = [];
  for (let offset = 0; offset <= previousCount; offset += 1) {
    const startYear = runningStartYear - offset;
    const endYear = startYear + 1;
    const shortEnd = String(endYear).slice(-2);
    options.push({
      key: `${startYear}-${shortEnd}`,
      label: offset === 0 ? `Running FY ${startYear}-${shortEnd}` : `FY ${startYear}-${shortEnd}`,
      from: `${startYear}-04-01`,
      to: `${endYear}-03-31`,
    });
  }
  return options;
}

export default function TaxPage() {
  const fyOptions = useMemo(() => buildFinancialYearOptions(5), []);
  const [selectedFy, setSelectedFy] = useState(fyOptions[0]?.key ?? '');
  const [taxReport, setTaxReport] = useState<TaxComplianceResponse | null>(null);
  const [reconciliations, setReconciliations] = useState<ReconciliationResponse | null>(null);
  const [verification, setVerification] = useState<TaxVerificationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadDocType, setUploadDocType] = useState('form_16');

  const load = async (fyKey?: string) => {
    const selectedRange =
      fyOptions.find((option) => option.key === (fyKey ?? selectedFy)) ?? fyOptions[0];
    if (!selectedRange) return;

    setLoading(true);
    setError('');
    try {
      const [tax, rec, verificationResult] = await Promise.all([
        api.getTaxCompliance({ from: selectedRange.from, to: selectedRange.to }),
        api.getTransferReconciliations({
          from: selectedRange.from,
          to: selectedRange.to,
          max_gap_days: 5,
          limit: 500,
        }),
        api.getTaxVerification(selectedRange.key).catch(() => null),
      ]);
      setTaxReport(tax);
      setReconciliations(rec);
      setVerification(verificationResult);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load tax/audit insights';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handlePortalUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      await api.uploadTaxPortalDocument(file, uploadDocType, selectedFy);
      const verificationResult = await api.getTaxVerification(selectedFy);
      setVerification(verificationResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not upload tax portal document.');
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  useEffect(() => {
    void load(selectedFy);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFy]);

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
        <button onClick={() => void load(selectedFy)} className="hc-btn hc-btn-outline">
          <RefreshCw size={14} strokeWidth={1.5} />
          Refresh
        </button>
      </header>

      <section className="hc-panel">
        <div className="hc-grid-2">
          <div>
            <label className="hc-label">Financial Year</label>
            <select
              value={selectedFy}
              onChange={(e) => setSelectedFy(e.target.value)}
              className="hc-select"
            >
              {fyOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="hc-label">Apply</label>
            <button onClick={() => void load(selectedFy)} className="hc-btn hc-btn-solid" style={{ width: '100%' }}>
              Refresh FY
            </button>
          </div>
        </div>
      </section>

      <RegimeComparator fy={selectedFy} />

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
            <div className="hc-panel">
              <p className="hc-stat-label">Savings Accounts Mapped</p>
              <p className="hc-stat-value">{taxReport.totals.savings_account_count}</p>
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
              <div style={{ marginTop: '0.8rem' }}>
                <p className="hc-panel-sub">Documented Amounts</p>
                <p className="hc-panel-sub" style={{ marginTop: '0.35rem' }}>
                  Interest: {formatAmount(taxReport.totals.documented_interest_income)} ·
                  Tax paid: {formatAmount(taxReport.totals.documented_tax_payments)}
                </p>
                <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>
                  FD principal: {formatAmount(taxReport.totals.documented_fd_principal)} ·
                  PPF contribution: {formatAmount(taxReport.totals.documented_ppf_contribution)}
                </p>
              </div>
            </div>
          </section>

          <section className="hc-grid-2">
            <div className="hc-panel">
              <div className="hc-panel-head">
                <div>
                  <h2 className="hc-panel-title">Portal Verification</h2>
                  <p className="hc-panel-sub">Compare ledger tax signals with uploaded Form 16 / 26AS / AIS / TIS documents.</p>
                </div>
                <div className="flex gap-2">
                  <select className="hc-select" value={uploadDocType} onChange={(e) => setUploadDocType(e.target.value)}>
                    <option value="form_16">Form 16</option>
                    <option value="form_26as">Form 26AS</option>
                    <option value="ais">AIS</option>
                    <option value="tis">TIS</option>
                  </select>
                  <label className="hc-btn hc-btn-solid" style={{ cursor: 'pointer' }}>
                    {uploading ? 'Uploading...' : 'Upload'}
                    <input type="file" hidden onChange={handlePortalUpload} />
                  </label>
                </div>
              </div>
              {verification ? (
                <div className="space-y-2" style={{ marginTop: '0.8rem' }}>
                  {verification.checks.map((check: TaxVerificationCheck) => (
                    <div key={check.check} className="hc-panel" style={{ background: 'transparent' }}>
                      <div className={`hc-badge ${check.status === 'match' ? 'hc-badge-ok' : check.status === 'mismatch' ? 'hc-badge-warn' : ''}`}>
                        {check.status}
                      </div>
                      <p style={{ fontWeight: 600, marginTop: '0.35rem' }}>{check.check}</p>
                      <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>
                        App {formatAmount(check.app_amount)} · Portal {formatAmount(check.portal_amount)} · Gap {formatAmount(Math.abs(check.gap))}
                      </p>
                      <p className="hc-panel-sub">{check.detail}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="hc-panel-sub" style={{ marginTop: '0.8rem' }}>
                  Upload portal documents to activate cross-verification.
                </p>
              )}
            </div>

            <div className="hc-panel">
              <h2 className="hc-panel-title">Portal Documents</h2>
              {verification && verification.portal_data.length > 0 ? (
                <div className="space-y-2" style={{ marginTop: '0.8rem' }}>
                  {verification.portal_data.map((item: TaxPortalData) => (
                    <div key={item.id} className="hc-badge" style={{ justifyContent: 'space-between' }}>
                      <span>{item.document_type.toUpperCase()} · {item.source_name ?? 'uploaded'}</span>
                      <span>{item.financial_year ?? 'FY unknown'}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="hc-panel-sub" style={{ marginTop: '0.8rem' }}>
                  No portal documents registered for this FY.
                </p>
              )}
            </div>
          </section>

          <section className="hc-grid-2">
            <div className="hc-panel">
              <h2 className="hc-panel-title">Savings Account Map</h2>
              {taxReport.savings_accounts.length === 0 ? (
                <p className="hc-panel-sub" style={{ marginTop: '0.7rem' }}>
                  No savings/current accounts detected yet.
                </p>
              ) : (
                <div className="space-y-2" style={{ marginTop: '0.8rem' }}>
                  {taxReport.savings_accounts.map((item) => (
                    <div key={`${item.bank_name}-${item.account_masked ?? 'na'}`} className="hc-badge" style={{ justifyContent: 'space-between' }}>
                      <span>
                        {item.bank_name}
                        {item.account_masked ? ` · ${item.account_masked}` : ''}
                      </span>
                      <span>
                        {item.statement_count} stmt · {formatAmount(item.interest_income)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="hc-panel">
              <h2 className="hc-panel-title">Ledger ↔ Document Linkage</h2>
              <div className="space-y-2" style={{ marginTop: '0.8rem' }}>
                {taxReport.linkage_checks.map((check) => (
                  <div key={check.check} className="hc-panel" style={{ background: 'transparent' }}>
                    <div
                      className={`hc-badge ${
                        check.status === 'matched'
                          ? 'hc-badge-ok'
                          : check.status === 'review_required'
                            ? 'hc-badge-warn'
                            : 'hc-badge-accent'
                      }`}
                    >
                      {check.status}
                    </div>
                    <p style={{ fontWeight: 600, marginTop: '0.35rem' }}>{check.check}</p>
                    <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>
                      Ledger {formatAmount(check.ledger_amount)} · Document {formatAmount(check.document_amount)} ·
                      Gap {formatAmount(Math.abs(check.gap))}
                    </p>
                    <p className="hc-panel-sub" style={{ marginTop: '0.2rem' }}>{check.detail}</p>
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
