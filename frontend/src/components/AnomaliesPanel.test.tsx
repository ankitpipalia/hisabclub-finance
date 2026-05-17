import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AnomaliesPanel } from './AnomaliesPanel';
import type { AnomalyTransaction } from '../api/client';

function makeAnomaly(over: Partial<AnomalyTransaction> = {}): AnomalyTransaction {
  return {
    transaction_id: 'txn-1',
    transaction_date: '2026-05-01',
    amount: '2000.00',
    merchant: 'Amazon',
    category_id: null,
    category_name: 'Shopping',
    bank_name: 'HDFC',
    reason: 'category_spike',
    detail: '₹2,000 on Shopping is 3.4σ above your average.',
    expected_mean: '500.00',
    expected_max: '1200.00',
    deviation_ratio: 3.4,
    ...over,
  };
}

describe('<AnomaliesPanel />', () => {
  it('shows a loading state before the fetcher resolves', () => {
    const fetchAnomalies = vi.fn(() => new Promise(() => {}));
    render(<AnomaliesPanel fetchAnomalies={fetchAnomalies as never} />);
    expect(screen.getByTestId('anomalies-loading')).toBeInTheDocument();
  });

  it('renders the empty state when no anomalies returned', async () => {
    const fetchAnomalies = vi.fn(async () => ({ items: [], total: 0 }));
    render(<AnomaliesPanel fetchAnomalies={fetchAnomalies} />);
    await waitFor(() => {
      expect(screen.getByTestId('anomalies-empty')).toBeInTheDocument();
    });
    expect(screen.getByText(/on track/i)).toBeInTheDocument();
  });

  it('renders anomaly rows with merchant, amount, and reason badge', async () => {
    const fetchAnomalies = vi.fn(async () => ({
      items: [
        makeAnomaly({ transaction_id: 't1', merchant: 'Amazon' }),
        makeAnomaly({
          transaction_id: 't2',
          merchant: 'NewBrand',
          reason: 'new_large_merchant',
        }),
      ],
      total: 2,
    }));
    render(<AnomaliesPanel fetchAnomalies={fetchAnomalies} />);
    await waitFor(() => {
      expect(screen.getByTestId('anomalies-list')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('anomaly-item')).toHaveLength(2);
    expect(screen.getByText(/Amazon/)).toBeInTheDocument();
    expect(screen.getByText(/NewBrand/)).toBeInTheDocument();
    expect(
      screen.getByTestId('anomaly-reason-category_spike'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('anomaly-reason-new_large_merchant'),
    ).toBeInTheDocument();
  });

  it('shows error state when the fetcher rejects', async () => {
    const fetchAnomalies = vi.fn(async () => {
      throw new Error('upstream timeout');
    });
    render(<AnomaliesPanel fetchAnomalies={fetchAnomalies} />);
    await waitFor(() => {
      expect(screen.getByTestId('anomalies-error')).toBeInTheDocument();
    });
    expect(screen.getByRole('alert')).toHaveTextContent('upstream timeout');
  });

  it('truncates to maxVisible and shows overflow count', async () => {
    const items: AnomalyTransaction[] = Array.from({ length: 8 }, (_, i) =>
      makeAnomaly({ transaction_id: `t${i}`, merchant: `M${i}` }),
    );
    const fetchAnomalies = vi.fn(async () => ({ items, total: 8 }));
    render(
      <AnomaliesPanel fetchAnomalies={fetchAnomalies} maxVisible={3} />,
    );
    await waitFor(() => {
      expect(screen.getAllByTestId('anomaly-item')).toHaveLength(3);
    });
    expect(screen.getByText(/\+5 more/i)).toBeInTheDocument();
  });
});
