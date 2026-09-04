#!/usr/bin/env python3
"""
Production Concurrency Benchmark for Falcon API.

Simulates 100+ concurrent users firing HTTP requests concurrently to benchmark:
- Throughput (Requests Per Second - RPS)
- Error Rate (must be 0.00%)
- Latency distribution (mean, p50, p90, p95, p99, min, max)

Can benchmark an already-running server or automatically spawn a server instance
(Granian / Gunicorn) via scripts/run_falcon_server.py.

Usage:
    # Benchmark an existing server at default http://127.0.0.1:8000
    python scripts/benchmark_concurrent_api.py --concurrency 100 --requests-per-user 20

    # Auto-spawn Granian with 4 workers & 16 threads, run benchmark, then shutdown
    python scripts/benchmark_concurrent_api.py --spawn-server --engine granian --concurrency 100

    # Benchmark raw WSGI health endpoint
    python scripts/benchmark_concurrent_api.py --endpoint-suite health --concurrency 100
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import httpx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

ENDPOINT_SUITES = {
    "health": [
        "/api/health",
    ],
    "inventory": [
        "/api/inventory",
    ],
    "mixed": [
        "/api/health",
        "/api/inventory",
        "/api/health",
        "/api/movers?retailer=Markets%20/%20Gurmar&max_files=1&limit=5",
        "/api/retailer-averages?retailer=Markets%20/%20Gurmar&max_files=1&aggregation=Average",
    ],
    "all": [
        "/api/health",
        "/api/inventory",
        "/api/history?retailer=Markets%20/%20Gurmar&max_files=1",
        "/api/retailer-averages?retailer=Markets%20/%20Gurmar&max_files=1&aggregation=Average",
        "/api/movers?retailer=Markets%20/%20Gurmar&max_files=1&limit=5",
        "/api/coverage?retailer=Markets%20/%20Gurmar&max_files=1&category_limit=20",
    ],
}


@dataclass
class RequestMetric:
    endpoint: str
    status_code: int
    duration_ms: float
    error: str | None = None


@dataclass
class BenchmarkSummary:
    engine: str
    target_url: str
    suite: str
    concurrent_users: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate_pct: float
    duration_seconds: float
    rps: float
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p75_ms: float
    latency_p90_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_min_ms: float
    latency_max_ms: float
    endpoint_breakdown: dict[str, dict[str, Any]]


async def simulated_user_worker(
    worker_id: int,
    client: httpx.AsyncClient,
    base_url: str,
    endpoints: list[str],
    requests_to_fire: int,
    metrics: list[RequestMetric],
) -> None:
    """Simulate a single concurrent user firing sequential requests against the API."""
    num_ep = len(endpoints)
    for i in range(requests_to_fire):
        # Round-robin or worker-offset selection through endpoint suite
        ep = endpoints[(worker_id + i) % num_ep]
        url = f"{base_url}{ep}"
        t0 = time.perf_counter()
        try:
            resp = await client.get(url)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code == 200:
                metrics.append(RequestMetric(endpoint=ep, status_code=resp.status_code, duration_ms=duration_ms))
            else:
                metrics.append(
                    RequestMetric(
                        endpoint=ep,
                        status_code=resp.status_code,
                        duration_ms=duration_ms,
                        error=f"HTTP {resp.status_code}: {resp.text[:120]}",
                    )
                )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            metrics.append(
                RequestMetric(
                    endpoint=ep,
                    status_code=0,
                    duration_ms=duration_ms,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )


async def execute_benchmark(
    base_url: str,
    suite_name: str,
    concurrency: int,
    requests_per_user: int,
    engine_label: str = "granian",
) -> BenchmarkSummary:
    """Execute concurrent user load test against Falcon API."""
    endpoints = ENDPOINT_SUITES[suite_name]

    # Configure connection pool for 100+ concurrent users
    limits = httpx.Limits(
        max_connections=concurrency + 50,
        max_keepalive_connections=concurrency + 20,
    )
    timeout = httpx.Timeout(30.0, connect=10.0)

    print(f"\n--> Pre-warming {len(endpoints)} endpoint(s)...")
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        for ep in endpoints:
            try:
                r = await client.get(f"{base_url}{ep}")
                if r.status_code != 200:
                    print(f"    [WARN] Warmup for {ep} returned {r.status_code}")
            except Exception as e:
                print(f"    [WARN] Warmup failed for {ep}: {e}")

        print(f"--> Launching load test: {concurrency} concurrent users firing {requests_per_user} requests each ({concurrency * requests_per_user} total)...")
        metrics: list[RequestMetric] = []
        t_start = time.perf_counter()

        tasks = [
            asyncio.create_task(
                simulated_user_worker(
                    worker_id=uid,
                    client=client,
                    base_url=base_url,
                    endpoints=endpoints,
                    requests_to_fire=requests_per_user,
                    metrics=metrics,
                )
            )
            for uid in range(concurrency)
        ]

        await asyncio.gather(*tasks)
        total_duration = time.perf_counter() - t_start

    total_requests = len(metrics)
    successful = [m for m in metrics if m.status_code == 200]
    failed = [m for m in metrics if m.status_code != 200]

    durations = [m.duration_ms for m in successful] if successful else [0.0]
    durations_arr = np.array(durations)

    err_rate = (len(failed) / total_requests * 100.0) if total_requests else 0.0
    rps = len(successful) / total_duration if total_duration > 0 else 0.0

    # Per-endpoint breakdown
    breakdown: dict[str, dict[str, Any]] = {}
    for ep in endpoints:
        ep_metrics = [m for m in metrics if m.endpoint == ep]
        if not ep_metrics:
            continue
        ep_success = [m for m in ep_metrics if m.status_code == 200]
        ep_durations = [m.duration_ms for m in ep_success]
        ep_arr = np.array(ep_durations) if ep_durations else np.array([0.0])
        breakdown[ep] = {
            "requests": len(ep_metrics),
            "success": len(ep_success),
            "errors": len(ep_metrics) - len(ep_success),
            "latency_mean_ms": round(float(np.mean(ep_arr)), 2),
            "latency_p50_ms": round(float(np.percentile(ep_arr, 50)), 2),
            "latency_p95_ms": round(float(np.percentile(ep_arr, 95)), 2),
        }

    return BenchmarkSummary(
        engine=engine_label,
        target_url=base_url,
        suite=suite_name,
        concurrent_users=concurrency,
        total_requests=total_requests,
        successful_requests=len(successful),
        failed_requests=len(failed),
        error_rate_pct=round(err_rate, 4),
        duration_seconds=round(total_duration, 3),
        rps=round(rps, 2),
        latency_mean_ms=round(float(np.mean(durations_arr)), 2),
        latency_p50_ms=round(float(np.percentile(durations_arr, 50)), 2),
        latency_p75_ms=round(float(np.percentile(durations_arr, 75)), 2),
        latency_p90_ms=round(float(np.percentile(durations_arr, 90)), 2),
        latency_p95_ms=round(float(np.percentile(durations_arr, 95)), 2),
        latency_p99_ms=round(float(np.percentile(durations_arr, 99)), 2),
        latency_min_ms=round(float(np.min(durations_arr)), 2),
        latency_max_ms=round(float(np.max(durations_arr)), 2),
        endpoint_breakdown=breakdown,
    )


def print_results(summary: BenchmarkSummary) -> None:
    """Print beautifully formatted benchmark results table."""
    sep = "=" * 70
    print("\n" + sep)
    print("   CONCURRENCY BENCHMARK RESULTS")
    print(sep)
    print(f"   Server Engine       : {summary.engine.upper()}")
    print(f"   Target URL          : {summary.target_url}")
    print(f"   Endpoint Suite      : {summary.suite}")
    print(f"   Simulated Users     : {summary.concurrent_users} concurrent clients")
    print(f"   Total Requests      : {summary.total_requests:,}")
    print(f"   Successful (200 OK) : {summary.successful_requests:,}")
    print(f"   Failed Requests     : {summary.failed_requests}")
    print(f"   Error Rate          : {summary.error_rate_pct:.2f}% " + ("(PASS)" if summary.error_rate_pct == 0.0 else "(FAIL)"))
    print(f"   Test Duration       : {summary.duration_seconds:.2f} seconds")
    print(f"   Throughput (RPS)    : {summary.rps:.1f} req/sec")
    print("-" * 70)
    print("   LATENCY PERCENTILES (ms):")
    print(f"     Min    : {summary.latency_min_ms:8.2f} ms")
    print(f"     Mean   : {summary.latency_mean_ms:8.2f} ms")
    print(f"     p50    : {summary.latency_p50_ms:8.2f} ms  (Median)")
    print(f"     p75    : {summary.latency_p75_ms:8.2f} ms")
    print(f"     p90    : {summary.latency_p90_ms:8.2f} ms")
    print(f"     p95    : {summary.latency_p95_ms:8.2f} ms")
    print(f"     p99    : {summary.latency_p99_ms:8.2f} ms")
    print(f"     Max    : {summary.latency_max_ms:8.2f} ms")
    print("-" * 70)
    print("   ENDPOINT BREAKDOWN:")
    for ep, data in summary.endpoint_breakdown.items():
        ep_short = ep if len(ep) <= 42 else ep[:39] + "..."
        print(f"     {ep_short:<42} | reqs: {data['requests']:4} | p50: {data['latency_p50_ms']:6.1f}ms | p95: {data['latency_p95_ms']:6.1f}ms")
    print(sep + "\n")


def find_free_port() -> int:
    """Find an available TCP port on localhost."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for_server(url: str, proc: subprocess.Popen[Any] | None = None, timeout_seconds: float = 20.0) -> bool:
    """Poll health check until server responds 200 OK."""
    t_end = time.time() + timeout_seconds
    while time.time() < t_end:
        if proc and proc.poll() is not None:
            return False
        try:
            r = httpx.get(f"{url}/api/health", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 100+ concurrent user benchmark for Falcon API.")
    parser.add_argument(
        "--target-url",
        default=DEFAULT_BASE_URL,
        help=f"Target Falcon API base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=100,
        help="Number of simulated concurrent users (default: 100).",
    )
    parser.add_argument(
        "--requests-per-user",
        type=int,
        default=20,
        help="Number of requests each concurrent user executes (default: 20 -> 2,000 total).",
    )
    parser.add_argument(
        "--endpoint-suite",
        choices=list(ENDPOINT_SUITES.keys()),
        default="mixed",
        help="Set of endpoints to test: 'health', 'inventory', 'mixed', or 'all' (default: mixed).",
    )
    parser.add_argument(
        "--spawn-server",
        action="store_true",
        help="Spawn a background server instance for the test and shut down after.",
    )
    parser.add_argument(
        "--engine",
        choices=["granian", "gunicorn"],
        default="granian",
        help="Server engine to spawn if --spawn-server is specified (default: granian).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Workers for spawned server (default: 4).",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=16,
        help="Threads per worker for spawned server (default: 16).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to bind if --spawn-server is used (default: dynamic free port).",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Path to write JSON benchmark summary.",
    )

    args = parser.parse_args()

    server_proc = None
    target_url = args.target_url
    engine_label = args.engine

    if args.spawn_server:
        listen_port = args.port if args.port > 0 else find_free_port()
        target_url = f"http://127.0.0.1:{listen_port}"
        print(f"--> Spawning background Falcon server ({args.engine}) on port {listen_port}...")
        server_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_falcon_server.py"),
            "--engine",
            args.engine,
            "--port",
            str(listen_port),
            "--workers",
            str(args.workers),
            "--threads",
            str(args.threads),
        ]
        server_proc = subprocess.Popen(server_cmd, stdin=subprocess.DEVNULL)
        if not wait_for_server(target_url, proc=server_proc, timeout_seconds=20.0):
            print(f"[ERROR] Spawned server on {target_url} failed to become healthy (exitcode={server_proc.poll()}).", file=sys.stderr)
            if server_proc:
                server_proc.terminate()
            return 1
        print(f"--> Server is healthy on {target_url}!")
    else:
        # Check if target_url is reachable
        try:
            r = httpx.get(f"{target_url}/api/health", timeout=2.0)
            if r.status_code != 200:
                print(f"[ERROR] Target {target_url}/api/health returned {r.status_code}", file=sys.stderr)
                return 1
        except Exception as e:
            print(f"[ERROR] Could not connect to {target_url}: {e}", file=sys.stderr)
            print("Tip: Use --spawn-server to automatically launch Granian or Gunicorn for testing.", file=sys.stderr)
            return 1

    try:
        summary = asyncio.run(
            execute_benchmark(
                base_url=target_url,
                suite_name=args.endpoint_suite,
                concurrency=args.concurrency,
                requests_per_user=args.requests_per_user,
                engine_label=engine_label,
            )
        )
        print_results(summary)

        if args.output_json:
            out_path = Path(args.output_json).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(asdict(summary), f, indent=2)
            print(f"--> Saved JSON benchmark summary to: {out_path}")

        # Requirement: Error rate must be 0%
        if summary.failed_requests > 0:
            print(f"[FAIL] Benchmark encountered {summary.failed_requests} failed requests!", file=sys.stderr)
            return 2

        print("[PASS] Benchmark completed successfully with 0% error rate!")
        return 0

    finally:
        if server_proc:
            print("--> Shutting down background server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
