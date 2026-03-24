/**
 * SMS transaction parser — extracts structured data from Indian bank SMS.
 */

import type { ClassifiedSms, ParsedSmsTransaction } from './types';
import {
  AMOUNT_PATTERNS,
  ACCOUNT_PATTERNS,
  BALANCE_PATTERNS,
  REFERENCE_PATTERNS,
  UPI_ID_PATTERNS,
  parseAmount,
} from './bankPatterns';

/**
 * Compute SHA-256 hash of a string (simplified — uses basic hash for dedup).
 */
function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash).toString(16).padStart(8, '0') +
    Math.abs(str.length * 31 + hash).toString(16).padStart(8, '0');
}

function extractAccount(body: string): string | null {
  for (const pattern of ACCOUNT_PATTERNS) {
    const match = body.match(pattern);
    if (match?.[1]) return `XX${match[1]}`;
  }
  return null;
}

function extractBalance(body: string): number | null {
  for (const pattern of BALANCE_PATTERNS) {
    const match = body.match(pattern);
    if (match?.[1]) {
      const amount = parseFloat(match[1].replace(/,/g, ''));
      if (!isNaN(amount)) return amount;
    }
  }
  return null;
}

function extractReference(body: string): string | null {
  for (const pattern of REFERENCE_PATTERNS) {
    const match = body.match(pattern);
    if (match?.[1]) return match[1];
  }
  return null;
}

function extractUpiId(body: string): string | null {
  for (const pattern of UPI_ID_PATTERNS) {
    const match = body.match(pattern);
    if (match?.[1]) return match[1];
  }
  return null;
}

/**
 * Parse a classified transaction SMS into structured data.
 */
export function parseSmsTransaction(classified: ClassifiedSms): ParsedSmsTransaction | null {
  const { raw, classification, bankName, senderId } = classified;

  if (classification !== 'transaction_debit' && classification !== 'transaction_credit') {
    return null;
  }

  const amount = parseAmount(raw.body);
  if (!amount || amount <= 0) return null;

  const direction = classification === 'transaction_debit' ? 'debit' : 'credit';
  const smsHash = simpleHash(`${raw.address}|${raw.body}|${raw.date}`);
  const accountMasked = extractAccount(raw.body);
  const balanceAfter = extractBalance(raw.body);
  const referenceNumber = extractReference(raw.body);
  const upiId = extractUpiId(raw.body);

  // Confidence scoring
  let confidence = 0.5; // base
  if (classified.senderValid) confidence += 0.25;
  if (accountMasked) confidence += 0.1;
  if (amount > 0) confidence += 0.1;
  if (referenceNumber) confidence += 0.05;
  confidence = Math.min(confidence, 1.0);

  return {
    smsHash,
    senderAddress: raw.address,
    senderId: senderId || 'UNKNOWN',
    body: raw.body,
    smsTimestamp: new Date(raw.date).toISOString(),
    classification,
    bankName: bankName || 'UNKNOWN',
    accountMasked,
    direction,
    amount,
    balanceAfter,
    description: raw.body.slice(0, 200), // Truncate for API
    referenceNumber,
    upiId,
    confidence,
  };
}

/**
 * Parse a batch of classified SMS into transactions.
 */
export function parseAllTransactions(classified: ClassifiedSms[]): ParsedSmsTransaction[] {
  return classified
    .map(parseSmsTransaction)
    .filter((t): t is ParsedSmsTransaction => t !== null);
}
