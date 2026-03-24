import { NavigationContainer } from '@react-navigation/native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PaperProvider } from 'react-native-paper';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, View } from 'react-native';
import { AuthProvider } from './auth/AuthContext';
import RootNavigator from './navigation/RootNavigator';
import { AppThemeProvider, useAppTheme } from './theme/AppThemeProvider';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 2 },
  },
});

function AppShell() {
  const { paperTheme, navigationTheme, isDark, ready, colors } = useAppTheme();

  if (!ready) {
    return (
      <View
        style={{
          flex: 1,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: colors.background,
        }}
      >
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <PaperProvider theme={paperTheme}>
      <AuthProvider>
        <NavigationContainer theme={navigationTheme}>
          <StatusBar style={isDark ? 'light' : 'dark'} />
          <RootNavigator />
        </NavigationContainer>
      </AuthProvider>
    </PaperProvider>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppThemeProvider>
        <AppShell />
      </AppThemeProvider>
    </QueryClientProvider>
  );
}
