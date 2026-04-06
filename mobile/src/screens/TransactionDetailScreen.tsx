import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Alert,
} from 'react-native';
import { TextInput, Button, Divider, ActivityIndicator, Chip } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { RouteProp } from '@react-navigation/native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import * as api from '../api/client';
import type { Category, TransactionDetail, TransactionSplitPart } from '../api/types';
import type { RootStackParamList } from '../navigation/types';
import AmountText from '../components/AmountText';
import { formatDate } from '../utils/formatters';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';

type DetailRoute = RouteProp<RootStackParamList, 'TransactionDetail'>;

type SplitDraft = {
  amount: string;
  merchant_raw: string;
  category_id: string;
  transaction_nature: string;
  notes: string;
  tagsText: string;
};

function buildDefaultSplit(detail: TransactionDetail): SplitDraft[] {
  const totalPaise = Math.round(detail.transaction.amount * 100);
  const firstPaise = Math.floor(totalPaise / 2);
  const secondPaise = totalPaise - firstPaise;
  const nature = detail.transaction.transaction_nature || 'expense';
  return [
    {
      amount: (firstPaise / 100).toFixed(2),
      merchant_raw: detail.transaction.merchant_raw,
      category_id: detail.transaction.category_id || '',
      transaction_nature: nature,
      notes: '',
      tagsText: '',
    },
    {
      amount: (secondPaise / 100).toFixed(2),
      merchant_raw: detail.transaction.merchant_raw,
      category_id: detail.transaction.category_id || '',
      transaction_nature: nature,
      notes: '',
      tagsText: '',
    },
  ];
}

