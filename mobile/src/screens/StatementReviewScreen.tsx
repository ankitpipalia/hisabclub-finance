import React, { useMemo, useState } from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';
import { ActivityIndicator, Button, Card, Chip, TextInput } from 'react-native-paper';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { RouteProp, useRoute } from '@react-navigation/native';
import * as Sharing from 'expo-sharing';
import * as api from '../api/client';
import type { RootStackParamList } from '../navigation/types';
import type { StatementReviewTransaction } from '../api/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import { useToast } from '../components/ui/Toast';
import { formatAmount } from '../utils/formatters';

type ReviewRoute = RouteProp<RootStackParamList, 'StatementReview'>;

export default function StatementReviewScreen() {
  const route = useRoute<ReviewRoute>();
  const queryClient = useQueryClient();
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const toast = useToast();
  const [selectedTxnId, setSelectedTxnId] = useState<string | null>(null);
  const [annotationType, setAnnotationType] = useState('comment');
  const [annotationText, setAnnotationText] = useState('');
  const [pageNumber, setPageNumber] = useState('');
  const [busy, setBusy] = useState(false);

  const reviewQuery = useQuery({
    queryKey: ['statement-review', route.params.statementId],
    queryFn: () => api.getStatementReview(route.params.statementId),
  });

  const selectedTxn = reviewQuery.data?.transactions.find((item) => item.id === selectedTxnId) ?? reviewQuery.data?.transactions[0] ?? null;

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['statement-review', route.params.statementId] });
  };

  const verifyTxn = async (txnId: string) => {
    setBusy(true);
    try {
      await api.verifyStatementTransaction(route.params.statementId, txnId);
      await refresh();
      toast.success('Transaction verified.');
    } catch (err: any) {
      toast.error(err?.message || 'Could not verify transaction');
    } finally {
      setBusy(false);
    }
  };

  const bulkVerify = async () => {
    setBusy(true);
    try {
      await api.bulkVerifyStatement(route.params.statementId);
      await refresh();
      toast.success('Statement bulk-verified.');
    } catch (err: any) {
      toast.error(err?.message || 'Could not verify statement');
    } finally {
      setBusy(false);
    }
  };

  const submitAnnotation = async () => {
    if (!selectedTxn || !annotationText.trim()) return;
    setBusy(true);
    try {
      await api.annotateStatementTransaction(route.params.statementId, selectedTxn.id, {
        annotation_type: annotationType,
        content: annotationText.trim(),
        page_number: pageNumber.trim() ? Number(pageNumber) : undefined,
      });
      setAnnotationText('');
      setPageNumber('');
      await refresh();
      toast.success('Note saved.');
    } catch (err: any) {
      toast.error(err?.message || 'Could not save note');
    } finally {
      setBusy(false);
    }
  };

  const openPdf = async () => {
    setBusy(true);
    try {
      const uri = await api.downloadStatementPdfToCache(
        route.params.statementId,
        review?.statement.pdf_filename || `statement-${route.params.statementId}.pdf`,
      );
      const available = await Sharing.isAvailableAsync();
      if (!available) {
        toast.warning('Sharing not available on this device.');
        return;
      }
      await Sharing.shareAsync(uri, {
        mimeType: 'application/pdf',
        dialogTitle: 'Open statement PDF',
      });
    } catch (err: any) {
      toast.error(err?.message || 'Could not open statement PDF');
    } finally {
      setBusy(false);
    }
  };

  if (reviewQuery.isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  const review = reviewQuery.data;
  if (!review) {
    return (
      <View style={styles.centered}>
        <Text style={styles.emptyText}>Review data unavailable.</Text>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={styles.content}
      data={review.transactions}
      keyExtractor={(item) => item.id}
      ListHeaderComponent={(
        <View style={styles.header}>
          <Text style={styles.kicker}>Review</Text>
          <Text style={styles.title}>{review.statement.bank_name} Statement</Text>
          <Text style={styles.subtitle}>{review.transactions.length} parsed transactions</Text>
          <View style={styles.headerActions}>
            <Button mode="outlined" onPress={openPdf} disabled={busy}>
              Open PDF
            </Button>
            <Button mode="contained" onPress={bulkVerify} loading={busy} disabled={busy}>
              Bulk Verify
            </Button>
          </View>
        </View>
      )}
      renderItem={({ item }) => (
        <Card style={styles.card}>
          <Card.Content>
            <Button mode={selectedTxn?.id === item.id ? 'contained' : 'text'} onPress={() => setSelectedTxnId(item.id)}>
              Select Transaction
            </Button>
            <TransactionCard item={item} colors={colors} />
            {selectedTxn?.id === item.id ? (
              <View style={styles.reviewBox}>
                <View style={styles.rowWrap}>
                  {['comment', 'flag', 'correction_request', 'verification'].map((type) => (
                    <Chip key={type} selected={annotationType === type} onPress={() => setAnnotationType(type)} style={styles.inlineChip}>
                      {type}
                    </Chip>
                  ))}
                </View>
                <TextInput
                  label="Add note"
                  mode="outlined"
                  multiline
                  value={annotationText}
                  onChangeText={setAnnotationText}
                  style={styles.input}
                />
                <TextInput
                  label="Linked Page (optional)"
                  mode="outlined"
                  value={pageNumber}
                  onChangeText={setPageNumber}
                  keyboardType="number-pad"
                  style={styles.input}
                />
                <View style={styles.actionRow}>
                  <Button mode="outlined" onPress={() => verifyTxn(item.id)} disabled={busy}>
                    Verify
                  </Button>
                  <Button mode="contained" onPress={submitAnnotation} loading={busy} disabled={busy || !annotationText.trim()}>
                    Save Note
                  </Button>
                </View>
              </View>
            ) : null}
          </Card.Content>
        </Card>
      )}
    />
  );
}

function TransactionCard({ item, colors }: { item: StatementReviewTransaction; colors: AppThemeColors }) {
  const styles = useMemo(() => createStyles(colors), [colors]);
  return (
    <View>
      <Text style={styles.txnTitle}>{item.description_raw}</Text>
      <Text style={styles.txnHint}>
        {item.transaction_date} · {item.direction} · confidence {(item.confidence * 100).toFixed(0)}%
      </Text>
      <Text style={styles.amountText}>{formatAmount(item.amount)}</Text>
      {item.annotations.map((annotation) => (
        <View key={annotation.id} style={styles.annotationRow}>
          <Text style={styles.annotationType}>{annotation.annotation_type}</Text>
          <Text style={styles.annotationText}>{annotation.content}</Text>
          {annotation.llm_response ? <Text style={styles.txnHint}>{annotation.llm_response}</Text> : null}
        </View>
      ))}
    </View>
  );
}

const createStyles = (colors: AppThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
    content: { padding: 16, gap: 12 },
    header: { gap: 12, marginBottom: 8 },
    kicker: { color: colors.primary, textTransform: 'uppercase', fontWeight: '700', letterSpacing: 1 },
    title: { fontSize: 28, fontWeight: '800', color: colors.text },
    subtitle: { color: colors.textSecondary },
    headerActions: { flexDirection: 'row', gap: 12, justifyContent: 'space-between' },
    card: { backgroundColor: colors.surface, marginBottom: 12 },
    txnTitle: { fontWeight: '700', color: colors.text, marginTop: 8 },
    txnHint: { color: colors.textSecondary, marginTop: 4 },
    amountText: { color: colors.primary, fontWeight: '700', marginTop: 6 },
    reviewBox: { marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 },
    rowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
    inlineChip: { backgroundColor: colors.background },
    input: { marginBottom: 12, backgroundColor: colors.surface },
    actionRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
    annotationRow: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8, marginTop: 8 },
    annotationType: { color: colors.primary, fontWeight: '700', textTransform: 'capitalize' },
    annotationText: { color: colors.text, marginTop: 4 },
    emptyText: { color: colors.textSecondary },
  });
