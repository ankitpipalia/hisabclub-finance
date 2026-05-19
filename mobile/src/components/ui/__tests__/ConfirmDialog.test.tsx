import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { ConfirmDialog } from '../ConfirmDialog';
import { AppThemeProvider } from '../../../theme/AppThemeProvider';

function renderWithTheme(node: React.ReactNode) {
  return render(<AppThemeProvider>{node}</AppThemeProvider>);
}

describe('ConfirmDialog', () => {
  it('does not render the dialog body when open=false', () => {
    const { queryByTestId } = renderWithTheme(
      <ConfirmDialog
        open={false}
        title="Delete row"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );
    // The Modal still renders but its content is hidden; we assert by the
    // inner card being absent when visible=false.
    expect(queryByTestId('confirm-dialog')).toBeNull();
  });

  it('renders title + description + actions when open=true', () => {
    const { getByTestId, getByText } = renderWithTheme(
      <ConfirmDialog
        open
        title="Delete this budget?"
        description="The budget will be removed permanently."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );
    expect(getByText('Delete this budget?')).toBeTruthy();
    expect(getByText('The budget will be removed permanently.')).toBeTruthy();
    expect(getByTestId('confirm-dialog-cancel')).toBeTruthy();
    expect(getByTestId('confirm-dialog-confirm')).toBeTruthy();
  });

  it('calls onCancel when the cancel button is pressed', () => {
    const onCancel = jest.fn();
    const { getByTestId } = renderWithTheme(
      <ConfirmDialog
        open
        title="Confirm"
        onConfirm={jest.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.press(getByTestId('confirm-dialog-cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onConfirm when the confirm button is pressed', () => {
    const onConfirm = jest.fn();
    const { getByTestId } = renderWithTheme(
      <ConfirmDialog
        open
        title="Confirm"
        onConfirm={onConfirm}
        onCancel={jest.fn()}
      />,
    );
    fireEvent.press(getByTestId('confirm-dialog-confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when the backdrop is pressed', () => {
    const onCancel = jest.fn();
    const { getByTestId } = renderWithTheme(
      <ConfirmDialog
        open
        title="Confirm"
        onConfirm={jest.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.press(getByTestId('confirm-dialog-backdrop'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