export default function TransactionDetailScreen() {
  const route = useRoute<DetailRoute>();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { id } = route.params;
  const queryClient = useQueryClient();
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);

  const [categoryId, setCategoryId] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [showCategoryPicker, setShowCategoryPicker] = useState(false);
  const [transactionNature, setTransactionNature] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [isExcluded, setIsExcluded] = useState(false);
  const [splitDrafts, setSplitDrafts] = useState<SplitDraft[]>([]);
  const [splitting, setSplitting] = useState(false);

  const detailQuery = useQuery({
    queryKey: ['transaction-detail', id],
    queryFn: () => api.getTransactionDetail(id),
  });

  const categoriesQuery = useQuery({
    queryKey: ['categories'],
    queryFn: () => api.getCategories(),
  });

  const detail = detailQuery.data ?? null;
  const transaction = detail?.transaction ?? null;
  const categories: Category[] = categoriesQuery.data ?? [];

  useEffect(() => {
    if (!detail) return;
    setCategoryId(detail.transaction.category_id ?? '');
    setNotes(detail.transaction.notes ?? '');
    setTransactionNature(detail.transaction.transaction_nature ?? '');
    setTagsText((detail.transaction.tags ?? []).join(', '));
    setIsExcluded(Boolean(detail.transaction.is_excluded));
    setSplitDrafts(buildDefaultSplit(detail));
  }, [detail]);

  const handleSave = async () => {
    if (!transaction) return;

    setSaving(true);
    try {
      await api.updateTransaction(transaction.id, {
        category_id: categoryId || null,
        transaction_nature: transactionNature || null,
        notes: notes.trim() || null,
        tags: tagsText
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
        is_excluded: isExcluded,
      });
      await queryClient.invalidateQueries({ queryKey: ['transactions'] });
      await queryClient.invalidateQueries({ queryKey: ['transaction-detail', id] });
      Alert.alert('Saved', 'Transaction updated successfully');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to update transaction');
    } finally {
      setSaving(false);
    }
  };

  const updateSplitDraft = (index: number, patch: Partial<SplitDraft>) => {
    setSplitDrafts((current) => current.map((item, idx) => (idx === index ? { ...item, ...patch } : item)));
  };

  const addSplitPart = () => {
    if (!transaction) return;
    setSplitDrafts((current) => [
      ...current,
      {
        amount: '0.00',
        merchant_raw: transaction.merchant_raw,
        category_id: categoryId,
        transaction_nature: transaction.transaction_nature || 'expense',
        notes: '',
        tagsText: '',
      },
    ]);
  };

  const removeSplitPart = (index: number) => {
    setSplitDrafts((current) => current.filter((_, idx) => idx !== index));
  };

  const handleSplit = async () => {
    if (!transaction) return;
    if (splitDrafts.length < 2) {
      Alert.alert('Split requires 2 parts', 'Add at least two split parts.');
      return;
    }
    const total = splitDrafts.reduce((sum, item) => sum + Math.round(Number(item.amount || 0) * 100), 0);
    if (total !== Math.round(transaction.amount * 100)) {
      Alert.alert('Split total mismatch', 'Split amounts must sum to the original transaction amount.');
      return;
    }

    setSplitting(true);
    try {
      const payload: { parts: TransactionSplitPart[]; exclude_original: boolean } = {
        exclude_original: true,
        parts: splitDrafts.map((item) => ({
          amount: Number(item.amount),
          merchant_raw: item.merchant_raw,
          category_id: item.category_id || null,
          transaction_nature: item.transaction_nature || null,
          notes: item.notes || null,
          tags: item.tagsText
            .split(',')
            .map((tag) => tag.trim())
            .filter(Boolean),
        })),
      };
      await api.splitTransaction(transaction.id, payload);
      await queryClient.invalidateQueries({ queryKey: ['transactions'] });
      await queryClient.invalidateQueries({ queryKey: ['transaction-detail', id] });
      Alert.alert('Split created', 'Child transactions were created and the original was excluded.');
    } catch (err: any) {
      Alert.alert('Split failed', err.message || 'Failed to split transaction');
    } finally {
      setSplitting(false);
    }
  };

  if (detailQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (!detail || !transaction) {
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
          {transaction.direction === 'credit' ? 'Credit' : 'Debit'} · {transaction.transaction_nature}
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
        <DetailRow label="Posted" value={transaction.posting_date ? formatDate(transaction.posting_date) : '-'} styles={styles} />
        <DetailRow label="Bank" value={transaction.bank_label || transaction.bank_name || '-'} styles={styles} />
        <DetailRow label="Account" value={transaction.account_type || '-'} styles={styles} />
        {transaction.account_masked && (
          <DetailRow label="Account No." value={transaction.account_masked} styles={styles} />
        )}
        <DetailRow label="Category" value={transaction.category_name || 'Uncategorized'} styles={styles} />
        <DetailRow label="Excluded" value={transaction.is_excluded ? 'Yes' : 'No'} styles={styles} />
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
                <Chip
                  selected={categoryId === ''}
                  onPress={() => {
                    setCategoryId('');
                    setShowCategoryPicker(false);
                  }}
                  style={styles.categoryChip}
                >
                  Clear
                </Chip>
                {categories.map((cat) => (
                  <Chip
                    key={cat.id}
                    selected={categoryId === cat.id}
                    onPress={() => {
                      setCategoryId(cat.id);
                      setShowCategoryPicker(false);
                    }}
                    style={styles.categoryChip}
                  >
                    {cat.icon} {cat.name}
                  </Chip>
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
              {categories.find((item) => item.id === categoryId)?.name || transaction.category_name || 'Select category'}
            </Button>
          )}
        </View>

        <Text style={styles.fieldLabel}>Nature</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.categoryChips}>
            {['expense', 'income', 'transfer_internal', 'refund', 'investment', 'tax'].map((item) => (
              <Chip
                key={item}
                selected={transactionNature === item}
                onPress={() => setTransactionNature(item)}
                style={styles.categoryChip}
              >
                {item}
              </Chip>
            ))}
          </View>
        </ScrollView>

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

        <TextInput
          label="Tags"
          value={tagsText}
          onChangeText={setTagsText}
          mode="outlined"
          style={styles.notesInput}
          outlineColor={COLORS.border}
          activeOutlineColor={COLORS.primary}
          placeholder="comma,separated,tags"
        />

        <View style={styles.categoryChips}>
          <Chip selected={!isExcluded} onPress={() => setIsExcluded(false)} style={styles.categoryChip}>
            Included
          </Chip>
          <Chip selected={isExcluded} onPress={() => setIsExcluded(true)} style={styles.categoryChip}>
            Excluded
          </Chip>
        </View>

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

      <Divider style={styles.divider} />

      <View style={styles.editSection}>
        <View style={styles.sectionHeader}>
          <Text style={styles.editTitle}>Split Transaction</Text>
          <Button mode="outlined" onPress={addSplitPart}>Add Part</Button>
        </View>
        {splitDrafts.map((item, index) => (
          <View key={`split-${index}`} style={styles.splitCard}>
            <View style={styles.sectionHeader}>
              <Text style={styles.fieldLabel}>Part {index + 1}</Text>
              {splitDrafts.length > 2 ? (
                <Button mode="text" onPress={() => removeSplitPart(index)}>Remove</Button>
              ) : null}
            </View>
            <TextInput
              label="Amount"
              value={item.amount}
              onChangeText={(amount) => updateSplitDraft(index, { amount })}
              mode="outlined"
              style={styles.notesInput}
            />
            <TextInput
              label="Description"
              value={item.merchant_raw}
              onChangeText={(merchant_raw) => updateSplitDraft(index, { merchant_raw })}
              mode="outlined"
              style={styles.notesInput}
            />
            <TextInput
              label="Notes"
              value={item.notes}
              onChangeText={(nextNotes) => updateSplitDraft(index, { notes: nextNotes })}
              mode="outlined"
              style={styles.notesInput}
            />
            <TextInput
              label="Tags"
              value={item.tagsText}
              onChangeText={(nextTags) => updateSplitDraft(index, { tagsText: nextTags })}
              mode="outlined"
              style={styles.notesInput}
            />
          </View>
        ))}
        <Button
          mode="contained"
          onPress={handleSplit}
          loading={splitting}
          disabled={splitting}
          style={styles.saveButton}
          buttonColor={COLORS.primary}
        >
          Create Split
        </Button>
      </View>

      <Divider style={styles.divider} />

      <View style={styles.detailSection}>
        <Text style={styles.editTitle}>Source Evidence</Text>
        {detail.sources.length === 0 ? (
          <Text style={styles.emptyHint}>No source rows found.</Text>
        ) : (
          detail.sources.map((source) => {
            const statementId = source.statement_id;
            return (
              <View key={source.parsed_txn_id} style={styles.auditBlock}>
                <Text style={styles.auditTitle}>
                  {source.source_type} · {source.extraction_method} · {source.match_method}
                </Text>
                <Text style={styles.auditMeta}>Confidence {source.confidence.toFixed(2)}</Text>
                <Text style={styles.auditText}>{source.description_raw}</Text>
                {statementId ? (
                  <Button
                    mode="text"
                    onPress={() => navigation.navigate('StatementReview', { statementId })}
                    compact
                  >
                    Open statement review
                  </Button>
                ) : null}
              </View>
            );
          })
        )}
      </View>

      <Divider style={styles.divider} />

      <View style={styles.detailSection}>
        <Text style={styles.editTitle}>Override History</Text>
        {detail.overrides.length === 0 ? (
          <Text style={styles.emptyHint}>No overrides recorded.</Text>
        ) : (
          detail.overrides.map((item) => (
            <View key={item.id} style={styles.auditBlock}>
              <Text style={styles.auditTitle}>{item.field_name}</Text>
              <Text style={styles.auditMeta}>{formatDate(item.created_at)}</Text>
              <Text style={styles.auditText}>
                {item.old_value ?? 'null'} → {item.new_value}
              </Text>
            </View>
          ))
        )}
      </View>

      {(detail.split_parent || detail.split_children.length > 0) && (
        <>
          <Divider style={styles.divider} />
          <View style={styles.detailSection}>
            <Text style={styles.editTitle}>Split Lineage</Text>
            {detail.split_parent ? (
              <View style={styles.auditBlock}>
                <Text style={styles.auditTitle}>Parent Transaction</Text>
                <Text style={styles.auditText}>
                  {detail.split_parent.merchant_normalized || detail.split_parent.merchant_raw}
                </Text>
              </View>
            ) : null}
            {detail.split_children.map((child) => (
              <View key={child.id} style={styles.auditBlock}>
                <Text style={styles.auditTitle}>Child Transaction</Text>
                <Text style={styles.auditText}>
                  {child.merchant_normalized || child.merchant_raw} · {child.amount}
                </Text>
              </View>
            ))}
          </View>
        </>
      )}
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
    paddingBottom: 32,
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
    gap: 12,
  },
  detailLabel: {
    color: COLORS.textSecondary,
    fontSize: 13,
  },
  detailValue: {
    color: COLORS.text,
    fontSize: 14,
    fontWeight: '500',
    flexShrink: 1,
    textAlign: 'right',
  },
  editSection: {
    backgroundColor: COLORS.surface,
    borderRadius: 8,
    padding: 16,
  },
  editTitle: {
    color: COLORS.text,
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 12,
  },
  fieldLabel: {
    color: COLORS.textSecondary,
    fontSize: 13,
    marginBottom: 8,
    fontWeight: '600',
  },
  categoryContainer: {
    marginBottom: 16,
  },
  categoryScroll: {
    maxHeight: 44,
  },
  categoryChips: {
    flexDirection: 'row',
    gap: 8,
    paddingRight: 16,
    flexWrap: 'wrap',
  },
  categoryChip: {
    borderRadius: 16,
  },
  categoryButton: {
    alignSelf: 'flex-start',
  },
  notesInput: {
    marginBottom: 12,
    backgroundColor: COLORS.surface,
  },
  saveButton: {
    marginTop: 8,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  splitCard: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  emptyHint: {
    color: COLORS.textSecondary,
    fontSize: 13,
  },
  auditBlock: {
    paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.border,
    marginTop: 10,
  },
  auditTitle: {
    color: COLORS.text,
    fontWeight: '700',
    fontSize: 13,
  },
  auditMeta: {
    color: COLORS.textSecondary,
    fontSize: 12,
    marginTop: 2,
  },
  auditText: {
    color: COLORS.text,
    fontSize: 13,
    marginTop: 4,
  },
});
