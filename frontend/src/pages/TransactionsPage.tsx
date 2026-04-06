import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Scissors, Search } from 'lucide-react';
import { Link } from 'react-router-dom';

import { api } from '../api/client';
import type { Category, Transaction, TransactionFilters } from '../api/client';

type TimelinePreset = 'all' | '7d' | '30d' | '90d' | 'fy' | 'custom';

type BulkEditorState = {
  applyCategory: boolean;
  category_id: string;
  applyNature: boolean;
  transaction_nature: string;
  applyNotes: boolean;
  notes: string;
  applyTags: boolean;
  tagsText: string;
  applyExclude: boolean;
  is_excluded: boolean;
};

type SplitPartDraft = {
  amount: string;
  merchant_raw: string;
  category_id: string;
  transaction_nature: string;
  notes: string;
  tagsText: string;
};

const emptyBulkEditor = (): BulkEditorState => ({
  applyCategory: false,
  category_id: '',
  applyNature: false,
  transaction_nature: '',
  applyNotes: false,
  notes: '',
  applyTags: false,
  tagsText: '',
  applyExclude: false,
  is_excluded: false,
});

function toInputDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function getPresetRange(preset: TimelinePreset): { from: string; to: string } {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const to = toInputDate(today);

  if (preset === '7d') {
    const from = new Date(today);
    from.setDate(from.getDate() - 6);
    return { from: toInputDate(from), to };
  }
  if (preset === '30d') {
    const from = new Date(today);
    from.setDate(from.getDate() - 29);
    return { from: toInputDate(from), to };
  }
  if (preset === '90d') {
    const from = new Date(today);
    from.setDate(from.getDate() - 89);
    return { from: toInputDate(from), to };
  }
  if (preset === 'fy') {
    const fyStartYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
    return { from: `${fyStartYear}-04-01`, to };
  }
  return { from: '', to: '' };
}

function formatAmount(amount: number, dir: string) {
  const formatted = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount);
  return dir === 'credit' ? `+${formatted}` : formatted;
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

