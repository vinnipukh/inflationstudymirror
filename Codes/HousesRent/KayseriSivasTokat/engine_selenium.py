"""
engine_selenium.py — Sarı site kira scraper (friend-tactics engine)

Implements the proven daily-run pattern from the IstanbulAvrupa scraper:

  1. undetected-chromedriver + PERSISTENT profile (--user-data-dir)
     → cookies (cf_clearance, _px3) survive across daily runs; the profile
       IS the trust. Solve the CAPTCHA once on day one, then every run is warm.
  2. Manual solve-retry loop: pause → human solves in the visible Chrome
     window → press ENTER → verify listings visible → continue.
  3. Adaptive pacing: 2.5s base page delay (±50% jitter), adaptive 1.5–8s,
     faster than the old 8–12s scheme.
  4. Adaptive price-bracket splitting: sarı site caps queries at 1,000
     listings (20 pages × 50); ranges above that are split recursively.

Compliance scope (docs/APPROACH.md B0): ilanId + District + Rooms + Price ONLY.
No detail pages, no contact info, no photos.
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

import config

logger = logging.getLogger("engine_selenium")

# ── Paths (persistent profile lives next to the script) ─────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
PROFILE_DIR = str(_SCRIPTS_DIR / "SeleniumProfile")


# ── Adaptive Delay Tracker (friend's tactic) ────────────────────────────────

class AdaptiveDelayTracker:
    """Delay that shrinks on success streaks and grows on errors."""

    def __init__(self, initial: float = 2.5):
        self.current = initial
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self._last_request = 0.0

    def wait(self):
        # base jitter: ±50% (friend's PAGE_LOAD_DELAY behaviour)
        actual = self.current * random.uniform(0.5, 1.5)
        elapsed = time.time() - self._last_request
        if elapsed < actual:
            time.sleep(actual - elapsed)
        self._last_request = time.time()

    def record_success(self):
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        if self.consecutive_successes >= 3:
            self.current = max(config.ADAPTIVE_MIN_DELAY, self.current * 0.95)
            self.consecutive_successes = 0

    def record_failure(self):
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.current = min(config.ADAPTIVE_MAX_DELAY, self.current * 1.5)


# ── Browser setup (friend's tool: undetected-chromedriver + persistent profile)

def setup_driver(profile_dir: str | None = None) -> "uc.Chrome":
    """Return an undetected-chromedriver Chrome instance bound to a persistent
    user-data-dir. The profile carries cf_clearance/_px3 between daily runs —
    this is the cookie-saving trust strategy."""
    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir or PROFILE_DIR}")
    options.add_argument("--start-maximized")
    # version_main auto-detected by uc from the installed Chrome
    driver = uc.Chrome(options=options)
    return driver


# ── HTML helpers (ported from our recon + friend's tactics) ─────────────────

def _normalise_tr(s: str) -> str:
    return (s.lower()
            .replace("ı", "i").replace("ö", "o").replace("ü", "u")
            .replace("ş", "s").replace("ç", "c").replace("ğ", "g"))


def normalize_price(t):
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
        if (len(parts) > 1 and all(d.isdigit() for d in parts)
                and all(len(d) == 3 for d in parts[1:])):
            c = "".join(parts)
    try:
        return float(c)
    except ValueError:
        return None


def _get_room_col_index(soup):
    ths = [_normalise_tr(th.text.strip())
           for th in soup.select("#searchResultsTable thead th.searchResultsAttributeHeader")]
    return next((i for i, h in enumerate(ths) if "oda" in h), None)


def parse_page(html: str) -> tuple[list[dict], object]:
    """Parse the search-results table. Fields: ilanId, District, Rooms, Price.
    Applies config.ROOMS_FILTER when set."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("#searchResultsTable tbody tr[data-id]") or soup.select(
        "#searchResultsTable tbody tr.searchResultsItem")
    ri = _get_room_col_index(soup)
    recs = []
    rooms_filter = getattr(config, "ROOMS_FILTER", None)

    for row in rows:
        try:
            pe = row.select_one(".searchResultsPriceValue")
            pr = normalize_price(pe.text.strip() if pe else None)
            le = row.select_one(".searchResultsLocationValue")
            d = " / ".join(le.stripped_strings) if le else "N/A"
            attrs = row.select(".searchResultsAttributeValue")
            ro = (attrs[ri].text.strip() if ri is not None and len(attrs) > ri
                  else (attrs[1].text.strip() if len(attrs) > 1 else "N/A"))
            ilan_id = row.get("data-id")
            if rooms_filter and ro.strip() != rooms_filter:
                continue
            if pr and d != "N/A":
                recs.append({"ilanId": ilan_id, "District": d, "Rooms": ro, "Price": pr})
        except Exception as e:  # noqa: BLE001
            logger.debug("Satır ayrıştırma hatası: %s", e)
    return recs, soup


