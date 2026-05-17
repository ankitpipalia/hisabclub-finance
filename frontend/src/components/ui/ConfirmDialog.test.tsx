import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from './ConfirmDialog';

describe('<ConfirmDialog />', () => {
  it('does not render anything when closed', () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        title="Delete account"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders title and description when open', () => {
    render(
      <ConfirmDialog
        open
        title="Delete statement?"
        description="This cannot be undone."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText('Delete statement?')).toBeInTheDocument();
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });

  it('fires onConfirm when confirm button clicked', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        title="OK?"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        confirmLabel="Yes"
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Yes' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('fires onCancel when cancel button clicked', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        title="OK?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
        cancelLabel="No"
      />,
    );
    await user.click(screen.getByRole('button', { name: 'No' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('fires onCancel when overlay backdrop clicked', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        title="OK?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    await user.click(screen.getByTestId('confirm-dialog'));
    expect(onCancel).toHaveBeenCalled();
  });

  it('applies destructive styling when variant=destructive', () => {
    render(
      <ConfirmDialog
        open
        title="Wipe data?"
        variant="destructive"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId('confirm-dialog-confirm')).toHaveClass(
      'hc-btn-destructive',
    );
  });
});
