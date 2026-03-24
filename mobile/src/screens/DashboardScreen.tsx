import React, { useEffect, useMemo, useRef } from 'react';
import {
  Animated,
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { Card, ActivityIndicator, Button } from 'react-native-paper';
import { useQuery } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as api from '../api/client';
import type { Transaction, Bill } from '../api/types';
import type { RootStackParamList } from '../navigation/types';
import TransactionRow from '../components/TransactionRow';
import EmptyState from '../components/EmptyState';
import { formatAmount, formatDate } from '../utils/formatters';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import AnimatedOrbs from '../components/AnimatedOrbs';
import FadeInView from '../components/FadeInView';

type NavProp = NativeStackNavigationProp<RootStackParamList>;

export default function DashboardScreen() {
  const navigation = useNavigation<NavProp>();
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);
  const headerAnim = useRef(new Animated.Value(0)).current;

  const txnQuery = useQuery({
    queryKey: ['transactions', 'recent'],
    queryFn: () => api.getTransactions({ per_page: 10 }),
  });

  const stmtQuery = useQuery({
    queryKey: ['statements'],
    queryFn: () => api.getStatements(),
  });

  const summaryQuery = useQuery({
    queryKey: ['monthly-summary'],
    queryFn: () => api.getMonthlySummary().catch(() => null),
  });

  const billsQuery = useQuery({
    queryKey: ['bills'],
    queryFn: () => api.getBills().catch(() => [] as Bill[]),
  });

  const transactions = txnQuery.data?.items ?? [];
  const statements = stmtQuery.data?.items ?? [];
  const summary = summaryQuery.data;
  const allBills: Bill[] = Array.isArray(billsQuery.data) ? billsQuery.data : [];
  const upcomingBills = allBills
    .filter((b) => !b.is_paid)
    .sort((a, b) => a.days_until_due - b.days_until_due)
    .slice(0, 3);

  // Use summary data if available, otherwise compute from recent transactions
  const expenses = summary?.total_expense ??
    transactions.filter((t) => t.direction === 'debit').reduce((sum, t) => sum + t.amount, 0);
  const credits = summary?.total_income ??
    transactions.filter((t) => t.direction === 'credit').reduce((sum, t) => sum + t.amount, 0);

  // Top 5 categories from summary
  const topCategories = summary?.category_breakdown
    ? Object.entries(summary.category_breakdown)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
    : [];
  const maxCategoryAmount = topCategories.length > 0 ? topCategories[0][1] : 1;

  const isLoading = txnQuery.isLoading || stmtQuery.isLoading;
  const isRefreshing = txnQuery.isRefetching || stmtQuery.isRefetching ||
    summaryQuery.isRefetching || billsQuery.isRefetching;

  const handleRefresh = () => {
    txnQuery.refetch();
    stmtQuery.refetch();
    summaryQuery.refetch();
    billsQuery.refetch();
  };

  const handleTransactionPress = (transaction: Transaction) => {
    navigation.navigate('TransactionDetail', { id: transaction.id });
  };

  const getBillBadgeColor = (bill: Bill): string => {
    if (bill.days_until_due < 0) return COLORS.danger;
    if (bill.days_until_due <= 7) return COLORS.warning;
    return COLORS.credit;
  };

  const getBillBadgeText = (bill: Bill): string => {
    if (bill.days_until_due < 0) return `${Math.abs(bill.days_until_due)}d overdue`;
    if (bill.days_until_due === 0) return 'Due today';
    if (bill.days_until_due === 1) return 'Tomorrow';
    return `${bill.days_until_due}d left`;
  };

  const renderHeader = () => (
    <FadeInView>
      <Animated.View
        style={{
          opacity: headerAnim,
          transform: [
            {
              translateY: headerAnim.interpolate({
                inputRange: [0, 1],
                outputRange: [12, 0],
              }),
            },
          ],
        }}
      >
        <View style={styles.hero}>
          <AnimatedOrbs compact />
          <Text style={styles.heroKicker}>Overview</Text>
          <Text style={styles.heroTitle}>Finance Snapshot</Text>
          <Text style={styles.heroSubtitle}>Track spend, dues, and trends from all linked sources.</Text>
        </View>

      {/* Summary Cards */}
      <View style={styles.cardsRow}>
        <Card style={[styles.summaryCard, styles.cardExpense]}>
          <Card.Content>
            <Text style={styles.cardLabel}>Expenses</Text>
            <Text style={[styles.cardValue, { color: COLORS.debit }]}>
              {formatAmount(expenses)}
            </Text>
          </Card.Content>
        </Card>

        <Card style={[styles.summaryCard, styles.cardCredit]}>
          <Card.Content>
            <Text style={styles.cardLabel}>Credits</Text>
            <Text style={[styles.cardValue, { color: COLORS.credit }]}>
              {formatAmount(credits)}
            </Text>
          </Card.Content>
        </Card>
      </View>

      <Card style={styles.stmtCard}>
        <Card.Content>
          <Text style={styles.cardLabel}>Statements</Text>
          <Text style={[styles.cardValue, { color: COLORS.primary }]}>
            {statements.length}
          </Text>
        </Card.Content>
      </Card>

      {/* Quick Actions */}
      <View style={styles.quickActions}>
        <TouchableOpacity
          style={styles.quickActionButton}
          onPress={() => navigation.navigate('Upload')}
        >
          <Text style={styles.quickActionText}>Upload</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.quickActionButton}
          onPress={() => navigation.navigate('Budgets')}
        >
          <Text style={styles.quickActionText}>Budgets</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.quickActionButton}
          onPress={() => navigation.navigate('Bills')}
        >
          <Text style={styles.quickActionText}>Bills</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.quickActionButton}
          onPress={() => navigation.navigate('Statements')}
        >
          <Text style={styles.quickActionText}>Statements</Text>
        </TouchableOpacity>
      </View>

      {/* Upcoming Bills */}
      {upcomingBills.length > 0 && (
        <View>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Upcoming Bills</Text>
            <TouchableOpacity onPress={() => navigation.navigate('Bills')}>
              <Text style={styles.seeAll}>See All</Text>
            </TouchableOpacity>
          </View>
          {upcomingBills.map((bill) => (
            <TouchableOpacity
              key={bill.id}
              style={styles.billRow}
              onPress={() => navigation.navigate('Bills')}
            >
              <View style={styles.billLeft}>
                <Text style={styles.billBank}>{bill.bank_name}</Text>
                <Text style={styles.billDue}>Due {formatDate(bill.due_date)}</Text>
              </View>
              <View style={styles.billRight}>
                <Text style={styles.billAmount}>{formatAmount(bill.total_due)}</Text>
                <View style={[styles.billBadge, { backgroundColor: getBillBadgeColor(bill) }]}>
                  <Text style={styles.billBadgeText}>{getBillBadgeText(bill)}</Text>
                </View>
              </View>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Spending by Category */}
      {topCategories.length > 0 && (
        <View>
          <Text style={styles.sectionTitle}>Top Spending Categories</Text>
          {topCategories.map(([name, amount]) => (
            <View key={name} style={styles.categoryRow}>
              <View style={styles.categoryInfo}>
                <Text style={styles.categoryName}>{name}</Text>
                <Text style={styles.categoryAmount}>{formatAmount(amount)}</Text>
              </View>
              <View style={styles.categoryBarBg}>
                <View
                  style={[
                    styles.categoryBarFill,
                    { width: `${(amount / maxCategoryAmount) * 100}%` },
                  ]}
                />
              </View>
            </View>
          ))}
        </View>
      )}

      <Text style={styles.sectionTitle}>Recent Transactions</Text>
      </Animated.View>
    </FadeInView>
  );

  useEffect(() => {
    Animated.timing(headerAnim, {
      toValue: 1,
      duration: 360,
      useNativeDriver: true,
    }).start();
  }, [headerAnim]);

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (transactions.length === 0) {
    return (
      <View style={styles.container}>
        {renderHeader()}
        <EmptyState
          title="No transactions yet"
          subtitle="Upload your first statement to get started"
        />
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      data={transactions}
      keyExtractor={(item) => item.id}
      ListHeaderComponent={renderHeader}
      renderItem={({ item }) => (
        <TransactionRow
          transaction={item}
          onPress={() => handleTransactionPress(item)}
        />
      )}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={handleRefresh} />
      }
    />
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
  hero: {
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 0,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
    overflow: 'hidden',
  },
  heroKicker: {
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
    marginTop: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  cardsRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 14,
    gap: 12,
  },
  summaryCard: {
    flex: 1,
    backgroundColor: COLORS.surface,
  },
  cardExpense: {},
  cardCredit: {},
  stmtCard: {
    marginHorizontal: 16,
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
  quickActions: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 16,
    gap: 8,
  },
  quickActionButton: {
    flex: 1,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingVertical: 10,
    borderRadius: 0,
    alignItems: 'center',
  },
  quickActionText: {
    color: COLORS.text,
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.9,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 20,
    paddingBottom: 8,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.text,
    paddingHorizontal: 16,
    paddingTop: 20,
    paddingBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  seeAll: {
    fontSize: 13,
    color: COLORS.primary,
    fontWeight: '500',
  },
  billRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: COLORS.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.border,
  },
  billLeft: {},
  billBank: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  billDue: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  billRight: {
    alignItems: 'flex-end',
  },
  billAmount: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  billBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 0,
    marginTop: 4,
  },
  billBadgeText: {
    fontSize: 10,
    fontWeight: '600',
    color: COLORS.surface,
  },
  categoryRow: {
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  categoryInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  categoryName: {
    fontSize: 13,
    color: COLORS.text,
    fontWeight: '500',
  },
  categoryAmount: {
    fontSize: 13,
    color: COLORS.textSecondary,
  },
  categoryBarBg: {
    height: 6,
    backgroundColor: COLORS.border,
    borderRadius: 3,
    overflow: 'hidden',
  },
  categoryBarFill: {
    height: '100%',
    backgroundColor: COLORS.primary,
    borderRadius: 3,
  },
});
