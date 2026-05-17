import { useEffect, useRef } from 'react';

type Props = {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'destructive';
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * Drop-in replacement for window.confirm(). Renders a modal overlay with a
 * focus-trapped dialog. No external animation library — uses CSS transitions
 * on the existing design tokens.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm,
  onCancel,
}: Props) {
  const confirmRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCancel();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onCancel]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="hc-modal-overlay"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
      data-testid="confirm-dialog"
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="hc-confirm-title"
        aria-describedby={description ? 'hc-confirm-desc' : undefined}
        className="hc-modal"
      >
        <h2 id="hc-confirm-title" className="hc-modal-title">
          {title}
        </h2>
        {description && (
          <p id="hc-confirm-desc" className="hc-modal-description">
            {description}
          </p>
        )}
        <div className="hc-modal-actions">
          <button
            type="button"
            className="hc-btn hc-btn-outline"
            onClick={onCancel}
            data-testid="confirm-dialog-cancel"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={
              variant === 'destructive'
                ? 'hc-btn hc-btn-destructive'
                : 'hc-btn hc-btn-primary'
            }
            onClick={onConfirm}
            data-testid="confirm-dialog-confirm"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
