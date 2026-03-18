from fastapi import APIRouter

from app.models.schemas import RewardRequest, RewardResponse
from app.services.reward_service import RewardService

router = APIRouter()
service = RewardService()


@router.post("/reward/decide", response_model=RewardResponse)
def decide_reward(request: RewardRequest) -> RewardResponse:
    return service.decide_reward(request)
