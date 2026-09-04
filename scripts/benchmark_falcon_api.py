import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from falcon.testing import TestClient
from inflation_dashboard.api.falcon_app import create_app

client = TestClient(create_app())

endpoints = [
    ("/api/health", "health"),
    ("/api/inventory", "inventory"),
    ("/api/retailer-averages", "retailer-averages"),
    ("/api/movers", "movers"),
    ("/api/coverage", "coverage"),
    ("/api/history", "history"),
    ("/api/products/search?q=ceket&limit=10", "products-search"),
    ("/api/product?product_id=M405487839-0027-0104", "product-detail"),
]

print(f"{'Endpoint':<22} | {'Cold (ms)':<10} | {'Warm 1 (ms)':<12} | {'Warm 2 (ms)':<12} | Status")
print("-" * 69)

for url, name in endpoints:
    t0 = time.perf_counter()
    r = client.simulate_get(url)
    cold_time = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    r1 = client.simulate_get(url)
    warm1_time = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    r2 = client.simulate_get(url)
    warm2_time = (time.perf_counter() - t0) * 1000

    assert r.status_code == 200, f"{name} cold failed: {r.status}"
    assert r1.status_code == 200, f"{name} warm1 failed: {r1.status}"
    assert r2.status_code == 200, f"{name} warm2 failed: {r2.status}"

    print(f"{name:<22} | {cold_time:8.2f} ms | {warm1_time:10.2f} ms | {warm2_time:10.2f} ms | {r.status}")
