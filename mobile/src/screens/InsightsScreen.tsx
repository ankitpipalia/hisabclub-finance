import React, { useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
} from 'react-native';
import { Card, ActivityIndicator } from 'react-native-paper';
import { useQuery } from '@tanstack/react-query';
import * as api from '../api/client';
import type { MonthlySummary, RecurringPattern } from '../api/types';
import EmptyState from '../components/EmptyState';
import { formatAmount } from '../utils/formatters';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import AnimatedOrbs from '../components/AnimatedOrbs';
import FadeInView from '../components/FadeInView';

interface SectionItem {
  type: 'hero' | 'summary' | 'categoryHeader' | 'category' | 'recurringHeader' | 'recurring' | 'merchantHeader' | 'merchant';
  key: string;
  data?: any;
}

export default function InsightsScreen() {
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);

  const summaryQuery = useQuery({
    queryKey: ['monthly-summary'],
    queryFn: () => api.getMonthlySummary(),
  });

  const recurringQuery = useQuery({
    queryKey: ['recurring'],
    queryFn: () => api.getRecurring(),
  });

  const isLoading = summaryQuery.isLoading || recurringQuery.isLoading;
  const isRefreshing = summaryQuery.isRefetching || recurringQuery.isRefetching;

  const handleRefresh = () => {
    summaryQuery.refetch();
    recurringQuery.refetch();
  };

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  const summary: MonthlySummary | undefined = summaryQuery.data;
  const recurring: RecurringPattern[] = recurringQuery.data ?? [];

  if (!summary || summary.transaction_count === 0) {
    return (
      <View style={styles.container}>
        <EmptyState
          title="No transactions yet"
          subtitle="Upload a statement to see insights."
        />
      </View>
    );
  }

  const totalExpense = summary.total_expense || 1;
  const categoryEntries = Object.entries(summary.category_breakdown)
    .sort(([, a], [, b]) => b - a);

  const sections: SectionItem[] = [];

  sections.push({ type: 'hero', key: 'hero' });
  // Summary cards
  sections.push({ type: 'summary', key: 'summary' });

  // Category breakdown
  if (categoryEntries.length > 0) {
    sections.push({ type: 'categoryHeader', key: 'cat-header' });
    categoryEntries.forEach(([name, amount]) => {
      sections.push({
        type: 'category',
        key: `cat-${name}`,
        data: { name, amount, percentage: (amount / totalExpense) * 100 },
      });
    });
  }

  // Recurring transactions
  if (recurring.length > 0) {
    sections.push({ type: 'recurringHeader', key: 'rec-header' });
    recurring.forEach((item) => {
      sections.push({
        type: 'recurring',
        key: `rec-${item.id}`,
        data: item,
      });
    });
  }

  // Top merchants
  if (summary.top_merchants && summary.top_merchants.length > 0) {
    sections.push({ type: 'merchantHeader', key: 'merch-header' });
    summary.top_merchants.forEach((m, index) => {
      sections.push({
        type: 'merchant',
        key: `merch-${index}`,
        data: m,
      });
    });
  }

  const renderItem = ({ item }: { item: SectionItem }) => {
    switch (item.type) {
      case 'hero':
        return renderHero();
      case 'summary':
        return renderSummaryCards();
      case 'categoryHeader':
        return <Text style={styles.sectionTitle}>Category Breakdown</Text>;
      case 'category':
        return renderCategoryRow(item.data);
      case 'recurringHeader':
        return <Text style={styles.sectionTitle}>Recurring / Subscriptions</Text>;
      case 'recurring':
        return renderRecurringRow(item.data);
      case 'merchantHeader':
        return <Text style={styles.sectionTitle}>Top Merchants</Text>;
      case 'merchant':
        return renderMerchantRow(item.data);
      default:
        return null;
    }
  };

  const renderSummaryCards = () => (
    <FadeInView delay={70} style={styles.summarySection}>
      <View style={styles.cardsRow}>
        <Card style={[styles.summaryCard, { borderLeftColor: COLORS.credit, borderLeftWidth: 3 }]}>
          <Card.Content>
            <Text style={styles.cardLabel}>Income</Text>
            <Text style={[styles.cardValue, { color: COLORS.credit }]}>
              {formatAmount(summary!.total_income)}
            </Text>
          </Card.Content>
        </Card>

        <Card style={[styles.summaryCard, { borderLeftColor: COLORS.danger, borderLeftWidth: 3 }]}>
          <Card.Content>
            <Text style={styles.cardLabel}>Expense</Text>
            <Text style={[styles.cardValue, { color: COLORS.danger }]}>
              {formatAmount(summary!.total_expense)}
            </Text>
          </Card.Content>
        </Card>
      </View>

      <Card style={[styles.netCard, {
        borderLeftColor: summary!.net_flow >= 0 ? COLORS.credit : COLORS.danger,
        borderLeftWidth: 3,
      }]}>
        <Card.Content>
          <Text style={styles.cardLabel}>Net Flow</Text>
          <Text style={[styles.cardValue, {
            color: summary!.net_flow >= 0 ? COLORS.credit : COLORS.danger,
          }]}>
            {summary!.net_flow >= 0 ? '+' : ''}{formatAmount(Math.abs(summary!.net_flow))}
          </Text>
        </Card.Content>
      </Card>

      {summary!.vs_last_month && (
        <View style={styles.changeRow}>
          <Text style={styles.changeText}>
            vs last month: Income{' '}
            <Text style={{ color: summary!.vs_last_month.income_change >= 0 ? COLORS.credit : COLORS.danger }}>
              {summary!.vs_last_month.income_change >= 0 ? '+' : ''}
              {summary!.vs_last_month.income_change.toFixed(0)}%
            </Text>
            {' | '}Expense{' '}
            <Text style={{ color: summary!.vs_last_month.expense_change <= 0 ? COLORS.credit : COLORS.danger }}>
              {summary!.vs_last_month.expense_change >= 0 ? '+' : ''}
              {summary!.vs_last_month.expense_change.toFixed(0)}%
            </Text>
          </Text>
        </View>
      )}
    </FadeInView>
  );

  const renderHero = () => (
    <FadeInView>
      <View style={styles.hero}>
        <AnimatedOrbs compact />
        <Text style={styles.kicker}>Analytics</Text>
        <Text style={styles.heroTitle}>Insights</Text>
        <Text style={styles.heroSubtitle}>Understand category drift, subscriptions, and merchant concentration.</Text>
      </View>
    </FadeInView>
  );

  const renderCategoryRow = (data: { name: string; amount: number; percentage: number }) => (
    <View style={styles.categoryRow}>
      <View style={styles.categoryInfo}>
        <Text style={styles.categoryName}>{data.name}</Text>
        <Text style={styles.categoryAmount}>{formatAmount(data.amount)}</Text>
      </View>
      <View style={styles.barBackground}>
        <View
          style={[
            styles.barFill,
            {
              width: `${Math.min(data.percentage, 100)}%`,
              backgroundColor: getCategoryColor(data.percentage, COLORS),
            },
          ]}
        />
      </View>
      <Text style={styles.percentText}>{data.percentage.toFixed(1)}%</Text>
    </View>
  );

  const renderRecurringRow = (item: RecurringPattern) => (
    <Card style={styles.listCard}>
      <Card.Content style={styles.recurringContent}>
        <View style={styles.recurringLeft}>
          <Text style={styles.recurringName}>
            {item.merchant_name || item.description_pattern}
          </Text>
          <Text style={styles.recurringMeta}>
            {item.frequency}{item.category_name ? ` \u00B7 ${item.category_name}` : ''}
          </Text>
        </View>
        <View style={styles.recurringRight}>
          <Text style={styles.recurringAmount}>{formatAmount(item.typical_amount)}</Text>
          {item.next_expected && (
            <Text style={styles.recurringNext}>Next: {item.next_expected}</Text>
          )}
        </View>
      </Card.Content>
    </Card>
  );

  const renderMerchantRow = (data: { name: string; amount: number; count: number }) => (
    <View style={styles.merchantRow}>
      <View style={styles.merchantLeft}>
        <Text style={styles.merchantName}>{data.name}</Text>
        <Text style={styles.merchantCount}>{data.count} transactions</Text>
      </View>
      <Text style={styles.merchantAmount}>{formatAmount(data.amount)}</Text>
    </View>
  );

  return (
    <FlatList
      style={styles.container}
      data={sections}
      keyExtractor={(item) => item.key}
      renderItem={renderItem}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={handleRefresh} />
      }
      contentContainerStyle={styles.listContent}
    />
  );
}