function buildDefaultSplitParts(txn: Transaction): SplitPartDraft[] {
  const totalPaise = Math.round(txn.amount * 100);
  const firstPaise = Math.floor(totalPaise / 2);
  const secondPaise = totalPaise - firstPaise;
  const defaultNature = txn.transaction_nature || (txn.direction === 'credit' ? 'income' : 'expense');
  return [
    {
      amount: (firstPaise / 100).toFixed(2),
      merchant_raw: txn.merchant_raw,
      category_id: '',
      transaction_nature: defaultNature,
      notes: '',
      tagsText: '',
    },
    {
      amount: (secondPaise / 100).toFixed(2),
      merchant_raw: txn.merchant_raw,
      category_id: '',
      transaction_nature: defaultNature,
      notes: '',
      tagsText: '',
    },
  ];
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [direction, setDirection] = useState('');
  const [timeline, setTimeline] = useState<TimelinePreset>('90d');
  const [fromDate, setFromDate] = useState(() => getPresetRange('90d').from);
  const [toDate, setToDate] = useState(() => getPresetRange('90d').to);
  const [autoCategorizeChecked, setAutoCategorizeChecked] = useState(false);
  const [autoCategorizeInfo, setAutoCategorizeInfo] = useState('');
  const [reclassifying, setReclassifying] = useState(false);
  const [reclassifyInfo, setReclassifyInfo] = useState('');
  const [reconcilingUpi, setReconcilingUpi] = useState(false);
  const [upiInfo, setUpiInfo] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkEditor, setBulkEditor] = useState<BulkEditorState>(emptyBulkEditor());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkInfo, setBulkInfo] = useState('');
  const [splitEditorOpen, setSplitEditorOpen] = useState(false);
  const [splitParts, setSplitParts] = useState<SplitPartDraft[]>([]);
  const [splitBusy, setSplitBusy] = useState(false);
  const [splitInfo, setSplitInfo] = useState('');

  const perPage = 25;

  const currentFilters: TransactionFilters = useMemo(() => {
    const filters: TransactionFilters = {
      page,
      per_page: perPage,
    };
    if (search) filters.search = search;
    if (direction) filters.direction = direction;
    if (fromDate) filters.from = fromDate;
    if (toDate) filters.to = toDate;
    return filters;
  }, [direction, fromDate, page, search, toDate]);

  const selectedTransaction =
    selectedIds.length === 1 ? transactions.find((txn) => txn.id === selectedIds[0]) ?? null : null;

  const fetchTransactions = async () => {
    setLoading(true);
    try {
      const res = await api.getTransactions(currentFilters);
      setTransactions(res.items);
      setTotal(res.total);
      setSelectedIds([]);
      setSplitEditorOpen(false);
      setSplitParts([]);

      if (!autoCategorizeChecked && res.items.some((item) => !item.category_name)) {
        setAutoCategorizeChecked(true);
        const recategorize = await api.autoCategorizeUncategorized(500);
        if (recategorize.updated > 0) {
          setAutoCategorizeInfo(
            `Auto-categorized ${recategorize.updated} of ${recategorize.scanned} uncategorized transactions.`,
          );
          const refreshed = await api.getTransactions(currentFilters);
          setTransactions(refreshed.items);
          setTotal(refreshed.total);
        }
      }
    } catch (err) {
      console.error('Failed to fetch transactions:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, direction, fromDate, toDate]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const result = await api.getCategories();
        if (active) setCategories(result);
      } catch (err) {
        console.error('Failed to fetch categories:', err);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchTransactions();
  };

  const applyTimelinePreset = (preset: TimelinePreset) => {
    setTimeline(preset);
    if (preset !== 'custom') {
      const next = getPresetRange(preset);
      setFromDate(next.from);
      setToDate(next.to);
    }
    setPage(1);
  };

  const handleAiTransferMatch = async () => {
    setReclassifying(true);
    try {
      const result = await api.reclassifyTransferPayments({
        days: 730,
        limit: 5000,
        max_gap_days: 7,
        use_llm: true,
      });
      setReclassifyInfo(
        `AI transfer scan: ${result.updated}/${result.scanned} updated, ${result.matched_credit_card_pairs} card-payment pairs, LLM promoted ${result.llm_promoted}.`,
      );
      await fetchTransactions();
    } catch (err) {
      console.error('Failed AI transfer match:', err);
      setReclassifyInfo('AI transfer scan failed. Check backend logs or LLM settings.');
    } finally {
      setReclassifying(false);
    }
  };

  const handleUpiReconcile = async () => {
    setReconcilingUpi(true);
    try {
      const result = await api.reconcileUpiFailures({
        days: 730,
        max_gap_days: 3,
        limit: 8000,
      });
      setUpiInfo(
        `UPI failure reconciliation: ${result.matched_pairs} pairs matched, ${result.updated_transactions} rows updated.`,
      );
      await fetchTransactions();
    } catch (err) {
      console.error('Failed UPI reconciliation:', err);
      setUpiInfo('UPI reconciliation failed. Check backend logs.');
    } finally {
      setReconcilingUpi(false);
    }
  };

  const toggleSelection = (txnId: string) => {
    setSelectedIds((current) =>
      current.includes(txnId) ? current.filter((id) => id !== txnId) : [...current, txnId],
    );
  };

  const toggleSelectPage = () => {
    if (selectedIds.length === transactions.length && transactions.length > 0) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(transactions.map((txn) => txn.id));
  };

  const openSplitEditor = (txn: Transaction) => {
    setSelectedIds([txn.id]);
    setSplitParts(buildDefaultSplitParts(txn));
    setSplitEditorOpen(true);
    setSplitInfo('');
  };

  const addSplitPart = () => {
    if (!selectedTransaction) return;
    setSplitParts((current) => [
      ...current,
      {
        amount: '0.00',
        merchant_raw: selectedTransaction.merchant_raw,
        category_id: '',
        transaction_nature: selectedTransaction.transaction_nature || 'expense',
        notes: '',
        tagsText: '',
      },
    ]);
  };

  const updateSplitPart = (index: number, patch: Partial<SplitPartDraft>) => {
    setSplitParts((current) => current.map((part, idx) => (idx === index ? { ...part, ...patch } : part)));
  };

  const removeSplitPart = (index: number) => {
    setSplitParts((current) => current.filter((_, idx) => idx !== index));
  };

  const handleBulkApply = async () => {
    if (!selectedIds.length) return;
    const payload: {
      transaction_ids: string[];
      category_id?: string | null;
      transaction_nature?: string | null;
      notes?: string | null;
      tags?: string[] | null;
      is_excluded?: boolean | null;
    } = {
      transaction_ids: selectedIds,
    };
    if (bulkEditor.applyCategory) payload.category_id = bulkEditor.category_id || null;
    if (bulkEditor.applyNature) payload.transaction_nature = bulkEditor.transaction_nature || null;
    if (bulkEditor.applyNotes) payload.notes = bulkEditor.notes || null;
    if (bulkEditor.applyTags) {
      payload.tags = bulkEditor.tagsText
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean);
    }
    if (bulkEditor.applyExclude) payload.is_excluded = bulkEditor.is_excluded;
    if (Object.keys(payload).length === 1) {
      setBulkInfo('Select at least one field to update.');
      return;
    }

    setBulkBusy(true);
    try {
      const result = await api.bulkUpdateTransactions(payload);
      setBulkInfo(`Updated ${result.updated_count} transaction(s).`);
      setBulkEditor(emptyBulkEditor());
      await fetchTransactions();
    } catch (err) {
      console.error('Failed bulk update:', err);
      setBulkInfo(err instanceof Error ? err.message : 'Bulk update failed.');
    } finally {
      setBulkBusy(false);
    }
  };

  const handleSplitTransaction = async () => {
    if (!selectedTransaction) return;
    if (splitParts.length < 2) {
      setSplitInfo('At least two split parts are required.');
      return;
    }
    const sum = splitParts.reduce((totalValue, part) => totalValue + Math.round(Number(part.amount || 0) * 100), 0);
    const original = Math.round(selectedTransaction.amount * 100);
    if (sum !== original) {
      setSplitInfo(
        `Split amounts must add up to ${formatAmount(selectedTransaction.amount, selectedTransaction.direction)}.`,
      );
      return;
    }

    setSplitBusy(true);
    try {
      const result = await api.splitTransaction(selectedTransaction.id, {
        exclude_original: true,
        parts: splitParts.map((part) => ({
          amount: Number(part.amount),
          merchant_raw: part.merchant_raw,
          category_id: part.category_id || null,
          transaction_nature: part.transaction_nature || null,
          notes: part.notes || null,
          tags: part.tagsText
            .split(',')
            .map((tag) => tag.trim())
            .filter(Boolean),
        })),
      });
      setSplitInfo(`Created ${result.created_transactions.length} split transaction(s).`);
      setSplitEditorOpen(false);
      setSplitParts([]);
      setSelectedIds([]);
      await fetchTransactions();
    } catch (err) {
      console.error('Failed split transaction:', err);
      setSplitInfo(err instanceof Error ? err.message : 'Split transaction failed.');
    } finally {
      setSplitBusy(false);
    }
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Ledger</p>
          <h1 className="hc-page-title">Transactions</h1>
          <p className="hc-page-subtitle">Search, bulk edit, and split normalized ledger entries.</p>
        </div>
        <div className="hc-inline-actions">
          <button
            type="button"
            onClick={handleUpiReconcile}
            disabled={reconcilingUpi}
            className="hc-btn hc-btn-outline"
          >
            {reconcilingUpi ? 'Reconciling UPI...' : 'Reconcile UPI Failures'}
          </button>
          <button
            type="button"
            onClick={handleAiTransferMatch}
            disabled={reclassifying}
            className="hc-btn hc-btn-solid"
          >
            {reclassifying ? 'AI Matching...' : 'AI Match Card Payments'}
          </button>
          <span className="hc-badge">{total} Total</span>
        </div>
      </header>

      <section className="hc-panel">
        <div className="hc-grid-4">
          <form onSubmit={handleSearch} className="relative">
            <Search
              size={16}
              strokeWidth={1.5}
              style={{ position: 'absolute', left: '0.8rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--hc-muted-fg)' }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search merchants..."
              className="hc-input"
              style={{ paddingLeft: '2.3rem' }}
            />
          </form>

          <select
            value={direction}
            onChange={(e) => {
              setDirection(e.target.value);
              setPage(1);
            }}
            className="hc-select"
          >
            <option value="">All Directions</option>
            <option value="debit">Debits</option>
            <option value="credit">Credits</option>
          </select>

          <select
            value={timeline}
            onChange={(e) => applyTimelinePreset(e.target.value as TimelinePreset)}
            className="hc-select"
          >
            <option value="7d">Timeline: Last 7 Days</option>
            <option value="30d">Timeline: Last 30 Days</option>
            <option value="90d">Timeline: Last 90 Days</option>
            <option value="fy">Timeline: Current FY</option>
            <option value="all">Timeline: All Time</option>
            <option value="custom">Timeline: Custom</option>
          </select>

          <div className="hc-inline-actions" style={{ justifyContent: 'space-between', width: '100%' }}>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => {
                setTimeline('custom');
                setFromDate(e.target.value);
                setPage(1);
              }}
              className="hc-input"
              style={{ minWidth: 140 }}
            />
            <input
              type="date"
              value={toDate}
              onChange={(e) => {
                setTimeline('custom');
                setToDate(e.target.value);
                setPage(1);
              }}
              className="hc-input"
              style={{ minWidth: 140 }}
            />
          </div>
        </div>
      </section>

      {autoCategorizeInfo && <div className="hc-msg hc-msg-ok">{autoCategorizeInfo}</div>}
      {reclassifyInfo && <div className="hc-msg hc-msg-ok">{reclassifyInfo}</div>}
      {upiInfo && <div className="hc-msg hc-msg-ok">{upiInfo}</div>}
      {bulkInfo && <div className="hc-msg hc-msg-ok">{bulkInfo}</div>}
      {splitInfo && <div className="hc-msg hc-msg-ok">{splitInfo}</div>}

      <section className="hc-panel">
        <div className="hc-panel-head">
          <div>
            <h2 className="hc-panel-title">Selection Tools</h2>
            <p className="hc-panel-sub">{selectedIds.length} transaction(s) selected on this page.</p>
          </div>
          <div className="hc-inline-actions">
            <button type="button" className="hc-btn hc-btn-outline" onClick={toggleSelectPage}>
              {selectedIds.length === transactions.length && transactions.length > 0 ? 'Clear Page' : 'Select Page'}
            </button>
            <button type="button" className="hc-btn hc-btn-outline" onClick={() => setSelectedIds([])}>
              Clear Selection
            </button>
            <button
              type="button"
              className="hc-btn hc-btn-outline"
              disabled={!selectedTransaction}
              onClick={() => selectedTransaction && openSplitEditor(selectedTransaction)}
            >
              <Scissors size={16} strokeWidth={1.5} />
              Split Selected
            </button>
          </div>
        </div>

        <div className="hc-grid-4">
          <label className="hc-field">
            <span className="hc-label">
              <input
                type="checkbox"
                checked={bulkEditor.applyCategory}
                onChange={(e) => setBulkEditor((current) => ({ ...current, applyCategory: e.target.checked }))}
                style={{ marginRight: '0.5rem' }}
              />
              Set Category
            </span>
            <select
              className="hc-select"
              value={bulkEditor.category_id}
              onChange={(e) => setBulkEditor((current) => ({ ...current, category_id: e.target.value }))}
              disabled={!bulkEditor.applyCategory}
            >
              <option value="">Clear Category</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>

          <label className="hc-field">
            <span className="hc-label">
              <input
                type="checkbox"
                checked={bulkEditor.applyNature}
                onChange={(e) => setBulkEditor((current) => ({ ...current, applyNature: e.target.checked }))}
                style={{ marginRight: '0.5rem' }}
              />
              Set Nature
            </span>
            <select
              className="hc-select"
              value={bulkEditor.transaction_nature}
              onChange={(e) => setBulkEditor((current) => ({ ...current, transaction_nature: e.target.value }))}
              disabled={!bulkEditor.applyNature}
            >
              <option value="">Choose nature</option>
              {['expense', 'income', 'transfer_internal', 'refund', 'investment', 'tax'].map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="hc-field">
            <span className="hc-label">
              <input
                type="checkbox"
                checked={bulkEditor.applyNotes}
                onChange={(e) => setBulkEditor((current) => ({ ...current, applyNotes: e.target.checked }))}
                style={{ marginRight: '0.5rem' }}
              />
              Set Notes
            </span>
            <input
              type="text"
              className="hc-input"
              value={bulkEditor.notes}
              onChange={(e) => setBulkEditor((current) => ({ ...current, notes: e.target.value }))}
              disabled={!bulkEditor.applyNotes}
              placeholder="Optional analyst note"
            />
          </label>

          <label className="hc-field">
            <span className="hc-label">
              <input
                type="checkbox"
                checked={bulkEditor.applyTags}
                onChange={(e) => setBulkEditor((current) => ({ ...current, applyTags: e.target.checked }))}
                style={{ marginRight: '0.5rem' }}
              />
              Replace Tags
            </span>
            <input
              type="text"
              className="hc-input"
              value={bulkEditor.tagsText}
              onChange={(e) => setBulkEditor((current) => ({ ...current, tagsText: e.target.value }))}
              disabled={!bulkEditor.applyTags}
              placeholder="comma,separated,tags"
            />
          </label>
        </div>

        <div className="hc-inline-actions" style={{ marginTop: '1rem', justifyContent: 'space-between' }}>
          <label className="hc-field" style={{ maxWidth: 260 }}>
            <span className="hc-label">
              <input
                type="checkbox"
                checked={bulkEditor.applyExclude}
                onChange={(e) => setBulkEditor((current) => ({ ...current, applyExclude: e.target.checked }))}
                style={{ marginRight: '0.5rem' }}
              />
              Set Excluded State
            </span>
            <select
              className="hc-select"
              value={bulkEditor.is_excluded ? 'true' : 'false'}
              onChange={(e) => setBulkEditor((current) => ({ ...current, is_excluded: e.target.value === 'true' }))}
              disabled={!bulkEditor.applyExclude}
            >
              <option value="false">Keep Included</option>
              <option value="true">Exclude from ledger views</option>
            </select>
          </label>

          <button
            type="button"
            className="hc-btn hc-btn-solid"
            disabled={!selectedIds.length || bulkBusy}
            onClick={handleBulkApply}
          >
            {bulkBusy ? 'Applying...' : `Apply to ${selectedIds.length || 0} Selected`}
          </button>
        </div>
      </section>

      {splitEditorOpen && selectedTransaction && (
        <section className="hc-panel">
          <div className="hc-panel-head">
            <div>
              <h2 className="hc-panel-title">Split Transaction</h2>
              <p className="hc-panel-sub">
                Splitting {formatAmount(selectedTransaction.amount, selectedTransaction.direction)} from{' '}
                {selectedTransaction.merchant_normalized || selectedTransaction.merchant_raw}.
              </p>
            </div>
            <div className="hc-inline-actions">
              <button type="button" className="hc-btn hc-btn-outline" onClick={addSplitPart}>
                Add Part
              </button>
              <button
                type="button"
                className="hc-btn hc-btn-solid"
                disabled={splitBusy}
                onClick={handleSplitTransaction}
              >
                {splitBusy ? 'Splitting...' : 'Create Split'}
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gap: '1rem' }}>
            {splitParts.map((part, index) => (
              <div key={`split-${index}`} className="hc-panel" style={{ padding: '1rem' }}>
                <div className="hc-inline-actions" style={{ justifyContent: 'space-between' }}>
                  <h3 className="hc-panel-title">Part {index + 1}</h3>
                  <button
                    type="button"
                    className="hc-btn hc-btn-outline"
                    disabled={splitParts.length <= 2}
                    onClick={() => removeSplitPart(index)}
                  >
                    Remove
                  </button>
                </div>
                <div className="hc-grid-4" style={{ marginTop: '0.85rem' }}>
                  <input
                    type="number"
                    step="0.01"
                    className="hc-input"
                    value={part.amount}
                    onChange={(e) => updateSplitPart(index, { amount: e.target.value })}
                    placeholder="Amount"
                  />
                  <input
                    type="text"
                    className="hc-input"
                    value={part.merchant_raw}
                    onChange={(e) => updateSplitPart(index, { merchant_raw: e.target.value })}
                    placeholder="Description"
                  />
                  <select
                    className="hc-select"
                    value={part.category_id}
                    onChange={(e) => updateSplitPart(index, { category_id: e.target.value })}
                  >
                    <option value="">Keep Original Category</option>
                    {categories.map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.name}
                      </option>
                    ))}
                  </select>
                  <select
                    className="hc-select"
                    value={part.transaction_nature}
                    onChange={(e) => updateSplitPart(index, { transaction_nature: e.target.value })}
                  >
                    {['expense', 'income', 'transfer_internal', 'refund', 'investment', 'tax'].map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="hc-grid-2" style={{ marginTop: '0.85rem' }}>
                  <input
                    type="text"
                    className="hc-input"
                    value={part.notes}
                    onChange={(e) => updateSplitPart(index, { notes: e.target.value })}
                    placeholder="Notes"
                  />
                  <input
                    type="text"
                    className="hc-input"
                    value={part.tagsText}
                    onChange={(e) => updateSplitPart(index, { tagsText: e.target.value })}
                    placeholder="comma,separated,tags"
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="hc-table-wrap">
        {loading ? (
          <div className="hc-panel">Loading transactions...</div>
        ) : transactions.length === 0 ? (
          <div className="hc-panel">No transactions found. Upload a statement to get started.</div>
        ) : (
          <table className="hc-table" style={{ minWidth: 1080 }}>
            <thead>
              <tr>
                <th style={{ width: 48 }}>Sel</th>
                <th>Date</th>
                <th>Description</th>
                <th>Category</th>
                <th>Bank</th>
                <th>Nature</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
                <th style={{ width: 90 }}>Split</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((txn) => (
                <tr key={txn.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(txn.id)}
                      onChange={() => toggleSelection(txn.id)}
                      aria-label={`Select transaction ${txn.id}`}
                    />
                  </td>
                  <td style={{ whiteSpace: 'nowrap', color: 'var(--hc-muted-fg)' }}>{formatDate(txn.transaction_date)}</td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{txn.merchant_normalized || txn.merchant_raw}</div>
                    <div style={{ marginTop: '0.25rem' }}>
                      <Link to={`/transactions/${txn.id}`} className="hc-panel-sub">
                        Open detail
                      </Link>
                    </div>
                    {txn.merchant_normalized && txn.merchant_normalized !== txn.merchant_raw && (
                      <div style={{ fontSize: '0.72rem', color: 'var(--hc-muted-fg)', maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {txn.merchant_raw}
                      </div>
                    )}
                    {txn.notes && (
                      <div style={{ fontSize: '0.72rem', color: 'var(--hc-muted-fg)', marginTop: '0.2rem' }}>
                        {txn.notes}
                      </div>
                    )}
                  </td>
                  <td>
                    {txn.category_name ? <span className="hc-badge">{txn.category_name}</span> : <span className="hc-panel-sub">Uncategorized</span>}
                  </td>
                  <td style={{ color: 'var(--hc-muted-fg)' }}>{txn.bank_label || txn.bank_name || '-'}</td>
                  <td>
                    <span className="hc-badge">{txn.transaction_nature}</span>
                  </td>
                  <td
                    style={{
                      textAlign: 'right',
                      whiteSpace: 'nowrap',
                      fontWeight: 600,
                      color: txn.direction === 'credit' ? '#22c55e' : 'var(--hc-fg)',
                    }}
                  >
                    {formatAmount(txn.amount, txn.direction)}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="hc-btn hc-btn-outline"
                      onClick={() => openSplitEditor(txn)}
                    >
                      <Scissors size={14} strokeWidth={1.5} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {totalPages > 1 && (
        <div className="hc-inline-actions" style={{ justifyContent: 'space-between' }}>
          <p className="hc-panel-sub">
            Page {page} of {totalPages}
          </p>
          <div className="hc-inline-actions">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1}
              className="hc-btn hc-btn-outline"
              aria-label="Previous page"
            >
              <ChevronLeft size={16} strokeWidth={1.5} />
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page === totalPages}
              className="hc-btn hc-btn-outline"
              aria-label="Next page"
            >
              <ChevronRight size={16} strokeWidth={1.5} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
