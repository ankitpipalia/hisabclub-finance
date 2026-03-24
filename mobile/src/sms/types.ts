export interface RawSms {
  id: string;
  address: string;  // sender, e.g., "AD-HDFCBK"
  body: string;
  date: number;     // timestamp in millis
}

export type SmsClassification =
  | 'transaction_debit'
  | 'transaction_credit'
  | 'otp'
  | 'balance_info'
  | 'promo'
  | 'spam'
  | 'unknown';

export interface ClassifiedSms {
  raw: RawSms;
  classification: SmsClassification;
  bankName: string | null;
  senderId: string | null;
  senderValid: boolean;
  spamScore: number;
}

export interface ParsedSmsTransaction {
  smsHash: string;
  senderAddress: string;
  senderId: string;
  body: string;
  smsTimestamp: string;  // ISO
  classification: 'transaction_debit' | 'transaction_credit';
  bankName: string;
  accountMasked: string | null;
  direction: 'debit' | 'credit';
  amount: number;
  balanceAfter: number | null;
  description: string;
  referenceNumber: string | null;
  upiId: string | null;
  confidence: number;
}

export interface SmsSyncResult {
  totalSmsRead: number;
  bankSmsFound: number;
  transactionsParsed: number;
  transactionsSynced: number;
  duplicatesSkipped: number;
  errors: string[];
  syncedAt: string;
}
