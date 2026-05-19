/**
 * RegimeComparator — runs the new tax-engine `compareTaxRegime` endpoint and
 * presents old vs new regime side-by-side with a single recommendation.
 *
 * Inputs are deliberately minimal here (gross salary + a handful of common
 * deductions). The "what-if optimizer" widget extends this with a what-if
 * slider; "ITR form recommender" sits in its own widget.
 */

import { useState } from 'react';
import { api } from '../../api/client';
import type {
  TaxRegimeComparison,
  TaxRegimeInputs,
  TaxRegimeResult,
} from '../../api/client';
import { useToast } from '../ui/Toast';

type Props = {
  fy: string; // canonical FY24-25 form; backend normalizes 2024-25 too
};

const blankInputs: TaxRegimeInputs = {
  gross_salary: '',
  deduction_80c: '',
  deduction_80ccd_1b: '',
  deduction_80d_self: '',
  home_loan_interest_self: '',
  is_salaried: true,
};

function inr(value: string | number): string {
  const num = typeof value === 'string' ? Number(value) : value;
  if (!Number.isFinite(num)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(num);
}

function RegimeColumn({ data, highlight }: { data: TaxRegimeResult; highlight: boolean }) {
  return (
    <div
      className="hc-panel"
      style={{
        borderColor: highlight ? 'var(--hc-accent)' : undefined,
        boxShadow: highlight ? '0 0 0 1px var(--hc-accent) inset' : undefined,
      }}
      data-testid={`regime-${data.regime}`}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h3 className="hc-panel-title" style={{ textTransform: 'capitalize' }}>
          {data.regime} regime
        </h3>
        {highlight && <span className="hc-badge hc-badge-accent">Recommended</span>}
      </div>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 18px', marginTop: 12 }}>
        <dt className="hc-panel-sub">Gross total income</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.gross_total_income)}</dd>
        <dt className="hc-panel-sub">Standard deduction</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.standard_deduction)}</dd>
        <dt className="hc-panel-sub">Chapter VI-A</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.chapter_via_deduction)}</dd>
        <dt className="hc-panel-sub">Section 24(b)</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.section_24b_deduction)}</dd>
        <dt className="hc-panel-sub">Taxable income</dt>
        <dd style={{ textAlign: 'right', fontWeight: 600 }}>{inr(data.taxable_income)}</dd>
        <dt className="hc-panel-sub">Slab tax</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.tax_on_slabs)}</dd>
        <dt className="hc-panel-sub">Special-rate tax</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.tax_on_special_rate_income)}</dd>
        <dt className="hc-panel-sub">87A rebate</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.rebate_87a)}</dd>
        <dt className="hc-panel-sub">Surcharge</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.surcharge)}</dd>
        <dt className="hc-panel-sub">Cess (4%)</dt>
        <dd style={{ textAlign: 'right' }}>{inr(data.cess)}</dd>
        <dt className="hc-panel-sub" style={{ fontWeight: 600 }}>
          Total tax
        </dt>
        <dd style={{ textAlign: 'right', fontWeight: 600, fontSize: '1.1rem' }}>
          {inr(data.total_tax)}
        </dd>
      </dl>
      {data.notes && data.notes.length > 0 && (
        <ul className="hc-panel-sub" style={{ marginTop: 10, fontSize: '0.78rem', paddingLeft: 18 }}>
          {data.notes.map((note, idx) => (
            <li key={idx}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function RegimeComparator({ fy }: Props) {
  const toast = useToast();
  const [inputs, setInputs] = useState<TaxRegimeInputs>(blankInputs);
  const [result, setResult] = useState<TaxRegimeComparison | null>(null);
  const [loading, setLoading] = useState(false);

  const compute = async () => {
    setLoading(true);
    try {
      const data = await api.compareTaxRegime(fy, inputs);
      setResult(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not compute regime comparison');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="hc-panel" data-testid="regime-comparator">
      <h2 className="hc-panel-title">Old vs New Regime — FY {fy}</h2>
      <p className="hc-panel-sub" style={{ marginTop: 4 }}>
        Enter your income + deductions; HisabClub picks the regime that saves more tax.
      </p>

      <div className="hc-grid-2" style={{ marginTop: 16 }}>
        <div>
          <label className="hc-label">Gross salary (annual)</label>
          <input
            type="number"
            value={inputs.gross_salary ?? ''}
            onChange={(e) => setInputs({ ...inputs, gross_salary: e.target.value })}
            placeholder="e.g. 1500000"
            className="hc-input"
            min="0"
          />
        </div>
        <div>
          <label className="hc-label">80C (₹1.5L cap)</label>
          <input
            type="number"
            value={inputs.deduction_80c ?? ''}
            onChange={(e) => setInputs({ ...inputs, deduction_80c: e.target.value })}
            placeholder="e.g. 150000"
            className="hc-input"
            min="0"
          />
        </div>
        <div>
          <label className="hc-label">80CCD(1B) NPS (₹50k cap)</label>
          <input
            type="number"
            value={inputs.deduction_80ccd_1b ?? ''}
            onChange={(e) => setInputs({ ...inputs, deduction_80ccd_1b: e.target.value })}
            placeholder="e.g. 50000"
            className="hc-input"
            min="0"
          />
        </div>
        <div>
          <label className="hc-label">80D self (cap depends on age)</label>
          <input
            type="number"
            value={inputs.deduction_80d_self ?? ''}
            onChange={(e) => setInputs({ ...inputs, deduction_80d_self: e.target.value })}
            placeholder="e.g. 25000"
            className="hc-input"
            min="0"
          />
        </div>
        <div>
          <label className="hc-label">Home loan interest, self-occupied (₹2L cap)</label>
          <input
            type="number"
            value={inputs.home_loan_interest_self ?? ''}
            onChange={(e) => setInputs({ ...inputs, home_loan_interest_self: e.target.value })}
            placeholder="e.g. 200000"
            className="hc-input"
            min="0"
          />
        </div>
        <div>
          <label className="hc-label">&nbsp;</label>
          <button
            onClick={() => void compute()}
            disabled={loading}
            className="hc-btn hc-btn-solid"
            style={{ width: '100%' }}
          >
            {loading ? 'Computing…' : 'Compare regimes'}
          </button>
        </div>
      </div>

      {result && (
        <div className="hc-grid-2" style={{ marginTop: 18 }}>
          <RegimeColumn data={result.old} highlight={result.recommendation === 'old'} />
          <RegimeColumn data={result.new} highlight={result.recommendation === 'new'} />
        </div>
      )}

      {result && result.recommendation !== 'neutral' && (
        <p className="hc-msg" style={{ marginTop: 12 }}>
          Choose the <strong>{result.recommendation} regime</strong> — saves{' '}
          <strong>{inr(Math.abs(Number(result.delta)))}</strong> for FY {result.fy}.
        </p>
      )}
      {result && result.sources && result.sources.length > 0 && (
        <p className="hc-panel-sub" style={{ marginTop: 8, fontSize: '0.76rem' }}>
          Rule basis: {result.sources.join(' • ')}
        </p>
      )}
    </section>
  );
}
