import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "policy_version": "v1",
    "xp_per_rupee": 2,
    "max_xp_per_txn": 100,
    "persona_multipliers": {
        "NEW": 1.2,
        "RETURNING": 1.0,
        "POWER": 0.8,
    },
    "daily_cac_cap": {
        "NEW": 500,
        "RETURNING": 300,
        "POWER": 200,
    },
    "reward_type_weights": {
        "CHECKOUT": 0.7,
        "GOLD": 0.2,
        "XP": 0.1,
    },
    "reward_value_rates": {
        "CHECKOUT": 0.10,
        "GOLD": 0.20,
    },
    "feature_flags": {
        "prefer_xp_mode": False,
        "cooldown_on_last_reward": False,
    },
    "reward_cooldown_seconds": 3600,
    "persona_cache_ttl_seconds": 3600,
    "idempotency_ttl_seconds": 86400,
}


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "policy.json"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    configured_path = os.getenv("POLICY_CONFIG_PATH")
    config_path = Path(configured_path) if configured_path else _default_config_path()

    if not config_path.exists():
        logger.warning("Policy file not found at %s. Falling back to defaults.", config_path)
        return dict(DEFAULT_CONFIG)

    try:
        with config_path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            raise ValueError("Policy config root must be a JSON object")
        merged = _deep_merge(DEFAULT_CONFIG, loaded)
        logger.info("Loaded policy config from %s", config_path)
        return merged
    except (OSError, ValueError, json.JSONDecodeError):
        logger.exception("Failed to load policy config from %s. Using defaults.", config_path)
        return dict(DEFAULT_CONFIG)


CONFIG = load_config()
