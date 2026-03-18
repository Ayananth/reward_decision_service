import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from app.cache.cache import cache
from app.models.schemas import RewardRequest, RewardResponse
from app.services.reward_service import IdempotencyConflictError, RewardService

router = APIRouter()
service = RewardService()
RATE_LIMIT_MAX_REQUESTS = max(1, int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "30")))
RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))


@router.post("/reward/decide", response_model=RewardResponse)
def decide_reward(request: RewardRequest) -> RewardResponse:
    idem_key = service.build_idempotency_key(request)
    cached = cache.get(idem_key)
    if cached:
        return RewardResponse.model_validate(cached)

    if not cache.exists(f"{idem_key}:lock"):
        bucket = int(datetime.utcnow().timestamp()) // RATE_LIMIT_WINDOW_SECONDS
        rate_limit_key = f"ratelimit:reward_decide:{request.user_id}:{bucket}"
        count, ttl = cache.increment_rate_limit_counter(rate_limit_key, RATE_LIMIT_WINDOW_SECONDS)

        if count > RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(max(1, ttl))},
            )

    try:
        return service.decide_reward(request)
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
