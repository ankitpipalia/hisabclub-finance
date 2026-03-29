import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  View,
  Text,
  ScrollView,
  StyleSheet,
  Alert,
} from 'react-native';
import { Button, TextInput, Divider, ActivityIndicator } from 'react-native-paper';
import * as DocumentPicker from 'expo-document-picker';
import * as api from '../api/client';
import { BANK_OPTIONS, DOCUMENT_TYPE_OPTIONS } from '../utils/constants';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import AnimatedOrbs from '../components/AnimatedOrbs';
import BrandMark from '../components/BrandMark';
import FadeInView from '../components/FadeInView';

type DocumentTypeHint = 'auto' | 'bank_account' | 'credit_card';

interface SelectedFile {
  id: string;
  uri: string;
  name: string;
  size: number | undefined;
  password: string;
  bankHint: string;
  accountTypeHint: DocumentTypeHint;
  forceReprocess?: boolean;
}

interface UploadNotification {
  id: string;
  fileName: string;
  status: 'reviewing' | 'success' | 'error';
  message: string;
  bankName?: string | null;
  accountType?: string | null;
}

export default function UploadScreen() {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const cardAnim = useRef(new Animated.Value(0)).current;

  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
  const [showPasswordFor, setShowPasswordFor] = useState<Record<string, boolean>>({});
  const [uploading, setUploading] = useState(false);
  const [notifications, setNotifications] = useState<UploadNotification[]>([]);

  useEffect(() => {
    Animated.timing(cardAnim, {
      toValue: 1,
      duration: 350,
      useNativeDriver: true,
    }).start();
  }, [cardAnim]);

  useEffect(() => {
    let active = true;
    const loadRecentUploads = async () => {
      try {
        const recent = await api.getRecentUploads(12);
        if (!active) return;
        setNotifications((current) => {
          const existing = new Set(current.map((item) => item.id));
          const fromServer = recent
            .filter((item) => !existing.has(item.pdf_id))
            .map((item) => ({
              id: item.pdf_id,
              fileName: item.file_name,
              status: normalizeReviewStatus(item.status),
              message: item.message,
              bankName: item.bank_name,
              accountType: item.account_type,
            }));
          return [...current, ...fromServer];
        });
      } catch {
        // Keep upload screen usable even if recent review feed is unavailable.
      }
    };
    void loadRecentUploads();
    return () => {
      active = false;
    };
  }, []);

  const reviewingCount = notifications.filter((item) => item.status === 'reviewing').length;

  const updateFile = (id: string, patch: Partial<SelectedFile>) => {
    setSelectedFiles((current) => current.map((file) => (file.id === id ? { ...file, ...patch } : file)));
  };

  const removeFile = (id: string) => {
    setSelectedFiles((current) => current.filter((file) => file.id !== id));
  };

  const setNotification = (id: string, patch: Partial<UploadNotification>) => {
    setNotifications((current) =>
      current.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)),
    );
  };

  const remapNotificationId = (fromId: string, toId: string, fileName: string) => {
    if (!toId || toId === fromId) return;
    setNotifications((current) => {
      const source = current.find((entry) => entry.id === fromId);
      const retained = current.filter((entry) => entry.id !== fromId && entry.id !== toId);
      if (!source) return retained;
      return [{ ...source, id: toId, fileName }, ...retained];
    });
  };

  const isReviewingStatus = (status: string) =>
    ['reviewing', 'queued', 'uploaded', 'classifying', 'extracting', 'validating'].includes(
      status.toLowerCase(),
    );

  const beginNotification = (file: SelectedFile) => {
    setNotifications((current) => [
      {
        id: file.id,
        fileName: file.name,
        status: 'reviewing',
        message: 'Document is under review by the local LLM. Please wait. We will notify you once it completes.',
      },
      ...current.filter((entry) => entry.id !== file.id),
    ]);
  };

  const handlePickFile = async () => {
    try {
      const pickResult = await DocumentPicker.getDocumentAsync({
        type: 'application/pdf',
        copyToCacheDirectory: true,
        multiple: true,
      });

      if (!pickResult.canceled && pickResult.assets && pickResult.assets.length > 0) {
        const next = pickResult.assets.map((asset) => ({
          id: `${asset.name}-${asset.uri}-${Date.now()}-${Math.random()}`,
          uri: asset.uri,
          name: asset.name,
          size: asset.size,
          password: '',
          bankHint: '',
          accountTypeHint: 'auto' as DocumentTypeHint,
        }));
        setSelectedFiles((current) => [...current, ...next]);
      }
    } catch {
      Alert.alert('Error', 'Failed to pick document');
    }
  };

  const getUploadErrorMessage = (err: any) => {
    if (err?.status === 409) {
      return 'This statement already exists. Marked for reprocess.';
    }
    if (typeof err?.message === 'string' && err.message.trim()) {
      return err.message;
    }
    return 'Upload failed. Please try again.';
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) {
      Alert.alert('Error', 'Please select at least one PDF file first');
      return;
    }

    setUploading(true);
    try {
      for (const file of selectedFiles) {
        beginNotification(file);
        try {
          // eslint-disable-next-line no-await-in-loop
          const response = await api.uploadPdf(
            file.uri,
            file.name,
            file.password || undefined,
            file.bankHint || undefined,
            file.accountTypeHint,
            file.forceReprocess ?? false,
          );
          const serverId = response.document_id || response.pdf_id || file.id;
          remapNotificationId(file.id, serverId, file.name);
          if (response.status === 'duplicate') {
            updateFile(file.id, { forceReprocess: true });
            setNotification(serverId, {
              status: 'error',
              message: response.message || 'This statement already exists. Marked for reprocess.',
              bankName: response.bank_name,
              accountType: response.account_type,
            });
            continue;
          }
          if (isReviewingStatus(response.status)) {
            setNotification(serverId, {
              status: 'reviewing',
              message:
                response.message ||
                'Document is under review by the local LLM. Please wait. We will notify you once it completes.',
              bankName: response.bank_name,
              accountType: response.account_type,
            });
            removeFile(file.id);
            continue;
          }
          if (response.status !== 'success' && response.status !== 'parsed') {
            setNotification(serverId, {
              status: 'error',
              message: response.message || 'Upload review failed.',
              bankName: response.bank_name,
              accountType: response.account_type,
            });
            continue;
          }
          setNotification(serverId, {
            status: 'success',
            message: response.message || `Statement uploaded successfully. Status: ${response.status}`,
            bankName: response.bank_name,
            accountType: response.account_type,
          });
          removeFile(file.id);
        } catch (err: any) {
          const message = getUploadErrorMessage(err);
          if (err?.status === 409) {
            updateFile(file.id, { forceReprocess: true });
          }
          setNotification(file.id, {
            status: 'error',
            message,
          });
        }
      }
    } finally {
      setUploading(false);
    }
  };

  const formatFileSize = (bytes: number | undefined) => {
    if (!bytes) return 'Unknown size';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <FadeInView>
        <View style={styles.hero}>
          <AnimatedOrbs compact />
          <BrandMark size={54} />
          <Text style={styles.kicker}>Statement Intake</Text>
          <Text style={styles.title}>Upload Documents</Text>
          <Text style={styles.subtitle}>
            Queue multiple PDFs, mark each as auto, bank account, or credit card, and let the local LLM review them.
          </Text>
        </View>
      </FadeInView>

      <FadeInView delay={90}>
        <Animated.View
          style={[
            styles.card,
            {
              opacity: cardAnim,
              transform: [
                {
                  translateY: cardAnim.interpolate({
                    inputRange: [0, 1],
                    outputRange: [16, 0],
                  }),
                },
              ],
            },
          ]}
        >
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Select Files</Text>
            <Button
              mode="outlined"
              onPress={handlePickFile}
              icon="file-pdf-box"
              style={styles.pickButton}
              textColor={colors.primary}
            >
              {selectedFiles.length > 0 ? 'Add More PDFs' : 'Pick PDF Files'}
            </Button>
          </View>

          {selectedFiles.length > 0 && (
            <>
              <Divider style={styles.divider} />
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Upload Queue</Text>
                {selectedFiles.map((file, index) => (
                  <View key={file.id} style={styles.fileCard}>
                    <View style={styles.fileHeader}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fileName} numberOfLines={1}>
                          {file.name}
                        </Text>
                        <Text style={styles.fileSize}>
                          File {index + 1} · {formatFileSize(file.size)}
                        </Text>
                      </View>
                      <Button compact mode="text" onPress={() => removeFile(file.id)} textColor={colors.danger}>
                        Remove
                      </Button>
                    </View>

                    <Text style={styles.fieldLabel}>Statement Type</Text>
                    <View style={styles.optionRow}>
                      {DOCUMENT_TYPE_OPTIONS.map((option) => (
                        <Button
                          key={option.value}
                          mode={file.accountTypeHint === option.value ? 'contained' : 'outlined'}
                          onPress={() => updateFile(file.id, { accountTypeHint: option.value as DocumentTypeHint })}
                          compact
                          style={styles.typeChip}
                          buttonColor={file.accountTypeHint === option.value ? colors.primary : undefined}
                          textColor={file.accountTypeHint === option.value ? '#FFFFFF' : colors.text}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </View>

                    <Text style={styles.fieldLabel}>Bank</Text>
                    <View style={styles.optionRow}>
                      {BANK_OPTIONS.map((option) => (
                        <Button
                          key={option.value || 'auto'}
                          mode={file.bankHint === option.value ? 'contained' : 'outlined'}
                          onPress={() => updateFile(file.id, { bankHint: option.value })}
                          compact
                          style={styles.bankChip}
                          buttonColor={file.bankHint === option.value ? colors.primary : undefined}
                          textColor={file.bankHint === option.value ? '#FFFFFF' : colors.text}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </View>

                    <TextInput
                      label="PDF Password (if encrypted)"
                      value={file.password}
                      onChangeText={(value) => updateFile(file.id, { password: value })}
                      mode="outlined"
                      secureTextEntry={!showPasswordFor[file.id]}
                      autoComplete="off"
                      textContentType="none"
                      importantForAutofill="no"
                      autoCorrect={false}
                      spellCheck={false}
                      right={(
                        <TextInput.Icon
                          icon={showPasswordFor[file.id] ? 'eye-off' : 'eye'}
                          onPress={() =>
                            setShowPasswordFor((current) => ({ ...current, [file.id]: !current[file.id] }))
                          }
                        />
                      )}
                      style={styles.input}
                      outlineColor={colors.border}
                      activeOutlineColor={colors.primary}
                    />
                    <Text style={styles.passwordHint}>
                      Auto mode lets the local LLM decide whether this PDF is a bank account statement or a credit card statement.
                    </Text>
                  </View>
                ))}
              </View>
            </>
          )}

          <Divider style={styles.divider} />

          <Button
            mode="contained"
            onPress={handleUpload}
            loading={uploading}
            disabled={uploading || selectedFiles.length === 0}
            icon="upload"
            style={styles.uploadButton}
            buttonColor={colors.primary}
          >
            Upload Queue
          </Button>

          {uploading && (
            <View style={styles.progressSection}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={styles.progressText}>
                {reviewingCount > 0
                  ? `${reviewingCount} document${reviewingCount > 1 ? 's' : ''} under local LLM review`
                  : 'Reviewing documents locally...'}
              </Text>
            </View>
          )}
        </Animated.View>
      </FadeInView>

      <FadeInView delay={130}>
        <View style={styles.notificationPanel}>
          <Text style={styles.sectionTitle}>Review Notifications</Text>
          {notifications.length === 0 ? (
            <Text style={styles.emptyNotification}>
              Upload notifications will appear here while the local LLM reviews each document.
            </Text>
          ) : (
            notifications.map((item) => (
              <View
                key={item.id}
                style={[
                  styles.notificationCard,
                  item.status === 'success'
                    ? styles.resultSuccess
                    : item.status === 'error'
                      ? styles.resultError
                      : styles.resultReviewing,
                ]}
              >
                <Text style={styles.notificationFile}>{item.fileName}</Text>
                <Text style={styles.notificationMessage}>{item.message}</Text>
                {(item.bankName || item.accountType) ? (
                  <Text style={styles.notificationMeta}>
                    {(item.bankName || 'Auto-detected')} · {item.accountType || 'type pending'}
                  </Text>
                ) : null}
              </View>
            ))
          )}
        </View>
      </FadeInView>
    </ScrollView>
  );
}

function normalizeReviewStatus(status: string): UploadNotification['status'] {
  if (
    status === 'reviewing' ||
    status === 'queued' ||
    status === 'pending' ||
    status === 'parsing' ||
    status === 'uploaded' ||
    status === 'classifying' ||
    status === 'extracting' ||
    status === 'validating'
  ) {
    return 'reviewing';
  }
  if (status === 'success' || status === 'parsed') {
    return 'success';
  }
  return 'error';
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  content: {
    padding: 16,
    paddingBottom: 28,
  },
  hero: {
    borderRadius: 0,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingHorizontal: 18,
    paddingTop: 16,
    paddingBottom: 14,
    backgroundColor: COLORS.surface,
    overflow: 'hidden',
    alignItems: 'flex-start',
  },
  card: {
    marginTop: 14,
    borderRadius: 0,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    paddingHorizontal: 14,
    paddingBottom: 12,
  },
  kicker: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.textSecondary,
    marginTop: 10,
    textTransform: 'uppercase',
    letterSpacing: 1.1,
  },
  title: {
    fontSize: 30,
    fontWeight: '800',
    color: COLORS.text,
    marginTop: 4,
    letterSpacing: -1.1,
  },
  subtitle: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 6,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  divider: {
    marginVertical: 16,
  },
  section: {
    marginBottom: 4,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 1.1,
  },
  pickButton: {
    borderColor: COLORS.primary,
    alignSelf: 'flex-start',
  },
  fileCard: {
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 12,
    marginBottom: 12,
    backgroundColor: COLORS.background,
  },
  fileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  fileName: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  fileSize: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  fieldLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.textSecondary,
    marginBottom: 8,
    marginTop: 8,
  },
  optionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 4,
  },
  typeChip: {
    marginBottom: 4,
  },
  bankChip: {
    marginBottom: 4,
  },
  input: {
    marginTop: 8,
    backgroundColor: COLORS.surface,
  },
  passwordHint: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 6,
    lineHeight: 17,
  },
  uploadButton: {
    paddingVertical: 4,
  },
  progressSection: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 16,
    gap: 8,
  },
  progressText: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },
  notificationPanel: {
    marginTop: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    padding: 14,
  },
  emptyNotification: {
    fontSize: 13,
    color: COLORS.textSecondary,
  },
  notificationCard: {
    marginBottom: 10,
    borderWidth: 1,
    padding: 12,
  },
  notificationFile: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
  },
  notificationMessage: {
    fontSize: 13,
    color: COLORS.text,
    marginTop: 4,
  },
  notificationMeta: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 4,
  },
  resultReviewing: {
    borderColor: COLORS.primary,
    backgroundColor: 'rgba(37, 99, 235, 0.10)',
  },
  resultSuccess: {
    borderColor: COLORS.success,
    backgroundColor: 'rgba(22, 163, 74, 0.12)',
  },
  resultError: {
    borderColor: COLORS.danger,
    backgroundColor: 'rgba(220, 38, 38, 0.12)',
  },
});
