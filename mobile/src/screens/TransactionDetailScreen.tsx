import React, { useState, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Alert,
} from 'react-native';
import { TextInput, Button, Divider, ActivityIndicator } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { RouteProp } from '@react-navigation/native';
import { useRoute } from '@react-navigation/native';
import * as api from '../api/client';
import type { Category } from '../api/types';
import type { RootStackParamList } from '../navigation/types';
import AmountText from '../components/AmountText';
import { formatDate } from '../utils/formatters';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';

type DetailRoute = RouteProp<RootStackParamList, 'TransactionDetail'>;

export default function TransactionDetailScreen() {
  const route = useRoute<DetailRoute>();
  const { id } = route.params;
  const queryClient = useQueryClient();
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);

  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [showCategoryPicker, setShowCategoryPicker] = useState(false);

  const txnQuery = useQuery({
    queryKey: ['transaction', id],
    queryFn: () => api.getTransactions({ search: id, per_page: 1 }),
  });

  const categoriesQuery = useQuery({
    queryKey: ['categories'],
    queryFn: () => api.getCategories(),
  });

  const transaction = txnQuery.data?.items?.[0] ?? null;
  const categories: Category[] = categoriesQuery.data ?? [];

  useEffect(() => {
    if (transaction) {
      setSelectedCategory(transaction.category_name ?? '');
      setNotes(transaction.notes ?? '');
    }
  }, [transaction]);

  const handleSave = async () => {
    if (!transaction) return;

    setSaving(true);
    try {
      await api.updateTransaction(transaction.id, {
        category_name: selectedCategory || null,
        notes: notes.trim() || null,
      });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['transaction', id] });
      Alert.alert('Saved', 'Transaction updated successfully');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to update transaction');
    } finally {
      setSaving(false);
    }
  };

  if (txnQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (!transaction) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>Transaction not found</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.amountSection}>
        <AmountText
          amount={transaction.amount}
          direction={transaction.direction}
          style={styles.amountText}
        />
        <Text style={styles.direction}>
          {transaction.direction === 'credit' ? 'Credit' : 'Debit'}
        </Text>
      </View>

      <Divider style={styles.divider} />

      <View style={styles.detailSection}>
        <DetailRow
          label="Merchant"
          value={transaction.merchant_normalized || transaction.merchant_raw}
          styles={styles}
        />
        <DetailRow label="Date" value={formatDate(transaction.transaction_date)} styles={styles} />
        <DetailRow label="Bank" value={transaction.bank_label || transaction.bank_name || '-'} styles={styles} />
        <DetailRow label="Account" value={transaction.account_type || '-'} styles={styles} />
        {transaction.account_masked && (
          <DetailRow label="Account No." value={transaction.account_masked} styles={styles} />
        )}
        {transaction.is_recurring && (
          <DetailRow label="Recurring" value="Yes" styles={styles} />
        )}
        {transaction.is_anomalous && (
          <DetailRow label="Anomalous" value="Yes" styles={styles} />
        )}
      </View>

      <Divider style={styles.divider} />

      <View style={styles.editSection}>
        <Text style={styles.editTitle}>Edit</Text>

        <Text style={styles.fieldLabel}>Category</Text>
        <View style={styles.categoryContainer}>
          {showCategoryPicker ? (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.categoryScroll}
            >
              <View style={styles.categoryChips}>
                {categories.map((cat) => (
                  <Button
                    key={cat.id}
                    mode={selectedCategory === cat.name ? 'contained' : 'outlined'}
                    onPress={() => {
                      setSelectedCategory(cat.name);
                      setShowCategoryPicker(false);
                    }}
                    compact
                    style={styles.categoryChip}
                    buttonColor={selectedCategory === cat.name ? COLORS.primary : undefined}
                    textColor={selectedCategory === cat.name ? COLORS.surface : COLORS.text}
                  >
                    {cat.icon} {cat.name}
                  </Button>
                ))}
              </View>
            </ScrollView>
          ) : (
            <Button
              mode="outlined"
              onPress={() => setShowCategoryPicker(true)}
              style={styles.categoryButton}
              textColor={COLORS.text}
            >
              {selectedCategory || 'Select category'}
            </Button>
          )}
        </View>

        <TextInput
          label="Notes"
          value={notes}
          onChangeText={setNotes}
          mode="outlined"
          multiline
          numberOfLines={3}
          style={styles.notesInput}
          outlineColor={COLORS.border}
          activeOutlineColor={COLORS.primary}
        />

        <Button
          mode="contained"
          onPress={handleSave}
          loading={saving}
          disabled={saving}
          style={styles.saveButton}
          buttonColor={COLORS.primary}
        >
          Save Changes
        </Button>
      </View>
    </ScrollView>
  );
}

function DetailRow({
  label,
  value,
  styles,
}: {
  label: string;
  value: string;
  styles: ReturnType<typeof createStyles>;
}) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  content: {
    padding: 16,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.background,
  },
  errorText: {
    fontSize: 16,
    color: COLORS.textSecondary,
  },
  amountSection: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  amountText: {
    fontSize: 32,
    fontWeight: '700',
  },
  direction: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginTop: 4,
    textTransform: 'uppercase',
    fontWeight: '500',
  },
  divider: {
    marginVertical: 16,
  },
  detailSection: {
    backgroundColor: COLORS.surface,
    borderRadius: 8,
    padding: 16,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  detailLabel: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },
  detailValue: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
    maxWidth: '60%',
    textAlign: 'right',
  },
  editSection: {
    marginTop: 8,
  },
  editTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 12,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.textSecondary,
    marginBottom: 6,
  },
  categoryContainer: {
    marginBottom: 12,
  },
  categoryScroll: {
    maxHeight: 44,
  },
  categoryChips: {
    flexDirection: 'row',
    gap: 8,
  },
  categoryChip: {
    marginRight: 4,
  },
  categoryButton: {
    borderColor: COLORS.border,
    alignSelf: 'flex-start',
  },
  notesInput: {
    backgroundColor: COLORS.surface,
    marginBottom: 16,
  },
  saveButton: {
    paddingVertical: 4,
  },
});
