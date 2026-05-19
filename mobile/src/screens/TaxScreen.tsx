import React, { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { ActivityIndicator, Button, Card, Chip } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as DocumentPicker from 'expo-document-picker';
import * as api from '../api/client';
import type { TaxPortalData, TaxVerificationCheck } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import { formatAmount } from '../utils/formatters';
import { useToast } from '../components/ui/Toast';

type FinancialYearOption = {
  key: string;
  label: string;
};

function buildFinancialYearOptions(previousCount: number): FinancialYearOption[] {
  const today = new Date();
  const runningStartYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
  return Array.from({ length: previousCount + 1 }).map((_, index) => {
    const start = runningStartYear - index;
    const endShort = String(start + 1).slice(-2);
    return {
      key: `${start}-${endShort}`,
      label: index === 0 ? `Running FY ${start}-${endShort}` : `FY ${start}-${endShort}`,
    };
  });
}

export default function TaxScreen() {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const queryClient = useQueryClient();
  const toast = useToast();
  const fyOptions = useMemo(() => buildFinancialYearOptions(5), []);
  const [selectedFy, setSelectedFy] = useState(fyOptions[0]?.key ?? '');
  const [documentType, setDocumentType] = useState('form_16');
  const [uploading, setUploading] = useState(false);

  const verificationQuery = useQuery({
    queryKey: ['tax-verification', selectedFy],
    queryFn: () => api.getTaxVerification(selectedFy),
  });

  const uploadPortalFile = async () => {
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        copyToCacheDirectory: false,
        multiple: false,
      });
      if (picked.canceled || !picked.assets?.[0]) return;
      setUploading(true);
      const asset = picked.assets[0];
      await api.uploadTaxPortalDocument(
        asset.uri,
        asset.name,
        documentType,
        selectedFy,
      );
      await queryClient.invalidateQueries({ queryKey: ['tax-verification', selectedFy] });
      await queryClient.invalidateQueries({ queryKey: ['tax-portal-data', selectedFy] });
    } catch (err: any) {
      toast.error(err?.message || 'Could not upload portal document');
    } finally {
      setUploading(false);
    }
  };

  if (verificationQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  const verification = verificationQuery.data;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.kicker}>Compliance</Text>
      <Text style={styles.title}>Tax & Audit</Text>
      <Text style={styles.subtitle}>FY-based portal verification and discrepancy review.</Text>

      <View style={styles.rowWrap}>
        {fyOptions.map((option) => (
          <Chip key={option.key} selected={selectedFy === option.key} onPress={() => setSelectedFy(option.key)} style={styles.chip}>
            {option.label}
          </Chip>
        ))}
      </View>

      <Card style={styles.card}>
        <Card.Content>
          <Text style={styles.sectionTitle}>Portal Verification</Text>
          <View style={styles.rowWrap}>
            {['form_16', 'form_26as', 'ais', 'tis'].map((item) => (
              <Chip key={item} selected={documentType === item} onPress={() => setDocumentType(item)} style={styles.chip}>
                {item.toUpperCase()}
              </Chip>
            ))}
          </View>
          <Button mode="contained" onPress={uploadPortalFile} loading={uploading} disabled={uploading}>
            Upload Portal Document
          </Button>
        </Card.Content>
      </Card>

      {verification ? (
        <>
          <Card style={styles.card}>
            <Card.Content>
              <Text style={styles.sectionTitle}>Checks</Text>
              {verification.checks.map((check) => (
                <CheckRow key={check.check} item={check} colors={colors} />
              ))}
            </Card.Content>
          </Card>
          <Card style={styles.card}>
            <Card.Content>
              <Text style={styles.sectionTitle}>Uploaded Documents</Text>
              {(verification.portal_data || []).map((item) => (
                <PortalRow key={item.id} item={item} colors={colors} />
              ))}
              {!verification.portal_data?.length ? (
                <Text style={styles.emptyText}>No portal documents uploaded for this FY.</Text>
              ) : null}
            </Card.Content>
          </Card>
        </>
      ) : (
        <Card style={styles.card}>
          <Card.Content>
            <Text style={styles.emptyText}>Upload portal documents to activate verification.</Text>
          </Card.Content>
        </Card>
      )}
    </ScrollView>
  );
}

function CheckRow({ item, colors }: { item: TaxVerificationCheck; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <View style={styles.checkRow}>
      <Chip style={styles.inlineChip}>{item.status}</Chip>
      <Text style={styles.checkTitle}>{item.check}</Text>
      <Text style={styles.checkHint}>
        App {formatAmount(item.app_amount)} · Portal {formatAmount(item.portal_amount)} · Gap {formatAmount(Math.abs(item.gap))}
      </Text>
      <Text style={styles.checkHint}>{item.detail}</Text>
    </View>
  );
}

function PortalRow({ item, colors }: { item: TaxPortalData; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <View style={styles.portalRow}>
      <Text style={styles.checkTitle}>{item.document_type.toUpperCase()}</Text>
      <Text style={styles.checkHint}>{item.source_name ?? 'uploaded'} · {item.financial_year ?? 'FY unknown'}</Text>
    </View>
  );
}

const createStyles = (colors: AppThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
    content: { padding: 16, gap: 12 },
    kicker: { color: colors.primary, textTransform: 'uppercase', fontWeight: '700', letterSpacing: 1 },
    title: { fontSize: 28, fontWeight: '800', color: colors.text },
    subtitle: { color: colors.textSecondary, marginTop: 6, marginBottom: 8 },
    card: { backgroundColor: colors.surface, marginBottom: 12 },
    sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 10 },
    rowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
    chip: { backgroundColor: colors.surface },
    inlineChip: { alignSelf: 'flex-start', marginBottom: 8 },
    checkRow: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, marginTop: 8 },
    checkTitle: { fontWeight: '700', color: colors.text },
    checkHint: { color: colors.textSecondary, marginTop: 4 },
    portalRow: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, marginTop: 8 },
    emptyText: { color: colors.textSecondary },
  });
