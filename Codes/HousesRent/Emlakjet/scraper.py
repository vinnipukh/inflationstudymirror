"""Browser-backed Emlakjet residential rental scraper.

Emlakjet exposes only 50 pagination links per geographic scope.  The scraper
therefore starts at ``/kiralik-konut``, discovers province routes, and splits
large provinces into the district/neighborhood routes advertised by the site.
It uses the allowed ``?sayfa=`` parameter and does not use the robots-disallowed
``filtreler=ilan-sayisi=50`` shortcut.

Reliability (CI): pages load through :class:`Codes.HousesRent.browser.BrowserSession`,
which watchdog-times every command and restarts Chrome when a session stalls or
dies.  Run state is checkpointed under ``Datas/HousesRent/Emlakjet/state/``
(tracked, committed by the workflow) so ``--resume`` continues an interrupted
crawl across GitHub Actions runs; a finished day's checkpoint is deleted.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

try:
    from Codes.HousesRent.common import (
        CsvSink,
        absolute_url,
        clean_text,
        is_explicitly_sale_listing,
        load_checkpoint,
        make_listing_row,
        normalize_price,
        parse_area_m2,
        parse_listing_date,
        parse_location,
        save_checkpoint,
    )
except ModuleNotFoundError:  # pragma: no cover - direct-script compatibility
    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from Codes.HousesRent.common import (
        CsvSink,
        absolute_url,
        clean_text,
        is_explicitly_sale_listing,
        load_checkpoint,
        make_listing_row,
        normalize_price,
        parse_area_m2,
        parse_listing_date,
        parse_location,
        save_checkpoint,
    )

LOGGER = logging.getLogger("houses-rent.emlakjet")
BASE_URL = "https://www.emlakjet.com"
START_URL = f"{BASE_URL}/kiralik-konut"
BASE_PATH = "/kiralik-konut"
PAGE_SIZE = 30
MAX_PAGES_PER_SCOPE = 50
_NON_PROVINCE_SLUGS = {
    "emlakcidan",
    "sahibinden",
    "muteahhitten",
    "projeler",
    # The site exposes KKTC beside Turkish provinces; the requested scope is
    # the Republic of Türkiye, so leave it out of the default crawl.
    "kktc",
}
DEFAULT_OUTPUT = Path("Datas/HousesRent/Emlakjet")
# Tracked under Datas/ so the workflow can commit it and --resume survives
# across GitHub Actions runs.  Named "state/" because .gitignore excludes any
# directory called "checkpoints".
DEFAULT_CHECKPOINT = Path("Datas/HousesRent/Emlakjet/state/checkpoint.json")


def _text(node: Any) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _url_path(href: str) -> str:
    path = urlsplit(href).path.rstrip("/")
    return path or "/"


def _listing_url(article: Any) -> str:
    title = article.select_one("[data-listing-title]")
    link = title.select_one("a[href]") if title else None
    link = link or article.select_one("a[href*='/ilan/']")
    return absolute_url(BASE_URL, link.get("href") if link else None)


def _rooms_from_specs(specs: str) -> str:
    match = re.search(r"\b(\d+\s*\+\s*\d+)\b", specs)
    if match:
        return re.sub(r"\s+", "", match.group(1))
    match = re.search(r"\b(\d+)\s*oda\b", specs, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _date_from_specs(specs: str) -> str:
    match = re.search(r"\b\d{2}[./]\d{2}[./]\d{4}\b", specs)
    return parse_listing_date(match.group(0)) if match else ""


def _price_from_content(content: Any) -> int | float | None:
    for span in content.select("span"):
        text = _text(span)
        if "₺" in text or "TL" in text.upper():
            price = normalize_price(text)
            if price is not None:
                return price
    return None


def parse_page(html: str, collected_at: str | None = None) -> list[dict[str, Any]]:
    """Parse Emlakjet's public rental cards, excluding explicit sale cards."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for article in soup.select("article[data-listing-id]"):
        listing_url = _listing_url(article)
        title_node = article.select_one("[data-listing-title]")
        title = _text(title_node)
        if not listing_url or is_explicitly_sale_listing(title, listing_url):
            continue

        content = title_node.parent if title_node and title_node.parent else article
        paragraphs = content.find_all("p", recursive=False)
        if len(paragraphs) < 2:
            paragraphs = title_node.find_next_siblings("p", limit=2) if title_node else []
        location = _text(paragraphs[0]) if paragraphs else ""
        specs = _text(paragraphs[1]) if len(paragraphs) > 1 else ""
        province, district, neighborhood = parse_location(location)
        price = _price_from_content(content)
        if not province or not district or price is None:
            continue

        identifier = clean_text(str(article.get("data-listing-id", "")))
        if not identifier:
            match = re.search(r"-(\d+)$", urlsplit(listing_url).path)
            identifier = match.group(1) if match else ""
        if not identifier:
            continue

        rows.append(
            make_listing_row(
                ilan_id=identifier,
                listing_url=listing_url,
                province=province,
                district=district,
                neighborhood=neighborhood,
                property_type="Konut",
                rooms=_rooms_from_specs(specs),
                area_m2=parse_area_m2(specs),
                price=price,
                listing_date=_date_from_specs(specs),
                collected_at=collected_at,
            )
        )
    return rows