function getCategoryColor(percentage: number, colors: AppThemeColors): string {
  if (percentage > 40) return colors.danger;
  if (percentage > 20) return colors.warning;
  return colors.primary;
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
    paddingBottom: 24,
  },
  hero: {
    marginHorizontal: 16,
    marginTop: 16,
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
  summarySection: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  cardsRow: {
    flexDirection: 'row',
    gap: 12,
  },
  summaryCard: {
    flex: 1,
    backgroundColor: COLORS.surface,
  },
  netCard: {
    marginTop: 12,
    backgroundColor: COLORS.surface,
  },
  cardLabel: {
    fontSize: 12,
    color: COLORS.textSecondary,
    fontWeight: '500',
    textTransform: 'uppercase',
  },
  cardValue: {
    fontSize: 20,
    fontWeight: '700',
    marginTop: 4,
  },
  changeRow: {
    marginTop: 8,
    paddingHorizontal: 4,
  },
  changeText: {
    fontSize: 12,
    color: COLORS.textSecondary,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.text,
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1.1,
  },
  categoryRow: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: COLORS.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.border,
  },
  categoryInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  categoryName: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  categoryAmount: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  barBackground: {
    height: 6,
    backgroundColor: COLORS.border,
    borderRadius: 0,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 0,
  },
  percentText: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginTop: 2,
    textAlign: 'right',
  },
  listCard: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: COLORS.surface,
  },
  recurringContent: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  recurringLeft: {
    flex: 1,
    marginRight: 12,
  },
  recurringName: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  recurringMeta: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  recurringRight: {
    alignItems: 'flex-end',
  },
  recurringAmount: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  recurringNext: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  merchantRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.border,
  },
  merchantLeft: {
    flex: 1,
    marginRight: 12,
  },
  merchantName: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  merchantCount: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  merchantAmount: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
});
