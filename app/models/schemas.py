from typing import Any, Literal

from pydantic import BaseModel, Field


class RewardRequest(BaseModel):
    txn_id: str
    user_id: str
    merchant_id: str
    amount: float = Field(gt=0)
    txn_type: str
    ts: str


class RewardResponse(BaseModel):
    decision_id: str
    policy_version: str
    reward_type: Literal["XP", "CHECKOUT", "GOLD"]
    reward_value: int = Field(ge=0)
    xp: int = Field(ge=0)
    reason_codes: list[str]
    meta: dict[str, Any] = Field(default_factory=dict)
