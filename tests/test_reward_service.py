import uuid

import pytest
from fastapi import HTTPException

from app.cache.cache import InMemoryCache
from app.models.schemas import RewardRequest
import app.routers.reward as reward_router_module
import app.services.reward_service as reward_service_module


def build_request(txn_id: str, user_id: str = "user_1", amount: float = 100) -> RewardRequest:
    return RewardRequest(
        txn_id=txn_id,
        user_id=user_id,
        merchant_id="m1",
        amount=amount,
        txn_type="PURCHASE",
        ts="2026-03-18T12:00:00Z",
    )


@pytest.fixture
def in_memory_cache() -> InMemoryCache:
    return InMemoryCache()


@pytest.fixture(autouse=True)
def reset_config():
    original = dict(reward_service_module.CONFIG)
    original_flags = dict(reward_service_module.CONFIG.get("feature_flags", {}))
    original_caps = dict(reward_service_module.CONFIG.get("daily_cac_cap", {}))
    original_weights = dict(reward_service_module.CONFIG.get("reward_type_weights", {}))
    original_rates = dict(reward_service_module.CONFIG.get("reward_value_rates", {}))
    original_persona = dict(reward_service_module.CONFIG.get("persona_multipliers", {}))
    yield
    reward_service_module.CONFIG.clear()
    reward_service_module.CONFIG.update(original)
    reward_service_module.CONFIG["feature_flags"] = original_flags
    reward_service_module.CONFIG["daily_cac_cap"] = original_caps
    reward_service_module.CONFIG["reward_type_weights"] = original_weights
    reward_service_module.CONFIG["reward_value_rates"] = original_rates
    reward_service_module.CONFIG["persona_multipliers"] = original_persona


@pytest.fixture
def service(monkeypatch, in_memory_cache):
    monkeypatch.setattr(reward_service_module, "cache", in_memory_cache)
    monkeypatch.setitem(reward_service_module.CONFIG, "reward_type_weights", {"CHECKOUT": 1.0})
    monkeypatch.setitem(reward_service_module.CONFIG, "reward_value_rates", {"CHECKOUT": 0.1, "GOLD": 0.2})
    monkeypatch.setitem(
        reward_service_module.CONFIG,
        "feature_flags",
        {"prefer_xp_mode": False, "cooldown_on_last_reward": False},
    )
    monkeypatch.setitem(
        reward_service_module.CONFIG,
        "daily_cac_cap",
        {"NEW": 500, "RETURNING": 300, "POWER": 200},
    )
    return reward_service_module.RewardService()


def test_reward_decision_logic(service):
    response = service.decide_reward(build_request("txn-1"))
    assert response.reward_type == "CHECKOUT"
    assert response.reward_value == 10
    assert response.xp == 100
    assert response.meta["persona"] == "NEW"


def test_idempotency_returns_exact_same_response(service):
    request = build_request("txn-idem")
    first = service.decide_reward(request)
    second = service.decide_reward(request)
    assert first.model_dump() == second.model_dump()


def test_cac_cap_enforces_xp_fallback(service, monkeypatch):
    monkeypatch.setitem(
        reward_service_module.CONFIG,
        "daily_cac_cap",
        {"NEW": 15, "RETURNING": 15, "POWER": 15},
    )

    first = service.decide_reward(build_request("txn-cac-1"))
    second = service.decide_reward(build_request("txn-cac-2"))

    assert first.reward_type == "CHECKOUT"
    assert second.reward_type == "XP"
    assert second.reward_value == 0
    assert "CAC_LIMIT" in second.reason_codes


def test_prefer_xp_mode_forces_xp_response(service, monkeypatch):
    monkeypatch.setitem(
        reward_service_module.CONFIG,
        "feature_flags",
        {"prefer_xp_mode": True, "cooldown_on_last_reward": False},
    )

    response = service.decide_reward(build_request("txn-pref-xp-1"))
    assert response.reward_type == "XP"
    assert response.reward_value == 0
    assert "PREFER_XP_MODE" in response.reason_codes


def test_cooldown_blocks_second_monetary_reward(service, monkeypatch):
    monkeypatch.setitem(
        reward_service_module.CONFIG,
        "feature_flags",
        {"prefer_xp_mode": False, "cooldown_on_last_reward": True},
    )
    monkeypatch.setitem(reward_service_module.CONFIG, "reward_cooldown_seconds", 3600)
    monkeypatch.setitem(
        reward_service_module.CONFIG,
        "daily_cac_cap",
        {"NEW": 1000, "RETURNING": 1000, "POWER": 1000},
    )

    first = service.decide_reward(build_request("txn-cool-1"))
    second = service.decide_reward(build_request("txn-cool-2"))

    assert first.reward_type == "CHECKOUT"
    assert second.reward_type == "XP"
    assert second.reward_value == 0
    assert "COOLDOWN_ACTIVE" in second.reason_codes


def test_router_rate_limit_and_idempotency_bypass(monkeypatch, in_memory_cache):
    monkeypatch.setattr(reward_service_module, "cache", in_memory_cache)
    service = reward_service_module.RewardService()
    monkeypatch.setitem(reward_service_module.CONFIG, "reward_type_weights", {"CHECKOUT": 1.0})

    monkeypatch.setattr(reward_router_module, "cache", in_memory_cache)
    monkeypatch.setattr(reward_router_module, "service", service)
    monkeypatch.setattr(reward_router_module, "RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(reward_router_module, "RATE_LIMIT_WINDOW_SECONDS", 60)

    first = reward_router_module.decide_reward(build_request("txn-router-1"))
    second_same = reward_router_module.decide_reward(build_request("txn-router-1"))
    assert first.model_dump() == second_same.model_dump()

    with pytest.raises(HTTPException) as excinfo:
        reward_router_module.decide_reward(build_request("txn-router-2"))
    assert excinfo.value.status_code == 429
    assert "Retry-After" in (excinfo.value.headers or {})


def test_router_returns_409_when_idempotency_lock_is_busy(monkeypatch, in_memory_cache):
    monkeypatch.setattr(reward_service_module, "cache", in_memory_cache)
    service = reward_service_module.RewardService()
    service.IDEM_WAIT_TIMEOUT_SECONDS = 0.05
    service.IDEM_WAIT_INTERVAL_SECONDS = 0.01

    monkeypatch.setattr(reward_router_module, "cache", in_memory_cache)
    monkeypatch.setattr(reward_router_module, "service", service)
    monkeypatch.setattr(reward_router_module, "RATE_LIMIT_MAX_REQUESTS", 100)
    monkeypatch.setattr(reward_router_module, "RATE_LIMIT_WINDOW_SECONDS", 60)

    request = build_request("txn-lock-1")
    idem_key = service.build_idempotency_key(request)
    lock_key = f"{idem_key}:lock"
    token = str(uuid.uuid4())
    acquired = in_memory_cache.acquire_lock(lock_key, token, ttl=2)
    assert acquired is True

    try:
        with pytest.raises(HTTPException) as excinfo:
            reward_router_module.decide_reward(request)
        assert excinfo.value.status_code == 409
    finally:
        in_memory_cache.release_lock(lock_key, token)
