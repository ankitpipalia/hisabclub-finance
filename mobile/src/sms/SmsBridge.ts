/**
 * Platform-gated SMS bridge.
 * On Android: calls the native SmsReader module for reading SMS,
 *   uses PermissionsAndroid for permission requests.
 * On iOS/web: no-op (SMS reading not available).
 */

import { Platform, PermissionsAndroid } from 'react-native';
import type { RawSms } from './types';

// This will be replaced with the actual native module import after expo prebuild
let NativeSmsReader: {
  readInbox(sinceTimestamp: number): Promise<RawSms[]>;
  hasPermission(): Promise<boolean>;
} | null = null;

// Try to load native module (will fail gracefully on iOS/web)
if (Platform.OS === 'android') {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    NativeSmsReader = require('../modules/sms-reader').default;
  } catch {
    // Native module not available (running in Expo Go or iOS)
  }
}

export async function isSmsAvailable(): Promise<boolean> {
  return Platform.OS === 'android' && NativeSmsReader !== null;
}

export async function hasSmsPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;
  const result = await PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.READ_SMS);
  return result;
}

export async function requestSmsPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;
  const granted = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.READ_SMS,
    {
      title: 'SMS Permission',
      message:
        'HisabClub needs access to read your bank transaction SMS for automatic expense tracking. We only read bank messages - OTPs and personal messages are never accessed.',
      buttonPositive: 'Allow',
      buttonNegative: 'Deny',
    },
  );
  return granted === PermissionsAndroid.RESULTS.GRANTED;
}

export async function readSmsInbox(sinceTimestamp: number): Promise<RawSms[]> {
  if (!NativeSmsReader) return [];
  return NativeSmsReader.readInbox(sinceTimestamp);
}