def extract_result_count(html: str) -> int | None:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = re.search(r"([\d.]+)\s+ilan\s+bulundu", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1).replace(".", ""))


def build_page_url(base_url: str, page: int) -> str:
    """Build an Emlakjet page URL using only the allowed ``sayfa`` query."""
    parts = urlsplit(base_url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "sayfa"]
    if page > 1:
        query.append(("sayfa", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), urlencode(query), ""))


def _canonical_scope_url(href: str) -> str:
    parts = urlsplit(absolute_url(BASE_URL, href))
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def discover_province_urls(html: str) -> set[str]:
    """Find first-level province rental routes from the country index."""
    found: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        href = _canonical_scope_url(anchor.get("href", ""))
        path_parts = [part for part in _url_path(href).split("/") if part]
        if len(path_parts) == 2 and path_parts[0] == BASE_PATH.strip("/"):
            # Province slugs are one token (including ``kktc``); the same
            # country page also contains SEO links to district/neighborhood
            # slugs with hyphens and category shortcuts such as
            # ``kiralik-daire``.  Use the route shape here rather than link
            # text because the site's province list is not consistently
            # labelled "Kiralık Ev".
            if "-" not in path_parts[1] and path_parts[1] not in _NON_PROVINCE_SLUGS:
                found.add(href)
    return found


def discover_child_scope_urls(html: str, scope_url: str) -> set[str]:
    """Find advertised district/neighborhood descendants of a scope."""
    current = _canonical_scope_url(scope_url)
    current_path = _url_path(current)
    current_slug = current_path.rsplit("/", 1)[-1]
    prefix = f"{BASE_PATH}/{current_slug}-"
    found: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        href = _canonical_scope_url(anchor.get("href", ""))
        path = _url_path(href)
        if path.startswith(prefix):
            # Province pages label some district links simply with the
            # district name, while others say "Kiralık Ev".  The route
            # prefix is the stable signal; category/source facets do not use
            # the current province slug as a prefix.
            found.add(href)
    return found


def _default_output() -> Path:
    return DEFAULT_OUTPUT / f"{time.strftime('%Y-%m-%d')}.csv"


def _default_checkpoint() -> Path:
    return DEFAULT_CHECKPOINT / f"checkpoint_{time.strftime('%Y-%m-%d')}.json"


def _scope_page_count(total: int | None) -> int:
    if total is None:
        return MAX_PAGES_PER_SCOPE
    return max(1, math.ceil(total / PAGE_SIZE))


def _has_listing_cards(html: str) -> bool:
    return bool(BeautifulSoup(html, "html.parser").select("article[data-listing-id]"))


