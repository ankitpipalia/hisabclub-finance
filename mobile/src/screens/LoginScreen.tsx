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
} from 'react-native';
import { TextInput, Button } from 'react-native-paper';
import { useAuth } from '../auth/AuthContext';
import * as api from '../api/client';
import { getServerUrl, setServerUrl } from '../utils/storage';
import { APP_NAME } from '../utils/constants';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import AnimatedOrbs from '../components/AnimatedOrbs';
import BrandMark from '../components/BrandMark';
import FadeInView from '../components/FadeInView';

export default function LoginScreen() {
  const { setAuthenticated } = useAuth();
  const { colors } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const fadeAnim = useRef(new Animated.Value(0)).current;

  const [serverUrl, setServerUrlLocal] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [isSetupMode, setIsSetupMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'ok' | 'fail'>('idle');

  useEffect(() => {
    getServerUrl().then((url) => {
      // Pre-populate with stored URL or the default
      setServerUrlLocal(url || 'http://localhost:8000/api/v1');
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
    const trimmed = serverUrl.trim();
    if (!trimmed) {
      Alert.alert('Error', 'Please enter a server URL');
      return;
    }
    await setServerUrl(trimmed);
  };

  const handleTestConnection = async () => {
    const trimmed = serverUrl.trim();
    if (!trimmed) {
      Alert.alert('Error', 'Please enter a server URL first');
      return;
    }
    await setServerUrl(trimmed);
    setTestingConnection(true);
    setConnectionStatus('idle');
    try {
      const ok = await api.testConnection();
      setConnectionStatus(ok ? 'ok' : 'fail');
      if (!ok) {
        Alert.alert('Connection Failed', 'Could not reach the server. Check the URL and try again.');
      }
    } catch {
      setConnectionStatus('fail');
      Alert.alert('Connection Failed', 'Could not reach the server.');
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSubmit = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert('Error', 'Email and password are required');
      return;
    }
    if (isSetupMode && !displayName.trim()) {
      Alert.alert('Error', 'Display name is required for setup');
      return;
    }

    // Save the server URL before attempting auth
    if (serverUrl.trim()) {
      await setServerUrl(serverUrl.trim());
    }

    setLoading(true);
    try {
      if (isSetupMode) {
        await api.setup({
          email: email.trim(),
          display_name: displayName.trim(),
          password: password.trim(),
        });
      } else {
        await api.login(email.trim(), password.trim());
      }
      setAuthenticated(true);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Authentication failed');
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
              <TextInput
                label="Server URL"
                value={serverUrl}
                onChangeText={setServerUrlLocal}
                mode="outlined"
                placeholder="https://your-server.com/api/v1"
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
              <View style={styles.urlButtons}>
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
                {isSetupMode ? 'Create Account' : 'Sign In'}
              </Text>

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

              {isSetupMode && (
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
              )}

              <Button
                mode="contained"
                onPress={handleSubmit}
                loading={loading}
                disabled={loading}
                style={styles.submitButton}
                buttonColor={colors.primary}
              >
                {isSetupMode ? 'Create Account' : 'Sign In'}
              </Button>

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
  urlButtons: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  urlButton: {
    borderColor: COLORS.primary,
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
  toggleButton: {
    marginTop: 8,
  },
});
