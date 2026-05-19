import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
  Linking,
} from 'react-native';
import { TextInput, Button, IconButton, Menu } from 'react-native-paper';
import { useAuth } from '../auth/AuthContext';
import * as api from '../api/client';
import { getServerUrl, isDefaultServerUrl, normalizeServerUrl, resetServerUrl, setServerUrl } from '../utils/storage';
import { APP_NAME, DEFAULT_API_DOMAIN, DEFAULT_API_URL } from '../utils/constants';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import AnimatedOrbs from '../components/AnimatedOrbs';
import BrandMark from '../components/BrandMark';
import FadeInView from '../components/FadeInView';
import { useToast } from '../components/ui/Toast';

export default function LoginScreen() {
  const { setAuthenticated } = useAuth();
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const toast = useToast();
  const fadeAnim = useRef(new Animated.Value(0)).current;

  const [serverUrl, setServerUrlLocal] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [isSetupMode, setIsSetupMode] = useState(false);
  const [isForgotMode, setIsForgotMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'ok' | 'fail'>('idle');
  const [serverMenuVisible, setServerMenuVisible] = useState(false);
  const [showCustomServer, setShowCustomServer] = useState(false);
  const [resetMessage, setResetMessage] = useState('');
  const [resetPreviewUrl, setResetPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    getServerUrl().then((url) => {
      const resolved = url || DEFAULT_API_URL;
      setServerUrlLocal(resolved);
      setShowCustomServer(!isDefaultServerUrl(resolved));
    });
  }, []);

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 380,
      useNativeDriver: true,
    }).start();
  }, [fadeAnim]);

  const handleSaveUrl = async () => {
    if (!showCustomServer) {
      await resetServerUrl();
      setServerUrlLocal(DEFAULT_API_URL);
      return;
    }

    const trimmed = normalizeServerUrl(serverUrl);
    if (!trimmed) {
      toast.warning('Please enter a server URL');
      return;
    }
    await setServerUrl(trimmed);
    setServerUrlLocal(trimmed);
  };

  const handleTestConnection = async () => {
    const trimmed = showCustomServer ? normalizeServerUrl(serverUrl) : DEFAULT_API_URL;
    if (!trimmed) {
      toast.warning('Please enter a server URL first');
      return;
    }
    await setServerUrl(trimmed);
    setServerUrlLocal(trimmed);
    setTestingConnection(true);
    setConnectionStatus('idle');
    try {
      const ok = await api.testConnection();
      setConnectionStatus(ok ? 'ok' : 'fail');
      if (!ok) {
        toast.error('Could not reach the server. Check the URL and try again.');
      }
    } catch {
      setConnectionStatus('fail');
      toast.error('Could not reach the server.');
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSubmit = async () => {
    if (!email.trim()) {
      toast.warning('Email is required');
      return;
    }
    if (!isForgotMode && !password.trim()) {
      toast.warning('Email and password are required');
      return;
    }
    if (isSetupMode && !isForgotMode && !displayName.trim()) {
      toast.warning('Display name is required for setup');
      return;
    }

    if (showCustomServer) {
      await setServerUrl(normalizeServerUrl(serverUrl));
    } else {
      await resetServerUrl();
      setServerUrlLocal(DEFAULT_API_URL);
    }

    setLoading(true);
    try {
      setResetMessage('');
      setResetPreviewUrl(null);
      if (isForgotMode) {
        const result = await api.requestPasswordReset(email.trim());
        setResetMessage(result.message);
        setResetPreviewUrl(result.preview_url);
      } else if (isSetupMode) {
        await api.register({
          email: email.trim(),
          display_name: displayName.trim(),
          password: password.trim(),
          first_name: firstName.trim() || undefined,
          last_name: lastName.trim() || undefined,
        });
      } else {
        await api.login(email.trim(), password.trim());
      }
      if (!isForgotMode) {
        setAuthenticated(true);
      }
    } catch (err: any) {
      toast.error(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <AnimatedOrbs />
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.menuRow}>
          <Menu
            visible={serverMenuVisible}
            onDismiss={() => setServerMenuVisible(false)}
            anchor={(
              <IconButton
                icon="dots-vertical"
                size={20}
                iconColor={colors.text}
                onPress={() => setServerMenuVisible(true)}
                style={styles.menuButton}
              />
            )}
            contentStyle={{ backgroundColor: colors.surface }}
          >
            <Menu.Item
              leadingIcon="server-network"
              onPress={async () => {
                setServerMenuVisible(false);
                setShowCustomServer(false);
                setConnectionStatus('idle');
                await resetServerUrl();
                setServerUrlLocal(DEFAULT_API_URL);
              }}
              title="Use HisabClub Dev"
            />
            <Menu.Item
              leadingIcon="cog-outline"
              onPress={() => {
                setServerMenuVisible(false);
                setShowCustomServer(true);
                setServerUrlLocal((current) => normalizeServerUrl(current || DEFAULT_API_URL));
              }}
              title="Custom self-hosted domain"
            />
          </Menu>
        </View>
        <FadeInView>
          <View style={styles.hero}>
            <BrandMark size={76} />
            <Text style={styles.appName}>{APP_NAME}</Text>
            <Text style={styles.tagline}>Private finance tracking for your statements and SMS</Text>
          </View>
        </FadeInView>

        <FadeInView delay={80}>
          <Animated.View style={[styles.card, { opacity: fadeAnim }]}>
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Server Configuration</Text>
              {!showCustomServer && (
                <View style={styles.serverSummary}>
                  <Text style={styles.serverLabel}>Default domain</Text>
                  <Text style={styles.serverValue}>{DEFAULT_API_DOMAIN}</Text>
                  <Text style={styles.serverHint}>
                    Open the 3-dot menu to use a custom self-hosted backend.
                  </Text>
                </View>
              )}
              {showCustomServer && (
                <TextInput
                  label="Server URL"
                  value={serverUrl}
                  onChangeText={setServerUrlLocal}
                  mode="outlined"
                  placeholder="https://your-server.com or https://your-server.com/api/v1"
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="url"
                  autoComplete="off"
                  textContentType="none"
                  importantForAutofill="no"
                  style={styles.input}
                  outlineColor={colors.border}
                  activeOutlineColor={colors.primary}
                />
              )}
              <View style={styles.urlButtons}>
                {showCustomServer && (
                  <Button
                    mode="text"
                    onPress={handleSaveUrl}
                    style={styles.inlineButton}
                    textColor={colors.primary}
                  >
                    Save
                  </Button>
                )}
                <Button
                  mode="outlined"
                  onPress={handleTestConnection}
                  loading={testingConnection}
                  disabled={testingConnection}
                  style={styles.urlButton}
                  textColor={colors.primary}
                >
                  Test Connection
                </Button>
              </View>
              {connectionStatus === 'ok' && (
                <Text style={styles.statusOk}>Connected successfully</Text>
              )}
              {connectionStatus === 'fail' && (
                <Text style={styles.statusFail}>Connection failed</Text>
              )}
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>
                {isForgotMode ? 'Reset Password' : isSetupMode ? 'Create Account' : 'Sign In'}
              </Text>
              {resetMessage ? <Text style={styles.statusOk}>{resetMessage}</Text> : null}
              {resetPreviewUrl ? (
                <Button
                  mode="text"
                  onPress={() => Linking.openURL(resetPreviewUrl)}
                  textColor={colors.primary}
                  style={styles.previewButton}
                >
                  Open Reset Link
                </Button>
              ) : null}

              <TextInput
                label="Email"
                value={email}
                onChangeText={setEmail}
                mode="outlined"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                autoComplete="email"
                textContentType="emailAddress"
                style={styles.input}
                outlineColor={colors.border}
                activeOutlineColor={colors.primary}
              />

              {!isForgotMode && (
                <TextInput
                  label="Password"
                  value={password}
                  onChangeText={setPassword}
                  mode="outlined"
                  secureTextEntry
                  autoComplete="password"
                  textContentType="password"
                  style={styles.input}
                  outlineColor={colors.border}
                  activeOutlineColor={colors.primary}
                />
              )}

              {isSetupMode && !isForgotMode && (
                <>
                  <TextInput
                    label="Display Name"
                    value={displayName}
                    onChangeText={setDisplayName}
                    mode="outlined"
                    autoCapitalize="words"
                    style={styles.input}
                    outlineColor={colors.border}
                    activeOutlineColor={colors.primary}
                  />
                  <TextInput
                    label="First Name"
                    value={firstName}
                    onChangeText={setFirstName}
                    mode="outlined"
                    autoCapitalize="words"
                    style={styles.input}
                    outlineColor={colors.border}
                    activeOutlineColor={colors.primary}
                  />
                  <TextInput
                    label="Last Name"
                    value={lastName}
                    onChangeText={setLastName}
                    mode="outlined"
                    autoCapitalize="words"
                    style={styles.input}
                    outlineColor={colors.border}
                    activeOutlineColor={colors.primary}
                  />
                </>
              )}

              <Button
                mode="contained"
                onPress={handleSubmit}
                loading={loading}
                disabled={loading}
                style={styles.submitButton}
                buttonColor={colors.primary}
              >
                {isForgotMode ? 'Send Reset Link' : isSetupMode ? 'Create Account' : 'Sign In'}
              </Button>

              {!isForgotMode && (
                <Button
                  mode="text"
                  onPress={() => setIsSetupMode(!isSetupMode)}
                  style={styles.toggleButton}
                  textColor={colors.primary}
                >
                  {isSetupMode
                    ? 'Already have an account? Sign In'
                    : 'First time? Create Account'}
                </Button>
              )}
              {!isSetupMode && (
                <Button
                  mode="text"
                  onPress={() => {
                    setIsForgotMode(!isForgotMode);
                    setResetMessage('');
                    setResetPreviewUrl(null);
                  }}
                  style={styles.toggleButton}
                  textColor={colors.primary}
                >
                  {isForgotMode ? 'Back to Sign In' : 'Forgot Password?'}
                </Button>
              )}
            </View>
          </Animated.View>
        </FadeInView>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const createStyles = (COLORS: AppThemeColors) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scrollContent: {
    flexGrow: 1,
    padding: 24,
    justifyContent: 'center',
  },
  menuRow: {
    alignItems: 'flex-end',
    marginBottom: 12,
  },
  menuButton: {
    margin: 0,
  },
  hero: {
    alignItems: 'center',
    marginBottom: 22,
  },
  appName: {
    fontSize: 36,
    fontWeight: '800',
    color: COLORS.text,
    marginTop: 14,
    letterSpacing: -1.2,
  },
  tagline: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 6,
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 1.3,
  },
  card: {
    backgroundColor: COLORS.surface,
    borderRadius: 0,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingHorizontal: 18,
    paddingTop: 16,
    paddingBottom: 10,
  },
  section: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
  },
  input: {
    marginBottom: 12,
    backgroundColor: COLORS.surface,
  },
  serverSummary: {
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 12,
  },
  serverLabel: {
    fontSize: 11,
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 1.1,
  },
  serverValue: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
    marginTop: 6,
  },
  serverHint: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 6,
  },
  urlButtons: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
  },
  urlButton: {
    borderColor: COLORS.primary,
  },
  inlineButton: {
    alignSelf: 'center',
  },
  statusOk: {
    color: COLORS.success,
    fontSize: 13,
    marginTop: 4,
  },
  statusFail: {
    color: COLORS.danger,
    fontSize: 13,
    marginTop: 4,
  },
  submitButton: {
    marginTop: 8,
    paddingVertical: 4,
  },
  previewButton: {
    alignSelf: 'flex-start',
    marginBottom: 8,
  },
  toggleButton: {
    marginTop: 8,
  },
});