def scrape(
    driver: Any | None = None,
    *,
    driver_factory: Any | None = None,
    start_url: str = START_URL,
    output_path: str | Path | None = None,
    checkpoint_path: str | Path | None = None,
    resume: bool = False,
    max_pages_per_scope: int = MAX_PAGES_PER_SCOPE,
    delay: float = 2.0,
    load_page: Any | None = None,
    max_page_retries: int = 3,
    page_timeout: float = 45.0,
) -> int:
    """Scrape all reachable rental scopes with checkpointed geographic splits.

    ``driver`` remains accepted for callers that already own a browser (and
    for tests injecting a ``load_page`` callable).  The normal CLI path passes
    ``driver_factory`` instead: :class:`BrowserSession` then restarts the
    browser up to ``max_page_retries`` times when the session stalls or dies
    (the CI failure mode), so a single hung page no longer kills the crawl.
    """
    if load_page is not None:

        def page_loader(url: str, *, wait_selector: str) -> str:
            if driver is None:  # pragma: no cover - defensive
                raise RuntimeError("load_page was injected without a driver")
            return load_page(driver, url, wait_selector=wait_selector)

        browser = None
    else:
        from Codes.HousesRent.browser import BrowserSession

        browser = BrowserSession(
            driver_factory,
            max_retries=max_page_retries,
            page_timeout=page_timeout,
            logger=LOGGER,
        )
        if driver is not None:
            browser.driver = driver

        def page_loader(url: str, *, wait_selector: str) -> str:
            assert browser is not None
            return browser.load(url, wait_selector=wait_selector)

    max_pages_per_scope = max(1, max_pages_per_scope)
    output = Path(output_path) if output_path else _default_output()
    checkpoint_file = Path(checkpoint_path) if checkpoint_path else _default_checkpoint()
    sink = CsvSink(output)
    state = load_checkpoint(checkpoint_file) if resume else {}
    # Resume only the crawl started today.  A checkpoint left by an earlier
    # day must not suppress a fresh daily crawl (all scopes are re-visited and
    # new listings are picked up; CsvSink deduplicates by ilanId).
    if state.get("checkpoint_date") != time.strftime("%Y-%m-%d"):
        state = {}
    processed = set(state.get("processed_scopes", []))
    pending = list(state.get("pending_scopes", []))
    active = state.get("active_scope")
    if active and active not in processed:
        pending.insert(0, active)
    if not pending:
        pending = [_canonical_scope_url(start_url)]

    homepage_html = page_loader(BASE_URL, wait_selector="body")
    if not homepage_html:
        raise RuntimeError("Emlakjet homepage returned an empty document")

    state.update(
        {
            "checkpoint_date": time.strftime("%Y-%m-%d"),
            "page_size": PAGE_SIZE,
            "max_pages_per_scope": max_pages_per_scope,
        }
    )
    save_checkpoint(checkpoint_file, state)
    written = 0

    try:
        while pending:
            scope_url = _canonical_scope_url(pending.pop(0))
            if scope_url in processed:
                continue
            state["active_scope"] = scope_url
            state["pending_scopes"] = pending
            save_checkpoint(checkpoint_file, state)

            first_html = page_loader(scope_url, wait_selector="article[data-listing-id]")
            total = extract_result_count(first_html)
            state.setdefault("scope_counts", {})[scope_url] = total
            scope_pages = _scope_page_count(total)
            cap = max_pages_per_scope * PAGE_SIZE

            if scope_url == _canonical_scope_url(start_url) and (total or 0) > cap:
                children = discover_province_urls(first_html)
            elif (total or 0) > cap:
                children = discover_child_scope_urls(first_html, scope_url)
            else:
                children = set()

            if children:
                for child in sorted(children):
                    if child not in processed and child not in pending:
                        pending.append(child)
                state.setdefault("split_scopes", []).append(scope_url)
                state["pending_scopes"] = pending
                state.pop("active_scope", None)
                save_checkpoint(checkpoint_file, state)
                LOGGER.info("Emlakjet split %s (%s listings) into %d scopes", scope_url, total or "unknown", len(children))
                continue

            if (total or 0) > cap:
                state.setdefault("partial_scopes", []).append(scope_url)
                LOGGER.warning(
                    "Emlakjet could not find geographic children for %s; only the first %d pages will be collected",
                    scope_url,
                    max_pages_per_scope,
                )

            if total is not None:
                scope_pages = min(scope_pages, max_pages_per_scope)
            else:
                scope_pages = max_pages_per_scope

            for page in range(1, scope_pages + 1):
                url = build_page_url(scope_url, page)
                html = first_html if page == 1 else page_loader(url, wait_selector="article[data-listing-id]")
                rows = parse_page(html)
                written += sink.write(rows)
                state["active_page"] = page
                state["rows_written"] = len(sink.seen_ids)
                save_checkpoint(checkpoint_file, state)
                LOGGER.info("Emlakjet %s page %d/%d: %d rows, %d new rows", scope_url, page, scope_pages, len(rows), written)
                if not _has_listing_cards(html) and page > 1:
                    break
                if page < scope_pages:
                    time.sleep(max(0.0, delay))

            processed.add(scope_url)
            state["processed_scopes"] = sorted(processed)
            state["pending_scopes"] = pending
            state.pop("active_scope", None)
            state.pop("active_page", None)
            save_checkpoint(checkpoint_file, state)

        state["status"] = "complete_with_warnings" if state.get("partial_scopes") else "complete"
        state["pending_scopes"] = []
        save_checkpoint(checkpoint_file, state)
        # The daily crawl finished; drop the checkpoint so tomorrow's --resume
        # starts a fresh crawl instead of replaying a completed day.
        try:
            checkpoint_file.unlink()
        except OSError:
            pass
    except Exception:
        state["status"] = "paused"
        state["pending_scopes"] = pending
        save_checkpoint(checkpoint_file, state)
        raise
    finally:
        if browser is not None:
            browser.close()
    return written


