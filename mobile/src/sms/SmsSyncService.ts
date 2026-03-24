/**
 * SMS Sync orchestrator.
 * Reads SMS → filters bank messages → parses transactions → syncs to backend.
 */

import { readSmsInbox, hasSmsPermission } from './SmsBridge';
import { filterTransactionSms } from './SmsFilterer';
import { parseAllTransactions } from './SmsParser';
import { syncSmsBatch } from '../api/client';
import { getLastSmsSync, setLastSmsSync } from '../utils/storage';
import type { SmsSyncResult, ParsedSmsTransaction } from './types';
import type { SmsBatchItem } from '../api/types';

function toApiBatchItem(parsed: ParsedSmsTransaction): SmsBatchItem {
  return {
    sms_hash: parsed.smsHash,
    sender_address: parsed.senderAddress,
    sender_id: parsed.senderId,
    body: parsed.body,
    sms_timestamp: parsed.smsTimestamp,
    classification: parsed.classification,
    bank_name: parsed.bankName,
    account_masked: parsed.accountMasked,
    direction: parsed.direction,
    amount: parsed.amount,
    description: parsed.description,
    reference_number: parsed.referenceNumber,
    upi_id: parsed.upiId,
    confidence: parsed.confidence,
  };
}

/**
 * Run a full SMS sync cycle.
 */
export async function syncNewSms(): Promise<SmsSyncResult> {
  const result: SmsSyncResult = {
    totalSmsRead: 0,
    bankSmsFound: 0,
    transactionsParsed: 0,
    transactionsSynced: 0,
    duplicatesSkipped: 0,
    errors: [],
    syncedAt: new Date().toISOString(),
  };

  try {
    // Check permission
    const hasPermission = await hasSmsPermission();
    if (!hasPermission) {
      result.errors.push('SMS permission not granted');
      return result;
    }

    // Get last sync timestamp (default: 30 days ago)
    const lastSync = (await getLastSmsSync()) || (Date.now() - 30 * 24 * 60 * 60 * 1000);

    // Step 1: Read SMS
    const allSms = await readSmsInbox(lastSync);
    result.totalSmsRead = allSms.length;

    if (allSms.length === 0) return result;

    // Step 2: Filter to bank transaction SMS only
    const bankSms = filterTransactionSms(allSms);
    result.bankSmsFound = bankSms.length;

    if (bankSms.length === 0) {
      await setLastSmsSync(Date.now());
      return result;
    }

    // Step 3: Parse transactions
    const parsed = parseAllTransactions(bankSms);
    result.transactionsParsed = parsed.length;

    if (parsed.length === 0) {
      await setLastSmsSync(Date.now());
      return result;
    }

    // Step 4: Sync to backend in batches of 50
    const batchSize = 50;
    for (let i = 0; i < parsed.length; i += batchSize) {
      const batch = parsed.slice(i, i + batchSize);
      const items = batch.map(toApiBatchItem);

      try {
        const response = await syncSmsBatch('android-app', items);
        result.transactionsSynced += response.accepted;
        result.duplicatesSkipped += response.duplicates;
      } catch (err: any) {
        result.errors.push(`Batch ${i / batchSize + 1}: ${err.message}`);
      }
    }

    // Update last sync timestamp
    await setLastSmsSync(Date.now());
  } catch (err: any) {
    result.errors.push(err.message);
  }

  return result;
}

/**
 * Preview what would be synced (parse only, no API call).
 */
export async function previewSmsSync(): Promise<{
  totalRead: number;
  transactions: ParsedSmsTransaction[];
}> {
  const lastSync = (await getLastSmsSync()) || (Date.now() - 30 * 24 * 60 * 60 * 1000);
  const allSms = await readSmsInbox(lastSync);
  const bankSms = filterTransactionSms(allSms);
  const transactions = parseAllTransactions(bankSms);
  return { totalRead: allSms.length, transactions };
}
