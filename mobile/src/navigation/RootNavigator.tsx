import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { ActivityIndicator, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import * as api from '../api/client';
import AuthStack from './AuthStack';
import MainTabs from './MainTabs';
import TransactionDetailScreen from '../screens/TransactionDetailScreen';
import SmsSyncScreen from '../screens/SmsSyncScreen';
import UploadScreen from '../screens/UploadScreen';
import StatementsScreen from '../screens/StatementsScreen';
import BudgetsScreen from '../screens/BudgetsScreen';
import BillsScreen from '../screens/BillsScreen';
import OnboardingScreen from '../screens/OnboardingScreen';
import AccountsScreen from '../screens/AccountsScreen';
import AssistantScreen from '../screens/AssistantScreen';
import NetWorthScreen from '../screens/NetWorthScreen';
import SubscriptionsScreen from '../screens/SubscriptionsScreen';
import TaxScreen from '../screens/TaxScreen';
import StatementReviewScreen from '../screens/StatementReviewScreen';
import { useAppTheme } from '../theme/AppThemeProvider';
import type { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const { isLoading, isAuthenticated } = useAuth();
  const { colors } = useAppTheme();
  const onboardingQuery = useQuery({
    queryKey: ['onboarding-status'],
    queryFn: api.getOnboardingStatus,
    enabled: isAuthenticated,
    retry: 1,
  });
  const needsOnboarding = isAuthenticated && !onboardingQuery.isError && onboardingQuery.data?.completed === false;

  if (isLoading || (isAuthenticated && onboardingQuery.isLoading)) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!isAuthenticated) {
    return <AuthStack />;
  }

  return (
    <Stack.Navigator
      screenOptions={{
        animation: 'slide_from_right',
        gestureEnabled: true,
        contentStyle: { backgroundColor: colors.background },
        headerStyle: { backgroundColor: colors.surface },
        headerTintColor: colors.text,
        headerTitleStyle: {
          fontWeight: '800',
        },
        headerShadowVisible: false,
      }}
    >
      {needsOnboarding ? (
        <Stack.Screen name="Onboarding" component={OnboardingScreen} options={{ title: 'Onboarding' }} />
      ) : null}
      <Stack.Screen name="MainTabs" component={MainTabs} options={{ headerShown: false }} />
      <Stack.Screen name="Accounts" component={AccountsScreen} options={{ title: 'Accounts' }} />
      <Stack.Screen name="Assistant" component={AssistantScreen} options={{ title: 'Assistant' }} />
      <Stack.Screen name="NetWorth" component={NetWorthScreen} options={{ title: 'Net Worth' }} />
      <Stack.Screen name="Subscriptions" component={SubscriptionsScreen} options={{ title: 'Subscriptions' }} />
      <Stack.Screen name="Tax" component={TaxScreen} options={{ title: 'Tax & Audit' }} />
      <Stack.Screen name="StatementReview" component={StatementReviewScreen} options={{ title: 'Statement Review' }} />
      <Stack.Screen name="TransactionDetail" component={TransactionDetailScreen} options={{ title: 'Transaction' }} />
      <Stack.Screen name="SmsSync" component={SmsSyncScreen} options={{ title: 'SMS Sync' }} />
      <Stack.Screen name="Upload" component={UploadScreen} options={{ title: 'Upload Statement' }} />
      <Stack.Screen name="Statements" component={StatementsScreen} options={{ title: 'Statements' }} />
      <Stack.Screen name="Budgets" component={BudgetsScreen} options={{ title: 'Budgets' }} />
      <Stack.Screen name="Bills" component={BillsScreen} options={{ title: 'Bills' }} />
    </Stack.Navigator>
  );
}
