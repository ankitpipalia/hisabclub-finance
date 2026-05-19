import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import RegimeComparator from './RegimeComparator';
import { ToastProvider } from '../ui/Toast';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    api: {
      compareTaxRegime: vi.fn(),
    },
  };
});

import { api } from '../../api/client';

function renderWithToast(node: React.ReactNode) {
  return render(<ToastProvider>{node}</ToastProvider>);
}

describe('RegimeComparator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders both regimes after a successful compare', async () => {
    const mocked = vi.mocked(api.compareTaxRegime);
    mocked.mockResolvedValueOnce({
      fy: 'FY24-25',
      old: {
        regime: 'old',
        fy: 'FY24-25',
        gross_total_income: '1500000',
        standard_deduction: '50000',
        section_24b_deduction: '0',
        chapter_via_deduction: '150000',
        taxable_income: '1300000',
        tax_on_slabs: '197500',
        tax_on_special_rate_income: '0',
        base_tax: '197500',
        rebate_87a: '0',
        tax_after_rebate: '197500',
        surcharge: '0',
        cess: '7900',
        total_tax: '205400',
        notes: [],
      },
      new: {
        regime: 'new',
        fy: 'FY24-25',
        gross_total_income: '1500000',
        standard_deduction: '75000',
        section_24b_deduction: '0',
        chapter_via_deduction: '0',
        taxable_income: '1425000',
        tax_on_slabs: '125000',
        tax_on_special_rate_income: '0',
        base_tax: '125000',
        rebate_87a: '0',
        tax_after_rebate: '125000',
        surcharge: '0',
        cess: '5000',
        total_tax: '130000',
        notes: ['New regime: 80C/80D etc. NOT deductible per Sec 115BAC(2).'],
      },
      recommendation: 'new',
      delta: '75400',
      sources: ['Finance (No. 2) Act 2024'],
    });

    renderWithToast(<RegimeComparator fy="FY24-25" />);

    await userEvent.click(screen.getByRole('button', { name: /compare regimes/i }));

    await waitFor(() => {
      expect(screen.getByTestId('regime-old')).toBeInTheDocument();
      expect(screen.getByTestId('regime-new')).toBeInTheDocument();
    });

    expect(mocked).toHaveBeenCalledOnce();
    expect(mocked.mock.calls[0][0]).toBe('FY24-25');
    expect(screen.getByText(/Choose the/)).toBeInTheDocument();
    // The recommendation banner is the <strong> containing "new regime".
    const banners = screen.getAllByText(/new regime/);
    expect(banners.length).toBeGreaterThanOrEqual(1);
  });

  it('shows an error toast when the API rejects', async () => {
    const mocked = vi.mocked(api.compareTaxRegime);
    mocked.mockRejectedValueOnce(new Error('Network down'));

    renderWithToast(<RegimeComparator fy="FY24-25" />);

    await userEvent.click(screen.getByRole('button', { name: /compare regimes/i }));

    await waitFor(() => {
      expect(screen.getByText('Network down')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('regime-old')).not.toBeInTheDocument();
  });
});
