import React, { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { ActivityIndicator, Button, Card, Chip } from 'react-native-paper';
import { useQuery } from '@tanstack/react-query';

import * as api from '../api/client';
import type { SubscriptionItem } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import { formatAmount, formatDate } from '../utils/formatters';

export default function SubscriptionsScreen() {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const subscriptionsQuery = useQuery({
    queryKey: ['subscriptions'],
    queryFn: api.getSubscriptions,
  });

  if (subscriptionsQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  if (subscriptionsQuery.isError || !subscriptionsQuery.data) {
    return (
      <View style={styles.centered}>
        <Text style={styles.emptyText}>Could not load subscriptions.</Text>
        <Button mode="contained" onPress={() => subscriptionsQuery.refetch()}>
          Retry
        </Button>
      </View>
    );
  }

  const overview = subscriptionsQuery.data;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.kicker}>Recurring Spend</Text>
      <Text style={styles.title}>Subscriptions</Text>
      <Text style={styles.subtitle}>
        Recurring expense patterns computed from canonical transactions.
      </Text>

      <View style={styles.statsGrid}>
        <StatCard label="Active" value={String(overview.summary.active_count)} colors={colors} />
        <StatCard label="Monthly" value={formatAmount(overview.summary.total_monthly_estimate)} colors={colors} />
        <StatCard label="Annual" value={formatAmount(overview.summary.total_annual_estimate)} colors={colors} />
        <StatCard label="Overdue" value={String(overview.summary.overdue_count)} colors={colors} />
      </View>

      <Card style={styles.card}>
        <Card.Content>
          <Text style={styles.sectionTitle}>Detected Recurring Charges</Text>
          {overview.items.length ? (
            overview.items.map((item) => <SubscriptionRow key={item.id} item={item} colors={colors} />)
          ) : (
            <Text style={styles.emptyText}>No recurring charges detected yet.</Text>
          )}
        </Card.Content>
      </Card>
    </ScrollView>
  );
}

function StatCard({ label, value, colors }: { label: string; value: string; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <Card style={styles.statCard}>
      <Card.Content>
        <Text style={styles.statLabel}>{label}</Text>
        <Text style={styles.statValue}>{value}</Text>
      </Card.Content>
    </Card>
  );
}

function SubscriptionRow({ item, colors }: { item: SubscriptionItem; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <View style={styles.row}>
      <View style={styles.rowMeta}>
        <Text style={styles.rowTitle}>{item.merchant_name}</Text>
        <Text style={styles.rowHint}>
          {item.category_name ? `${item.category_name} · ` : ''}
          {item.frequency} · next {formatDate(item.next_expected)}
        </Text>
        <Text style={styles.rowHint}>
          Typical {formatAmount(item.typical_amount)} · Annual {formatAmount(item.annual_cost_estimate)}
        </Text>
      </View>
      <View style={styles.rowActions}>
        <Chip compact style={[styles.inlineChip, statusChipStyle(item.status, colors)]} textStyle={styles.chipText}>
          {item.status}
        </Chip>
        <Text style={styles.rowAmount}>{formatAmount(item.monthly_cost_equivalent)}</Text>
      </View>
    </View>
  );
}

function statusChipStyle(status: string, colors: AppThemeColors) {
  if (status === 'overdue') return { backgroundColor: colors.surface, borderColor: colors.danger, borderWidth: 1 };
  if (status === 'upcoming') return { backgroundColor: colors.surface, borderColor: colors.warning, borderWidth: 1 };
  if (status === 'scheduled') return { backgroundColor: colors.surface, borderColor: colors.success, borderWidth: 1 };
  return { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1 };
}

const createStyles = (colors: AppThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: 16, gap: 12 },
    centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background, padding: 24 },
    kicker: { color: colors.primary, textTransform: 'uppercase', fontWeight: '700', letterSpacing: 1 },
    title: { fontSize: 28, fontWeight: '800', color: colors.text },
    subtitle: { color: colors.textSecondary, marginTop: 6, marginBottom: 8 },
    statsGrid: { gap: 12 },
    statCard: { backgroundColor: colors.surface },
    statLabel: { color: colors.textSecondary, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.8 },
    statValue: { color: colors.text, fontWeight: '800', fontSize: 24, marginTop: 6 },
    card: { backgroundColor: colors.surface },
    sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 10 },
    row: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, marginTop: 8 },
    rowMeta: { flex: 1 },
    rowTitle: { fontWeight: '700', color: colors.text },
    rowHint: { color: colors.textSecondary, marginTop: 4 },
    rowActions: { alignItems: 'flex-end', justifyContent: 'center', gap: 8 },
    rowAmount: { fontWeight: '700', color: colors.primary },
    inlineChip: { alignSelf: 'flex-end' },
    chipText: { textTransform: 'capitalize' },
    emptyText: { color: colors.textSecondary },
  });
