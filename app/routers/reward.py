from fastapi import APIRouter, HTTPException, status

from app.models.schemas import RewardRequest, RewardResponse
from app.services.reward_service import IdempotencyConflictError, RewardService

router = APIRouter()
service = RewardService()


@router.post("/reward/decide", response_model=RewardResponse)
def decide_reward(request: RewardRequest) -> RewardResponse:
    try:
        return service.decide_reward(request)
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