def extract_total_listings(html: str) -> int | None:
    """Total listings for the current query, e.g. '3.193 ilan bulundu' or the
    pager 'Toplam 101 sayfa içerisinde...'."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select(".result-text"):
        m = re.search(r"([\d.]+)\s*ilan", el.get_text(" ", strip=True), re.I)
        if m:
            return int(m.group(1).replace(".", ""))
    pager = soup.select_one(".pageNavigator")
    if pager:
        m = re.search(r"Toplam\s+([\d.]+)\s+sayfa", pager.get_text(" ", strip=True), re.I)
        if m:
            return int(m.group(1).replace(".", "")) * config.PAGE_SIZE
    return None


# ── Challenge / login-wall handling (friend's solve-retry loop) ─────────────

def _is_listings_visible(driver) -> bool:
    try:
        html = driver.execute_script("return document.documentElement.outerHTML;")
        soup = BeautifulSoup(html, "html.parser")
        if soup.select("#searchResultsTable tbody tr"):
            return True
        text = soup.get_text(" ", strip=True).lower()
        return "ilan bulunamadı" in text or "bulunamamıştır" in text
    except Exception:  # noqa: BLE001
        return False


def solve_captcha_loop(driver, reason: str = "CAPTCHA veya giriş duvarı") -> None:
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
        except Exception:  # noqa: BLE001
            pass
        if _is_listings_visible(driver):
            print("   ✅ Listeler görünür — devam ediliyor.")
            return


def page_needs_solve(html: str) -> bool:
    low = html.lower()
    if "tarayıcınızı kontrol ediyoruz" in low or "/cs/tloading" in low:
        return True
    if "giriş yap" in low and "e-posta" in low and "şifre" in low:
        return True
    return False


# ── Bracket resolution (friend's adaptive splitting) ────────────────────────

def _bracket_url(city_slug: str, lo: int, hi: int) -> str:
    return (f"{config.BASE_URL}/kiralik/{city_slug}"
            f"?pagingSize={config.PAGE_SIZE}&price_min={lo}&price_max={hi}")


def resolve_brackets(driver, delay: AdaptiveDelayTracker, city_slug: str,
                     ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Probe each seed range; split recursively when the query exceeds the
    site's 1,000-listing cap. Returns safe leaf brackets."""
    safe: list[tuple[int, int]] = []

    def probe(lo: int, hi: int, depth: int = 0):
        if depth > 6 or (hi - lo) < config.MIN_BRACKET_WIDTH:
            safe.append((lo, hi))
            return
        delay.wait()
        driver.get(_bracket_url(city_slug, lo, hi))
        time.sleep(1.0)
        html = driver.page_source
        if page_needs_solve(html):
            solve_captcha_loop(driver)
            html = driver.page_source
        total = extract_total_listings(html)
        if total is None:
            total = 0
        if total > config.MAX_LISTINGS_PER_QUERY:
            mid = (lo + hi) // 2
            probe(lo, mid, depth + 1)
            probe(mid + 1, hi, depth + 1)
        else:
            safe.append((lo, hi))

    for lo, hi in ranges:
        probe(lo, hi)
    return safe


# ── Page scraping ───────────────────────────────────────────────────────────

