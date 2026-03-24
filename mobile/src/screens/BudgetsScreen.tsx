import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  ScrollView,
  StyleSheet,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import {
  Card,
  FAB,
  Portal,
  Dialog,
  Button,
  TextInput,
  Chip,
  ActivityIndicator,
} from 'react-native-paper';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import type { BudgetWithSpent, Category } from '../api/types';
import EmptyState from '../components/EmptyState';
import { formatAmount } from '../utils/formatters';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import FadeInView from '../components/FadeInView';
import AnimatedOrbs from '../components/AnimatedOrbs';

const PERIODS = [
  { label: 'Monthly', value: 'monthly' },
  { label: 'Weekly', value: 'weekly' },
  { label: 'Yearly', value: 'yearly' },
];

export default function BudgetsScreen() {
  const queryClient = useQueryClient();
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);
  const [dialogVisible, setDialogVisible] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [amountText, setAmountText] = useState('');
  const [selectedPeriod, setSelectedPeriod] = useState('monthly');

  const budgetsQuery = useQuery({
    queryKey: ['budgets'],
    queryFn: () => api.getBudgets(),
  });

  const categoriesQuery = useQuery({
    queryKey: ['categories'],
    queryFn: () => api.getCategories(),
  });

  const createMutation = useMutation({
    mutationFn: (data: { category_id?: string; amount_limit: number; period: string }) =>
      api.createBudget(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgets'] });
      resetDialog();
    },
  });

  const budgets: BudgetWithSpent[] = budgetsQuery.data ?? [];
  const categories: Category[] = categoriesQuery.data ?? [];
  const isLoading = budgetsQuery.isLoading;
  const isRefreshing = budgetsQuery.isRefetching;

  const resetDialog = () => {
    setDialogVisible(false);
    setSelectedCategory('');
    setAmountText('');
    setSelectedPeriod('monthly');
  };

  const handleCreate = () => {
    const amount = parseFloat(amountText);
    if (isNaN(amount) || amount <= 0) return;

    createMutation.mutate({
      category_id: selectedCategory || undefined,
      amount_limit: amount,
      period: selectedPeriod,
    });
  };

  const getProgressColor = (percentage: number): string => {
    if (percentage > 90) return COLORS.danger;
    if (percentage > 75) return COLORS.warning;
    return COLORS.credit;
  };

  const renderBudgetItem = ({ item }: { item: BudgetWithSpent }) => {
    const pct = Math.min(item.percentage_used, 100);
    const color = getProgressColor(item.percentage_used);

    return (
      <Card style={styles.budgetCard}>
        <Card.Content>
          <View style={styles.budgetHeader}>
            <Text style={styles.budgetCategory}>
              {item.category_name || 'Overall'}
            </Text>
            <Text style={styles.budgetPeriod}>{item.period}</Text>
          </View>

          <View style={styles.amountsRow}>
            <Text style={styles.spentText}>
              {formatAmount(item.spent_amount)} <Text style={styles.ofText}>of {formatAmount(item.amount_limit)}</Text>
            </Text>
            <Text style={[styles.remainingText, {
              color: item.remaining >= 0 ? COLORS.credit : COLORS.danger,
            }]}>
              {item.remaining >= 0 ? formatAmount(item.remaining) + ' left' : formatAmount(Math.abs(item.remaining)) + ' over'}
            </Text>
          </View>

          <View style={styles.progressBackground}>
            <View
              style={[
                styles.progressFill,
                {
                  width: `${pct}%`,
                  backgroundColor: color,
                },
              ]}
            />
          </View>

          <Text style={[styles.percentLabel, { color }]}>
            {item.percentage_used.toFixed(0)}% used
          </Text>
        </Card.Content>
      </Card>
    );
  };

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FadeInView>
        <View style={styles.hero}>
          <AnimatedOrbs compact />
          <Text style={styles.kicker}>Controls</Text>
          <Text style={styles.heroTitle}>Budgets</Text>
          <Text style={styles.heroSubtitle}>Set category guardrails and monitor drift in real time.</Text>
        </View>
      </FadeInView>

      {budgets.length === 0 ? (
        <EmptyState
          title="No budgets set"
          subtitle="Tap + to create your first budget"
        />
      ) : (
        <FadeInView delay={70} style={styles.listWrap}>
          <FlatList
            data={budgets}
            keyExtractor={(item) => item.id}
            renderItem={renderBudgetItem}
            contentContainerStyle={styles.listContent}
            refreshControl={
              <RefreshControl refreshing={isRefreshing} onRefresh={() => budgetsQuery.refetch()} />
            }
          />
        </FadeInView>
      )}

      <FAB
        icon="plus"
        style={styles.fab}
        onPress={() => setDialogVisible(true)}
        color={COLORS.surface}
        customSize={56}
      />

      <Portal>
        <Dialog visible={dialogVisible} onDismiss={resetDialog}>
          <Dialog.Title>Create Budget</Dialog.Title>
          <Dialog.ScrollArea style={styles.dialogScroll}>
            <ScrollView>
              <Text style={styles.fieldLabel}>Category</Text>
              <View style={styles.chipGroup}>
                <Chip
                  selected={selectedCategory === ''}
                  onPress={() => setSelectedCategory('')}
                  style={styles.chip}
                  selectedColor={COLORS.primary}
                >
                  Overall
                </Chip>
                {categories.map((cat) => (
                  <Chip
                    key={cat.id}
                    selected={selectedCategory === cat.id}
                    onPress={() => setSelectedCategory(cat.id)}
                    style={styles.chip}
                    selectedColor={COLORS.primary}
                  >
                    {cat.name}
                  </Chip>
                ))}
              </View>

              <TextInput
                label="Budget Amount"
                value={amountText}
                onChangeText={setAmountText}
                keyboardType="numeric"
                mode="outlined"
                style={styles.amountInput}
                outlineColor={COLORS.border}
                activeOutlineColor={COLORS.primary}
              />

              <Text style={styles.fieldLabel}>Period</Text>
              <View style={styles.chipGroup}>
                {PERIODS.map((p) => (
                  <Chip
                    key={p.value}
                    selected={selectedPeriod === p.value}
                    onPress={() => setSelectedPeriod(p.value)}
                    style={styles.chip}
                    selectedColor={COLORS.primary}
                  >
                    {p.label}
                  </Chip>
                ))}
              </View>
            </ScrollView>
          </Dialog.ScrollArea>
          <Dialog.Actions>
            <Button onPress={resetDialog} textColor={COLORS.textSecondary}>
              Cancel
            </Button>
            <Button
              onPress={handleCreate}
              loading={createMutation.isPending}
              disabled={createMutation.isPending || !amountText}
              textColor={COLORS.primary}
            >
              Create
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </View>
  );
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.background,
  },
  listContent: {
    padding: 16,
    paddingBottom: 80,
  },
  listWrap: {
    flex: 1,
  },
  hero: {
    margin: 16,
    marginBottom: 0,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
    overflow: 'hidden',
  },
  kicker: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
  },
  heroTitle: {
    fontSize: 28,
    fontWeight: '800',
    color: COLORS.text,
    letterSpacing: -1.1,
  },
  heroSubtitle: {
    fontSize: 12,
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  budgetCard: {
    marginBottom: 12,
    backgroundColor: COLORS.surface,
  },
  budgetHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  budgetCategory: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
  },
  budgetPeriod: {
    fontSize: 11,
    color: COLORS.textSecondary,
    textTransform: 'capitalize',
    backgroundColor: 'transparent',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 0,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  amountsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  spentText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  ofText: {
    fontWeight: '400',
    color: COLORS.textSecondary,
  },
  remainingText: {
    fontSize: 13,
    fontWeight: '500',
  },
  progressBackground: {
    height: 8,
    backgroundColor: COLORS.border,
    borderRadius: 0,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 0,
  },
  percentLabel: {
    fontSize: 11,
    fontWeight: '500',
    marginTop: 4,
    textAlign: 'right',
  },
  fab: {
    position: 'absolute',
    right: 16,
    bottom: 16,
    backgroundColor: COLORS.primary,
  },
  dialogScroll: {
    maxHeight: 400,
    paddingHorizontal: 0,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.textSecondary,
    marginBottom: 8,
    marginTop: 16,
    paddingHorizontal: 24,
  },
  chipGroup: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    paddingHorizontal: 24,
  },
  chip: {
    marginBottom: 2,
  },
  amountInput: {
    marginTop: 16,
    marginHorizontal: 24,
    backgroundColor: COLORS.surface,
  },
});
