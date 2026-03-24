import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Platform,
  ScrollView,
  PermissionsAndroid,
} from 'react-native';
import { Button, Divider, ActivityIndicator } from 'react-native-paper';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { syncNewSms, previewSmsSync } from '../sms/SmsSyncService';
import { hasSmsPermission } from '../sms/SmsBridge';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import type { SmsSyncResult, ParsedSmsTransaction } from '../sms/types';

const LAST_SYNC_RESULT_KEY = 'hisabclub_last_sync_result';

async function saveLastSyncResult(result: SmsSyncResult): Promise<void> {
  await AsyncStorage.setItem(LAST_SYNC_RESULT_KEY, JSON.stringify(result));
}

async function loadLastSyncResult(): Promise<SmsSyncResult | null> {
  const raw = await AsyncStorage.getItem(LAST_SYNC_RESULT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SmsSyncResult;
  } catch {
    return null;
  }
}

export default function SmsSyncScreen() {
  const { colors } = useAppTheme();
  const COLORS = colors;
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);
  const [permissionStatus, setPermissionStatus] = useState<'unknown' | 'granted' | 'denied'>('unknown');
  const [syncing, setSyncing] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [syncResult, setSyncResult] = useState<SmsSyncResult | null>(null);
  const [previewResult, setPreviewResult] = useState<{
    totalRead: number;
    transactions: ParsedSmsTransaction[];
  } | null>(null);
  const [lastSyncResult, setLastSyncResult] = useState<SmsSyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkPermission = useCallback(async () => {
    if (Platform.OS !== 'android') {
      setPermissionStatus('denied');
      return;
    }
    const granted = await hasSmsPermission();
    setPermissionStatus(granted ? 'granted' : 'denied');
  }, []);

  useEffect(() => {
    checkPermission();
    loadLastSyncResult().then(setLastSyncResult);
  }, [checkPermission]);

  const requestPermission = async () => {
    if (Platform.OS !== 'android') return;
    setError(null);
    try {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.READ_SMS,
        {
          title: 'SMS Permission',
          message: 'HisabClub needs SMS access to read bank transaction messages',
          buttonPositive: 'Allow',
          buttonNegative: 'Deny',
        },
      );
      const isGranted = granted === PermissionsAndroid.RESULTS.GRANTED;
      setPermissionStatus(isGranted ? 'granted' : 'denied');
      if (!isGranted) {
        setError('SMS permission was denied. You can grant it from Settings.');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to request permission');
    }
  };

  const handleSync = async () => {
    setError(null);
    setSyncResult(null);
    setPreviewResult(null);
    setSyncing(true);
    try {
      const result = await syncNewSms();
      setSyncResult(result);
      setLastSyncResult(result);
      await saveLastSyncResult(result);
    } catch (err: any) {
      setError(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const handlePreview = async () => {
    setError(null);
    setSyncResult(null);
    setPreviewResult(null);
    setPreviewing(true);
    try {
      const result = await previewSmsSync();
      setPreviewResult(result);
    } catch (err: any) {
      setError(err.message || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const isAndroid = Platform.OS === 'android';
  const hasPermission = permissionStatus === 'granted';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>SMS Sync</Text>
      <Text style={styles.subtitle}>
        Automatically read bank transaction SMS and sync them to your account.
      </Text>

      {!isAndroid && (
        <View style={styles.warningBanner}>
          <Text style={styles.warningText}>
            SMS sync is only available on Android devices.
          </Text>
        </View>
      )}

      {/* Permission Section */}
      {isAndroid && (
        <>
          <Divider style={styles.divider} />
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>SMS Permission</Text>
            <View style={styles.permissionRow}>
              <Text style={styles.permissionLabel}>Status:</Text>
              <Text
                style={[
                  styles.permissionValue,
                  hasPermission ? styles.statusGranted : styles.statusDenied,
                ]}
              >
                {permissionStatus === 'unknown'
                  ? 'Checking...'
                  : hasPermission
                  ? 'Granted'
                  : 'Not Granted'}
              </Text>
            </View>
            {!hasPermission && permissionStatus !== 'unknown' && (
              <Button
                mode="contained"
                onPress={requestPermission}
                style={styles.permissionButton}
                buttonColor={COLORS.primary}
              >
                Grant SMS Permission
              </Button>
            )}
          </View>
        </>
      )}

      {/* Sync Section */}
      {isAndroid && (
        <>
          <Divider style={styles.divider} />
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Sync Transactions</Text>
            <Text style={styles.description}>
              Reads new SMS since your last sync, identifies bank transaction
              messages, and syncs them to your HisabClub account.
            </Text>
            <View style={styles.buttonRow}>
              <Button
                mode="contained"
                onPress={handleSync}
                loading={syncing}
                disabled={syncing || previewing || !hasPermission}
                icon="sync"
                style={styles.actionButton}
                buttonColor={COLORS.primary}
              >
                Sync Now
              </Button>
              <Button
                mode="outlined"
                onPress={handlePreview}
                loading={previewing}
                disabled={syncing || previewing || !hasPermission}
                icon="eye"
                style={styles.actionButton}
                textColor={COLORS.primary}
              >
                Preview
              </Button>
            </View>
          </View>
        </>
      )}

      {/* Error */}
      {error && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* Sync Results */}
      {syncResult && (
        <>
          <Divider style={styles.divider} />
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Sync Results</Text>
            <View style={styles.resultCard}>
              <ResultRow label="Total SMS read" value={syncResult.totalSmsRead} styles={styles} />
              <ResultRow label="Bank SMS found" value={syncResult.bankSmsFound} styles={styles} />
              <ResultRow label="Transactions parsed" value={syncResult.transactionsParsed} styles={styles} />
              <ResultRow label="Transactions synced" value={syncResult.transactionsSynced} styles={styles} />
              <ResultRow label="Duplicates skipped" value={syncResult.duplicatesSkipped} styles={styles} />
              {syncResult.errors.length > 0 && (
                <View style={styles.errorsSection}>
                  <Text style={styles.errorsTitle}>Errors:</Text>
                  {syncResult.errors.map((e, i) => (
                    <Text key={i} style={styles.errorItem}>
                      {e}
                    </Text>
                  ))}
                </View>
              )}
            </View>
          </View>
        </>
      )}

      {/* Preview Results */}
      {previewResult && (
        <>
          <Divider style={styles.divider} />
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Preview (No Data Sent)</Text>
            <View style={styles.resultCard}>
              <ResultRow label="Total SMS read" value={previewResult.totalRead} styles={styles} />
              <ResultRow
                label="Transactions found"
                value={previewResult.transactions.length}
                styles={styles}
              />
              {previewResult.transactions.length > 0 && (
                <View style={styles.previewList}>
                  <Text style={styles.previewListTitle}>
                    Transactions to sync:
                  </Text>
                  {previewResult.transactions.slice(0, 20).map((txn, i) => (
                    <View key={i} style={styles.previewItem}>
                      <Text style={styles.previewBank}>{txn.bankName}</Text>
                      <Text style={styles.previewAmount}>
                        {txn.direction === 'debit' ? '-' : '+'}
                        {'\u20B9'}
                        {txn.amount.toLocaleString('en-IN')}
                      </Text>
                      <Text style={styles.previewDesc} numberOfLines={1}>
                        {txn.description}
                      </Text>
                    </View>
                  ))}
                  {previewResult.transactions.length > 20 && (
                    <Text style={styles.moreText}>
                      ...and {previewResult.transactions.length - 20} more
                    </Text>
                  )}
                </View>
              )}
            </View>
          </View>
        </>
      )}

      {/* Last Sync History */}
      {lastSyncResult && !syncResult && (
        <>
          <Divider style={styles.divider} />
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Last Sync</Text>
            <View style={styles.resultCard}>
              <Text style={styles.lastSyncTime}>
                {new Date(lastSyncResult.syncedAt).toLocaleString()}
              </Text>
              <ResultRow label="SMS read" value={lastSyncResult.totalSmsRead} styles={styles} />
              <ResultRow label="Bank SMS" value={lastSyncResult.bankSmsFound} styles={styles} />
              <ResultRow label="Synced" value={lastSyncResult.transactionsSynced} styles={styles} />
              <ResultRow label="Duplicates" value={lastSyncResult.duplicatesSkipped} styles={styles} />
            </View>
          </View>
        </>
      )}

      <View style={styles.bottomPadding} />
    </ScrollView>
  );
}

function ResultRow({
  label,
  value,
  styles,
}: {
  label: string;
  value: number;
  styles: ReturnType<typeof createStyles>;
}) {
  return (
    <View style={styles.resultRow}>
      <Text style={styles.resultLabel}>{label}</Text>
      <Text style={styles.resultValue}>{value}</Text>
    </View>
  );
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  content: {
    padding: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.text,
  },
  subtitle: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginTop: 4,
    lineHeight: 20,
  },
  divider: {
    marginVertical: 16,
  },
  section: {
    marginBottom: 4,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 8,
  },
  description: {
    fontSize: 13,
    color: COLORS.textSecondary,
    lineHeight: 19,
    marginBottom: 12,
  },
  warningBanner: {
    backgroundColor: '#FFFBEB',
    borderColor: COLORS.warning,
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
  },
  warningText: {
    fontSize: 13,
    color: COLORS.warning,
    fontWeight: '500',
    textAlign: 'center',
  },
  permissionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  permissionLabel: {
    fontSize: 14,
    color: COLORS.textSecondary,
    marginRight: 8,
  },
  permissionValue: {
    fontSize: 14,
    fontWeight: '600',
  },
  statusGranted: {
    color: COLORS.success,
  },
  statusDenied: {
    color: COLORS.danger,
  },
  permissionButton: {
    alignSelf: 'flex-start',
    marginTop: 4,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
  },
  actionButton: {
    flex: 1,
  },
  errorBanner: {
    backgroundColor: '#FEF2F2',
    borderColor: COLORS.danger,
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
  },
  errorText: {
    fontSize: 13,
    color: COLORS.danger,
    fontWeight: '500',
  },
  resultCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 8,
    padding: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
  },
  resultRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
  },
  resultLabel: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },
  resultValue: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  errorsSection: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.border,
  },
  errorsTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.danger,
    marginBottom: 4,
  },
  errorItem: {
    fontSize: 12,
    color: COLORS.danger,
    marginBottom: 2,
  },
  previewList: {
    marginTop: 12,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.border,
  },
  previewListTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 8,
  },
  previewItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 4,
    gap: 8,
  },
  previewBank: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
    width: 50,
  },
  previewAmount: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.text,
    width: 80,
    textAlign: 'right',
  },
  previewDesc: {
    flex: 1,
    fontSize: 12,
    color: COLORS.textSecondary,
  },
  moreText: {
    fontSize: 12,
    color: COLORS.textSecondary,
    fontStyle: 'italic',
    marginTop: 4,
  },
  lastSyncTime: {
    fontSize: 13,
    color: COLORS.textSecondary,
    marginBottom: 8,
  },
  bottomPadding: {
    height: 32,
  },
});
