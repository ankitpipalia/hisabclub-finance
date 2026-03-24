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
import { BANKS } from '../utils/constants';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import AnimatedOrbs from '../components/AnimatedOrbs';
import BrandMark from '../components/BrandMark';
import FadeInView from '../components/FadeInView';

type StatementType = 'credit_card' | 'bank_account';

interface SelectedFile {
  uri: string;
  name: string;
  size: number | undefined;
}

interface UploadResultState {
  type: 'success' | 'error';
  message: string;
  canReprocess?: boolean;
}

export default function UploadScreen() {
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const cardAnim = useRef(new Animated.Value(0)).current;

  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [bankHint, setBankHint] = useState('');
  const [statementType, setStatementType] = useState<StatementType>('bank_account');
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResultState | null>(null);

  useEffect(() => {
    Animated.timing(cardAnim, {
      toValue: 1,
      duration: 350,
      useNativeDriver: true,
    }).start();
  }, [cardAnim]);

  const handlePickFile = async () => {
    try {
      const pickResult = await DocumentPicker.getDocumentAsync({
        type: 'application/pdf',
        copyToCacheDirectory: true,
      });

      if (!pickResult.canceled && pickResult.assets && pickResult.assets.length > 0) {
        const asset = pickResult.assets[0];
        setSelectedFile({
          uri: asset.uri,
          name: asset.name,
          size: asset.size,
        });
        setResult(null);
      }
    } catch {
      Alert.alert('Error', 'Failed to pick document');
    }
  };

  const getUploadError = (err: any): UploadResultState => {
    if (err?.status === 409) {
      return {
        type: 'error',
        message: 'This statement already exists. Tap "Reprocess Existing PDF" to parse it again.',
        canReprocess: true,
      };
    }

    if (err?.status === 0) {
      return {
        type: 'error',
        message: err.message || 'Could not reach backend server. Verify Server URL and backend status.',
      };
    }

    if (typeof err?.message === 'string' && err.message.trim()) {
      return { type: 'error', message: err.message };
    }

    return { type: 'error', message: 'Upload failed. Please try again.' };
  };

  const handleUpload = async (forceReprocess: boolean = false) => {
    if (!selectedFile) {
      Alert.alert('Error', 'Please select a PDF file first');
      return;
    }

    setUploading(true);
    setResult(null);
    try {
      // Build bank_hint with account type info
      const hintParts: string[] = [];
      if (bankHint) hintParts.push(bankHint);
      hintParts.push(statementType === 'credit_card' ? 'credit_card' : 'bank_account');
      const combinedHint = hintParts.join(':');

      const response = await api.uploadPdf(
        selectedFile.uri,
        selectedFile.name,
        password || undefined,
        combinedHint,
        forceReprocess,
      );
      setResult({
        type: 'success',
        message: response.message || `Statement uploaded successfully. Status: ${response.status}`,
      });
      // Reset form after successful upload
      setSelectedFile(null);
      setPassword('');
      setBankHint('');
    } catch (err: any) {
      setResult(getUploadError(err));
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
          <Text style={styles.title}>Upload Document</Text>
          <Text style={styles.subtitle}>
            {statementType === 'credit_card'
              ? 'Upload your monthly credit card statement PDF'
              : 'Upload your bank account statement PDF (savings or current)'}
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
        <Divider style={styles.divider} />

        {/* Statement Type Picker */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Statement Type</Text>
          <View style={styles.typeRow}>
            <Button
              mode={statementType === 'credit_card' ? 'contained' : 'outlined'}
              onPress={() => setStatementType('credit_card')}
              icon="credit-card"
              style={styles.typeButton}
              buttonColor={statementType === 'credit_card' ? colors.primary : undefined}
              textColor={statementType === 'credit_card' ? '#FFFFFF' : colors.text}
            >
              Credit Card
            </Button>
            <Button
              mode={statementType === 'bank_account' ? 'contained' : 'outlined'}
              onPress={() => setStatementType('bank_account')}
              icon="bank"
              style={styles.typeButton}
              buttonColor={statementType === 'bank_account' ? colors.primary : undefined}
              textColor={statementType === 'bank_account' ? '#FFFFFF' : colors.text}
            >
              Bank Account
            </Button>
          </View>
        </View>

        <Divider style={styles.divider} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Select File</Text>
          <Button
            mode="outlined"
            onPress={handlePickFile}
            icon="file-pdf-box"
            style={styles.pickButton}
            textColor={colors.primary}
          >
            {selectedFile ? 'Change File' : 'Pick PDF File'}
          </Button>

          {selectedFile && (
            <View style={styles.fileInfo}>
              <Text style={styles.fileName} numberOfLines={1}>
                {selectedFile.name}
              </Text>
              <Text style={styles.fileSize}>
                {formatFileSize(selectedFile.size)}
              </Text>
            </View>
          )}
        </View>

        <Divider style={styles.divider} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Options</Text>

          <TextInput
            label="PDF Password (if encrypted)"
            value={password}
            onChangeText={setPassword}
            mode="outlined"
            secureTextEntry={!showPassword}
            autoComplete="off"
            textContentType="none"
            importantForAutofill="noExcludeDescendants"
            autoCorrect={false}
            spellCheck={false}
            right={(
              <TextInput.Icon
                icon={showPassword ? 'eye-off' : 'eye'}
                onPress={() => setShowPassword((prev) => !prev)}
              />
            )}
            style={styles.input}
            outlineColor={colors.border}
            activeOutlineColor={colors.primary}
          />
          <Text style={styles.passwordHint}>
            For statements, this is a document password, not your account password.
          </Text>

          <Text style={styles.fieldLabel}>Bank Hint (optional)</Text>
          <View style={styles.bankRow}>
            {BANKS.map((bank) => (
              <Button
                key={bank}
                mode={bankHint === bank ? 'contained' : 'outlined'}
                onPress={() => setBankHint(bankHint === bank ? '' : bank)}
                compact
                style={styles.bankChip}
                buttonColor={bankHint === bank ? colors.primary : undefined}
                textColor={bankHint === bank ? '#FFFFFF' : colors.text}
              >
                {bank}
              </Button>
            ))}
          </View>
        </View>

        <Divider style={styles.divider} />

        <Button
          mode="contained"
          onPress={() => handleUpload()}
          loading={uploading}
          disabled={uploading || !selectedFile}
          icon="upload"
          style={styles.uploadButton}
          buttonColor={colors.primary}
        >
          Upload Statement
        </Button>

        {uploading && (
          <View style={styles.progressSection}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={styles.progressText}>Uploading and processing...</Text>
          </View>
        )}

        {result && (
          <View
            style={[
              styles.resultBanner,
              result.type === 'success' ? styles.resultSuccess : styles.resultError,
            ]}
          >
            <Text
              style={[
                styles.resultText,
                { color: result.type === 'success' ? colors.success : colors.danger },
              ]}
            >
              {result.message}
            </Text>
            {result.type === 'error' && result.canReprocess && selectedFile && (
              <Button
                mode="outlined"
                onPress={() => handleUpload(true)}
                disabled={uploading}
                style={styles.reprocessButton}
                textColor={colors.danger}
              >
                Reprocess Existing PDF
              </Button>
            )}
          </View>
        )}
        </Animated.View>
      </FadeInView>
    </ScrollView>
  );
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
  typeRow: {
    flexDirection: 'row',
    gap: 12,
  },
  typeButton: {
    flex: 1,
  },
  pickButton: {
    borderColor: COLORS.primary,
    alignSelf: 'flex-start',
  },
  fileInfo: {
    backgroundColor: COLORS.surface,
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
  },
  fileName: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  fileSize: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
  },
  input: {
    marginBottom: 4,
    backgroundColor: COLORS.surface,
  },
  passwordHint: {
    fontSize: 12,
    color: COLORS.textSecondary,
    fontStyle: 'normal',
    marginBottom: 12,
    lineHeight: 17,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.textSecondary,
    marginBottom: 8,
  },
  bankRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  bankChip: {
    marginBottom: 4,
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
  resultBanner: {
    marginTop: 16,
    padding: 16,
    borderRadius: 8,
    borderWidth: 1,
  },
  resultSuccess: {
    backgroundColor: 'rgba(22, 163, 74, 0.12)',
    borderColor: COLORS.success,
  },
  resultError: {
    backgroundColor: 'rgba(220, 38, 38, 0.12)',
    borderColor: COLORS.danger,
  },
  resultText: {
    fontSize: 14,
    fontWeight: '500',
  },
  reprocessButton: {
    marginTop: 12,
    borderColor: COLORS.danger,
    alignSelf: 'flex-start',
  },
});