def scrape_bracket(driver, delay: AdaptiveDelayTracker, city_slug: str,
                   lo: int, hi: int, city_name: str) -> int:
    """Scrape all pages of one safe bracket, saving incrementally."""
    saved = 0
    page_num = 0
    while True:
        url = (f"{config.BASE_URL}/kiralik/{city_slug}"
               f"?pagingSize={config.PAGE_SIZE}&pagingOffset={page_num * config.PAGE_SIZE}"
               f"&price_min={lo}&price_max={hi}")
        delay.wait()
        driver.get(url)
        time.sleep(1.0)
        html = driver.page_source
        if page_needs_solve(html):
            solve_captcha_loop(driver)
            html = driver.page_source

        recs, soup = parse_page(html)
        if not recs:
            # last page or genuinely empty bracket
            break
        save_incremental(city_name, recs)
        saved += len(recs)
        logger.info("   💾 %s [%d-%d TL] sayfa %d → %d kayıt (toplam %d)",
                    city_name, lo, hi, page_num + 1, len(recs), saved)
        delay.record_success()
        page_num += 1
        if page_num >= config.MAX_PAGES_PER_BRACKET:
            break
        # detect last page via pager: "Toplam N sayfa" / current page
        pager = soup.select_one(".pageNavigator")
        if pager:
            m = re.search(r"Toplam\s+([\d.]+)\s+sayfa", pager.get_text(" ", strip=True), re.I)
            if m:
                total_pages = int(m.group(1).replace(".", ""))
                cur = soup.select_one("#currentPageValue")
                cur_p = int(cur.get("value")) if cur and cur.get("value") else page_num + 1
                if cur_p >= total_pages:
                    break
    return saved


# ── Persistence (reuse of our CSV schema) ───────────────────────────────────

def save_incremental(city_name: str, batch: list[dict]) -> None:
    if not batch:
        return
    path = config.get_city_csv_path(city_name)
    os.makedirs(config.get_city_output_dir(city_name), exist_ok=True)
    file_exists = os.path.isfile(path)
    fieldnames = ["ilanId", "District", "Rooms", "Price"]
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(batch)


# ── Orchestration ───────────────────────────────────────────────────────────

def scrape_city(city: dict, resume: bool = False) -> int:
    city_slug, city_name = city["url_slug"], city["name"]
    logger.info("🚀 %s başlıyor (engine: selenium + kalıcı profil)…", city_name)
    print("\n💡 GÜN 1 RİTÜELİ: ilk çalıştırmada doğrulama çıkarsa Chrome penceresinde "
          "ÇÖZÜN — profil kaydedilir, sonraki günler ısınmış oturumla geçer.\n")

    driver = setup_driver()
    try:
        delay = AdaptiveDelayTracker()
        brackets = resolve_brackets(driver, delay, city_slug, city["brackets"])
        logger.info("🔍 Güvenli bracketler: %s", brackets)

        total = 0
        for lo, hi in brackets:
            try:
                total += scrape_bracket(driver, delay, city_slug, lo, hi, city_name)
            except Exception as e:  # noqa: BLE001
                logger.warning("⚠️ Bracket [%d-%d] hatası: %s — atlanıyor.", lo, hi, e)
                delay.record_failure()
        logger.info("🏁 %s TAMAM: %d kayıt", city_name, total)
        return total
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="Sarı site kira scraper (selenium engine)")
    p.add_argument("--city", type=str, default=None, help="Tek şehir (url slug): kayseri|sivas|tokat")
    p.add_argument("--rooms", type=str, default=None, help="Oda filtresi (örn: 3+1); boş = tümü")
    p.add_argument("--resume", action="store_true", help="(uyumluluk) checkpoint'ten devam")
    args = p.parse_args()

    if args.rooms is not None:
        config.ROOMS_FILTER = args.rooms or None
        logger.info("🏠 Oda filtresi: %s", config.ROOMS_FILTER)

    cities = config.CITIES
    if args.city:
        cities = [c for c in config.CITIES if c["url_slug"] == args.city.lower()]
        if not cities:
            logger.error("Geçersiz şehir: %s", args.city)
            return

    for city in cities:
        try:
            scrape_city(city, resume=args.resume)
        except KeyboardInterrupt:
            logger.warning("🛑 Kullanıcı durdurdu.")
            break


if __name__ == "__main__":
    main()
