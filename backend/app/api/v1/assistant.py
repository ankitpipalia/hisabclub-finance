from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.engines.llm.correction_chat import run_transaction_correction_chat
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse

router = APIRouter()


@router.post("/chat", response_model=AssistantChatResponse)
async def correction_chat(
    request: AssistantChatRequest,
    user: CurrentUser,
    db: DbSession,
):
    try:
        result = await run_transaction_correction_chat(
            db=db,
            user_id=user.id,
            message=request.message,
            apply_changes=request.apply_changes,
            max_candidates=request.max_candidates,
        )
        if request.apply_changes and result.applied_count > 0:
            await db.flush()
        return AssistantChatResponse(
            reply=result.reply,
            proposed_count=result.proposed_count,
            applied_count=result.applied_count,
            skipped_count=result.skipped_count,
            warnings=result.warnings,
            actions=result.actions,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
