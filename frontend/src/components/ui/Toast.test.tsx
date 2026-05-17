import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ToastProvider, useToast } from './Toast';

function ToastBench({ variant = 'success' as const, durationMs }: { variant?: 'success' | 'error' | 'info'; durationMs?: number }) {
  const toast = useToast();
  return (
    <button onClick={() => toast[variant]('Saved', durationMs)}>fire</button>
  );
}

describe('<Toast />', () => {
  it('renders the dispatched success message with the success testid', async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ToastBench variant="success" />
      </ToastProvider>,
    );
    await user.click(screen.getByRole('button', { name: /fire/i }));
    expect(screen.getByTestId('toast-success')).toHaveTextContent('Saved');
  });

  it('uses role=alert for error variant so screen readers interrupt', async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ToastBench variant="error" />
      </ToastProvider>,
    );
    await user.click(screen.getByRole('button', { name: /fire/i }));
    const toast = await screen.findByTestId('toast-error');
    expect(toast).toHaveAttribute('role', 'alert');
  });

  it('auto-dismisses after the configured duration', async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ToastBench variant="info" durationMs={120} />
      </ToastProvider>,
    );
    await user.click(screen.getByRole('button', { name: /fire/i }));
    expect(screen.getByTestId('toast-info')).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.queryByTestId('toast-info')).not.toBeInTheDocument();
      },
      { timeout: 1000 },
    );
  });

  it('dismisses on close button click', async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ToastBench variant="info" durationMs={60_000} />
      </ToastProvider>,
    );
    await user.click(screen.getByRole('button', { name: /fire/i }));
    await user.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(screen.queryByTestId('toast-info')).not.toBeInTheDocument();
  });

  it('throws if useToast called outside ToastProvider', () => {
    function Orphan() {
      useToast();
      return null;
    }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Orphan />)).toThrow(/ToastProvider/);
    spy.mockRestore();
  });
});
