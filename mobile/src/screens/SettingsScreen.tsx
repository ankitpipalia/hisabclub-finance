import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Alert,
} from 'react-native';
import { TextInput, Button, Divider, ActivityIndicator } from 'react-native-paper';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import * as api from '../api/client';
import { getServerUrl, setServerUrl } from '../utils/storage';
import type { RootStackParamList } from '../navigation/types';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import BrandMark from '../components/BrandMark';
import FadeInView from '../components/FadeInView';
import AnimatedOrbs from '../components/AnimatedOrbs';

type NavProp = NativeStackNavigationProp<RootStackParamList>;

export default function SettingsScreen() {
  const navigation = useNavigation<NavProp>();
  const auth = useAuth();
  const { colors, mode, setMode } = useAppTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const [serverUrl, setServerUrlLocal] = useState('');
  const [savingUrl, setSavingUrl] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: () => api.getMe(),
  });

  useEffect(() => {
    getServerUrl().then((url) => {
      if (url) setServerUrlLocal(url);
    });
  }, []);

  const handleSaveUrl = async () => {
    const trimmed = serverUrl.trim();
    if (!trimmed) {
      Alert.alert('Error', 'Please enter a server URL');
      return;
    }
    setSavingUrl(true);
    try {
      await setServerUrl(trimmed);
      Alert.alert('Saved', 'Server URL updated');
    } catch {
      Alert.alert('Error', 'Failed to save server URL');
    } finally {
      setSavingUrl(false);
    }
  };

  const handleTestConnection = async () => {
    if (serverUrl.trim()) {
      await setServerUrl(serverUrl.trim());
    }
    setTestingConnection(true);
    try {
      const ok = await api.testConnection();
      if (ok) {
        Alert.alert('Success', 'Server is reachable');
      } else {
        Alert.alert('Failed', 'Could not connect to the server');
      }
    } catch {
      Alert.alert('Failed', 'Could not connect to the server');
    } finally {
      setTestingConnection(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout',
        style: 'destructive',
        onPress: () => auth.logout(),
      },
    ]);
  };

  const user = meQuery.data;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <FadeInView>
        <View style={styles.hero}>
          <AnimatedOrbs compact />
          <View style={styles.headerRow}>
            <BrandMark size={46} />
            <View>
              <Text style={styles.pageKicker}>Preferences</Text>
              <Text style={styles.pageTitle}>Settings</Text>
              <Text style={styles.pageSubtitle}>Manage app preferences and server configuration.</Text>
            </View>
          </View>
        </View>
      </FadeInView>

      <Divider style={styles.divider} />

      {/* Quick Navigation */}
      <FadeInView delay={70} style={styles.section}>
        <Text style={styles.sectionTitle}>Quick Access</Text>
        <View style={styles.navGrid}>
          <Button
            mode="outlined"
            onPress={() => navigation.navigate('Upload')}
            icon="file-upload"
            style={styles.navButton}
            textColor={colors.primary}
          >
            Upload
          </Button>
          <Button
            mode="outlined"
            onPress={() => navigation.navigate('Statements')}
            icon="file-document"
            style={styles.navButton}
            textColor={colors.primary}
          >
            Statements
          </Button>
          <Button
            mode="outlined"
            onPress={() => navigation.navigate('Budgets')}
            icon="wallet"
            style={styles.navButton}
            textColor={colors.primary}
          >
            Budgets
          </Button>
          <Button
            mode="outlined"
            onPress={() => navigation.navigate('Bills')}
            icon="receipt"
            style={styles.navButton}
            textColor={colors.primary}
          >
            Bills
          </Button>
        </View>
      </FadeInView>

      <Divider style={styles.divider} />

      <FadeInView delay={100} style={styles.section}>
        <Text style={styles.sectionTitle}>Appearance</Text>
        <View style={styles.buttonRow}>
          <Button
            mode={mode === 'auto' ? 'contained' : 'outlined'}
            onPress={() => setMode('auto')}
            style={styles.rowButton}
            buttonColor={mode === 'auto' ? colors.primary : undefined}
            textColor={mode === 'auto' ? '#FFFFFF' : colors.primary}
          >
            Auto
          </Button>
          <Button
            mode={mode === 'light' ? 'contained' : 'outlined'}
            onPress={() => setMode('light')}
            style={styles.rowButton}
            buttonColor={mode === 'light' ? colors.primary : undefined}
            textColor={mode === 'light' ? '#FFFFFF' : colors.primary}
          >
            Light
          </Button>
          <Button
            mode={mode === 'dark' ? 'contained' : 'outlined'}
            onPress={() => setMode('dark')}
            style={styles.rowButton}
            buttonColor={mode === 'dark' ? colors.primary : undefined}
            textColor={mode === 'dark' ? '#FFFFFF' : colors.primary}
          >
            Dark
          </Button>
        </View>
      </FadeInView>

      <Divider style={styles.divider} />

      <FadeInView delay={130} style={styles.section}>
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
        <View style={styles.buttonRow}>
          <Button
            mode="contained"
            onPress={handleSaveUrl}
            loading={savingUrl}
            disabled={savingUrl}
            style={styles.rowButton}
            buttonColor={colors.primary}
          >
            Save
          </Button>
          <Button
            mode="outlined"
            onPress={handleTestConnection}
            loading={testingConnection}
            disabled={testingConnection}
            style={styles.rowButton}
            textColor={colors.primary}
          >
            Test
          </Button>
        </View>
      </FadeInView>

      <Divider style={styles.divider} />

      <FadeInView delay={160} style={styles.section}>
        <Text style={styles.sectionTitle}>SMS Sync</Text>
        <Text style={styles.sectionDescription}>
          Sync financial SMS messages from your phone to automatically detect transactions.
        </Text>
        <Button
          mode="outlined"
          onPress={() => navigation.navigate('SmsSync')}
          icon="message-text"
          style={styles.smsSyncButton}
          textColor={colors.primary}
        >
          Open SMS Sync
        </Button>
      </FadeInView>

      <Divider style={styles.divider} />

      <FadeInView delay={190} style={styles.section}>
        <Text style={styles.sectionTitle}>Account</Text>
        {meQuery.isLoading ? (
          <ActivityIndicator size="small" color={colors.primary} />
        ) : user ? (
          <View style={styles.userInfo}>
            <View style={styles.userRow}>
              <Text style={styles.userLabel}>Name</Text>
              <Text style={styles.userValue}>{user.display_name}</Text>
            </View>
            <View style={styles.userRow}>
              <Text style={styles.userLabel}>Email</Text>
              <Text style={styles.userValue}>{user.email}</Text>
            </View>
          </View>
        ) : (
          <Text style={styles.errorText}>Could not load user info</Text>
        )}
      </FadeInView>

      <Divider style={styles.divider} />

      <Button
        mode="contained"
        onPress={handleLogout}
        style={styles.logoutButton}
        buttonColor={colors.danger}
        textColor="#FFFFFF"
      >
        Logout
      </Button>
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
  },
  hero: {
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    paddingHorizontal: 14,
    paddingVertical: 14,
    overflow: 'hidden',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  pageKicker: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 1.1,
  },
  pageTitle: {
    fontSize: 30,
    fontWeight: '800',
    color: COLORS.text,
    letterSpacing: -1.1,
  },
  pageSubtitle: {
    fontSize: 12,
    color: COLORS.textSecondary,
    marginTop: 2,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  section: {
    marginBottom: 4,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1.1,
  },
  sectionDescription: {
    fontSize: 13,
    color: COLORS.textSecondary,
    marginBottom: 12,
  },
  navGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  navButton: {
    borderColor: COLORS.border,
    flexGrow: 1,
    flexBasis: '45%',
  },
  input: {
    marginBottom: 12,
    backgroundColor: COLORS.surface,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
  },
  rowButton: {
    flex: 1,
  },
  divider: {
    marginVertical: 20,
  },
  smsSyncButton: {
    alignSelf: 'flex-start',
    borderColor: COLORS.primary,
  },
  userInfo: {
    backgroundColor: COLORS.surface,
    borderRadius: 0,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  userRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  userLabel: {
    fontSize: 14,
    color: COLORS.textSecondary,
  },
  userValue: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.text,
  },
  errorText: {
    fontSize: 14,
    color: COLORS.textSecondary,
    fontStyle: 'italic',
  },
  logoutButton: {
    marginTop: 8,
    paddingVertical: 4,
  },
});
