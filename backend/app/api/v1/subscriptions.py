from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession
from app.engines.insights.subscriptions import build_subscription_overview
from app.schemas.subscriptions import SubscriptionOverviewResponse

router = APIRouter()


@router.get("", response_model=SubscriptionOverviewResponse)
async def get_subscriptions(user: CurrentUser, db: DbSession):
    payload = await build_subscription_overview(db, user_id=user.id)
    await db.flush()
    return SubscriptionOverviewResponse(**payload)
