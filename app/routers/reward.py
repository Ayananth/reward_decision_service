import uuid

from fastapi import APIRouter

from app.core.config import CONFIG
from app.models.schemas import RewardRequest, RewardResponse

router = APIRouter()


@router.post("/reward/decide", response_model=RewardResponse)
def decide_reward(request: RewardRequest) -> RewardResponse:
    # Step-2 contract stub: real decision logic comes in later steps.
    return RewardResponse(
        decision_id=str(uuid.uuid4()),
        policy_version=str(CONFIG["policy_version"]),
        reward_type="XP",
        reward_value=0,
        xp=int(request.amount),
        reason_codes=["STUB_RESPONSE"],
        meta={"note": "API contract validated"},
    )
