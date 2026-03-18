# Performance Report Template

## Run Context
- Date:
- Git commit:
- Environment (CPU/RAM/OS):
- Service config:
- Cache backend:

## Load Test Command
```bash
python3 scripts/load_test.py --url http://localhost:8000/reward/decide --duration 30 --workers 120 --timeout 2 --user-pool 10000
```

## Result Summary
- Total requests:
- HTTP responses:
- Successful requests:
- Attempt throughput (RPS):
- Response throughput (RPS):
- p50 latency (ms):
- p95 latency (ms):
- p99 latency (ms):

## Status Breakdown
- 2xx:
- 4xx:
- 5xx:
- Network/client errors:

## Assignment Target Check
- Target throughput (~300 RPS): PASS/FAIL
- p95 acceptable for local run: PASS/FAIL
- p99 acceptable for local run: PASS/FAIL

## Bottlenecks / Improvements
1.
2.
3.
