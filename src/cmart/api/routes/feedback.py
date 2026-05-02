from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.api.dependencies import get_current_account, get_db
from cmart.db.models import Account
from cmart.db.repositories.feedback import insert_feedback
from cmart.db.repositories.query_log import get_by_id
from cmart.schemas.feedback import FeedbackRequest, FeedbackResponse
from cmart.utils.errors import NotFoundError

router = APIRouter()


@router.post("", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    request: FeedbackRequest,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    log = await get_by_id(db, request.query_id)
    if log is None or log.account_id != account.id:
        raise NotFoundError("Query not found.")

    feedback = await insert_feedback(
        db,
        query_id=request.query_id,
        account_id=account.id,
        rating=request.rating.value,
        agent_id=request.agent_id,
        note=request.note,
    )

    return FeedbackResponse(
        id=feedback.id,
        query_id=feedback.query_id,
        rating=request.rating,
        created_at=feedback.created_at,
    )
