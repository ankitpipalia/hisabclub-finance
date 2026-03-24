import React, { useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
} from 'react-native';
import { Card, Divider, ActivityIndicator } from 'react-native-paper';
import { useQuery } from '@tanstack/react-query';
import type { Statement } from '../api/types';
import * as api from '../api/client';
import EmptyState from '../components/EmptyState';
import { formatDate, formatAmount } from '../utils/formatters';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';

function getStatusColor(status: string, colors: AppThemeColors): string {
  switch (status) {
    case 'completed':
      return colors.success;
    case 'processing':
      return colors.warning;
    case 'failed':
      return colors.danger;
    default:
      return colors.textSecondary;
  }
}

function StatementCard({
  statement,
  colors,
}: {
  statement: Statement;
  colors: AppThemeColors;
}) {
  const styles = useMemo(() => createStyles(colors), [colors]);

  const periodText =
    statement.statement_period_start && statement.statement_period_end
      ? `${formatDate(statement.statement_period_start)} - ${formatDate(statement.statement_period_end)}`
      : 'Period not available';

  return (
    <Card style={styles.card}>
      <Card.Content>
        <View style={styles.cardHeader}>
          <Text style={styles.bankName}>{statement.bank_name}</Text>
          <View
            style={[
              styles.statusBadge,
              { backgroundColor: getStatusColor(statement.parse_status, colors) + '20' },
            ]}
          >
            <Text
              style={[
                styles.statusText,
                { color: getStatusColor(statement.parse_status, colors) },
              ]}
            >
              {statement.parse_status}
            </Text>
          </View>
        </View>

        <Text style={styles.accountType}>{statement.account_type}</Text>
        {statement.account_number_masked && (
          <Text style={styles.accountNumber}>{statement.account_number_masked}</Text>
        )}
        {statement.reprocess_count > 1 && (
          <Text style={styles.reprocessHint}>
            {statement.is_reprocess ? 'Reprocessed run' : 'Original run'} • {statement.reprocess_count} versions
          </Text>
        )}

        <Divider style={styles.cardDivider} />

        <View style={styles.metaRow}>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Period</Text>
            <Text style={styles.metaValue}>{periodText}</Text>
          </View>
        </View>

        <View style={styles.statsRow}>
          {statement.transaction_count != null && (
            <View style={styles.statItem}>
              <Text style={styles.statValue}>{statement.transaction_count}</Text>
              <Text style={styles.statLabel}>Transactions</Text>
            </View>
          )}
          {statement.total_amount_due != null && (
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: colors.danger }]}>
                {formatAmount(statement.total_amount_due)}
              </Text>
              <Text style={styles.statLabel}>Total Due</Text>
            </View>
          )}
          {statement.min_amount_due != null && (
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: colors.warning }]}>
                {formatAmount(statement.min_amount_due)}
              </Text>
              <Text style={styles.statLabel}>Min Due</Text>
            </View>
          )}
        </View>

        {statement.due_date && (
          <Text style={styles.dueDate}>
            Due: {formatDate(statement.due_date)}
          </Text>
        )}
      </Card.Content>
    </Card>
  );
}

export default function StatementsScreen() {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['statements'],
    queryFn: () => api.getStatements(),
  });

  const statements = data?.items ?? [];

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (statements.length === 0) {
    return (
      <EmptyState
        title="No statements yet"
        subtitle="Upload a bank statement PDF to get started"
      />
    );
  }

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={styles.listContent}
      data={statements}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => <StatementCard statement={item} colors={colors} />}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} />
      }
    />
  );
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  listContent: {
    padding: 16,
    gap: 12,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.background,
  },
  card: {
    backgroundColor: COLORS.surface,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  bankName: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  accountType: {
    fontSize: 13,
    color: COLORS.textSecondary,
    marginTop: 2,
    textTransform: 'capitalize',
  },
  accountNumber: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 1,
  },
  reprocessHint: {
    fontSize: 12,
    color: COLORS.primary,
    marginTop: 4,
    fontWeight: '500',
  },
  cardDivider: {
    marginVertical: 12,
  },
  metaRow: {
    marginBottom: 8,
  },
  metaItem: {},
  metaLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    fontWeight: '500',
    textTransform: 'uppercase',
  },
  metaValue: {
    fontSize: 13,
    color: COLORS.text,
    marginTop: 2,
  },
  statsRow: {
    flexDirection: 'row',
    marginTop: 8,
    gap: 24,
  },
  statItem: {
    alignItems: 'flex-start',
  },
  statValue: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
  },
  statLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    marginTop: 1,
  },
  dueDate: {
    fontSize: 12,
    color: COLORS.warning,
    fontWeight: '500',
    marginTop: 8,
  },
});
