import hashlib
import time
import uuid

from app.cache.cache import cache
from app.core.config import CONFIG
from app.models.schemas import RewardRequest, RewardResponse

PERSONA_MAP = {
    "user_1": "NEW",
    "user_2": "POWER",
}
SUPPORTED_REWARD_TYPES = {"XP", "CHECKOUT", "GOLD"}


class IdempotencyConflictError(Exception):
    pass


class RewardService:
    IDEM_TTL_SECONDS = int(CONFIG.get("idempotency_ttl_seconds", 86400))
    IDEM_LOCK_TTL_SECONDS = int(CONFIG.get("idempotency_lock_ttl_seconds", 30))
    IDEM_WAIT_TIMEOUT_SECONDS = float(CONFIG.get("idempotency_wait_timeout_seconds", 5))
    IDEM_WAIT_INTERVAL_SECONDS = float(CONFIG.get("idempotency_wait_interval_seconds", 0.05))
    PERSONA_CACHE_TTL_SECONDS = int(CONFIG.get("persona_cache_ttl_seconds", 3600))

    def build_decision_seed(self, request: RewardRequest) -> str:
        return f"{request.txn_id}:{request.user_id}:{request.merchant_id}"

    def build_idempotency_key(self, request: RewardRequest) -> str:
        return f"idem:{request.txn_id}:{request.user_id}:{request.merchant_id}"

    def decide_reward(self, request: RewardRequest) -> RewardResponse:
        idem_key = self.build_idempotency_key(request)
        lock_key = f"{idem_key}:lock"
        lock_token = str(uuid.uuid4())

        cached_response = cache.get(idem_key)
        if cached_response:
            return RewardResponse.model_validate(cached_response)

        if not cache.acquire_lock(lock_key, lock_token, ttl=self.IDEM_LOCK_TTL_SECONDS):
            cached_response = self.wait_for_idempotent_result(idem_key)
            if cached_response:
                return RewardResponse.model_validate(cached_response)
            raise IdempotencyConflictError("Request is already being processed")

        try:
            cached_response = cache.get(idem_key)
            if cached_response:
                return RewardResponse.model_validate(cached_response)

            seed = self.build_decision_seed(request)
            persona = self.get_persona(request.user_id)

            xp = self.calculate_xp(request.amount, persona)
            reward_type = self.pick_reward_type(seed)
            reward_value = self.calculate_reward_value(request.amount, reward_type)

            response = RewardResponse(
                decision_id=str(uuid.uuid5(uuid.NAMESPACE_OID, seed)),
                policy_version=str(CONFIG["policy_version"]),
                reward_type=reward_type,
                reward_value=reward_value,
                xp=xp,
                reason_codes=[],
                meta={"persona": persona},
            )

            cache.set(idem_key, response.model_dump(), ttl=self.IDEM_TTL_SECONDS)
            return response
        finally:
            cache.release_lock(lock_key, lock_token)

    def get_persona(self, user_id: str) -> str:
        cache_key = f"persona:{user_id}"
        cached_persona = cache.get(cache_key)
        if isinstance(cached_persona, str) and cached_persona in CONFIG["persona_multipliers"]:
            return cached_persona

        persona = PERSONA_MAP.get(user_id, "RETURNING")
        cache.set(cache_key, persona, ttl=self.PERSONA_CACHE_TTL_SECONDS)
        return persona

    def calculate_xp(self, amount: float, persona: str) -> int:
        multiplier = float(CONFIG["persona_multipliers"][persona])
        xp = amount * float(CONFIG["xp_per_rupee"]) * multiplier
        return max(0, int(min(xp, float(CONFIG["max_xp_per_txn"]))))

    def pick_reward_type(self, seed: str) -> str:
        weights = CONFIG.get("reward_type_weights", {})
        reward_type = self.weighted_reward_choice(seed, weights)
        if reward_type not in SUPPORTED_REWARD_TYPES:
            return "XP"
        return reward_type

    def weighted_reward_choice(self, seed: str, weights: dict) -> str:
        weighted_entries: list[tuple[str, float]] = []
        for reward_type, weight in weights.items():
            value = float(weight)
            if value > 0:
                weighted_entries.append((reward_type, value))

        if not weighted_entries:
            return "XP"

        total_weight = sum(weight for _, weight in weighted_entries)
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        normalized = int.from_bytes(digest[:8], "big") / float(2**64)
        target = normalized * total_weight

        running = 0.0
        for reward_type, weight in weighted_entries:
            running += weight
            if target < running:
                return reward_type
        return weighted_entries[-1][0]

    def calculate_reward_value(self, amount: float, reward_type: str) -> int:
        if reward_type == "XP":
            return 0
        rates = CONFIG.get("reward_value_rates", {})
        rate = float(rates.get(reward_type, 0))
        return max(0, int(amount * rate))

    def wait_for_idempotent_result(self, idem_key: str) -> dict | None:
        deadline = time.monotonic() + self.IDEM_WAIT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            cached_response = cache.get(idem_key)
            if cached_response:
                return cached_response
            time.sleep(self.IDEM_WAIT_INTERVAL_SECONDS)
        return None
