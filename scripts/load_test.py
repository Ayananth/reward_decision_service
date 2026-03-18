#!/usr/bin/env python3
import argparse
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    ordered = sorted(values)
    rank = int((p / 100.0) * (len(ordered) - 1))
    return ordered[rank]


def format_percentile(values: list[float], p: float) -> str:
    if not values:
        return "n/a"
    return f"{percentile(values, p):.2f}"


def build_payload(index: int, user_pool_size: int) -> bytes:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "txn_id": f"load-{uuid.uuid4()}",
        "user_id": f"load_user_{index % user_pool_size}",
        "merchant_id": f"merchant_{index % 50}",
        "amount": 100 + (index % 900),
        "txn_type": "PURCHASE",
        "ts": now,
    }
    return json.dumps(payload).encode("utf-8")


def worker(
    worker_id: int,
    url: str,
    duration_seconds: int,
    timeout_seconds: float,
    user_pool_size: int,
    counter_lock: threading.Lock,
    counter_ref: dict[str, int],
    results_lock: threading.Lock,
    latencies_ms: list[float],
    status_counts: Counter,
    error_counts: Counter,
) -> None:
    end_time = time.monotonic() + duration_seconds
    headers = {"Content-Type": "application/json"}

    while time.monotonic() < end_time:
        with counter_lock:
            request_index = counter_ref["value"]
            counter_ref["value"] += 1

        body = build_payload(request_index + worker_id, user_pool_size)
        request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                status_code = response.status
                response.read()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            with results_lock:
                latencies_ms.append(elapsed_ms)
                status_counts[status_code] += 1
        except urllib.error.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            with results_lock:
                latencies_ms.append(elapsed_ms)
                status_counts[exc.code] += 1
        except urllib.error.URLError as exc:
            reason_name = type(exc.reason).__name__ if exc.reason else "UnknownReason"
            with results_lock:
                error_counts[f"URLError:{reason_name}"] += 1
        except Exception as exc:  # noqa: BLE001
            with results_lock:
                error_counts[type(exc).__name__] += 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple threaded load test for POST /reward/decide",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/reward/decide",
        help="Target reward decision endpoint URL",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Test duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=120,
        help="Number of concurrent worker threads (default: 120)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Per-request timeout in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--user-pool",
        type=int,
        default=10000,
        help="Distinct user_id count to reduce per-user rate-limit collisions",
    )
    args = parser.parse_args()

    if args.duration <= 0:
        raise SystemExit("--duration must be > 0")
    if args.workers <= 0:
        raise SystemExit("--workers must be > 0")
    if args.user_pool <= 0:
        raise SystemExit("--user-pool must be > 0")

    latencies_ms: list[float] = []
    status_counts: Counter = Counter()
    error_counts: Counter = Counter()
    results_lock = threading.Lock()

    request_counter = {"value": 0}
    counter_lock = threading.Lock()

    print("Starting load test...")
    print(f"url={args.url}")
    print(
        f"duration={args.duration}s workers={args.workers} timeout={args.timeout}s user_pool={args.user_pool}"
    )

    start = time.perf_counter()
    threads = []
    for worker_id in range(args.workers):
        thread = threading.Thread(
            target=worker,
            args=(
                worker_id,
                args.url,
                args.duration,
                args.timeout,
                args.user_pool,
                counter_lock,
                request_counter,
                results_lock,
                latencies_ms,
                status_counts,
                error_counts,
            ),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - start

    total_requests = sum(status_counts.values()) + sum(error_counts.values())
    http_responses = sum(status_counts.values())
    successful_requests = sum(count for code, count in status_counts.items() if 200 <= code < 300)
    attempt_throughput = (total_requests / elapsed) if elapsed > 0 else 0.0
    response_throughput = (http_responses / elapsed) if elapsed > 0 else 0.0

    print("\nResults")
    print(f"total_requests={total_requests}")
    print(f"http_responses={http_responses}")
    print(f"successful_requests={successful_requests}")
    print(f"attempt_throughput_rps={attempt_throughput:.2f}")
    print(f"response_throughput_rps={response_throughput:.2f}")
    print(f"latency_p50_ms={format_percentile(latencies_ms, 50)}")
    print(f"latency_p95_ms={format_percentile(latencies_ms, 95)}")
    print(f"latency_p99_ms={format_percentile(latencies_ms, 99)}")

    if status_counts:
        print("status_counts:")
        for code in sorted(status_counts):
            print(f"  {code}: {status_counts[code]}")

    if error_counts:
        print("error_counts:")
        for name in sorted(error_counts):
            print(f"  {name}: {error_counts[name]}")


if __name__ == "__main__":
    main()
