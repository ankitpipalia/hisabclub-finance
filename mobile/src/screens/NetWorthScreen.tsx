import React, { useMemo, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { ActivityIndicator, Button, Card, Chip, TextInput } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from '../api/client';
import type { BalanceSnapshot, NetWorthHistoryPoint } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import { formatAmount, formatDate, formatDateShort } from '../utils/formatters';

type ManualFormState = {
  label: string;
  entryKind: 'asset' | 'liability';
  assetType: string;
  balance: string;
  asOfDate: string;
  institutionName: string;
  accountMasked: string;
};

const initialFormState = (): ManualFormState => ({
  label: '',
  entryKind: 'asset',
  assetType: 'cash',
  balance: '',
  asOfDate: new Date().toISOString().slice(0, 10),
  institutionName: '',
  accountMasked: '',
});

export default function NetWorthScreen() {
  const queryClient = useQueryClient();
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const [months, setMonths] = useState(12);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<ManualFormState>(initialFormState);

  const overviewQuery = useQuery({
    queryKey: ['net-worth-overview', months],
    queryFn: () => api.getNetWorthOverview(months),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['net-worth-overview'] });
  };

  const submitManualPosition = async () => {
    if (!form.label.trim() || !form.balance.trim()) {
      Alert.alert('Missing fields', 'Label and balance are required.');
      return;
    }
    setSaving(true);
    try {
      await api.createManualNetWorthSnapshot({
        label: form.label.trim(),
        entry_kind: form.entryKind,
        asset_type: form.assetType.trim() || 'other_asset',
        balance: Number(form.balance),
        as_of_date: form.asOfDate,
        institution_name: form.institutionName.trim() || undefined,
        account_masked: form.accountMasked.trim() || undefined,
      });
      setForm(initialFormState());
      setShowForm(false);
      await refresh();
    } catch (err: any) {
      Alert.alert('Save failed', err?.message || 'Could not save manual position');
    } finally {
      setSaving(false);
    }
  };

  const deleteManualPosition = (snapshot: BalanceSnapshot) => {
    Alert.alert(
      'Delete position?',
      `${snapshot.label} will be removed from manual net worth tracking.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.deleteManualNetWorthSnapshot(snapshot.id);
              await refresh();
            } catch (err: any) {
              Alert.alert('Delete failed', err?.message || 'Could not delete manual position');
            }
          },
        },
      ],
    );
  };

  if (overviewQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  if (overviewQuery.isError || !overviewQuery.data) {
    return (
      <View style={styles.centered}>
        <Text style={styles.emptyText}>Could not load net worth.</Text>
        <Button mode="contained" onPress={() => overviewQuery.refetch()}>
          Retry
        </Button>
      </View>
    );
  }

  const overview = overviewQuery.data;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.kicker}>Balance Sheet</Text>
      <Text style={styles.title}>Net Worth</Text>
      <Text style={styles.subtitle}>
        Latest statement balances plus manual assets and liabilities.
      </Text>

      <View style={styles.rowWrap}>
        {[6, 12, 24, 36].map((value) => (
          <Chip key={value} selected={months === value} onPress={() => setMonths(value)} style={styles.chip}>
            {value}m
          </Chip>
        ))}
      </View>

      <View style={styles.statsGrid}>
        <StatCard label="Net Worth" value={formatAmount(overview.totals.net_worth)} colors={colors} />
        <StatCard label="Assets" value={formatAmount(overview.totals.assets)} colors={colors} />
        <StatCard label="Liabilities" value={formatAmount(overview.totals.liabilities)} colors={colors} />
        <StatCard label="Manual" value={String(overview.totals.manual_positions_count)} colors={colors} />
      </View>

      <Card style={styles.card}>
        <Card.Content>
          <View style={styles.sectionHeader}>
            <View style={styles.sectionTextWrap}>
              <Text style={styles.sectionTitle}>Manual Position</Text>
              <Text style={styles.sectionHint}>Track assets or liabilities not present in parsed statements.</Text>
            </View>
            <Button compact mode={showForm ? 'outlined' : 'contained'} onPress={() => setShowForm((v) => !v)}>
              {showForm ? 'Close' : 'Add'}
            </Button>
          </View>
          {showForm ? (
            <View style={styles.form}>
              <TextInput
                label="Label"
                mode="outlined"
                value={form.label}
                onChangeText={(value) => setForm((current) => ({ ...current, label: value }))}
                style={styles.input}
              />
              <View style={styles.rowWrap}>
                <Chip selected={form.entryKind === 'asset'} onPress={() => setForm((current) => ({ ...current, entryKind: 'asset' }))} style={styles.chip}>
                  Asset
                </Chip>
                <Chip selected={form.entryKind === 'liability'} onPress={() => setForm((current) => ({ ...current, entryKind: 'liability' }))} style={styles.chip}>
                  Liability
                </Chip>
              </View>
              <TextInput
                label="Asset Type"
                mode="outlined"
                value={form.assetType}
                onChangeText={(value) => setForm((current) => ({ ...current, assetType: value }))}
                style={styles.input}
              />
              <TextInput
                label="Balance"
                mode="outlined"
                keyboardType="numeric"
                value={form.balance}
                onChangeText={(value) => setForm((current) => ({ ...current, balance: value }))}
                style={styles.input}
              />
              <TextInput
                label="As of Date (YYYY-MM-DD)"
                mode="outlined"
                value={form.asOfDate}
                onChangeText={(value) => setForm((current) => ({ ...current, asOfDate: value }))}
                style={styles.input}
              />
              <TextInput
                label="Institution Name"
                mode="outlined"
                value={form.institutionName}
                onChangeText={(value) => setForm((current) => ({ ...current, institutionName: value }))}
                style={styles.input}
              />
              <TextInput
                label="Masked Account"
                mode="outlined"
                value={form.accountMasked}
                onChangeText={(value) => setForm((current) => ({ ...current, accountMasked: value }))}
                style={styles.input}
              />
              <Button mode="contained" onPress={submitManualPosition} loading={saving} disabled={saving}>
                Save Position
              </Button>
            </View>
          ) : null}
        </Card.Content>
      </Card>

      <Card style={styles.card}>
        <Card.Content>
          <Text style={styles.sectionTitle}>History</Text>
          {overview.history.length ? (
            overview.history.map((point) => (
              <HistoryRow key={point.as_of_date} point={point} colors={colors} />
            ))
          ) : (
            <Text style={styles.emptyText}>No balance history yet.</Text>
          )}
        </Card.Content>
      </Card>

      <Card style={styles.card}>
        <Card.Content>
          <Text style={styles.sectionTitle}>Current Positions</Text>
          {overview.positions.length ? (
            overview.positions.map((position) => (
              <PositionRow key={position.id} snapshot={position} colors={colors} />
            ))
          ) : (
            <Text style={styles.emptyText}>No positions found.</Text>
          )}
        </Card.Content>
      </Card>

      <Card style={styles.card}>
        <Card.Content>
          <Text style={styles.sectionTitle}>Manual Snapshot Log</Text>
          {overview.manual_snapshots.length ? (
            overview.manual_snapshots.map((snapshot) => (
              <View key={snapshot.id} style={styles.row}>
                <View style={styles.rowMeta}>
                  <Text style={styles.rowTitle}>{snapshot.label}</Text>
                  <Text style={styles.rowHint}>
                    {snapshot.entry_kind} · {snapshot.asset_type} · {formatDate(snapshot.as_of_date)}
                  </Text>
                </View>
                <View style={styles.rowActions}>
                  <Text style={styles.rowAmount}>{formatAmount(snapshot.balance)}</Text>
                  <Button compact mode="text" textColor={colors.danger} onPress={() => deleteManualPosition(snapshot)}>
                    Delete
                  </Button>
                </View>
              </View>
            ))
          ) : (
            <Text style={styles.emptyText}>No manual positions added yet.</Text>
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

function HistoryRow({ point, colors }: { point: NetWorthHistoryPoint; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <View style={styles.row}>
      <View style={styles.rowMeta}>
        <Text style={styles.rowTitle}>{formatDateShort(point.as_of_date)}</Text>
        <Text style={styles.rowHint}>
          Assets {formatAmount(point.assets)} · Liabilities {formatAmount(point.liabilities)}
        </Text>
      </View>
      <Text style={styles.rowAmount}>{formatAmount(point.net_worth)}</Text>
    </View>
  );
}

function PositionRow({ snapshot, colors }: { snapshot: BalanceSnapshot; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <View style={styles.row}>
      <View style={styles.rowMeta}>
        <Text style={styles.rowTitle}>{snapshot.label}</Text>
        <Text style={styles.rowHint}>
          {snapshot.entry_kind} · {snapshot.asset_type}
          {snapshot.institution_name ? ` · ${snapshot.institution_name}` : ''}
          {snapshot.account_masked ? ` · ${snapshot.account_masked}` : ''}
        </Text>
      </View>
      <View style={styles.rowActions}>
        <Text style={styles.rowAmount}>{formatAmount(snapshot.balance)}</Text>
        <Chip compact style={styles.inlineChip}>
          {snapshot.source_kind}
        </Chip>
      </View>
    </View>
  );
}

const createStyles = (colors: AppThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: 16, gap: 12 },
    centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background, padding: 24 },
    kicker: { color: colors.primary, textTransform: 'uppercase', fontWeight: '700', letterSpacing: 1 },
    title: { fontSize: 28, fontWeight: '800', color: colors.text },
    subtitle: { color: colors.textSecondary, marginTop: 6, marginBottom: 8 },
    rowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 4 },
    chip: { backgroundColor: colors.surface },
    statsGrid: { gap: 12 },
    statCard: { backgroundColor: colors.surface },
    statLabel: { color: colors.textSecondary, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.8 },
    statValue: { color: colors.text, fontWeight: '800', fontSize: 24, marginTop: 6 },
    card: { backgroundColor: colors.surface },
    sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 8 },
    sectionTextWrap: { flex: 1 },
    sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 6 },
    sectionHint: { color: colors.textSecondary },
    form: { marginTop: 8 },
    input: { marginBottom: 12, backgroundColor: colors.surface },
    row: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, marginTop: 8 },
    rowMeta: { flex: 1 },
    rowTitle: { fontWeight: '700', color: colors.text },
    rowHint: { color: colors.textSecondary, marginTop: 4 },
    rowAmount: { fontWeight: '700', color: colors.primary, textAlign: 'right' },
    rowActions: { alignItems: 'flex-end', justifyContent: 'center', gap: 6 },
    inlineChip: { backgroundColor: colors.surface },
    emptyText: { color: colors.textSecondary },
  });
