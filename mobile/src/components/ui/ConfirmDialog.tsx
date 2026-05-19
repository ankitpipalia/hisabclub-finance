import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useAppTheme } from '../../theme/AppThemeProvider';

type Variant = 'default' | 'destructive';

type Props = {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: Variant;
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * Mobile counterpart of the web `ConfirmDialog`. Renders a modal-overlay
 * confirmation prompt using React Native's `Modal` primitive (no external
 * dependency, no Reanimated). Replaces `Alert.alert(..., [..., {...}])`
 * multi-button confirmation patterns.
 *
 * Migration recipe:
 *   const [pendingId, setPendingId] = useState<string | null>(null);
 *   <ConfirmDialog
 *     open={pendingId !== null}
 *     title="Delete this row?"
 *     description="The row will be removed permanently."
 *     variant="destructive"
 *     onConfirm={async () => { await api.delete(pendingId!); setPendingId(null); }}
 *     onCancel={() => setPendingId(null)}
 *   />
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
  const { colors } = useAppTheme();
  const styles = React.useMemo(() => createStyles(colors), [colors]);

  return (
    <Modal
      animationType="fade"
      transparent
      visible={open}
      onRequestClose={onCancel}
      statusBarTranslucent
    >
      <Pressable
        style={styles.backdrop}
        accessible
        accessibilityLabel="Close dialog"
        onPress={onCancel}
        testID="confirm-dialog-backdrop"
      >
        {/* Inner Pressable swallows backdrop dismiss when tapping the card. */}
        <Pressable
          style={styles.card}
          onPress={() => undefined}
          accessibilityRole="alert"
          accessibilityLabel={title}
          testID="confirm-dialog"
        >
          <Text style={styles.title}>{title}</Text>
          {description ? <Text style={styles.description}>{description}</Text> : null}
          <View style={styles.actions}>
            <Pressable
              style={[styles.button, styles.cancelButton]}
              onPress={onCancel}
              accessibilityRole="button"
              testID="confirm-dialog-cancel"
            >
              <Text style={[styles.buttonText, styles.cancelText]}>{cancelLabel}</Text>
            </Pressable>
            <Pressable
              style={[
                styles.button,
                variant === 'destructive' ? styles.destructiveButton : styles.confirmButton,
              ]}
              onPress={onConfirm}
              accessibilityRole="button"
              testID="confirm-dialog-confirm"
            >
              <Text style={[styles.buttonText, styles.confirmText]}>{confirmLabel}</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function createStyles(colors: ReturnType<typeof useAppTheme>['colors']) {
  return StyleSheet.create({
    backdrop: {
      flex: 1,
      backgroundColor: 'rgba(0, 0, 0, 0.55)',
      justifyContent: 'center',
      alignItems: 'center',
      padding: 24,
    },
    card: {
      width: '100%',
      maxWidth: 420,
      backgroundColor: colors.surface,
      borderRadius: 14,
      padding: 20,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border,
    },
    title: {
      fontSize: 18,
      fontWeight: '600',
      color: colors.text,
      marginBottom: 8,
    },
    description: {
      fontSize: 14,
      color: colors.textSecondary,
      lineHeight: 20,
      marginBottom: 18,
    },
    actions: {
      flexDirection: 'row',
      justifyContent: 'flex-end',
      gap: 10,
    },
    button: {
      paddingHorizontal: 16,
      paddingVertical: 10,
      borderRadius: 10,
      minWidth: 96,
      alignItems: 'center',
    },
    cancelButton: {
      backgroundColor: 'transparent',
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border,
    },
    confirmButton: {
      backgroundColor: colors.primary,
    },
    destructiveButton: {
      backgroundColor: colors.danger,
    },
    buttonText: {
      fontSize: 14,
      fontWeight: '600',
    },
    cancelText: {
      color: colors.text,
    },
    confirmText: {
      color: '#fff',
    },
  });
}
