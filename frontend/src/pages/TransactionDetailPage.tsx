import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { api, type Category, type TransactionDetail } from '../api/client';

const NATURES = ['expense', 'income', 'transfer_internal', 'refund', 'investment', 'tax'];

const formatAmount = (amount: number, direction: string) =>
  `${direction === 'credit' ? '+' : ''}${new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount)}`;

function formatDate(value?: string | null) {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export default function TransactionDetailPage() {
  const { transactionId } = useParams<{ transactionId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<TransactionDetail | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [form, setForm] = useState({
    category_id: '',
    transaction_nature: '',
    notes: '',
    tagsText: '',
    is_excluded: false,
  });

  const transaction = detail?.transaction ?? null;

  const load = async () => {
    if (!transactionId) return;
    setLoading(true);
    try {
      const [detailRes, categoriesRes] = await Promise.all([
        api.getTransactionDetail(transactionId),
        api.getCategories(),
      ]);
      setDetail(detailRes);
      setCategories(categoriesRes);
      setForm({
        category_id: detailRes.transaction.category_id ?? '',
        transaction_nature: detailRes.transaction.transaction_nature ?? '',
        notes: detailRes.transaction.notes ?? '',
        tagsText: (detailRes.transaction.tags ?? []).join(', '),
        is_excluded: Boolean(detailRes.transaction.is_excluded),
      });
    } catch (err) {
      console.error('Failed to load transaction detail:', err);
      setMessage(err instanceof Error ? err.message : 'Failed to load transaction detail.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transactionId]);

  const hasChanges = useMemo(() => {
    if (!transaction) return false;
    return (
      (transaction.category_id ?? '') !== form.category_id ||
      (transaction.transaction_nature ?? '') !== form.transaction_nature ||
      (transaction.notes ?? '') !== form.notes ||
      (transaction.tags ?? []).join(', ') !==
        form.tagsText
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean)
          .join(', ') ||
      Boolean(transaction.is_excluded) !== form.is_excluded
    );
  }, [form, transaction]);

  const handleSave = async () => {
    if (!transactionId || !transaction || !hasChanges) return;
    setSaving(true);
    setMessage('');
    try {
      await api.updateTransaction(transactionId, {
        category_id: form.category_id || null,
        transaction_nature: form.transaction_nature || null,
        notes: form.notes.trim() || null,
        tags: form.tagsText
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        is_excluded: form.is_excluded,
      });
      await load();
      setMessage('Transaction updated.');
    } catch (err) {
      console.error('Failed to update transaction:', err);
      setMessage(err instanceof Error ? err.message : 'Failed to update transaction.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="hc-page">
        <div className="hc-panel">Loading transaction...</div>
      </div>
    );
  }

  if (!transaction || !detail) {
    return (
      <div className="hc-page">
        <div className="hc-panel">
          <p className="hc-panel-title">Transaction not found</p>
          <button type="button" className="hc-btn hc-btn-outline" onClick={() => navigate('/transactions')}>
            Back to Transactions
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Ledger</p>
          <h1 className="hc-page-title">Transaction Detail</h1>
          <p className="hc-page-subtitle">
            Audit source evidence, override history, and split lineage for a canonical ledger row.
          </p>
        </div>
        <div className="hc-inline-actions">
          <button type="button" className="hc-btn hc-btn-outline" onClick={() => navigate('/transactions')}>
            Back
          </button>
          <button type="button" className="hc-btn hc-btn-solid" disabled={!hasChanges || saving} onClick={handleSave}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </header>

      {message && <div className="hc-msg hc-msg-ok">{message}</div>}

      <section className="hc-grid-3">
        <div className="hc-panel">
          <p className="hc-stat-label">Amount</p>
          <p className="hc-stat-value">{formatAmount(transaction.amount, transaction.direction)}</p>
          <p className="hc-panel-sub">
            {transaction.direction} · {transaction.transaction_nature} · {transaction.currency ?? 'INR'}
          </p>
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">Merchant</p>
          <p className="hc-stat-value" style={{ fontSize: '1.4rem' }}>
            {transaction.merchant_normalized || transaction.merchant_raw}
          </p>
          {transaction.merchant_normalized && transaction.merchant_normalized !== transaction.merchant_raw && (
            <p className="hc-panel-sub">{transaction.merchant_raw}</p>
          )}
        </div>
        <div className="hc-panel">
          <p className="hc-stat-label">Account</p>
          <p className="hc-stat-value" style={{ fontSize: '1.2rem' }}>
            {transaction.bank_label || transaction.bank_name || '-'}
          </p>
          <p className="hc-panel-sub">
            {transaction.account_type || '-'}
            {transaction.account_masked ? ` · ${transaction.account_masked}` : ''}
          </p>
        </div>
      </section>

      <section className="hc-grid-2">
        <div className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Edit Transaction</h2>
              <p className="hc-panel-sub">Changes are recorded to override history.</p>
            </div>
          </div>
          <div className="hc-grid-2">
            <label className="hc-field">
              <span className="hc-label">Category</span>
              <select
                className="hc-select"
                value={form.category_id}
                onChange={(e) => setForm((current) => ({ ...current, category_id: e.target.value }))}
              >
                <option value="">Clear category</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="hc-field">
              <span className="hc-label">Nature</span>
              <select
                className="hc-select"
                value={form.transaction_nature}
                onChange={(e) =>
                  setForm((current) => ({ ...current, transaction_nature: e.target.value }))
                }
              >
                <option value="">Choose nature</option>
                {NATURES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="hc-grid-2" style={{ marginTop: '1rem' }}>
            <label className="hc-field">
              <span className="hc-label">Notes</span>
              <input
                className="hc-input"
                type="text"
                value={form.notes}
                onChange={(e) => setForm((current) => ({ ...current, notes: e.target.value }))}
                placeholder="Analyst note"
              />
            </label>
            <label className="hc-field">
              <span className="hc-label">Tags</span>
              <input
                className="hc-input"
                type="text"
                value={form.tagsText}
                onChange={(e) => setForm((current) => ({ ...current, tagsText: e.target.value }))}
                placeholder="comma,separated,tags"
              />
            </label>
          </div>
          <label className="hc-field" style={{ marginTop: '1rem' }}>
            <span className="hc-label">Ledger Inclusion</span>
            <select
              className="hc-select"
              value={form.is_excluded ? 'true' : 'false'}
              onChange={(e) =>
                setForm((current) => ({ ...current, is_excluded: e.target.value === 'true' }))
              }
            >
              <option value="false">Included</option>
              <option value="true">Excluded</option>
            </select>
          </label>
          <div className="hc-inline-actions" style={{ marginTop: '1rem', justifyContent: 'space-between' }}>
            <div className="hc-inline-actions">
              <span className="hc-badge">{transaction.category_name || 'Uncategorized'}</span>
              <span className="hc-badge">{transaction.transaction_nature}</span>
              {transaction.is_excluded ? <span className="hc-badge hc-badge-warn">Excluded</span> : null}
            </div>
            <div className="hc-panel-sub">
              Posted {formatDate(transaction.posting_date)} · Created {formatDate(transaction.created_at)}
            </div>
          </div>
        </div>

        <div className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Split Lineage</h2>
              <p className="hc-panel-sub">Track parent-child relationships created through manual split.</p>
            </div>
          </div>
          {detail.split_parent ? (
            <div style={{ marginBottom: '1rem' }}>
              <p className="hc-label">Parent Transaction</p>
              <Link to={`/transactions/${detail.split_parent.id}`} style={{ fontWeight: 600 }}>
                {detail.split_parent.merchant_normalized || detail.split_parent.merchant_raw}
              </Link>
              <p className="hc-panel-sub">
                {formatDate(detail.split_parent.transaction_date)} ·{' '}
                {formatAmount(detail.split_parent.amount, detail.split_parent.direction)}
              </p>
            </div>
          ) : null}
          {!detail.split_children.length ? (
            detail.split_parent ? null : <p className="hc-panel-sub">This transaction is not acting as a split parent.</p>
          ) : (
            <div style={{ display: 'grid', gap: '0.85rem' }}>
              {detail.split_children.map((child) => (
                <div key={child.id} style={{ borderTop: '1px solid var(--hc-border)', paddingTop: '0.85rem' }}>
                  <Link to={`/transactions/${child.id}`} style={{ fontWeight: 600 }}>
                    {child.merchant_normalized || child.merchant_raw}
                  </Link>
                  <p className="hc-panel-sub">
                    {formatDate(child.transaction_date)} · {formatAmount(child.amount, child.direction)} ·{' '}
                    {child.transaction_nature}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="hc-grid-2">
        <div className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Source Evidence</h2>
              <p className="hc-panel-sub">Primary parsed rows that promoted or merged into this canonical transaction.</p>
            </div>
          </div>
          {!detail.sources.length ? (
            <p className="hc-panel-sub">No source rows found.</p>
          ) : (
            <div style={{ display: 'grid', gap: '0.9rem' }}>
              {detail.sources.map((source) => (
                <div key={source.parsed_txn_id} style={{ borderTop: '1px solid var(--hc-border)', paddingTop: '0.85rem' }}>
                  <div className="hc-inline-actions" style={{ justifyContent: 'space-between' }}>
                    <div>
                      <p style={{ fontWeight: 600 }}>{source.source_type}</p>
                      <p className="hc-panel-sub">
                        {source.extraction_method} · {source.match_method} · confidence {source.confidence.toFixed(2)}
                      </p>
                    </div>
                    {source.statement_id ? (
                      <Link className="hc-btn hc-btn-outline" to={`/statements/${source.statement_id}/review`}>
                        Open Review
                      </Link>
                    ) : null}
                  </div>
                  <p style={{ marginTop: '0.45rem' }}>{source.description_raw}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Override History</h2>
              <p className="hc-panel-sub">Every manual change remains visible here.</p>
            </div>
          </div>
          {!detail.overrides.length ? (
            <p className="hc-panel-sub">No manual overrides recorded yet.</p>
          ) : (
            <div style={{ display: 'grid', gap: '0.8rem' }}>
              {detail.overrides.map((item) => (
                <div key={item.id} style={{ borderTop: '1px solid var(--hc-border)', paddingTop: '0.85rem' }}>
                  <div className="hc-inline-actions" style={{ justifyContent: 'space-between' }}>
                    <span className="hc-badge">{item.field_name}</span>
                    <span className="hc-panel-sub">{formatDate(item.created_at)}</span>
                  </div>
                  <p className="hc-panel-sub">
                    {item.old_value ?? 'null'} → {item.new_value}
                  </p>
                  {item.override_reason ? <p>{item.override_reason}</p> : null}
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
