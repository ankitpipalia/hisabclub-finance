import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

type ToastVariant = 'success' | 'error' | 'info' | 'warning';

type Toast = {
  id: string;
  message: string;
  variant: ToastVariant;
  durationMs: number;
};

type ToastContextValue = {
  toasts: Toast[];
  show: (message: string, opts?: { variant?: ToastVariant; durationMs?: number }) => string;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

let toastCounter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (
      message: string,
      opts: { variant?: ToastVariant; durationMs?: number } = {},
    ): string => {
      const id = `toast-${++toastCounter}`;
      const toast: Toast = {
        id,
        message,
        variant: opts.variant ?? 'info',
        durationMs: opts.durationMs ?? (opts.variant === 'error' ? 6000 : 3500),
      };
      setToasts((prev) => [...prev, toast]);
      window.setTimeout(() => dismiss(id), toast.durationMs);
      return id;
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toasts, show, dismiss }), [toasts, show, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  // Stable helpers so consumers can call toast.success(...) directly.
  return useMemo(
    () => ({
      show: ctx.show,
      dismiss: ctx.dismiss,
      success: (msg: string, durationMs?: number) =>
        ctx.show(msg, { variant: 'success', durationMs }),
      error: (msg: string, durationMs?: number) =>
        ctx.show(msg, { variant: 'error', durationMs }),
      info: (msg: string, durationMs?: number) =>
        ctx.show(msg, { variant: 'info', durationMs }),
      warning: (msg: string, durationMs?: number) =>
        ctx.show(msg, { variant: 'warning', durationMs }),
    }),
    [ctx],
  );
}

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) {
    return null;
  }
  return (
    <div className="hc-toast-viewport" role="region" aria-label="Notifications">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  const [entering, setEntering] = useState(true);
  useEffect(() => {
    const handle = window.setTimeout(() => setEntering(false), 30);
    return () => window.clearTimeout(handle);
  }, []);
  return (
    <div
      className={`hc-toast hc-toast-${toast.variant}${entering ? ' is-entering' : ''}`}
      role={toast.variant === 'error' ? 'alert' : 'status'}
      data-testid={`toast-${toast.variant}`}
    >
      <span className="hc-toast-message">{toast.message}</span>
      <button
        type="button"
        className="hc-toast-close"
        aria-label="Dismiss"
        onClick={() => onDismiss(toast.id)}
      >
        ×
      </button>
    </div>
  );
}
