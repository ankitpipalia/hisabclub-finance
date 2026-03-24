import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { ActivityIndicator, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import AuthStack from './AuthStack';
import MainTabs from './MainTabs';
import TransactionDetailScreen from '../screens/TransactionDetailScreen';
import SmsSyncScreen from '../screens/SmsSyncScreen';
import UploadScreen from '../screens/UploadScreen';
import StatementsScreen from '../screens/StatementsScreen';
import BudgetsScreen from '../screens/BudgetsScreen';
import BillsScreen from '../screens/BillsScreen';
import { useAppTheme } from '../theme/AppThemeProvider';
import type { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const { isLoading, isAuthenticated } = useAuth();
  const { colors } = useAppTheme();

  if (isLoading) {
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
      <Stack.Screen name="MainTabs" component={MainTabs} options={{ headerShown: false }} />
      <Stack.Screen name="TransactionDetail" component={TransactionDetailScreen} options={{ title: 'Transaction' }} />
      <Stack.Screen name="SmsSync" component={SmsSyncScreen} options={{ title: 'SMS Sync' }} />
      <Stack.Screen name="Upload" component={UploadScreen} options={{ title: 'Upload Statement' }} />
      <Stack.Screen name="Statements" component={StatementsScreen} options={{ title: 'Statements' }} />
      <Stack.Screen name="Budgets" component={BudgetsScreen} options={{ title: 'Budgets' }} />
      <Stack.Screen name="Bills" component={BillsScreen} options={{ title: 'Bills' }} />
    </Stack.Navigator>
  );
}
