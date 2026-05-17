// Minimum Jest setup for HisabClub mobile.
// Mocks expo modules that don't run under jest-expo's jsdom-flavored env.

jest.mock('expo-secure-store', () => {
  const store = new Map();
  return {
    setItemAsync: jest.fn(async (key, value) => {
      store.set(key, value);
    }),
    getItemAsync: jest.fn(async (key) => store.get(key) ?? null),
    deleteItemAsync: jest.fn(async (key) => {
      store.delete(key);
    }),
  };
});

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-file-system', () => ({
  cacheDirectory: '/tmp/',
  documentDirectory: '/tmp/docs/',
  makeDirectoryAsync: jest.fn(),
  downloadAsync: jest.fn(async () => ({ uri: '/tmp/file.pdf' })),
}));

jest.mock('expo-file-system/legacy', () => ({
  cacheDirectory: '/tmp/',
  documentDirectory: '/tmp/docs/',
  makeDirectoryAsync: jest.fn(),
  downloadAsync: jest.fn(async () => ({ uri: '/tmp/file.pdf' })),
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(async () => ({ canceled: true, assets: [] })),
}));

// Silence the warnings RNTL prints from animations and act() boundaries during
// tests; they're not actionable in a unit suite.
const originalWarn = console.warn;
console.warn = (message, ...args) => {
  if (typeof message === 'string' && message.includes('not wrapped in act')) {
    return;
  }
  originalWarn(message, ...args);
};
