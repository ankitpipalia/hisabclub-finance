from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DbSession
from app.engines.llm.correction_chat import run_transaction_correction_chat
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.statement import Statement
from app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationMessageResponse,
    ConversationPendingCountResponse,
    ConversationReplyRequest,
    ConversationReplyResponse,
    ConversationResolveResponse,
    ConversationThreadResponse,
)

router = APIRouter()


def _to_thread_response(thread: ConversationThread) -> ConversationThreadResponse:
    metadata = thread.metadata_json or {}
    return ConversationThreadResponse(
        id=str(thread.id),
        statement_id=str(thread.statement_id) if thread.statement_id else None,
        title=thread.title,
        status=thread.status,
        summary=thread.summary,
        metadata_json=metadata,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        pending_question_count=int(metadata.get("pending_question_count") or 0),
    )


def _to_message_response(message: ConversationMessage) -> ConversationMessageResponse:
    return ConversationMessageResponse(
        id=str(message.id),
        thread_id=str(message.thread_id),
        role=message.role,
        content=message.content,
        message_index=message.message_index,
        metadata_json=message.metadata_json,
        is_applied=message.is_applied,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _compose_thread_message(history: list[ConversationMessage], latest_message: str) -> str:
    if not history:
        return latest_message
    recent = history[-6:]
    history_lines = "\n".join(f"{msg.role}: {msg.content}" for msg in recent)
    return f"Conversation history:\n{history_lines}\n\nLatest user reply:\n{latest_message}"


@router.get("", response_model=list[ConversationThreadResponse])
async def list_conversations(user: CurrentUser, db: DbSession):
    threads = (
        await db.execute(
            select(ConversationThread)
            .where(ConversationThread.user_id == user.id)
            .order_by(ConversationThread.updated_at.desc(), ConversationThread.created_at.desc())
        )
    ).scalars().all()
    return [_to_thread_response(thread) for thread in threads]


@router.post("", response_model=ConversationThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(request: ConversationCreateRequest, user: CurrentUser, db: DbSession):
    statement_id = None
    if request.statement_id:
        statement = (
            await db.execute(
                select(Statement).where(Statement.id == request.statement_id, Statement.user_id == user.id)
            )
        ).scalar_one_or_none()
        if statement is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Statement not found.")
        statement_id = statement.id

    thread = ConversationThread(
        user_id=user.id,
        statement_id=statement_id,
        title=request.title.strip() or "Assistant Thread",
        metadata_json={"pending_question_count": 0},
    )
    db.add(thread)
    await db.flush()

    if request.initial_message:
        message = ConversationMessage(
            thread_id=thread.id,
            user_id=user.id,
            role="user",
            content=request.initial_message.strip(),
            message_index=0,
        )
        db.add(message)
        await db.flush()
    return _to_thread_response(thread)


@router.get("/{thread_id}/messages", response_model=list[ConversationMessageResponse])
async def list_conversation_messages(thread_id: str, user: CurrentUser, db: DbSession):
    thread = (
        await db.execute(
            select(ConversationThread).where(ConversationThread.id == thread_id, ConversationThread.user_id == user.id)
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    messages = (
        await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.thread_id == thread.id, ConversationMessage.user_id == user.id)
            .order_by(ConversationMessage.message_index.asc(), ConversationMessage.created_at.asc())
        )
    ).scalars().all()
    return [_to_message_response(message) for message in messages]


@router.post("/{thread_id}/reply", response_model=ConversationReplyResponse)
async def reply_to_conversation(
    thread_id: str,
    request: ConversationReplyRequest,
    user: CurrentUser,
    db: DbSession,
):
    thread = (
        await db.execute(
            select(ConversationThread).where(ConversationThread.id == thread_id, ConversationThread.user_id == user.id)
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    history = (
        await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.thread_id == thread.id, ConversationMessage.user_id == user.id)
            .order_by(ConversationMessage.message_index.asc(), ConversationMessage.created_at.asc())
        )
    ).scalars().all()
    next_index = len(history)

    user_message = ConversationMessage(
        thread_id=thread.id,
        user_id=user.id,
        role="user",
        content=request.message.strip(),
        message_index=next_index,
    )
    db.add(user_message)
    await db.flush()

    result = await run_transaction_correction_chat(
        db=db,
        user_id=user.id,
        message=_compose_thread_message(history, request.message.strip()),
        apply_changes=request.apply_changes,
        max_candidates=250,
    )

    assistant_message = ConversationMessage(
        thread_id=thread.id,
        user_id=user.id,
        role="assistant",
        content=result.reply,
        message_index=next_index + 1,
        metadata_json={"warnings": result.warnings, "actions": result.actions},
        is_applied=bool(request.apply_changes and result.applied_count > 0),
    )
    db.add(assistant_message)

    pending_question_count = 0
    if result.warnings or (result.proposed_count > 0 and not request.apply_changes):
        pending_question_count = 1
    thread.metadata_json = {
        **(thread.metadata_json or {}),
        "pending_question_count": pending_question_count,
    }
    thread.summary = result.reply[:280]
    await db.flush()

    return ConversationReplyResponse(
        thread=_to_thread_response(thread),
        message=_to_message_response(user_message),
        assistant_message=_to_message_response(assistant_message),
        warnings=result.warnings,
        actions=result.actions,
        proposed_count=result.proposed_count,
        applied_count=result.applied_count,
        skipped_count=result.skipped_count,
    )


@router.get("/pending-count", response_model=ConversationPendingCountResponse)
async def get_pending_conversation_count(user: CurrentUser, db: DbSession):
    threads = (
        await db.execute(
            select(ConversationThread).where(
                ConversationThread.user_id == user.id,
                ConversationThread.status == "active",
            )
        )
    ).scalars().all()
    pending = sum(int((thread.metadata_json or {}).get("pending_question_count") or 0) for thread in threads)
    return ConversationPendingCountResponse(pending_count=pending)


@router.post("/{thread_id}/resolve", response_model=ConversationResolveResponse)
async def resolve_conversation(thread_id: str, user: CurrentUser, db: DbSession):
    thread = (
        await db.execute(
            select(ConversationThread).where(ConversationThread.id == thread_id, ConversationThread.user_id == user.id)
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    thread.status = "archived"
    thread.metadata_json = {**(thread.metadata_json or {}), "pending_question_count": 0}
    await db.flush()
    await db.refresh(thread)
    return ConversationResolveResponse(thread=_to_thread_response(thread), resolved=True)