def _build_driver_factory(args: argparse.Namespace) -> Any:
    """Return a callable that creates a fresh Chrome for the crawl.

    CI runs launch with a brand-new temporary profile (``fresh_profile``) so
    every browser restart starts clean instead of reusing a possibly locked or
    corrupted profile directory.
    """
    from Codes.HousesRent.browser import create_chrome_driver

    def factory() -> Any:
        return create_chrome_driver(
            debugger_address=args.debugger_address,
            profile_dir=args.profile_dir,
            headless=args.headless,
            disable_images=not args.images,
            fresh_profile=not bool(args.profile_dir or args.debugger_address),
        )

    return factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape Emlakjet long-term residential rentals")
    parser.add_argument("--resume", action="store_true", help="resume today's geographic checkpoint (kept under Datas/ so CI runs can continue)")
    parser.add_argument("--start-url", default=START_URL, help="initial residential route; use a province/district for a bounded smoke run")
    parser.add_argument("--max-pages-per-scope", type=int, default=MAX_PAGES_PER_SCOPE, help="cap pages in one geographic route")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between listing pages")
    parser.add_argument("--max-page-retries", type=int, default=3, help="restart the browser and retry a page up to this many times")
    parser.add_argument("--page-timeout", type=float, default=45.0, help="seconds to wait for the listing grid on one page")
    parser.add_argument("--output", type=Path, default=None, help="CSV output path")
    parser.add_argument("--checkpoint", type=Path, default=None, help="checkpoint JSON path")
    parser.add_argument("--debugger-address", default=os.getenv("CHROME_DEBUGGER_ADDRESS"), help="attach to an existing Chrome, e.g. 127.0.0.1:9222")
    parser.add_argument("--profile-dir", type=Path, default=None, help="persistent Chrome profile when launching a browser")
    parser.add_argument("--headless", action="store_true", help="launch headless Chrome (not recommended for protected sites)")
    parser.add_argument("--images", action="store_true", help="allow listing images; disabled by default")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from Codes.HousesRent.browser import ChallengeDetected

    driver_factory = _build_driver_factory(args)
    try:
        return scrape(
            driver_factory=driver_factory,
            start_url=args.start_url,
            output_path=args.output,
            checkpoint_path=args.checkpoint,
            resume=args.resume,
            max_pages_per_scope=args.max_pages_per_scope,
            delay=args.delay,
            max_page_retries=args.max_page_retries,
            page_timeout=args.page_timeout,
        )
    except ChallengeDetected as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
