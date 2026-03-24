import { useEffect, useMemo, useState } from 'react';
import { Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { api } from '../api/client';
import type { Transaction, TransactionFilters } from '../api/client';

type TimelinePreset = 'all' | '7d' | '30d' | '90d' | 'fy' | 'custom';

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

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
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

  const fetchTransactions = async () => {
    setLoading(true);
    try {
      const res = await api.getTransactions(currentFilters);
      setTransactions(res.items);
      setTotal(res.total);

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

  const totalPages = Math.ceil(total / perPage);

  const formatAmount = (amount: number, dir: string) => {
    const formatted = new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(amount);
    return dir === 'credit' ? `+${formatted}` : formatted;
  };

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });

  return (
    <div className="hc-page">
      <header className="hc-page-header">
        <div>
          <p className="hc-kicker">Ledger</p>
          <h1 className="hc-page-title">Transactions</h1>
          <p className="hc-page-subtitle">Search and filter normalized debit/credit entries across all sources.</p>
        </div>
        <div className="hc-inline-actions">
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

      <section className="hc-table-wrap">
        {loading ? (
          <div className="hc-panel">Loading transactions...</div>
        ) : transactions.length === 0 ? (
          <div className="hc-panel">No transactions found. Upload a statement to get started.</div>
        ) : (
          <table className="hc-table" style={{ minWidth: 960 }}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Category</th>
                <th>Bank</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((txn) => (
                <tr key={txn.id}>
                  <td style={{ whiteSpace: 'nowrap', color: 'var(--hc-muted-fg)' }}>{formatDate(txn.transaction_date)}</td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{txn.merchant_normalized || txn.merchant_raw}</div>
                    {txn.merchant_normalized && txn.merchant_normalized !== txn.merchant_raw && (
                      <div style={{ fontSize: '0.72rem', color: 'var(--hc-muted-fg)', maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {txn.merchant_raw}
                      </div>
                    )}
                  </td>
                  <td>
                    {txn.category_name ? <span className="hc-badge">{txn.category_name}</span> : <span className="hc-panel-sub">Uncategorized</span>}
                  </td>
                  <td style={{ color: 'var(--hc-muted-fg)' }}>{txn.bank_label || txn.bank_name || '-'}</td>
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
