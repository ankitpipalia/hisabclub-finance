import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  Alert,
} from 'react-native';
import {
  Card,
  Button,
  SegmentedButtons,
  ActivityIndicator,
} from 'react-native-paper';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import type { Bill } from '../api/types';
import EmptyState from '../components/EmptyState';
import { formatAmount, formatDate } from '../utils/formatters';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import FadeInView from '../components/FadeInView';
import AnimatedOrbs from '../components/AnimatedOrbs';

type FilterTab = 'upcoming' | 'paid';

export default function BillsScreen() {
  const queryClient = useQueryClient();
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);
  const [activeTab, setActiveTab] = useState<FilterTab>('upcoming');

  const billsQuery = useQuery({
    queryKey: ['bills'],
    queryFn: () => api.getBills(),
  });

  const markPaidMutation = useMutation({
    mutationFn: ({ id, amount }: { id: string; amount: number }) =>
      api.markBillPaid(id, {
        paid_amount: amount,
        paid_date: new Date().toISOString().split('T')[0],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bills'] });
    },
    onError: (error: Error) => {
      Alert.alert('Error', error.message || 'Failed to mark bill as paid');
    },
  });

  const allBills: Bill[] = billsQuery.data ?? [];
  const filteredBills = allBills.filter((b) =>
    activeTab === 'upcoming' ? !b.is_paid : b.is_paid
  );

  const isLoading = billsQuery.isLoading;
  const isRefreshing = billsQuery.isRefetching;

  const getDueBadgeColor = (bill: Bill): string => {
    if (bill.is_paid) return COLORS.credit;
    if (bill.days_until_due < 0) return COLORS.danger;
    if (bill.days_until_due <= 7) return COLORS.warning;
    return COLORS.credit;
  };

  const getDueBadgeText = (bill: Bill): string => {
    if (bill.is_paid) return 'Paid';
    if (bill.days_until_due < 0) return `${Math.abs(bill.days_until_due)}d overdue`;
    if (bill.days_until_due === 0) return 'Due today';
    if (bill.days_until_due === 1) return 'Due tomorrow';
    return `${bill.days_until_due}d left`;
  };

  const handleMarkPaid = (bill: Bill) => {
    Alert.alert(
      'Mark as Paid',
      `Mark ${bill.bank_name} bill of ${formatAmount(bill.total_due)} as paid?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Mark Paid',
          onPress: () =>
            markPaidMutation.mutate({ id: bill.id, amount: bill.total_due }),
        },
      ],
    );
  };

  const renderBillItem = ({ item }: { item: Bill }) => {
    const badgeColor = getDueBadgeColor(item);
    const badgeText = getDueBadgeText(item);

    return (
      <Card style={styles.billCard}>
        <Card.Content>
          <View style={styles.billHeader}>
            <View style={styles.billBankInfo}>
              <Text style={styles.bankName}>{item.bank_name}</Text>
              {item.account_masked && (
                <Text style={styles.accountText}>{item.account_masked}</Text>
              )}
            </View>
            <View style={[styles.dueBadge, { backgroundColor: badgeColor }]}>
              <Text style={styles.dueBadgeText}>{badgeText}</Text>
            </View>
          </View>

          <View style={styles.billDetails}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Due Date</Text>
              <Text style={styles.detailValue}>{formatDate(item.due_date)}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Total Due</Text>
              <Text style={[styles.detailValue, styles.totalDue]}>
                {formatAmount(item.total_due)}
              </Text>
            </View>
            {item.min_due != null && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Min Due</Text>
                <Text style={styles.detailValue}>{formatAmount(item.min_due)}</Text>
              </View>
            )}
            {item.is_paid && item.paid_amount != null && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Paid</Text>
                <Text style={[styles.detailValue, { color: COLORS.credit }]}>
                  {formatAmount(item.paid_amount)}
                  {item.paid_date ? ` on ${formatDate(item.paid_date)}` : ''}
                </Text>
              </View>
            )}
          </View>

          {!item.is_paid && (
            <Button
              mode="contained"
              onPress={() => handleMarkPaid(item)}
              loading={markPaidMutation.isPending}
              style={styles.markPaidButton}
              buttonColor={COLORS.primary}
              compact
            >
              Mark Paid
            </Button>
          )}
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
          <Text style={styles.kicker}>Repayments</Text>
          <Text style={styles.heroTitle}>Bills</Text>
          <Text style={styles.heroSubtitle}>Track due risk and mark repayments with clear audit history.</Text>
        </View>
      </FadeInView>

      <FadeInView delay={80}>
        <View style={styles.filterContainer}>
          <SegmentedButtons
            value={activeTab}
            onValueChange={(val) => setActiveTab(val as FilterTab)}
            buttons={[
              { value: 'upcoming', label: 'Upcoming' },
              { value: 'paid', label: 'Paid' },
            ]}
            style={styles.segmented}
          />
        </View>
      </FadeInView>

      {filteredBills.length === 0 ? (
        <EmptyState
          title={activeTab === 'upcoming' ? 'No upcoming bills' : 'No paid bills'}
          subtitle={activeTab === 'upcoming'
            ? 'All caught up! No pending bills.'
            : 'No bills have been marked as paid yet.'
          }
        />
      ) : (
        <FlatList
          data={filteredBills}
          keyExtractor={(item) => item.id}
          renderItem={renderBillItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={isRefreshing} onRefresh={() => billsQuery.refetch()} />
          }
        />
      )}
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
  filterContainer: {
    marginTop: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
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
  segmented: {},
  listContent: {
    padding: 16,
    paddingBottom: 24,
  },
  billCard: {
    marginBottom: 12,
    backgroundColor: COLORS.surface,
  },
  billHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  billBankInfo: {},
  bankName: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
  },
  accountText: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  dueBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 0,
  },
  dueBadgeText: {
    fontSize: 11,
    fontWeight: '600',
    color: COLORS.surface,
  },
  billDetails: {
    gap: 6,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  detailLabel: {
    fontSize: 13,
    color: COLORS.textSecondary,
  },
  detailValue: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.text,
  },
  totalDue: {
    fontSize: 15,
    fontWeight: '700',
  },
  markPaidButton: {
    marginTop: 12,
  },
});
