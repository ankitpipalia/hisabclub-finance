import React, { useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import AmountText from './AmountText';
import { formatDateShort } from '../utils/formatters';
import type { Transaction } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';

interface Props {
  transaction: Transaction;
  onPress?: () => void;
  onLongPress?: () => void;
  selected?: boolean;
  selectionMode?: boolean;
}

export default function TransactionRow({
  transaction,
  onPress,
  onLongPress,
  selected = false,
  selectionMode = false,
}: Props) {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const t = transaction;
  return (
    <TouchableOpacity
      style={[styles.row, selected ? styles.rowSelected : null]}
      onPress={onPress}
      onLongPress={onLongPress}
      activeOpacity={0.7}
    >
      {selectionMode ? (
        <View style={[styles.selector, selected ? styles.selectorActive : null]}>
          {selected ? <Text style={styles.selectorText}>✓</Text> : null}
        </View>
      ) : null}
      <View style={styles.left}>
        <Text style={styles.merchant} numberOfLines={1}>
          {t.merchant_normalized || t.merchant_raw}
        </Text>
        <Text style={styles.meta} numberOfLines={1}>
          {formatDateShort(t.transaction_date)}
          {t.category_name && ` · ${t.category_name}`}
          {(t.bank_label || t.bank_name) && ` · ${t.bank_label || t.bank_name}`}
        </Text>
      </View>
      <AmountText amount={t.amount} direction={t.direction} />
    </TouchableOpacity>
  );
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.border,
  },
  rowSelected: {
    backgroundColor: COLORS.surface,
  },
  selector: {
    width: 22,
    height: 22,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  selectorActive: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  selectorText: {
    color: COLORS.surface,
    fontSize: 12,
    fontWeight: '700',
  },
  left: { flex: 1, marginRight: 12 },
  merchant: { fontSize: 14, fontWeight: '500', color: COLORS.text },
  meta: { fontSize: 12, color: COLORS.textSecondary, marginTop: 2 },
});
