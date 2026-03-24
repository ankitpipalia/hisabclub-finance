/**
 * SMS Reader native module interface.
 * This module reads SMS from the Android inbox using ContentResolver.
 *
 * After running `npx expo prebuild`, the Kotlin native code at
 * android/app/src/main/java/.../SmsReaderModule.kt will be available.
 *
 * For now, this provides the TypeScript interface and a mock for development.
 */

import { NativeModules, Platform } from 'react-native';
import type { RawSms } from '../../sms/types';

interface SmsReaderInterface {
  readInbox(sinceTimestamp: number): Promise<RawSms[]>;
  hasPermission(): Promise<boolean>;
  requestPermission(): Promise<boolean>;
}

const NativeSmsReaderModule: SmsReaderInterface | undefined =
  Platform.OS === 'android' ? NativeModules.SmsReaderModule : undefined;

const SmsReader: SmsReaderInterface = {
  async readInbox(sinceTimestamp: number): Promise<RawSms[]> {
    if (!NativeSmsReaderModule) return [];
    return NativeSmsReaderModule.readInbox(sinceTimestamp);
  },

  async hasPermission(): Promise<boolean> {
    if (!NativeSmsReaderModule) return false;
    return NativeSmsReaderModule.hasPermission();
  },

  async requestPermission(): Promise<boolean> {
    if (!NativeSmsReaderModule) return false;
    return NativeSmsReaderModule.requestPermission();
  },
};

export default SmsReader;
