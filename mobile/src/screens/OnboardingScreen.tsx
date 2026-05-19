import React, { useEffect, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View, Alert } from 'react-native';
import { ActivityIndicator, Button, Card, Chip, TextInput } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as api from '../api/client';
import type { Institution, OnboardingBank } from '../api/types';
import type { RootStackParamList } from '../navigation/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import { useToast } from '../components/ui/Toast';

type AccountDraft = {
  account_type: string;
  account_number_masked: string;
  nickname: string;
};

type NavProp = NativeStackNavigationProp<RootStackParamList>;

export default function OnboardingScreen() {
  const navigation = useNavigation<NavProp>();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [selectedBanks, setSelectedBanks] = useState<string[]>([]);
  const [accountsByBank, setAccountsByBank] = useState<Record<string, AccountDraft[]>>({});
  const [profile, setProfile] = useState({
    first_name: '',
    last_name: '',
    date_of_birth: '',
    pan_number: '',
  });

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: api.getMe,
  });
  const statusQuery = useQuery({
    queryKey: ['onboarding-status'],
    queryFn: api.getOnboardingStatus,
  });
  const institutionsQuery = useQuery({
    queryKey: ['institutions'],
    queryFn: api.getInstitutions,
  });

  useEffect(() => {
    if (meQuery.data) {
      setProfile((current) => ({
        ...current,
        first_name: meQuery.data.first_name ?? '',
        last_name: meQuery.data.last_name ?? '',
      }));
    }
  }, [meQuery.data]);

  useEffect(() => {
    if (statusQuery.data?.completed) {
      navigation.replace('MainTabs');
    } else if (statusQuery.data?.current_step) {
      setStep(Math.max(1, Math.min(4, statusQuery.data.current_step)));
    }
  }, [navigation, statusQuery.data]);

  const toggleBank = (name: string) => {
    setSelectedBanks((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
    setAccountsByBank((current) => ({
      ...current,
      [name]:
        current[name] ?? [{ account_type: 'savings', account_number_masked: '', nickname: '' }],
    }));
  };

  const updateBankAccount = (bank: string, index: number, patch: Partial<AccountDraft>) => {
    setAccountsByBank((current) => ({
      ...current,
      [bank]: (current[bank] || []).map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    }));
  };

  const addBankAccount = (bank: string) => {
    setAccountsByBank((current) => ({
      ...current,
      [bank]: [
        ...(current[bank] || []),
        { account_type: 'savings', account_number_masked: '', nickname: '' },
      ],
    }));
  };

  const saveProfile = async () => {
    setSaving(true);
    try {
      await api.updateOnboardingProfile(profile);
      await queryClient.invalidateQueries({ queryKey: ['me'] });
      await queryClient.invalidateQueries({ queryKey: ['onboarding-status'] });
      setStep(2);
    } catch (err: any) {
      toast.error(err?.message || 'Could not save profile');
    } finally {
      setSaving(false);
    }
  };

  const saveBanks = async () => {
    const banks: OnboardingBank[] = selectedBanks.map((bank) => ({
      institution_name: bank,
      accounts: (accountsByBank[bank] || []).map((item) => ({
        account_type: item.account_type,
        account_number_masked: item.account_number_masked || undefined,
        nickname: item.nickname || undefined,
      })),
    }));
    setSaving(true);
    try {
      await api.saveOnboardingBanks({ banks });
      await queryClient.invalidateQueries({ queryKey: ['accounts-tree'] });
      await queryClient.invalidateQueries({ queryKey: ['accounts'] });
      await queryClient.invalidateQueries({ queryKey: ['onboarding-status'] });
      setStep(4);
    } catch (err: any) {
      toast.error(err?.message || 'Could not save bank setup');
    } finally {
      setSaving(false);
    }
  };

  const complete = async () => {
    setSaving(true);
    try {
      await api.completeOnboarding();
      await queryClient.invalidateQueries({ queryKey: ['onboarding-status'] });
      navigation.replace('MainTabs');
    } catch (err: any) {
      toast.error(err?.message || 'Could not complete onboarding');
    } finally {
      setSaving(false);
    }
  };

  if (meQuery.isLoading || statusQuery.isLoading || institutionsQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  const institutions = institutionsQuery.data ?? [];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.kicker}>Phase 2 Setup</Text>
      <Text style={styles.title}>Onboarding</Text>
      <Text style={styles.subtitle}>Complete profile and account linking before regular use.</Text>

      <View style={styles.stepRow}>
        {[1, 2, 3, 4].map((item) => (
          <Chip key={item} selected={step >= item} style={styles.stepChip}>
            Step {item}
          </Chip>
        ))}
      </View>

      {step <= 1 && (
        <Card style={styles.card}>
          <Card.Content>
            <Text style={styles.sectionTitle}>Personal Info</Text>
            <TextInput label="First Name" mode="outlined" value={profile.first_name} onChangeText={(v) => setProfile((p) => ({ ...p, first_name: v }))} style={styles.input} />
            <TextInput label="Last Name" mode="outlined" value={profile.last_name} onChangeText={(v) => setProfile((p) => ({ ...p, last_name: v }))} style={styles.input} />
            <TextInput label="Date of Birth" mode="outlined" placeholder="DDMMYYYY" value={profile.date_of_birth} onChangeText={(v) => setProfile((p) => ({ ...p, date_of_birth: v }))} style={styles.input} />
            <TextInput label="PAN" mode="outlined" placeholder="ABCDE1234F" autoCapitalize="characters" value={profile.pan_number} onChangeText={(v) => setProfile((p) => ({ ...p, pan_number: v.toUpperCase() }))} style={styles.input} />
            <Button mode="contained" onPress={saveProfile} loading={saving} disabled={saving}>
              Save and Continue
            </Button>
          </Card.Content>
        </Card>
      )}

      {step === 2 && (
        <Card style={styles.card}>
          <Card.Content>
            <Text style={styles.sectionTitle}>Select Institutions</Text>
            <View style={styles.bankWrap}>
              {institutions.map((institution: Institution) => (
                <Chip
                  key={institution.id}
                  selected={selectedBanks.includes(institution.name)}
                  onPress={() => toggleBank(institution.name)}
                  style={styles.bankChip}
                >
                  {institution.name}
                </Chip>
              ))}
            </View>
            <Button mode="contained" disabled={selectedBanks.length === 0} onPress={() => setStep(3)}>
              Continue to Accounts
            </Button>
          </Card.Content>
        </Card>
      )}

      {step === 3 && (
        <View style={styles.stack}>
          {selectedBanks.map((bank) => (
            <Card key={bank} style={styles.card}>
              <Card.Content>
                <View style={styles.bankHeader}>
                  <Text style={styles.sectionTitle}>{bank}</Text>
                  <Button mode="text" onPress={() => addBankAccount(bank)}>
                    Add Account
                  </Button>
                </View>
                {(accountsByBank[bank] || []).map((account, index) => (
                  <View key={`${bank}-${index}`} style={styles.accountBlock}>
                    <TextInput
                      label="Type"
                      mode="outlined"
                      value={account.account_type}
                      onChangeText={(v) => updateBankAccount(bank, index, { account_type: v })}
                      style={styles.input}
                    />
                    <TextInput
                      label="Masked Number"
                      mode="outlined"
                      value={account.account_number_masked}
                      onChangeText={(v) => updateBankAccount(bank, index, { account_number_masked: v })}
                      style={styles.input}
                    />
                    <TextInput
                      label="Nickname"
                      mode="outlined"
                      value={account.nickname}
                      onChangeText={(v) => updateBankAccount(bank, index, { nickname: v })}
                      style={styles.input}
                    />
                  </View>
                ))}
              </Card.Content>
            </Card>
          ))}

          <View style={styles.actionRow}>
            <Button mode="outlined" onPress={() => setStep(2)}>
              Back
            </Button>
            <Button mode="contained" onPress={saveBanks} loading={saving} disabled={saving}>
              Save Accounts
            </Button>
          </View>
        </View>
      )}

      {step >= 4 && (
        <Card style={styles.card}>
          <Card.Content>
            <Text style={styles.sectionTitle}>Ready</Text>
            <Text style={styles.subtitleInline}>
              Profile and account map are saved. Future statements will link into this hierarchy.
            </Text>
            <Button mode="contained" onPress={complete} loading={saving} disabled={saving}>
              Go to Dashboard
            </Button>
          </Card.Content>
        </Card>
      )}
    </ScrollView>
  );
}

const createStyles = (colors: AppThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: 16, gap: 12 },
    centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
    kicker: { color: colors.primary, textTransform: 'uppercase', letterSpacing: 1, fontWeight: '700', marginBottom: 6 },
    title: { fontSize: 28, fontWeight: '800', color: colors.text },
    subtitle: { color: colors.textSecondary, marginTop: 6, marginBottom: 12 },
    subtitleInline: { color: colors.textSecondary, marginBottom: 16 },
    stepRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
    stepChip: { backgroundColor: colors.surface },
    card: { backgroundColor: colors.surface },
    sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 12 },
    input: { marginBottom: 12, backgroundColor: colors.surface },
    bankWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
    bankChip: { backgroundColor: colors.background },
    stack: { gap: 12 },
    bankHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    accountBlock: { marginBottom: 8, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
    actionRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, marginBottom: 24 },
  });
