from fastapi import APIRouter

router = APIRouter()


@router.post("/reward/decide")
def decide_reward() -> dict[str, str]:
    return {"status": "stub", "message": "Reward decision endpoint scaffolded"}
