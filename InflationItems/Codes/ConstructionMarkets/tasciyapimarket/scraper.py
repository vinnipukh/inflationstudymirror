#!/usr/bin/env python
"""TasciYapi (tasciyapi.com.tr) daily price scraper.

Two-stage concurrent crawl:

1.  DISCOVER  — one request per category page 1. The CodeIgniter paginator's
    last-page link ("»") carries data-ci-pagination-page=N, so the exact page
    count is known after a single request per category. No "fetch until empty"
    probing, no wasted trailing requests.
2.  BULK      — fetch all remaining pages concurrently (small worker pool,
    jittered delays, retry-with-backoff), extract products, write a dated CSV.

Design notes (see docs/scraping-wiki/ and docs/TECH-STACK-SEARCH.md):

- Transport: curl_cffi with Chrome TLS impersonation when available (the
  resilient client behind a Cloudflare proxy), plain requests as fallback.
- Resilience: Cloudflare challenge detection ("Just a moment" / 403+cf-mitigated)
  aborts loudly instead of silently committing a partial/empty CSV; per-request
  retries; per-category failure accounting; non-zero exit on significant failure.
- Data quality: stable product IDs decoded from the base64 tail of each product
  URL (e.g. /...-MTg3NQ== -> 1875), dedupe by ID, Turkish price normalization
  ("1.234,56 TL" -> 1234.56).

Compatibility: CSV columns are a superset of the previous
"Product Name,Price,Category" schema so the dashboard reader
(inflation_dashboard/adapters/csv_price_repository.py) keeps working:
filename pattern tasciyapi_products_YYYY-MM-DD.csv (date regex parses), plus
product_id column (ID_COLUMNS contains "product_id").

Usage:
    python scraper.py                     # full daily run
    python scraper.py --out /tmp/out      # write CSV elsewhere (testing)
    python scraper.py --categories alarm  # single category
    python scraper.py --smoke             # one category, page 1 only
"""
from __future__ import annotations

import argparse
import base64
import csv
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

try:  # preferred: Chrome TLS impersonation (Cloudflare-friendly)
    from curl_cffi import requests as http
    HTTP_LIB = "curl_cffi"
except ImportError:  # fallback: plain requests
    import requests as http
    HTTP_LIB = "requests"

BASE_URL = "https://www.tasciyapi.com.tr"
CATEGORY_URL = f"{BASE_URL}/kategori/{{category}}"
PAGE_URL = f"{BASE_URL}/kategori/{{category}}/sayfa/{{offset}}"

# Top-level category slugs from the site's category menu (verified 2026-08-16).
# The menu also exposes ~180 subcategory slugs; these 17 keep output comparable
# with historical data.
CATEGORIES = [
    "alarm",
    "bahce-ve-balkon",
    "banyo",
    "beyaz-esya",
    "dekorasyon-ve-ev-gerecleri",
    "elektrik-ve-aydinlatma",
    "elektrikli-el-aletleri",
    "hirdavat-el-aletleri-ve-oto",
    "hobi-boyalari",
    "insaat-malzemeleri",
    "isitma-ve-sogutma",
    "kamp-kapcilik-malzemeleri",
    "kisisel-bakim-setleri",
    "mobilya",
    "mutfak",
    "temizlik",
    "tesisat-malzemesi",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

# CodeIgniter pagination: first page is offset 0, then +PRODUCTS_PER_PAGE.
PRODUCTS_PER_PAGE = 15
CSV_COLUMNS = ["Product Name", "Price", "Category", "product_id", "url"]
CHALLENGE_TITLES = ("just a moment", "attention required", "verify you are human")
MAX_RETRIES = 3
MAX_WORKERS = 5


class ChallengeDetected(RuntimeError):
    """Cloudflare (or similar) interstitial served instead of page content."""


@dataclass
class Product:
    name: str
    price: float
    category: str
    product_id: str
    url: str

    def as_row(self) -> list[str | float]:
        return [self.name, self.price, self.category, self.product_id, self.url]


@dataclass
class CategoryRun:
    category: str
    pages: int = 0
    products: list[Product] = field(default_factory=list)  # thread-safe append (GIL)
    skipped_dup: int = 0
    skipped_zero: int = 0
    errors: list[str] = field(default_factory=list)


def fetch(url: str, *, retries: int = MAX_RETRIES) -> str:
    """GET ``url`` with retry/backoff; raise on challenge or persistent failure."""
    kwargs: dict = {"headers": HEADERS, "timeout": 30}
    if HTTP_LIB == "curl_cffi":
        kwargs["impersonate"] = "chrome124"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = http.get(url, **kwargs)
            _assert_not_challenged(resp, url)
            resp.raise_for_status()
            return resp.text
        except ChallengeDetected:
            raise
        except Exception as exc:  # noqa: BLE001 - network/status errors, retried
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt + random.random())
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_error!r}")


