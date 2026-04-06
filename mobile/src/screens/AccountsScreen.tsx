import React, { useMemo, useState } from 'react';
import { Alert, FlatList, StyleSheet, Text, View } from 'react-native';
import { Button, Card, TextInput, ActivityIndicator } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import type { AccountInstitutionGroup, Institution } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import { formatAmount } from '../utils/formatters';

export default function AccountsScreen() {
  const queryClient = useQueryClient();
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    institution_name: '',
    account_type: 'savings',
    account_number_masked: '',
    nickname: '',
  });

  const treeQuery = useQuery({
    queryKey: ['accounts-tree'],
    queryFn: api.getAccountsTree,
  });
  const institutionsQuery = useQuery({
    queryKey: ['institutions'],
    queryFn: api.getInstitutions,
  });

  const institutions = institutionsQuery.data ?? [];

  const createAccount = async () => {
    try {
      await api.createAccount({
        institution_name: form.institution_name,
        account_type: form.account_type,
        account_number_masked: form.account_number_masked || undefined,
        nickname: form.nickname || undefined,
      });
      setShowCreate(false);
      setForm((current) => ({ ...current, account_number_masked: '', nickname: '' }));
      await queryClient.invalidateQueries({ queryKey: ['accounts-tree'] });
      await queryClient.invalidateQueries({ queryKey: ['accounts'] });
    } catch (err: any) {
      Alert.alert('Create account failed', err?.message || 'Could not create account');
    }
  };

  if (treeQuery.isLoading || institutionsQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  const tree = treeQuery.data ?? [];

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={styles.content}
      data={tree}
      keyExtractor={(item) => item.institution_name}
      ListHeaderComponent={(
        <View style={styles.header}>
          <Text style={styles.kicker}>Hierarchy</Text>
          <Text style={styles.title}>Accounts</Text>
          <Text style={styles.subtitle}>Institution to account map for statements and tax linkage.</Text>
          <Button mode="contained" onPress={() => setShowCreate((v) => !v)}>
            {showCreate ? 'Close' : 'Add Account'}
          </Button>
          {showCreate && (
            <Card style={styles.card}>
              <Card.Content>
                <Text style={styles.sectionTitle}>Create Account</Text>
                <TextInput
                  label="Institution"
                  mode="outlined"
                  value={form.institution_name}
                  onChangeText={(v) => setForm((current) => ({ ...current, institution_name: v }))}
                  placeholder={institutions[0]?.name ?? 'Institution'}
                  style={styles.input}
                />
                <TextInput label="Account Type" mode="outlined" value={form.account_type} onChangeText={(v) => setForm((current) => ({ ...current, account_type: v }))} style={styles.input} />
                <TextInput label="Masked Number" mode="outlined" value={form.account_number_masked} onChangeText={(v) => setForm((current) => ({ ...current, account_number_masked: v }))} style={styles.input} />
                <TextInput label="Nickname" mode="outlined" value={form.nickname} onChangeText={(v) => setForm((current) => ({ ...current, nickname: v }))} style={styles.input} />
                <Button mode="contained" onPress={createAccount} disabled={!form.institution_name.trim()}>
                  Save Account
                </Button>
              </Card.Content>
            </Card>
          )}
        </View>
      )}
      renderItem={({ item }: { item: AccountInstitutionGroup }) => (
        <Card style={styles.card}>
          <Card.Content>
            <Text style={styles.sectionTitle}>{item.institution_name}</Text>
            {item.accounts.map((account) => (
              <View key={account.id} style={styles.accountRow}>
                <View style={styles.accountMeta}>
                  <Text style={styles.accountTitle}>
                    {account.account_type} {account.account_number_masked ? `· ${account.account_number_masked}` : ''}
                  </Text>
                  {account.nickname ? <Text style={styles.accountHint}>{account.nickname}</Text> : null}
                  <Text style={styles.accountHint}>
                    {account.statement_count} statements · {account.total_transactions} transactions
                  </Text>
                </View>
                <View style={styles.accountSide}>
                  <Text style={styles.balanceText}>
                    {account.latest_balance == null ? '—' : formatAmount(account.latest_balance)}
                  </Text>
                </View>
              </View>
            ))}
          </Card.Content>
        </Card>
      )}
    />
  );
}

const createStyles = (colors: AppThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: 16, gap: 12 },
    centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
    header: { gap: 12, marginBottom: 8 },
    kicker: { color: colors.primary, textTransform: 'uppercase', fontWeight: '700', letterSpacing: 1 },
    title: { fontSize: 28, fontWeight: '800', color: colors.text },
    subtitle: { color: colors.textSecondary },
    card: { backgroundColor: colors.surface, marginBottom: 12 },
    sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 10 },
    input: { marginBottom: 12, backgroundColor: colors.surface },
    accountRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, marginTop: 8 },
    accountMeta: { flex: 1 },
    accountTitle: { fontWeight: '700', color: colors.text, textTransform: 'capitalize' },
    accountHint: { color: colors.textSecondary, marginTop: 4 },
    accountSide: { alignItems: 'flex-end', justifyContent: 'center' },
    balanceText: { color: colors.primary, fontWeight: '700' },
  });
