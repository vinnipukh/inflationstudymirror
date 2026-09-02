"""
engine_selenium.py — Sarı site kira scraper engine.

Implements the proven daily-run pattern from the IstanbulAvrupa scraper:

  1. undetected-chromedriver + PERSISTENT profile (--user-data-dir)
     → cookies (cf_clearance, _px3) survive across daily runs; the profile
       IS the trust. Solve the CAPTCHA once on day one, then every run is warm.
  2. Manual solve-retry loop: pause → human solves in the visible Chrome
     window → press ENTER → verify listings visible → continue.
  3. Adaptive pacing: 2.5s base page delay (±50% jitter), adaptive 1.5–8s.
  4. Adaptive price-bracket splitting: the site caps queries at 1,000
     listings (20 pages × 50); ranges above that are split recursively.
  5. Checkpoint/resume: resolved brackets + completed brackets are cached
     per day, so a crashed run resumes without re-probing.

Compliance scope (docs/APPROACH.md B0): District, Rooms, Price, ilanId ONLY.
No detail pages, no contact info, no photos.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import re
import time
from typing import Any

import config
from bs4 import BeautifulSoup
from tqdm import tqdm

logger = logging.getLogger("engine_selenium")


# ── Adaptive Delay Tracker (friend's tactic) ────────────────────────────────


class AdaptiveDelayTracker:
    """Delay that shrinks on success streaks and grows on errors."""

    def __init__(self, initial: float = config.PAGE_LOAD_DELAY) -> None:
        self.current = initial
        self.consecutive_successes = 0
        self._last_request = 0.0

    def wait(self) -> None:
        """Wait for the current delay (±50% jitter), then mark request time."""
        actual = self.current * random.uniform(0.5, 1.5)
        elapsed = time.time() - self._last_request
        if elapsed < actual:
            time.sleep(actual - elapsed)
        self._last_request = time.time()

    def record_success(self) -> None:
        self.consecutive_successes += 1
        if self.consecutive_successes >= config.ADAPTIVE_SUCCESS_THRESHOLD:
            self.current = max(
                config.ADAPTIVE_MIN_DELAY,
                self.current * config.ADAPTIVE_DECREASE_FACTOR,
            )
            self.consecutive_successes = 0

    def record_failure(self) -> None:
        self.consecutive_successes = 0
        self.current = min(
            config.ADAPTIVE_MAX_DELAY, self.current * config.ADAPTIVE_INCREASE_FACTOR
        )


# ── Checkpoint (friend's pattern: per-day resolved/cached state) ────────────


def load_checkpoint() -> dict[str, Any]:
    path = config.get_checkpoint_file()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning("⚠️ Checkpoint bozuk — sıfırdan başlanıyor.")
    return {}


def save_checkpoint(state: dict[str, Any]) -> None:
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    tmp = config.get_checkpoint_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.get_checkpoint_file())  # atomic write


def clear_checkpoint() -> None:
    try:
        os.remove(config.get_checkpoint_file())
    except OSError:
        pass


# ── Browser setup (friend's tool: undetected-chromedriver + persistent profile)


def setup_driver(profile_dir: str | None = None) -> Any:
    """Return an undetected-chromedriver Chrome bound to a persistent
    user-data-dir. The profile carries cf_clearance/_px3 between daily runs —
    this is the cookie-saving trust strategy."""
    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir or config.PROFILE_DIR}")
    options.add_argument("--start-maximized")
    return uc.Chrome(options=options)


# ── HTML helpers ─────────────────────────────────────────────────────────────


def _normalise_tr(s: str) -> str:
    return (
        s.lower()
        .replace("ı", "i")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ç", "c")
        .replace("ğ", "g")
    )


def normalize_price(t: str | None) -> float | None:
    """'17.900 TL' / '16000' / '1.000.000 TL' → float; invalid → None."""
    if not t or t == "N/A":
        return None
    c = re.sub(r"[^\d,.]", "", t.lower().replace("tl", "").replace("₺", "").strip())
    if not c:
        return None
    if "." in c and "," in c:
        c = c.replace(".", "").replace(",", ".")
    elif "," in c:
        c = c.replace(",", ".")
    elif "." in c:
        parts = c.split(".")
        if (
            len(parts) > 1
            and all(d.isdigit() for d in parts)
            and all(len(d) == 3 for d in parts[1:])
        ):
            c = "".join(parts)
    try:
        return float(c)
    except ValueError:
        return None


def _get_room_col_index(soup: BeautifulSoup) -> int | None:
    ths = [
        _normalise_tr(th.text.strip())
        for th in soup.select(
            "#searchResultsTable thead th.searchResultsAttributeHeader"
        )
    ]
    return next((i for i, h in enumerate(ths) if "oda" in h), None)


def parse_page(html: str) -> tuple[list[dict[str, Any]], BeautifulSoup]:
    """Parse the search-results table. Fields: District, Rooms, Price, ilanId.
    Applies config.ROOMS_FILTER when set (compliance scope)."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("#searchResultsTable tbody tr[data-id]") or soup.select(
        "#searchResultsTable tbody tr.searchResultsItem"
    )
    ri = _get_room_col_index(soup)
    recs: list[dict[str, Any]] = []
    rooms_filter = getattr(config, "ROOMS_FILTER", None)

    for row in rows:
        try:
            pe = row.select_one(".searchResultsPriceValue")
            pr = normalize_price(pe.text.strip() if pe else None)
            le = row.select_one(".searchResultsLocationValue")
            d = " / ".join(le.stripped_strings) if le else "N/A"
            attrs = row.select(".searchResultsAttributeValue")
            ro = (
                attrs[ri].text.strip()
                if ri is not None and len(attrs) > ri
                else (attrs[1].text.strip() if len(attrs) > 1 else "N/A")
            )
            ilan_id = row.get("data-id")
            if rooms_filter and ro.strip() != rooms_filter:
                continue
            if pr and d != "N/A":
                recs.append(
                    {"District": d, "Rooms": ro, "Price": pr, "ilanId": ilan_id}
                )
        except Exception:
            logger.debug("Satır ayrıştırma hatası", exc_info=True)
    return recs, soup