def _assert_not_challenged(resp: object, url: str) -> None:
    status = getattr(resp, "status_code", None)
    headers = getattr(resp, "headers", {}) or {}
    if status in (403, 503) and "cf-mitigated" in headers:
        raise ChallengeDetected(f"Cloudflare challenge on {url} (status {status})")
    if status == 503:  # typical for challenge interstitials that lack the header
        title = re.search(r"<title[^>]*>(.*?)</title>", resp.text or "", re.I | re.S)
        if title and title.group(1).strip().lower() in CHALLENGE_TITLES:
            raise ChallengeDetected(f"Cloudflare challenge interstitial on {url}")


def extract_last_page(soup: BeautifulSoup) -> int:
    """Last page index from the CodeIgniter paginator '»' link.

    The first page pagination block looks like: 1 2 3 > »
    where the '»' link carries data-ci-pagination-page=N. Its max value is the
    total page count; a single-page category has no block (or only page 1).
    """
    pagination = soup.select_one("ul.pagination")
    if not pagination:
        return 1
    pages = [
        int(li.get("data-ci-pagination-page"))
        for li in pagination.select("[data-ci-pagination-page]")
        if (li.get("data-ci-pagination-page") or "").isdigit()
    ]
    return max(pages) if pages else 1


def extract_products(soup: BeautifulSoup, category: str, skipped_zero: list[int] | None = None) -> list[Product]:
    """Parse products from a category page.

    Zero-priced items (data-price="0.0000") are placeholders / call-for-price
    listings and are skipped, matching historical scraper behaviour; each skip
    is appended to ``skipped_zero`` (if provided) as a counter.
    """
    products: list[Product] = []
    for container in soup.find_all("div", class_="product-item-container"):
        name_tag = container.find("h4")
        name = _collapse(name_tag.get_text(" ", strip=True)) if name_tag else ""
        if not name:
            continue

        a = container.find("a", href=True)
        url = a["href"] if a else ""
        if url.startswith("/"):
            url = f"{BASE_URL}{url}"
        product_id = decode_product_id(url)

        price = parse_price(_first_price_text(container))
        if price is None or price <= 0:
            if skipped_zero is not None:
                skipped_zero[0] += 1
            continue  # no usable price -> keep rows price-bearing (matches old behaviour)

        products.append(Product(name, price, category, product_id, url))
    return products


def _first_price_text(container: BeautifulSoup) -> str | None:
    for sel in ("span.price-new", "div.price"):
        node = container.select_one(sel)
        if node:
            return node.get_text(" ", strip=True)
    return None


def decode_product_id(url: str) -> str:
    """Base64 product id from the URL tail: /...-slug-MTg3NQ== -> '1875'."""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    token = tail.rsplit("-", 1)[-1] if "-" in tail else tail
    try:
        decoded = base64.b64decode(token, validate=True).decode("ascii")
        if decoded.isdigit():
            return decoded
    except Exception:  # noqa: BLE001 - fall back to URL-based key
        pass
    return url  # stable key even when id is unavailable


def parse_price(text: str | None) -> float | None:
    """Normalize Turkish prices: '1.234,56 TL' -> 1234.56, '320,30' -> 320.3."""
    if not text:
        return None
    cleaned = (
        text.replace("₺", "")
        .replace("TL", "")
        .replace("TRY", "")
        .replace("\xa0", " ")
    )
    cleaned = re.sub(r"[^0-9.,-]", "", cleaned)
    if not cleaned or cleaned in {"-", ".", ","}:
        return None
    if "," in cleaned:  # decimal comma: drop thousands separators, swap comma
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def discover_pages(category: str) -> int:
    """Fetch category page 1 and return the exact number of pages."""
    html = fetch(CATEGORY_URL.format(category=category))
    soup = BeautifulSoup(html, "html.parser")
    if not soup.find_all("div", class_="product-item-container"):
        return 0  # empty category
    return extract_last_page(soup)


