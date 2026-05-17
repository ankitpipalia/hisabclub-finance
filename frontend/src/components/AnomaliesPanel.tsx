import { useEffect, useState } from 'react';
import type { AnomalyTransaction } from '../api/client';

type Props = {
  /** Caller supplies the fetcher so the component is testable without MSW. */
  fetchAnomalies: () => Promise<{ items: AnomalyTransaction[]; total: number }>;
  /** Limit shown on the panel before "see all". */
  maxVisible?: number;
};

type Status = 'loading' | 'empty' | 'error' | 'ready';

/**
 * Compact list of recent anomalies for the Dashboard. Pure presentation — the
 * fetcher is injected so tests can drive it without mocking fetch.
 */
export function AnomaliesPanel({ fetchAnomalies, maxVisible = 5 }: Props) {
  const [status, setStatus] = useState<Status>('loading');
  const [items, setItems] = useState<AnomalyTransaction[]>([]);
  const [total, setTotal] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    fetchAnomalies()
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
        setTotal(response.total);
        setStatus(response.items.length === 0 ? 'empty' : 'ready');
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setErrorMessage(err.message || 'Failed to load anomalies.');
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [fetchAnomalies]);

  if (status === 'loading') {
    return (
      <section aria-label="Anomalies" data-testid="anomalies-loading">
        <h2>Anomalies</h2>
        <p>Looking for unusual activity…</p>
      </section>
    );
  }

  if (status === 'error') {
    return (
      <section aria-label="Anomalies" data-testid="anomalies-error">
        <h2>Anomalies</h2>
        <p role="alert">{errorMessage}</p>
      </section>
    );
  }

  if (status === 'empty') {
    return (
      <section aria-label="Anomalies" data-testid="anomalies-empty">
        <h2>Anomalies</h2>
        <p>No anomalies in the last 30 days. You're on track.</p>
      </section>
    );
  }

  const visible = items.slice(0, maxVisible);
  return (
    <section aria-label="Anomalies" data-testid="anomalies-list">
      <h2>Anomalies ({total})</h2>
      <ul>
        {visible.map((item) => (
          <li key={item.transaction_id} data-testid="anomaly-item">
            <strong>₹{item.amount}</strong> · {item.merchant}
            {item.category_name && ` · ${item.category_name}`}
            <span data-testid={`anomaly-reason-${item.reason}`}>
              {' '}
              · {item.reason === 'category_spike' ? 'spike' : 'first time'}
            </span>
            <p>{item.detail}</p>
          </li>
        ))}
      </ul>
      {items.length > maxVisible && (
        <p>+{items.length - maxVisible} more — see all</p>
      )}
    </section>
  );
}
