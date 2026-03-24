/**
 * SMS classification and spam detection.
 * Classifies each SMS as: transaction_debit, transaction_credit, otp, balance_info, promo, spam, unknown.
 */

import type { RawSms, ClassifiedSms, SmsClassification } from './types';
import {
  identifyBank,
  extractSenderId,
  OTP_PATTERNS,
  DEBIT_PATTERNS,
  CREDIT_PATTERNS,
  PROMO_PATTERNS,
  AMOUNT_PATTERNS,
} from './bankPatterns';

/**
 * Compute a spam score from 0 (legit) to 100 (spam).
 */
function computeSpamScore(sms: RawSms): number {
  let score = 0;
  const { address, body } = sms;

  // Signal 1: Unknown sender format or sender ID
  const bankInfo = identifyBank(address);
  if (!bankInfo) {
    score += 40;
  } else if (!bankInfo.valid) {
    score += 15; // Partial match
  }

  // Signal 2: Personal phone number as sender
  if (/^\+?91?\d{10}$/.test(address.replace(/[\s-]/g, ''))) {
    score += 40;
  }

  // Signal 3: Suspicious URLs
  if (/https?:\/\//.test(body)) {
    if (/bit\.ly|tinyurl|cutt\.ly|is\.gd|short\.url/i.test(body)) {
      score += 25;
    } else if (!/hdfc|icici|axis|sbi|kotak|yesbank/i.test(body)) {
      score += 15;
    }
  }

  // Signal 4: Urgency / scare language
  const urgencyPatterns = [
    /account\s*(?:will\s*be\s*)?(?:blocked|suspended|closed|frozen)/i,
    /immediate(?:ly)?\s*(?:action|attention|verification)/i,
    /(?:verify|update)\s*(?:your\s*)?(?:KYC|PAN|Aadhaar)/i,
    /(?:will\s*be\s*)?(?:blocked|suspended)\s*(?:in|within)\s*\d+/i,
  ];
  const urgencyCount = urgencyPatterns.filter(p => p.test(body)).length;
  score += Math.min(urgencyCount * 10, 20);

  // Signal 5: Asks for sensitive info
  const sensitivePatterns = [
    /(?:share|send|provide|enter)\s*(?:your\s*)?(?:OTP|PIN|CVV|password|card\s*number)/i,
    /(?:click|tap)\s*(?:here|link|below)\s*to\s*(?:verify|update|confirm)/i,
    /call\s*(?:this|the)?\s*(?:number|helpline)\s*(?:immediately|urgently)/i,
  ];
  if (sensitivePatterns.some(p => p.test(body))) {
    score += 25;
  }

  // Signal 6: Known spam templates
  const knownSpam = [
    /if\s*not\s*(?:done|authorized)\s*by\s*you.*?call\s*\d{10}/i,
    /KYC\s*(?:expired?|expir(?:ing|es)|not\s*updated).*?(?:click|link|update)/i,
    /(?:won|winner|prize|lottery|jackpot).*?(?:claim|collect|click)/i,
    /(?:earn|income)\s*(?:Rs\.?|INR)\s*[\d,]+\s*(?:per|daily|weekly)/i,
  ];
  if (knownSpam.some(p => p.test(body))) {
    score += 40;
  }

  // Signal 7: No amount detected (most legit bank SMS have amounts)
  if (!AMOUNT_PATTERNS.some(p => p.test(body))) {
    score += 10;
  }

  return Math.min(score, 100);
}

/**
 * Classify a single SMS message.
 */
export function classifySms(sms: RawSms): ClassifiedSms {
  const { address, body } = sms;
  const bankInfo = identifyBank(address);
  const senderId = extractSenderId(address);
  const spamScore = computeSpamScore(sms);

  // Default classification
  let classification: SmsClassification = 'unknown';

  // Promo detection FIRST (even if it has amounts — cashback offers mention Rs.X)
  const isPromo = PROMO_PATTERNS.some(p => p.test(body));
  // A real transaction says "debited/credited FROM/TO account" — promos don't
  const hasAccountRef = /(?:a\/c|account|acct|ac)\s*(?:no\.?\s*)?(?:XX|xx|X{2,}|\*{2,})\d/i.test(body);

  // High spam score → spam
  if (spamScore >= 50) {
    classification = 'spam';
  }
  // OTP detection (highest priority — never process)
  else if (OTP_PATTERNS.some(p => p.test(body))) {
    classification = 'otp';
  }
  // Promotional: if it has promo keywords AND no account reference, it's a promo
  else if (isPromo && !hasAccountRef) {
    classification = 'promo';
  }
  // Debit transaction — must have account reference or strong debit language
  else if (DEBIT_PATTERNS.some(p => p.test(body)) && AMOUNT_PATTERNS.some(p => p.test(body)) && hasAccountRef) {
    classification = 'transaction_debit';
  }
  // Credit transaction — must have account reference
  else if (CREDIT_PATTERNS.some(p => p.test(body)) && AMOUNT_PATTERNS.some(p => p.test(body)) && hasAccountRef) {
    classification = 'transaction_credit';
  }
  // Balance info (has amount but no debit/credit indicator)
  else if (AMOUNT_PATTERNS.some(p => p.test(body)) && /balance/i.test(body)) {
    classification = 'balance_info';
  }

  return {
    raw: sms,
    classification,
    bankName: bankInfo?.bank ?? null,
    senderId,
    senderValid: bankInfo?.valid ?? false,
    spamScore,
  };
}

/**
 * Filter a batch of SMS: returns only transaction SMS.
 */
export function filterTransactionSms(messages: RawSms[]): ClassifiedSms[] {
  return messages
    .map(classifySms)
    .filter(m =>
      m.classification === 'transaction_debit' ||
      m.classification === 'transaction_credit'
    );
}
