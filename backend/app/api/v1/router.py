from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    assistant,
    auth,
    bills,
    budgets,
    categories,
    conversations,
    export,
    gmail,
    imports,
    insights,
    merchants,
    net_worth,
    reviews,
    sms,
    statements,
    subscriptions,
    tax,
    transactions,
    transfers,
    upload,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(statements.router, prefix="/statements", tags=["statements"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(merchants.router, prefix="/merchants", tags=["merchants"])
api_router.include_router(sms.router, prefix="/sms", tags=["sms"])
api_router.include_router(insights.router, prefix="/insights", tags=["insights"])
api_router.include_router(net_worth.router, prefix="/net-worth", tags=["net-worth"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
api_router.include_router(budgets.router, prefix="/budgets", tags=["budgets"])
api_router.include_router(bills.router, prefix="/bills", tags=["bills"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(gmail.router, prefix="/gmail", tags=["gmail"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(tax.router, prefix="/tax", tags=["tax"])
api_router.include_router(transfers.router, prefix="/transfers", tags=["transfers"])
