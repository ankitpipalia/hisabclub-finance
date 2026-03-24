import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';

export type AuthStackParamList = {
  Login: undefined;
};

export type MainTabParamList = {
  Home: undefined;
  Transactions: undefined;
  Insights: undefined;
  Settings: undefined;
};

export type RootStackParamList = {
  MainTabs: undefined;
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