def extract_total_listings(html: str) -> int | None:
    """Total listings for the current query: '3.193 ilan bulundu' or the pager
    'Toplam N sayfa içerisinde…' fallback."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select(".result-text"):
        m = re.search(r"([\d.]+)\s*ilan", el.get_text(" ", strip=True), re.IGNORECASE)
        if m:
            return int(m.group(1).replace(".", ""))
    pager = soup.select_one(".pageNavigator")
    if pager:
        m = re.search(
            r"Toplam\s+([\d.]+)\s+sayfa", pager.get_text(" ", strip=True), re.IGNORECASE
        )
        if m:
            return int(m.group(1).replace(".", "")) * config.PAGE_SIZE
    return None


# ── Challenge / login-wall handling (friend's solve-retry loop) ─────────────


def _is_listings_visible(driver: Any) -> bool:
    try:
        html = driver.execute_script("return document.documentElement.outerHTML;")
        soup = BeautifulSoup(html, "html.parser")
        if soup.select("#searchResultsTable tbody tr"):
            return True
        text = soup.get_text(" ", strip=True).lower()
        return "ilan bulunamadı" in text or "bulunamamıştır" in text
    except Exception:  # noqa: BLE001
        return False


def solve_captcha_loop(driver: Any, reason: str = "CAPTCHA veya giriş duvarı") -> None:
    """Pause and let the human solve the challenge in the visible Chrome window.
    Keep retrying until listings are visible (friend's loop)."""
    while True:
        print("\n" + "=" * 55)
        print(f"⚠️  ACTION REQUIRED: {reason} tespit edildi.")
        print("   1. Chrome penceresine bakın ve doğrulamayı çözün.")
        print("   2. İlan listesini AÇIKÇA görene kadar bekleyin.")
        print("=" * 55)
        input("   ▶ Listeyi gördükten sonra ENTER'a basın… ")

        time.sleep(2.0)
        try:
            driver.switch_to.window(driver.window_handles[-1])
            driver.switch_to.default_content()
        except Exception:  # noqa: BLE001, S110 — best-effort window focus
            pass
        if _is_listings_visible(driver):
            print("   ✅ Listeler görünür — devam ediliyor.")
            return


def page_needs_solve(html: str) -> bool:
    low = html.lower()
    return (
        "tarayıcınızı kontrol ediyoruz" in low
        or "/cs/tloading" in low
        or ("giriş yap" in low and "e-posta" in low and "şifre" in low)
    )


# ── Fetch with retry + backoff ───────────────────────────────────────────────


def fetch_page(
    driver: Any, delay: AdaptiveDelayTracker, url: str, attempts: int | None = None
) -> str:
    """Navigate with adaptive pacing; retry with exponential backoff on failure.
    If a challenge appears, hand control to the human (friend's loop)."""
    attempts = attempts or config.MAX_RETRIES
    backoff = config.RETRY_BACKOFF_BASE
    for attempt in range(1, attempts + 1):
        try:
            delay.wait()
            driver.get(url)
            time.sleep(1.0)
            html = driver.page_source
            if page_needs_solve(html):
                solve_captcha_loop(driver)
                html = driver.page_source
            delay.record_success()
            return html
        except Exception as e:
            delay.record_failure()
            if attempt >= attempts:
                raise
            wait = min(backoff * (2 ** (attempt - 1)), config.RETRY_BACKOFF_MAX)
            logger.warning(
                "⚠️ Getirme hatası (%s): %s — %.1fs sonra tekrar (%d/%d)",
                url[:80],
                e,
                wait,
                attempt + 1,
                attempts,
            )
            time.sleep(wait)
    raise RuntimeError("fetch_page: unreachable")  # pragma: no cover


# ── Bracket resolution (friend's adaptive splitting) ────────────────────────


def _bracket_url(city_slug: str, lo: int, hi: int) -> str:
    return (
        f"{config.BASE_URL}/kiralik/{city_slug}"
        f"?pagingSize={config.PAGE_SIZE}&price_min={lo}&price_max={hi}"
    )


def resolve_brackets(
    driver: Any,
    delay: AdaptiveDelayTracker,
    city_slug: str,
    ranges: list[tuple[int, int]],
    cached: list[list[int]] | None = None,
) -> list[tuple[int, int]]:
    """Probe each seed range; split recursively when the query exceeds the
    site's 1,000-listing cap. Cached leaf brackets are reused on resume."""
    if cached:
        return [tuple(b) for b in cached]

    safe: list[tuple[int, int]] = []

    def probe(lo: int, hi: int, depth: int = 0) -> None:
        if (
            depth > config.MAX_BRACKET_SPLIT_DEPTH
            or (hi - lo) < config.MIN_BRACKET_WIDTH
        ):
            safe.append((lo, hi))
            return
        html = fetch_page(driver, delay, _bracket_url(city_slug, lo, hi))
        total = extract_total_listings(html) or 0
        if total > config.MAX_LISTINGS_PER_QUERY:
            mid = (lo + hi) // 2
            probe(lo, mid, depth + 1)
            probe(mid + 1, hi, depth + 1)
        else:
            safe.append((lo, hi))

    for lo, hi in ranges:
        time.sleep(
            random.uniform(
                config.BETWEEN_BRACKET_DELAY_MIN, config.BETWEEN_BRACKET_DELAY_MAX
            )
        )
        probe(lo, hi)
    return safe


# ── Page scraping ───────────────────────────────────────────────────────────


def scrape_bracket(
    driver: Any,
    delay: AdaptiveDelayTracker,
    city_slug: str,
    lo: int,
    hi: int,
    city_name: str,
) -> int:
    """Scrape all pages of one safe bracket, saving incrementally."""
    saved = 0
    page_num = 0
    pager = None
    while page_num < config.MAX_PAGES_PER_BRACKET:
        url = (
            f"{config.BASE_URL}/kiralik/{city_slug}"
            f"?pagingSize={config.PAGE_SIZE}&pagingOffset={page_num * config.PAGE_SIZE}"
            f"&price_min={lo}&price_max={hi}"
        )
        html = fetch_page(driver, delay, url)
        recs, soup = parse_page(html)
        if not recs:
            break  # last page or genuinely empty bracket
        save_incremental(city_name, recs)
        saved += len(recs)
        page_num += 1

        # stop when the pager says we are on the final page
        pager = soup.select_one(".pageNavigator")
        if pager:
            m = re.search(
                r"Toplam\s+([\d.]+)\s+sayfa",
                pager.get_text(" ", strip=True),
                re.IGNORECASE,
            )
            if m:
                total_pages = int(m.group(1).replace(".", ""))
                cur = soup.select_one("#currentPageValue")
                cur_p = int(cur.get("value")) if cur and cur.get("value") else page_num
                if cur_p >= total_pages:
                    break
    logger.info("   💾 %s [%d-%d TL] → %d kayıt", city_name, lo, hi, saved)
    return saved


# ── Persistence (compliance schema: District, Rooms, Price, ilanId) ─────────


def save_incremental(city_name: str, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    path = config.get_city_csv_path(city_name)
    os.makedirs(config.get_city_output_dir(city_name), exist_ok=True)
    file_exists = os.path.isfile(path)
    fieldnames = ["District", "Rooms", "Price", "ilanId"]
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(batch)


# ── Orchestration ───────────────────────────────────────────────────────────


def scrape_city(city: dict[str, Any], resume: bool = False) -> int:
    city_slug, city_name = city["url_slug"], city["name"]
    logger.info("🚀 %s başlıyor (engine: selenium + kalıcı profil)…", city_name)
    print(
        "\n💡 GÜN 1 RİTÜELİ: ilk çalıştırmada doğrulama çıkarsa Chrome penceresinde "
        "ÇÖZÜN — profil kaydedilir, sonraki günler ısınmış oturumla geçer.\n"
    )

    checkpoint = load_checkpoint() if resume else {}
    done_key = f"done_{city_slug}"
    if checkpoint.get(done_key):
        logger.info("⏭️  %s bugün zaten tamamlandı.", city_name)
        return 0

    driver = setup_driver()
    try:
        delay = AdaptiveDelayTracker()
        cached_brackets = checkpoint.get(f"brackets_{city_slug}")
        brackets = resolve_brackets(
            driver, delay, city_slug, city["brackets"], cached=cached_brackets
        )
        if not cached_brackets:
            checkpoint[f"brackets_{city_slug}"] = [list(b) for b in brackets]
            save_checkpoint(checkpoint)
        logger.info("🔍 Güvenli bracketler: %s", brackets)

        total = 0
        for lo, hi in tqdm(brackets, desc=city_name, unit="bracket"):
            try:
                total += scrape_bracket(driver, delay, city_slug, lo, hi, city_name)
            except Exception as e:  # noqa: BLE001
                logger.warning("⚠️ Bracket [%d-%d] hatası: %s — atlanıyor.", lo, hi, e)
                delay.record_failure()

        checkpoint[done_key] = True
        save_checkpoint(checkpoint)
        logger.info("🏁 %s TAMAM: %d kayıt", city_name, total)
        return total
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001, S110 — best-effort teardown
            pass


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Sarı site kira scraper (selenium + kalıcı profil engine)"
    )
    parser.add_argument(
        "--city",
        type=str,
        default=None,
        help="Tek şehir (url slug): kayseri|sivas|tokat",
    )
    parser.add_argument(
        "--rooms", type=str, default=None, help="Oda filtresi (örn: 3+1); boş = tümü"
    )
    parser.add_argument("--resume", action="store_true", help="Checkpoint'ten devam et")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug loglama")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.rooms is not None:
        config.ROOMS_FILTER = args.rooms or None
        logger.info("🏠 Oda filtresi: %s", config.ROOMS_FILTER)

    cities = config.CITIES
    if args.city:
        cities = [c for c in config.CITIES if c["url_slug"] == args.city.lower()]
        if not cities:
            logger.error("Geçersiz şehir: %s", args.city)
            return

    completed = True
    try:
        for city in cities:
            scrape_city(city, resume=args.resume)
    except KeyboardInterrupt:
        completed = False
        logger.warning("🛑 Kullanıcı durdurdu.")
    finally:
        # Keep the checkpoint on crash/stop so --resume can continue;
        # clear it only after a fully successful run (fresh start next day).
        if completed:
            clear_checkpoint()


if __name__ == "__main__":
    main()
