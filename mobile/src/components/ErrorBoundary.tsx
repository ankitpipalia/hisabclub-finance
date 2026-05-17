import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

type Props = {
  children: React.ReactNode;
  onReset?: () => void;
};

type State = {
  error: Error | null;
  componentStack: string | null;
};

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null, componentStack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('[HisabClub] uncaught render error', error, info);
    this.setState({ componentStack: info.componentStack ?? null });
  }

  reset = () => {
    this.setState({ error: null, componentStack: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.error) {
      return (
        <ScrollView contentContainerStyle={styles.container}>
          <Text style={styles.title}>Something went wrong</Text>
          <Text style={styles.body}>
            HisabClub hit an unexpected error. Your data is safe. Tap Reload to
            restart the screen, or restart the app if the issue persists.
          </Text>
          <View style={styles.errBox}>
            <Text style={styles.errLabel}>{this.state.error.name}</Text>
            <Text style={styles.errMessage}>{this.state.error.message}</Text>
          </View>
          <Pressable style={styles.button} onPress={this.reset}>
            <Text style={styles.buttonLabel}>Reload</Text>
          </Pressable>
        </ScrollView>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    padding: 24,
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    marginBottom: 12,
    color: '#1F1B16',
  },
  body: {
    fontSize: 15,
    color: '#4A4540',
    marginBottom: 16,
    lineHeight: 21,
  },
  errBox: {
    backgroundColor: '#FFF1EF',
    borderColor: '#E68A82',
    borderWidth: 1,
    padding: 12,
    borderRadius: 8,
    marginBottom: 20,
  },
  errLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: '#B11F1F',
    marginBottom: 4,
  },
  errMessage: {
    fontSize: 13,
    color: '#5A1414',
    fontFamily: 'Courier',
  },
  button: {
    backgroundColor: '#1851B2',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  buttonLabel: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
  },
});