def fetch_and_parse(url: str, category: str, zero_counter: list[int]) -> list[Product]:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    return extract_products(soup, category, skipped_zero=zero_counter)


def run_category(category: str, *, workers: int) -> CategoryRun:
    """Discover + bulk-fetch one category; returns run statistics."""
    run = CategoryRun(category=category)
    last_page = discover_pages(category)
    if last_page == 0:
        return run  # empty category (verified: site shows "Ürün yok!" notice)
    run.pages = last_page

    urls = [
        (PAGE_URL.format(category=category, offset=(page - 1) * PRODUCTS_PER_PAGE), category)
        for page in range(1, last_page + 1)
    ]
    seen: set[str] = set()
    zero_counter: list[int] = [0]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_and_parse, url, cat, zero_counter): url for url, cat in urls}
        for future in as_completed(futures):
            try:
                for product in future.result():
                    if product.product_id in seen:
                        run.skipped_dup += 1
                        continue
                    seen.add(product.product_id)
                    run.products.append(product)  # append is atomic under the GIL
            except Exception as exc:  # noqa: BLE001 - category-level accounting
                run.errors.append(f"{futures[future]}: {exc!r}")
            finally:
                time.sleep(random.uniform(0.05, 0.2))  # spread completion bursts
    run.skipped_zero = zero_counter[0]
    return run


def write_csv(products: Iterable[Product], path: Path) -> int:
    """Write CSV at ``path``; returns number of rows written."""
    seen: set[str] = set()
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for product in products:
            if product.product_id in seen:
                continue
            seen.add(product.product_id)
            writer.writerow(product.as_row())
            rows += 1
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TasciYapi daily price scraper")
    parser.add_argument("--out", type=Path, default=None, help="output directory (default: Datas/...)")
    parser.add_argument("--categories", default=None, help="comma-separated category subset")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--smoke", action="store_true", help="first category, page 1 only")
    args = parser.parse_args(argv)

    categories = args.categories.split(",") if args.categories else CATEGORIES
    if args.smoke:
        categories = categories[:1]

    if args.out:
        save_dir = args.out
    else:
        script_dir = Path(__file__).resolve().parent
        items_root = script_dir.parents[2]
        save_dir = items_root / "Datas" / "ConstructionSuppliesMarkets" / "TasciYapiMarket"
    save_dir.mkdir(parents=True, exist_ok=True)

    csv_path = save_dir / f"tasciyapi_products_{datetime.now():%Y-%m-%d}.csv"
    print(f"[tasciyapi] transport={HTTP_LIB} categories={len(categories)} workers={args.workers}")
    print(f"[tasciyapi] CSV -> {csv_path}")

    # Warmup: homepage first (wiki: homepage-first-navigation).
    fetch(f"{BASE_URL}/")

    summary: list[CategoryRun] = []
    for category in categories:
        run = run_category(category, workers=args.workers)
        summary.append(run)
        status = "ok" if not run.errors else f"{len(run.errors)} error(s)"
        if run.pages == 0 and not run.errors:
            status = "empty-category"
        print(
            f"[tasciyapi] {category:<32} pages={run.pages:>3} "
            f"products={len(run.products):>4} dup={run.skipped_dup:>3} "
            f"zero={run.skipped_zero:>4} {status}"
        )

    all_products = (p for run in summary for p in run.products)
    rows = write_csv(all_products, csv_path)
    failed = [r for r in summary if r.errors]
    print(f"[tasciyapi] done: total rows={rows}, failed categories={len(failed)}")

    for run in failed:
        for err in run.errors:
            print(f"[tasciyapi]   {run.category}: {err}")

    if rows == 0:
        return 2  # nothing scraped -> loudly fail (e.g. Cloudflare wall)
    if len(failed) / max(len(categories), 1) >= 0.3:
        return 1  # significant partial failure -> visible in Actions
    return 0


if __name__ == "__main__":
    sys.exit(main())