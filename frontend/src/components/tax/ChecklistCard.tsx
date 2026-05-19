/**
 * ChecklistCard — Sprint B.6.
 *
 * Renders the GET /api/v1/tax/checklist/{fy} response as a prioritised list:
 *   1. block_filing items first (red),
 *   2. warning items (amber),
 *   3. info items (slate).
 * Each item carries a CTA that links to the upload / imports page that
 * resolves the gap.
 */

import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { TaxChecklistBundle, TaxChecklistItem } from '../../api/client';
import { useToast } from '../ui/Toast';

type Props = {
  fy: string;
};

const SEVERITY_ORDER: Record<TaxChecklistItem['severity'], number> = {
  block_filing: 0,
  warning: 1,
  info: 2,
};

function severityStyle(severity: TaxChecklistItem['severity']): {
  badge: string;
  border: string;
  label: string;
} {
  switch (severity) {
    case 'block_filing':
      return { badge: 'hc-badge hc-badge-danger', border: 'var(--hc-danger)', label: 'Blocker' };
    case 'warning':
      return { badge: 'hc-badge hc-badge-warn', border: 'var(--hc-warn)', label: 'Warning' };
    default:
      return { badge: 'hc-badge', border: 'var(--hc-border)', label: 'Info' };
  }
}

export default function ChecklistCard({ fy }: Props) {
  const toast = useToast();
  const [bundle, setBundle] = useState<TaxChecklistBundle | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getTaxChecklist(fy)
      .then((data) => {
        if (!cancelled) setBundle(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          toast.error(err instanceof Error ? err.message : 'Could not load checklist');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fy, toast]);

  const items = (bundle?.items || []).slice().sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );
  const blockerCount = items.filter((i) => i.severity === 'block_filing').length;

  return (
    <section className="hc-panel" data-testid="checklist-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2 className="hc-panel-title">Tax checklist — FY {fy}</h2>
        {blockerCount > 0 && (
          <span className="hc-badge hc-badge-danger">{blockerCount} blocker(s)</span>
        )}
        {bundle && blockerCount === 0 && (
          <span className="hc-badge hc-badge-accent">Ready</span>
        )}
      </div>

      {loading && (
        <p className="hc-panel-sub" style={{ marginTop: 8 }}>
          Loading…
        </p>
      )}

      {!loading && items.length === 0 && bundle && (
        <p className="hc-panel-sub" style={{ marginTop: 8 }}>
          All checked items are present. Upload more documents (broker P&L, rent receipts) to improve match rate.
        </p>
      )}

      {!loading && items.length > 0 && (
        <ul style={{ marginTop: 12, listStyle: 'none', padding: 0 }}>
          {items.map((item) => {
            const style = severityStyle(item.severity);
            return (
              <li
                key={item.kind}
                data-testid={`checklist-item-${item.kind}`}
                style={{
                  borderLeft: `3px solid ${style.border}`,
                  paddingLeft: 12,
                  marginBottom: 12,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <strong>{item.title}</strong>
                  <span className={style.badge}>{style.label}</span>
                </div>
                <p className="hc-panel-sub" style={{ marginTop: 4 }}>
                  {item.detail}
                </p>
                {item.cta_link && (
                  <a
                    href={item.cta_link}
                    className="hc-link"
                    style={{ marginTop: 4, display: 'inline-block', fontSize: '0.85rem' }}
                  >
                    Resolve →
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
