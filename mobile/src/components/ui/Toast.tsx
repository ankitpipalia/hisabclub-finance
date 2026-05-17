import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  Animated,
  Easing,
  Pressable,
  StyleSheet,
  Text,
  View,
  useColorScheme,
} from 'react-native';

type ToastVariant = 'success' | 'error' | 'info' | 'warning';

type Toast = {
  id: string;
  message: string;
  variant: ToastVariant;
  durationMs: number;
};

type ToastContextValue = {
  show: (
    message: string,
    opts?: { variant?: ToastVariant; durationMs?: number },
  ) => string;
  dismiss: (id: string) => void;
  success: (msg: string, durationMs?: number) => string;
  error: (msg: string, durationMs?: number) => string;
  info: (msg: string, durationMs?: number) => string;
  warning: (msg: string, durationMs?: number) => string;
};

const ToastContext = createContext<ToastContextValue | null>(null);

let counter = 0;

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
      const id = `mtoast-${++counter}`;
      const toast: Toast = {
        id,
        message,
        variant: opts.variant ?? 'info',
        durationMs:
          opts.durationMs ?? (opts.variant === 'error' ? 5000 : 3000),
      };
      setToasts((prev) => [...prev, toast]);
      const timer = setTimeout(() => dismiss(id), toast.durationMs);
      // Best-effort cleanup; React Native doesn't unmount timers on app close
      // but the in-process state will be discarded anyway.
      return id;
      void timer;
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      show,
      dismiss,
      success: (msg, durationMs) => show(msg, { variant: 'success', durationMs }),
      error: (msg, durationMs) => show(msg, { variant: 'error', durationMs }),
      info: (msg, durationMs) => show(msg, { variant: 'info', durationMs }),
      warning: (msg, durationMs) => show(msg, { variant: 'warning', durationMs }),
    }),
    [show, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  return ctx;
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
    <View pointerEvents="box-none" style={styles.viewport} accessibilityLiveRegion="polite">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </View>
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  const slide = useRef(new Animated.Value(40)).current;
  const opacity = useRef(new Animated.Value(0)).current;
  const scheme = useColorScheme();

  useEffect(() => {
    Animated.parallel([
      Animated.timing(slide, {
        toValue: 0,
        duration: 200,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.timing(opacity, {
        toValue: 1,
        duration: 180,
        useNativeDriver: true,
      }),
    ]).start();
  }, [slide, opacity]);

  const bg = scheme === 'dark' ? '#1F1B16' : '#FFFFFF';
  const fg = scheme === 'dark' ? '#FFFFFF' : '#1F1B16';
  const accentByVariant: Record<ToastVariant, string> = {
    success: '#22C55E',
    error: '#EF4444',
    warning: '#F59E0B',
    info: '#3B82F6',
  };
  return (
    <Animated.View
      style={[
        styles.toast,
        {
          backgroundColor: bg,
          transform: [{ translateY: slide }],
          opacity,
          borderLeftColor: accentByVariant[toast.variant],
        },
      ]}
      testID={`toast-${toast.variant}`}
      accessibilityRole={toast.variant === 'error' ? 'alert' : 'text'}
    >
      <Text style={[styles.message, { color: fg }]} numberOfLines={3}>
        {toast.message}
      </Text>
      <Pressable
        onPress={() => onDismiss(toast.id)}
        hitSlop={10}
        accessibilityRole="button"
        accessibilityLabel="Dismiss"
      >
        <Text style={[styles.close, { color: fg }]}>×</Text>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  viewport: {
    position: 'absolute',
    top: 56,
    left: 16,
    right: 16,
    zIndex: 1000,
  },
  toast: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 8,
    borderLeftWidth: 3,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  message: {
    flex: 1,
    fontSize: 14,
    lineHeight: 19,
    marginRight: 12,
  },
  close: {
    fontSize: 18,
    paddingHorizontal: 4,
  },
});
