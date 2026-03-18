# Reward Decision Service

Low-latency FastAPI microservice that returns deterministic reward decisions for transactions.

## Features
- `POST /reward/decide` API contract with request/response validation
- Deterministic reward decisioning from config
- Idempotency (`txn_id + user_id + merchant_id`) with lock/wait handling
- Cache-first architecture with Redis backend and in-memory fallback
- Daily CAC cap enforcement with XP fallback
- Feature flags:
  - `prefer_xp_mode`
  - `cooldown_on_last_reward`
- Router-level rate limiting with `Retry-After` header
- Unit tests with `pytest`
- Custom threaded load-test script for throughput and latency metrics

## Project Structure
```text
app/
  app.py
  routers/reward.py
  services/reward_service.py
  models/schemas.py
  cache/cache.py
  core/config.py
config/
  policy.json
tests/
  test_reward_service.py
scripts/
  load_test.py
docs/
  performance_report_template.md
```

## API
### `POST /reward/decide`

Request fields:
- `txn_id` (string)
- `user_id` (string)
- `merchant_id` (string)
- `amount` (number, > 0)
- `txn_type` (string)
- `ts` (string)

Response fields:
- `decision_id` (UUID string)
- `policy_version` (string)
- `reward_type` (`XP` / `CHECKOUT` / `GOLD`)
- `reward_value` (integer)
- `xp` (integer)
- `reason_codes` (list of strings)
- `meta` (object)

## Configuration
Policy is loaded from `config/policy.json` by default.

Override path with:
```bash
export POLICY_CONFIG_PATH=/absolute/path/to/policy.json
```

Cache/rate-limit environment variables:
```bash
export CACHE_BACKEND=memory        # memory | redis
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
export RATE_LIMIT_MAX_REQUESTS=30
export RATE_LIMIT_WINDOW_SECONDS=60
```

## Local Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
```

## Run Service
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger docs:
- `http://localhost:8000/docs`

## Quick API Check
```bash
curl -X POST "http://localhost:8000/reward/decide" \
  -H "Content-Type: application/json" \
  -d '{
    "txn_id": "txn-1",
    "user_id": "user_1",
    "merchant_id": "m1",
    "amount": 100,
    "txn_type": "PURCHASE",
    "ts": "2026-03-18T12:00:00Z"
  }'
```

## Run Tests
```bash
python3 -m pytest -q
```

## Load Test
```bash
python3 scripts/load_test.py \
  --url http://localhost:8000/reward/decide \
  --duration 30 \
  --workers 120 \
  --timeout 2 \
  --user-pool 10000
```

Outputs include:
- `attempt_throughput_rps`
- `response_throughput_rps`
- `latency_p50_ms`
- `latency_p95_ms`
- `latency_p99_ms`
- `status_counts`
- `error_counts`

Use `docs/performance_report_template.md` for reporting.

## Assumptions
1. Persona is mocked in service with an in-memory map and cached per user.
2. Time-based counters (CAC/rate limit) are handled in UTC.
3. Idempotent response consistency is guaranteed within configured idempotency TTL.
4. Redis is optional for local development due to in-memory fallback.
