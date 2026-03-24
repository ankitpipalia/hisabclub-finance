/**
 * Indian bank sender IDs and SMS parsing patterns.
 * Sender format: XX-BANKID (XX varies by telecom circle)
 */

export interface BankInfo {
  bank: string;
  type: 'savings' | 'credit_card' | 'wallet';
}

// Known bank sender ID suffixes (the 6-char part after XX-)
export const BANK_SENDER_IDS: Record<string, BankInfo> = {
  // HDFC
  HDFCBK: { bank: 'HDFC', type: 'savings' },
  HDFCBN: { bank: 'HDFC', type: 'savings' },
  HDFCCC: { bank: 'HDFC', type: 'credit_card' },
  HDFCRD: { bank: 'HDFC', type: 'savings' },

  // ICICI
  ICICIB: { bank: 'ICICI', type: 'savings' },
  ICICIS: { bank: 'ICICI', type: 'savings' },
  ICICIP: { bank: 'ICICI', type: 'savings' },

  // Axis
  AXISBK: { bank: 'AXIS', type: 'savings' },
  AXISBN: { bank: 'AXIS', type: 'savings' },

  // SBI
  SBIINB: { bank: 'SBI', type: 'savings' },
  SBIPSG: { bank: 'SBI', type: 'savings' },
  SBICRD: { bank: 'SBI', type: 'credit_card' },
  SABORB: { bank: 'SBI', type: 'savings' },

  // Kotak
  KOTAKB: { bank: 'KOTAK', type: 'savings' },
  KOTKBK: { bank: 'KOTAK', type: 'savings' },

  // Yes Bank
  YESBKL: { bank: 'YES', type: 'savings' },

  // IndusInd
  INDBNK: { bank: 'INDUSIND', type: 'savings' },

  // RBL
  RBLBNK: { bank: 'RBL', type: 'savings' },

  // IDFC First
  IDFCFB: { bank: 'IDFC_FIRST', type: 'savings' },

  // PNB
  PNBSMS: { bank: 'PNB', type: 'savings' },

  // Canara
  CANBNK: { bank: 'CANARA', type: 'savings' },

  // BOI
  BOIIND: { bank: 'BOI', type: 'savings' },

  // UCO
  UCOBNK: { bank: 'UCO', type: 'savings' },

  // UPI / Wallets
  JIOBNK: { bank: 'JIO_PAYMENTS', type: 'wallet' },
  PAYTMB: { bank: 'PAYTM', type: 'wallet' },
};

// Amount extraction patterns
export const AMOUNT_PATTERNS = [
  /(?:Rs\.?|INR|₹)\s?([\d,]+\.?\d*)/i,
  /(?:debited|credited|spent|received|paid|withdrawn)\s+(?:Rs\.?|INR|₹)?\s?([\d,]+\.?\d*)/i,
  /([\d,]+\.?\d*)\s*(?:has been|was)\s*(?:debited|credited)/i,
];

// Account number extraction
export const ACCOUNT_PATTERNS = [
  /(?:a\/c|account|acct|ac)\s*(?:no\.?\s*)?(?:XX|xx|X{2,}|\*{2,})(\d{3,6})/i,
  /(?:card)\s*(?:ending|no\.?|xx)\s*(\d{4})/i,
  /(?:XX|xx|\*{2,})(\d{4,6})/,
];

// Balance after transaction
export const BALANCE_PATTERNS = [
  /(?:bal|balance|avl\.?\s*bal\.?|available)\s*(?:is|:)?\s*(?:Rs\.?|INR|₹)?\s?([\d,]+\.?\d*)/i,
];

// UPI / NEFT / IMPS reference
export const REFERENCE_PATTERNS = [
  /(?:UPI|Ref)\s*(?:No\.?|Ref\.?|ID)?\s*[:.]?\s*(\d{12,})/i,
  /(?:NEFT|RTGS|IMPS)\s*(?:Ref\.?)?\s*[:.]?\s*([A-Z0-9]{8,})/i,
];

// UPI VPA
export const UPI_ID_PATTERNS = [
  /(?:to|from|VPA)\s*[:.]?\s*([a-zA-Z0-9._-]+@[a-zA-Z]+)/i,
];

// OTP patterns (NEVER process these)
export const OTP_PATTERNS = [
  /\bOTP\b/i,
  /\bone[\s-]time[\s-]password\b/i,
  /\bverification\s*code\b/i,
  /\b\d{4,8}\b.*(?:is your|use this)/i,
  /(?:do not share|never share).*(?:OTP|password|PIN)/i,
];

// Debit indicators
export const DEBIT_PATTERNS = [
  /(?:debited|deducted|spent|paid|purchase|withdrawn|transferred|sent)\b/i,
  /\bdr\b/i,
];

// Credit indicators
export const CREDIT_PATTERNS = [
  /(?:credited|received|deposited|refund|cashback|reversed)\b/i,
  /\bcr\b/i,
];

// Promotional / marketing
export const PROMO_PATTERNS = [
  /\b(?:offer|discount|cashback|reward|apply\s*now|limited\s*time|exclusive|pre-?approved)\b/i,
  /\b(?:EMI\s*available|instant\s*loan|credit\s*limit.*increased)\b/i,
  /\b(?:congratulations|eligible|selected|lucky)\b/i,
];

/**
 * Extract sender ID suffix from raw address.
 * Handles various Indian sender formats:
 *   "AD-HDFCBK"    -> "HDFCBK"
 *   "VM-ICICIT-S"  -> "ICICIT" (strips trailing dash-suffix)
 *   "VA-KOTAKA-P"  -> "KOTAKA" (strips trailing dash-suffix)
 *   "BZ-AXISBK"    -> "AXISBK"
 */
export function extractSenderId(address: string): string | null {
  // Match XX-SENDER or XX-SENDER-X format
  const match = address.match(/^[A-Z]{2}-([A-Z]{4,8})(?:-[A-Z])?$/i);
  if (match) return match[1].toUpperCase();

  // Try without strict prefix (some senders have longer prefixes)
  const match2 = address.match(/([A-Z]{4,8})(?:-[A-Z])?$/i);
  if (match2) return match2[1].toUpperCase();

  return null;
}

/**
 * Look up bank info from sender address.
 */
export function identifyBank(address: string): { bank: string; type: string; valid: boolean } | null {
  const senderId = extractSenderId(address);
  if (!senderId) return null;

  // Exact match
  const info = BANK_SENDER_IDS[senderId];
  if (info) return { ...info, valid: true };

  // Try without trailing chars (ICICIT -> ICICI match)
  for (let len = senderId.length - 1; len >= 4; len--) {
    const prefix = senderId.slice(0, len);
    for (const [knownId, knownInfo] of Object.entries(BANK_SENDER_IDS)) {
      if (knownId === prefix || knownId.startsWith(prefix)) {
        return { ...knownInfo, valid: true };
      }
    }
  }

  return null;
}

/**
 * Parse INR amount from text.
 */
export function parseAmount(text: string): number | null {
  for (const pattern of AMOUNT_PATTERNS) {
    const match = text.match(pattern);
    if (match?.[1]) {
      const cleaned = match[1].replace(/,/g, '');
      const amount = parseFloat(cleaned);
      if (!isNaN(amount) && amount > 0) return amount;
    }
  }
  return null;
}
