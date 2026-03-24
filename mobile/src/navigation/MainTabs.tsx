import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import DashboardScreen from '../screens/DashboardScreen';
import TransactionsScreen from '../screens/TransactionsScreen';
import InsightsScreen from '../screens/InsightsScreen';
import SettingsScreen from '../screens/SettingsScreen';
import { useAppTheme, type AppThemeColors } from '../theme/AppThemeProvider';
import type { MainTabParamList } from './types';

const Tab = createBottomTabNavigator<MainTabParamList>();

export default function MainTabs() {
  const { colors } = useAppTheme();
  const styles = React.useMemo(() => createStyles(colors), [colors]);

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        animation: 'shift',
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        headerStyle: styles.header,
        headerTitleStyle: styles.headerTitle,
        headerShadowVisible: false,
        tabBarStyle: styles.tabBar,
        tabBarLabelStyle: styles.tabLabel,
        tabBarIcon: ({ color, size }) => {
          const iconByRoute = {
            Home: 'view-dashboard-outline',
            Transactions: 'swap-horizontal',
            Insights: 'chart-line',
            Settings: 'cog-outline',
          } as const;
          return (
            <MaterialCommunityIcons
              name={iconByRoute[route.name]}
              color={color}
              size={size}
            />
          );
        },
      })}
    >
      <Tab.Screen
        name="Home"
        component={DashboardScreen}
        options={{ title: 'HisabClub', tabBarLabel: 'Home' }}
      />
      <Tab.Screen
        name="Transactions"
        component={TransactionsScreen}
        options={{ title: 'Transactions' }}
      />
      <Tab.Screen
        name="Insights"
        component={InsightsScreen}
        options={{ title: 'Insights' }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{ title: 'Settings' }}
      />
    </Tab.Navigator>
  );
}

const createStyles = (colors: AppThemeColors) => ({
  header: {
    backgroundColor: colors.surface,
  },
  headerTitle: {
    fontWeight: '800' as const,
    color: colors.text,
  },
  tabBar: {
    backgroundColor: colors.surface,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    height: 64,
    paddingBottom: 5,
    paddingTop: 5,
  },
  tabLabel: {
    fontSize: 11,
    fontWeight: '600' as const,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.8,
  },
});
