
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from falcon.testing import TestClient
from inflation_dashboard.api.falcon_app import create_app

client = TestClient(create_app())

# Check /api/products/search
r_search = client.simulate_get("/api/products/search?q=ceket&limit=3")
print("Search status:", r_search.status)
data_search = r_search.json
print("Search envelope keys:", list(data_search.keys()))
print("Search meta:", data_search["meta"])
print("Search errors:", data_search["errors"])
print("Search sample product:", data_search["data"][0] if data_search["data"] else None)

# Check /api/product
r_prod = client.simulate_get("/api/product?product_id=M405487839-0027-0104")
print("\nProduct detail status:", r_prod.status)
data_prod = r_prod.json
print("Product detail envelope keys:", list(data_prod.keys()))
print("Product detail meta:", data_prod["meta"])
print("Product detail summary:", data_prod["data"]["summary"])
print("Product detail history points:", len(data_prod["data"]["history"]))

# Check /api/product not found
r_404 = client.simulate_get("/api/product?product_id=NONEXISTENT_XYZ")
print("\n404 status:", r_404.status)
print("404 envelope keys:", list(r_404.json.keys()))
print("404 errors:", r_404.json["errors"])

# Check /api/product invalid filter
r_400 = client.simulate_get("/api/product")
print("\n400 status:", r_400.status)
print("400 errors:", r_400.json["errors"])
