import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';

export type AuthStackParamList = {
  Login: undefined;
};

export type MainTabParamList = {
  Home: undefined;
  Transactions: undefined;
  Insights: undefined;
  Tax: undefined;
  Settings: undefined;
};

export type RootStackParamList = {
  MainTabs: undefined;
  Onboarding: undefined;
  Accounts: undefined;
  Assistant: { threadId?: string } | undefined;
  NetWorth: undefined;
  Subscriptions: undefined;
  Tax: undefined;
  StatementReview: { statementId: string };
  TransactionDetail: { id: string };
  SmsSync: undefined;
  Upload: undefined;
  Statements: undefined;
  Budgets: undefined;
  Bills: undefined;
};

export type AuthScreenProps = NativeStackScreenProps<AuthStackParamList, 'Login'>;
export type MainTabProps<T extends keyof MainTabParamList> = BottomTabScreenProps<MainTabParamList, T>;
export type RootStackProps<T extends keyof RootStackParamList> = NativeStackScreenProps<RootStackParamList, T>;
