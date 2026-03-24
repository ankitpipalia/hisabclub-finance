"""Auto-categorization helpers for uncategorized transactions."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Iterable

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.llm.categorizer import llm_categorize_transaction
from app.engines.llm.client import LLMClient
from app.models.category import Category

logger = logging.getLogger(__name__)

# Ordered rules: first match wins.
_DESCRIPTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ATM WDL", "ATM WITHDRAW", "CASH WITHDRAW"), "ATM Withdrawal"),
    (
        ("CREDIT CARD PAYMENT", "CC PAYMENT", "CARD PAYMENT", "BILLDESK", "AUTOPAY"),
        "Credit Card Payment",
    ),
    (("SALARY", "PAYROLL", "WAGES"), "Salary"),
    (("INTEREST", "FD INT", "SAVINGS INTEREST"), "Interest"),
    (("DIVIDEND",), "Dividend"),
    (("MUTUAL FUND", "SIP", "NPS", "PPF", "ZERODHA", "GROWW", "ICICI DIRECT"), "Investment"),
    (("INCOME TAX", "ADVANCE TAX", "SELF ASSESSMENT TAX", "TDS", "CHALLAN", "GST"), "Tax"),
    (("SWIGGY", "ZOMATO"), "Food Delivery"),
    (("UBER", "OLA", "RAPIDO"), "Cab & Auto"),
    (("NETFLIX", "HOTSTAR", "PRIME VIDEO", "SPOTIFY"), "OTT Subscriptions"),
    (("RENT", "HOUSE RENT"), "Rent"),
    (("ELECTRICITY", "BESCOM", "MSEB", "TNEB"), "Electricity"),
    (("AIRTEL", "JIO", "VODAFONE", "BSNL", "ACT FIBERNET"), "Mobile & Internet"),
    (("INSURANCE", "LIC"), "Insurance"),
)

_WEB_TEXT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("E-COMMERCE", "ONLINE RETAIL", "MARKETPLACE"), "Online Shopping"),
    (("FOOD DELIVERY", "RESTAURANT CHAIN", "QUICK SERVICE RESTAURANT"), "Food Delivery"),
    (("RIDE-HAILING", "CAB", "TAXI SERVICE"), "Cab & Auto"),
    (("BROKERAGE", "MUTUAL FUND PLATFORM", "STOCK BROKER"), "Investment"),
    (("INSURANCE",), "Insurance"),
    (("SUBSCRIPTION VIDEO", "MUSIC STREAMING", "STREAMING SERVICE"), "OTT Subscriptions"),
)

_GENERIC_MERCHANT_WORDS = {
    "UPI",
    "IMPS",
    "NEFT",
    "RTGS",
    "TRANSFER",
    "PAYMENT",
    "DEBIT",
    "CREDIT",
    "PURCHASE",
    "POS",
    "INR",
    "TRF",
    "TXN",
    "REF",
    "ID",
    "NO",
}


async def infer_uncategorized_category(
    db: AsyncSession,
    user_id: uuid.UUID,
    description_raw: str,
    amount: float,
) -> tuple[uuid.UUID | None, str]:
    """Infer a category ID and category_source for uncategorized transaction rows."""
    category_rows = await _load_category_rows(db, user_id)
    if not category_rows:
        return None, "auto"

    by_name = {name.lower(): cid for cid, name in category_rows}
    category_names = [name for _, name in category_rows]

    # 1) Fast deterministic rules.
    rule_name = _guess_from_description(description_raw)
    if rule_name:
        category_id = _lookup_category_id(by_name, [rule_name])
        if category_id:
            return category_id, "auto"

    # 2) Local LLM (if enabled).
    if settings.llm_enabled:
        try:
            llm_client = LLMClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
            )
            llm_match = await llm_categorize_transaction(
                client=llm_client,
                description=description_raw,
                amount=amount,
                categories=category_names,
            )
            if llm_match:
                llm_id = by_name.get(llm_match.lower())
                if llm_id:
                    return llm_id, "llm"
        except Exception as exc:
            logger.warning("LLM categorization failed: %s", exc)

    # 3) Optional web lookup fallback.
    if settings.local_only_mode or not settings.category_web_lookup_enabled:
        return None, "auto"

    web_hint = await _fetch_web_business_hint(description_raw)
    if web_hint:
        web_guess = _guess_from_web_text(web_hint)
        if web_guess:
            web_id = _lookup_category_id(by_name, [web_guess])
            if web_id:
                return web_id, "llm"

    return None, "auto"


async def _load_category_rows(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[tuple[uuid.UUID, str]]:
    rows = (
        await db.execute(
            select(Category.id, Category.name)
            .where(or_(Category.user_id == user_id, Category.user_id.is_(None)))
            .order_by(Category.is_system.desc(), Category.sort_order.asc(), Category.name.asc())
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


def _guess_from_description(description_raw: str) -> str | None:
    text = _normalize(description_raw)
    for keywords, category_name in _DESCRIPTION_RULES:
        if any(keyword in text for keyword in keywords):
            return category_name
    return None


def _guess_from_web_text(web_text: str) -> str | None:
    text = _normalize(web_text)
    for keywords, category_name in _WEB_TEXT_RULES:
        if any(keyword in text for keyword in keywords):
            return category_name
    return None


def _lookup_category_id(
    category_name_to_id: dict[str, uuid.UUID],
    candidates: Iterable[str],
) -> uuid.UUID | None:
    for candidate in candidates:
        found = category_name_to_id.get(candidate.lower())
        if found:
            return found
    return None


async def _fetch_web_business_hint(description_raw: str) -> str | None:
    merchant_hint = _extract_merchant_hint(description_raw)
    if not merchant_hint:
        return None

    try:
        async with httpx.AsyncClient(timeout=settings.category_web_lookup_timeout_sec) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": f"{merchant_hint} company business India",
                    "format": "json",
                    "no_redirect": "1",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("Web category hint lookup failed for '%s': %s", merchant_hint, exc)
        return None

    chunks: list[str] = []
    for key in ("Heading", "AbstractText"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())

    related = payload.get("RelatedTopics")
    if isinstance(related, list):
        for entry in related[:3]:
            if isinstance(entry, dict):
                text = entry.get("Text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())

    combined = " ".join(chunks).strip()
    return combined or None


def _extract_merchant_hint(description_raw: str) -> str:
    text = re.sub(r"[^A-Z\s]", " ", description_raw.upper())
    tokens = [t for t in text.split() if len(t) > 2 and t not in _GENERIC_MERCHANT_WORDS]
    if not tokens:
        return ""
    return " ".join(tokens[:4])


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.upper().strip())
