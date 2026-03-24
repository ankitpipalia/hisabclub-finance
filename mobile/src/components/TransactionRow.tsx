import React, { useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import AmountText from './AmountText';
import { formatDateShort } from '../utils/formatters';
import type { Transaction } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';

interface Props {
  transaction: Transaction;
  onPress?: () => void;
}

export default function TransactionRow({ transaction, onPress }: Props) {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const t = transaction;
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.7}>
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
  left: { flex: 1, marginRight: 12 },
  merchant: { fontSize: 14, fontWeight: '500', color: COLORS.text },
  meta: { fontSize: 12, color: COLORS.textSecondary, marginTop: 2 },
});
