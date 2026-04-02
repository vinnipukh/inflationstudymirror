import asyncio
import csv
import json
import logging
import os
import queue
import random
import re
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup
import rayobrowse
from playwright.async_api import async_playwright

import config

logger = logging.getLogger(__name__)
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class SkipCitySignal(Exception):      pass
class SkipBracketSignal(Exception):   pass
class StopSignal(Exception):          pass
class BrowserBlockedError(Exception): pass


# ---------------------------------------------------------------------------
# Command queue helpers
# ---------------------------------------------------------------------------

def check_commands(cmd_queue):
    """Drain the command queue and raise the appropriate signal."""
    try:
        while True:
            cmd = cmd_queue.get_nowait().strip().lower()
            if cmd in ("skip", "skip city"):
                raise SkipCitySignal()
            elif cmd in ("next", "skip bracket"):
                raise SkipBracketSignal()
            elif cmd == "stop":
                raise StopSignal()
            elif cmd in ("ok", "devam", "continue"):
                # FIX: was silently swallowed — user had no confirmation it was received
                logger.info("✅ 'ok' komutu alındı.")
    except queue.Empty:
        pass


async def interruptible_sleep(seconds, cmd_queue):
    end_time = time.time() + seconds
    while time.time() < end_time:
        check_commands(cmd_queue)
        await asyncio.sleep(min(0.5, end_time - time.time()))


# ---------------------------------------------------------------------------
# Alert & manual-solve
# ---------------------------------------------------------------------------

def beep_alert():
    try:
        import winsound
        for s in ["SystemExclamation", "SystemHand"]:
            try:
                winsound.PlaySound(s, winsound.SND_ALIAS | winsound.SND_SYNC)
                time.sleep(0.3)
            except Exception as e:
                # FIX: was silently swallowed — log so user knows why it's quiet
                logger.debug("Ses çalınamadı (%s): %s", s, e)
    except ImportError:
        import sys
        sys.stdout.write("\a\a\a")
        sys.stdout.flush()


async def wait_for_manual_solve(loop, reason, cmd_queue=None, timeout=90):
    """
    Reads only from cmd_queue — never calls input() directly.
    console_listener is the sole owner of stdin, preventing the deadlock
    that previously made CLI commands stop working and hangs last hours.
    Hard timeout ensures it can never block forever.
    """
    beep_alert()
    print(f"\n{'=' * 55}")
    print(f"🔒 {reason}")
    print(f"   Konsola 'ok' yazın devam etmek için.")
    print(f"   Veya: skip / next / stop")
    print(f"   {timeout}s içinde yanıt gelmezse otomatik devam edilir.")
    print(f"{'=' * 55}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(0.5)
        if cmd_queue:
            try:
                cmd = cmd_queue.get_nowait().strip().lower()
                if cmd == "next":
                    raise SkipBracketSignal()
                elif cmd == "skip":
                    raise SkipCitySignal()
                elif cmd == "stop":
                    raise StopSignal()
                elif cmd in ("ok", "devam", "continue"):
                    logger.info("✅ Manuel onay alındı.")
                    return
            except queue.Empty:
                pass

    logger.warning("⏱  Bekleme süresi doldu (%ds), otomatik devam.", timeout)


# ---------------------------------------------------------------------------
# Mouse helpers
# ---------------------------------------------------------------------------

async def _get_viewport(page):
    """Return (width, height) of the current viewport with safe fallback."""
    try:
        vp = page.viewport_size
        if vp:
            return vp["width"], vp["height"]
    except Exception:
        pass
    return 1280, 800


async def human_jittery_move(page, tx, ty, steps=15):
    # FIX: was hardcoded to (100-400, 50-150) regardless of viewport size.
    # Now uses actual viewport dimensions so it works on any resolution.
    vw, vh = await _get_viewport(page)
    sx = random.uniform(vw * 0.1, vw * 0.5)
    sy = random.uniform(vh * 0.05, vh * 0.2)
    await page.mouse.move(sx, sy)
    for i in range(steps):
        p = (i + 1) / steps
        nx = sx + (tx - sx) * p + random.uniform(-8, 8)
        ny = sy + (ty - sy) * p + random.uniform(-8, 8)
        await page.mouse.move(nx, ny)
        await asyncio.sleep(random.uniform(0.01, 0.05))


async def human_browsing_clicks(page, count=2):
    """
    Renamed from do_stupid_human_clicks — same behaviour, professional name.
    FIX: now uses actual viewport size instead of hardcoded dimensions.
    """
    try:
        vw, vh = await _get_viewport(page)
        for _ in range(count):
            x = random.uniform(vw * 0.1, vw * 0.9)
            y = random.uniform(vh * 0.2, vh * 0.9)
            await human_jittery_move(page, x, y)
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await page.mouse.click(x, y)
            await asyncio.sleep(random.uniform(0.2, 0.5))
    except Exception as e:
        logger.debug("human_browsing_clicks hatası: %s", e)


# Keep old name as alias so nothing else breaks
do_stupid_human_clicks = human_browsing_clicks


async def bracket_safe_clicks(page, count=1):
    """
    FIX: now picks from 6 varied zones instead of only the 4 screen edges,
    which was detectable as robotic after a few brackets.
    """
    try:
        vw, vh = await _get_viewport(page)
        zones = [
            (vw * 0.05, vw * 0.25, vh * 0.05, vh * 0.20),   # top-left
            (vw * 0.75, vw * 0.95, vh * 0.05, vh * 0.20),   # top-right
            (vw * 0.05, vw * 0.25, vh * 0.80, vh * 0.95),   # bottom-left
            (vw * 0.75, vw * 0.95, vh * 0.80, vh * 0.95),   # bottom-right
            (vw * 0.30, vw * 0.70, vh * 0.40, vh * 0.60),   # center
            (vw * 0.05, vw * 0.25, vh * 0.40, vh * 0.60),   # left-middle
        ]
        for _ in range(count):
            x1, x2, y1, y2 = random.choice(zones)
            x = random.uniform(x1, x2)
            y = random.uniform(y1, y2)
            await human_jittery_move(page, x, y)
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await page.mouse.click(x, y)
    except Exception as e:
        logger.debug("bracket_safe_clicks hatası: %s", e)


# ---------------------------------------------------------------------------
# Page classification
#
# FIX (Issues 1 & 2) — ROOT CAUSE of "everything is a login page":
#
#   sahibinden.com injects a hidden login modal into EVERY page (homepage,
#   search results, category pages) for the header login button. This modal
#   contains type="password" and type="email" fields even when completely
#   invisible. The old code fired is_login_page=True on any page that had
#   those fields anywhere in the DOM — which is almost every page.
#
#   THE FIX: URL-first logic with an explicit safe-URL allowlist.
#   HTML field checks are a last resort and now require "google ile giriş yap"
#   as the discriminator — this button only appears on the actual /giris page,
#   not in the hidden header modal.
# ---------------------------------------------------------------------------

_SAFE_URL_FRAGMENTS = (
    "/kiralik/",
    "/satilik/",
    "/ilan/",
    "/kategori/",
    "/cs/checkloading",
    "sahibinden.com/?",
    "sahibinden.com/arama",
)

_HOMEPAGE_URLS = (
    "https://www.sahibinden.com",
    "http://www.sahibinden.com",
    "https://sahibinden.com",
    "http://sahibinden.com",
)


def is_login_page(html, page=None):
    """
    Returns True ONLY when on the actual sahibinden /giris login page.
    Conservative by design: false negatives are recoverable; false positives
    abort the entire city scrape.
    """
    url = ""
    if page:
        try:
            url = page.url.lower().rstrip("/")
        except Exception:
            pass

    # --- Definitive LOGIN: URL contains /giris ---
    if url and (
        "secure.sahibinden.com/giris" in url
        or url.endswith("/giris")
        or ("/giris?" in url and "sahibinden.com" in url)
    ):
        return True

    # --- Definitive NOT LOGIN: URL is a known-safe path ---
    if url:
        if any(url == h.lower().rstrip("/") for h in _HOMEPAGE_URLS):
            return False
        if any(f in url for f in _SAFE_URL_FRAGMENTS):
            return False

    l = html.lower()

    # --- Definitive NOT LOGIN: search results or homepage body present ---
    if "searchresultstable" in l:
        return False
    if 'class="homepage' in l or 'id="homepage' in l:
        return False

    # --- Last-resort HTML check ---
    # "google ile giriş yap" is a visible button that appears ONLY on the
    # dedicated /giris page — it is NOT in the hidden header modal on other pages.
    # Require this alongside the password/email fields to avoid false positives.
    has_password     = 'type="password"' in l
    has_email        = 'type="email"' in l or 'name="email"' in l
    has_google_login = "google ile giriş yap" in l

    if has_password and has_email and has_google_login:
        return True

    return False


def is_protection_page(html, page):
    # Check login first so hCaptcha on the /giris page doesn't get
    # misreported as a protection page (was Issue 1).
    if is_login_page(html, page):
        return False, ""

    l = html.lower()
    checks = [
        ("px-captcha",   "PerimeterX"),
        ("cf-turnstile", "Turnstile"),
        ("datadome",     "DataDome"),
        ("g-recaptcha",  "reCAPTCHA"),
        ("h-captcha",    "hCaptcha"),
    ]
    for marker, name in checks:
        if marker in l:
            return True, name

    if "olağan dışı erişim" in l:
        return True, "PerimeterX"

    try:
        if "/cs/checkloading" in page.url.lower():
            return True, "Managed Challenge"
    except Exception:
        pass

    if "güvenlik doğrulaması" in l or "tarayıcınızı kontrol ediyoruz" in l:
        return True, "Cloudflare"

    if any(s in l for s in ["bir dakika lütfen", "doğrulanıyor"]):
        return True, "Cloudflare Wait"

    return False, ""


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------

async def warmup_with_human_surf(page, loop, cmd_queue=None):
    logger.info("🧑‍💻 Hızlı güven inşası (~10s)...")
    try:
        await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=60_000)
    except Exception as e:
        raise BrowserBlockedError(f"Ana sayfaya erişilemedi: {e}")

    await interruptible_sleep(random.uniform(*config.HOMEPAGE_WAIT), cmd_queue)
    html = await get_page_content(page)

    if is_login_page(html, page):
        raise BrowserBlockedError("Isınma sırasında login yönlendirmesi")

    # FIX: added exponential backoff between protection checks (was re-checking
    # immediately which itself looks bot-like to detection systems)
    backoff = 2.0
    for attempt in range(3):
        p, r = is_protection_page(html, page)
        if not p:
            break
        logger.info("🛡️  Koruma tespit edildi: %s (deneme %d/3)", r, attempt + 1)
        if "turnstile" in r.lower() or "cloudflare" in r.lower():
            if await auto_solve_turnstile(page, r, loop, cmd_queue):
                html = await get_page_content(page)
                if is_login_page(html, page):
                    raise BrowserBlockedError("Login (Turnstile sonrası)")
                continue
        await wait_for_manual_solve(loop, f"Isınma — {r}", cmd_queue)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 15)
        html = await get_page_content(page)
        if is_login_page(html, page):
            raise BrowserBlockedError("Login (manuel çözüm sonrası)")

    for _ in range(random.randint(2, 4)):
        await page.mouse.wheel(0, random.randint(200, 400))
        await asyncio.sleep(0.4)

    try:
        nav = page.locator("nav a, .mainNavigation a")
        cnt = await nav.count()
        if cnt > 0:
            box = await nav.nth(random.randint(0, min(cnt, 5) - 1)).bounding_box()
            if box:
                await human_jittery_move(
                    page,
                    box["x"] + box["width"]  / 2,
                    box["y"] + box["height"] / 2,
                )
    except Exception as e:
        logger.debug("Nav hover hatası: %s", e)

    await human_browsing_clicks(page, count=1)


# ---------------------------------------------------------------------------
# Cloudflare / Turnstile helpers
# ---------------------------------------------------------------------------

async def _wait_for_managed_redirect(page, max_wait=40):
    for _ in range(int(max_wait / 2)):
        await asyncio.sleep(2)
        try:
            if "/cs/checkloading" not in page.url.lower():
                return True
        except Exception:
            pass
        try:
            h = (await get_page_content(page, 3000)).lower()
            if "güvenlik doğrulaması" not in h and "searchresultstable" in h:
                return True
        except Exception:
            pass
    return False


async def _auto_solve_interactive_turnstile(page, loop, cmd_queue=None):
    bb = None
    for _ in range(15):
        for f in page.frames:
            if "challenges.cloudflare.com" in f.url:
                try:
                    bb = await f.frame_element().bounding_box()
                except Exception:
                    bb = None
                break
        if bb:
            break
        await asyncio.sleep(1)

    if not bb:
        await asyncio.sleep(25)
        return "tarayıcınızı kontrol ediyoruz" not in (await get_page_content(page)).lower()

    cx = bb["x"] + 14
    cy = bb["y"] + bb["height"] / 2
    wait = random.uniform(20.0, 30.0)

    await human_jittery_move(page, cx + random.uniform(30, 60), cy + random.uniform(-10, 10))
    for _ in range(random.randint(4, 6)):
        await asyncio.sleep(wait / 5)
        await page.mouse.move(cx + random.uniform(-5, 5), cy + random.uniform(-3, 3))

    await human_jittery_move(page, cx, cy)
    await asyncio.sleep(0.5)
    await page.mouse.click(cx, cy)
    await asyncio.sleep(3)

    try:
        btn = page.locator("#btn-continue")
        if await btn.count() > 0 and await btn.is_visible():
            bx = await btn.bounding_box()
            if bx:
                await human_jittery_move(
                    page,
                    bx["x"] + bx["width"]  / 2,
                    bx["y"] + bx["height"] / 2,
                )
                await btn.click()
    except Exception as e:
        logger.debug("Turnstile buton hatası: %s", e)

    for _ in range(10):
        await asyncio.sleep(2)
        if "tarayıcınızı kontrol ediyoruz" not in (await get_page_content(page, 3000)).lower():
            return True
    return False


async def auto_solve_turnstile(page, reason, loop, cmd_queue=None):
    managed = "managed" in reason.lower() or "checkloading" in reason.lower()
    success = (
        await _wait_for_managed_redirect(page)
        if managed
        else await _auto_solve_interactive_turnstile(page, loop, cmd_queue)
    )
    if success:
        await asyncio.sleep(3)
    return success


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

async def get_page_content(page, timeout=10000):
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception as e:
        logger.debug("wait_for_load_state zaman aşımı: %s", e)
    try:
        return await page.content()
    except Exception as e:
        # FIX: was silently swallowed — now logged so we can diagnose browser crashes
        logger.debug("page.content() ilk denemede hata, tekrar deneniyor: %s", e)
        await asyncio.sleep(3)
        return await page.content()


async def goto_with_retry(page, url, retries=3, timeout=60000):
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as e:
            err = str(e).lower()
            if "timeout" in err:
                if attempt < retries:
                    wait = random.uniform(*config.GOTO_RETRY_WAIT)
                    logger.debug("Timeout, %.1fs sonra tekrar (deneme %d/%d)", wait, attempt, retries)
                    await asyncio.sleep(wait)
                else:
                    raise BrowserBlockedError(f"Timeout: {url}") from e
            else:
                # FIX: non-timeout errors should fail immediately, not be retried.
                # Retrying a connection-reset or browser-closed error is pointless.
                raise BrowserBlockedError(f"Goto hatası: {e}") from e


async def safe_goto(page, url, loop, cmd_queue=None):
    await goto_with_retry(page, url)
    await interruptible_sleep(random.uniform(*config.PAGE_LOAD_AFTER_GOTO), cmd_queue)
    html = await get_page_content(page)

    if is_login_page(html, page):
        raise BrowserBlockedError(f"Login yönlendirmesi: {url}")

    backoff = 2.0
    for _ in range(3):
        p, r = is_protection_page(html, page)
        if not p:
            break
        if "turnstile" in r.lower() or "cloudflare" in r.lower():
            if await auto_solve_turnstile(page, r, loop, cmd_queue):
                html = await get_page_content(page)
                if is_login_page(html, page):
                    raise BrowserBlockedError("Login (Turnstile sonrası)")
                continue
        await wait_for_manual_solve(loop, r, cmd_queue)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 15)
        html = await get_page_content(page)
        if is_login_page(html, page):
            raise BrowserBlockedError("Login (manuel çözüm sonrası)")

    try:
        await page.wait_for_selector(
            "#searchResultsTable tbody tr.searchResultsItem",
            timeout=20000,
        )
    except Exception:
        pass

    return await get_page_content(page)


# ---------------------------------------------------------------------------
# Smart Adaptive Brackets
# ---------------------------------------------------------------------------

def extract_total_listings(soup):
    """
    Extract total listing count from sahibinden search results.
    Tries multiple strategies in order of reliability.
    Returns int or None.
    """
    # Strategy 1: dedicated result-count element
    res_elem = soup.select_one(".result-text, .search-result-title, [class*='resultCount']")
    if res_elem:
        text = res_elem.get_text(strip=True).replace(".", "").replace(",", "")
        m = re.search(r"(\d+)\s*ilan", text, re.IGNORECASE)
        if m:
            return int(m.group(1))

    # Strategy 2: any text node with "ilan bulundu / ilan var"
    for tag in soup.find_all(string=lambda t: t and "ilan" in t.lower()):
        parent = tag.parent
        if parent and parent.name not in ("script", "style", "title"):
            text = tag.strip().replace(".", "").replace(",", "")
            m = re.search(r"(\d+)\s*ilan\s*(?:bulundu|var)", text, re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass

    # Strategy 3: broad regex across full page text
    page_text = soup.get_text(separator=" ", strip=True)
    for pattern in [
        r"(\d[\d.]*)\s+ilan\s+bulundu",
        r"(\d[\d.]*)\s+ilan\s+var",
        r"aramanizda\s+(\d[\d.]*)\s+ilan",
        r"toplam\s+(\d[\d.]*)\s+ilan",
    ]:
        m = re.search(pattern, page_text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).replace(".", "").replace(",", ""))
            except ValueError:
                continue

    return None


async def scrape_adaptive_bracket(
    page,
    city_slug,
    city_name,
    min_price,
    max_price,
    loop,
    cmd_queue,
    done_ranges=None,
    depth=0,
    max_depth=6,
):
    """
    Smart adaptive bracket scraper.
    Peeks at total listing count and splits the range in half when too dense,
    up to max_depth=6 recursion levels (prevents stack overflow).
    """
    if done_ranges is None:
        done_ranges = set()

    range_key = (city_slug, min_price, max_price)
    pad = "  " * depth

    if range_key in done_ranges:
        logger.info("%s↩️  Zaten tamamlandı: %d-%d TL", pad, min_price, max_price)
        return 0

    width = max_price - min_price
    logger.info("%s🔍 Aralık kontrol: %d-%d TL [%s]", pad, min_price, max_price, city_slug)

    url = (
        f"{config.BASE_URL}/kiralik/{city_slug}"
        f"?pagingSize={config.PAGE_SIZE}&price_min={min_price}&price_max={max_price}"
    )

    try:
        html = await safe_goto(page, url, loop, cmd_queue)
    except (SkipBracketSignal, SkipCitySignal, StopSignal):
        raise
    except BrowserBlockedError as e:
        logger.error("%s❌ Engellendi (%d-%d TL): %s", pad, min_price, max_price, e)
        return 0

    soup = BeautifulSoup(html, "html.parser")
    total_listings = extract_total_listings(soup)

    if total_listings is not None:
        logger.info("%s📊 %d ilan (%d-%d TL)", pad, total_listings, min_price, max_price)
    else:
        logger.info("%s❓ İlan sayısı bilinmiyor, taranıyor (%d-%d TL)", pad, min_price, max_price)

    max_per_query = getattr(config, "MAX_LISTINGS_PER_QUERY", 1000)
    min_width     = getattr(config, "MIN_BRACKET_WIDTH", 500)

    should_split = (
        total_listings is not None
        and total_listings > max_per_query
        and width > min_width
        and depth < max_depth
    )

    if should_split:
        logger.info(
            "%s⚠️  Çok yoğun (%d > %d), ikiye bölünüyor: %d-%d TL",
            pad, total_listings, max_per_query, min_price, max_price,
        )
        mid = (min_price + max_price) // 2
        total_saved = 0

        logger.info("%s→ Sol: %d-%d TL", pad, min_price, mid)
        total_saved += await scrape_adaptive_bracket(
            page, city_slug, city_name, min_price, mid,
            loop, cmd_queue, done_ranges, depth + 1, max_depth,
        )

        await interruptible_sleep(random.uniform(*config.BETWEEN_BRACKETS), cmd_queue)

        logger.info("%s→ Sağ: %d-%d TL", pad, mid + 1, max_price)
        total_saved += await scrape_adaptive_bracket(
            page, city_slug, city_name, mid + 1, max_price,
            loop, cmd_queue, done_ranges, depth + 1, max_depth,
        )

        logger.info("%s✅ Bölme bitti: %d-%d TL → %d kayıt", pad, min_price, max_price, total_saved)
        done_ranges.add(range_key)
        return total_saved

    if total_listings is not None and total_listings > max_per_query:
        logger.warning(
            "%s⚠️  Min genişlik (%d TL) aşıldı ama sayı (%d) hâlâ yüksek, yine taranıyor.",
            pad, width, total_listings,
        )

    # --- Scrape page 1 (already loaded above) ---
    records, soup = parse_page(html)
    total_saved = len(records)
    if records:
        save_incremental(city_name, records)
        logger.info("%s💾 Sayfa 1: %d kayıt", pad, len(records))

    # --- Paginate ---
    page_num  = 1
    max_pages = getattr(config, "MAX_PAGES_PER_BRACKET", 20)

    while page_num < max_pages:
        check_commands(cmd_queue)
        next_btn = soup.find("a", title="Sonraki")
        if not next_btn or "href" not in next_btn.attrs:
            break

        next_url  = config.BASE_URL + next_btn["href"]
        page_num += 1

        await human_jittery_move(page, random.uniform(300, 600), random.uniform(300, 600), steps=5)
        await asyncio.sleep(0.5)
        await interruptible_sleep(random.uniform(*config.BETWEEN_PAGES), cmd_queue)

        try:
            html = await safe_goto(page, next_url, loop, cmd_queue)
        except (SkipBracketSignal, SkipCitySignal, StopSignal):
            raise
        except BrowserBlockedError as e:
            logger.error("%s❌ Sayfa %d'de engellendi: %s", pad, page_num, e)
            break

        records, soup = parse_page(html)
        if not records:
            logger.info("%s✅ Sayfa %d'de ilan yok, aralık bitti.", pad, page_num)
            break

        save_incremental(city_name, records)
        total_saved += len(records)
        logger.info("%s✔ Sayfa %d: %d kayıt (toplam: %d)", pad, page_num, len(records), total_saved)

        if page_num % 5 == 0:
            save_checkpoint(city_slug, min_price, page_num)

    done_ranges.add(range_key)
    save_checkpoint(city_slug, min_price, page_num)
    logger.info("%s🎉 %d-%d TL bitti: %d kayıt [%s]", pad, min_price, max_price, total_saved, city_slug)
    return total_saved


# ---------------------------------------------------------------------------
# Data parsing & persistence
# ---------------------------------------------------------------------------

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
        if len(parts) > 1 and all(d.isdigit() for d in parts) and all(len(d) == 3 for d in parts[1:]):
            c = "".join(parts)
    try:
        return float(c)
    except ValueError:
        return None


def get_room_col_index(soup):
    """
    FIX: normalises Turkish characters and does substring match so headers
    like "Oda Sayısı", "Oda/Salon", or just "Oda" all match correctly.
    """
    def normalise(s):
        return (s.lower()
                .replace("ı", "i").replace("ö", "o").replace("ü", "u")
                .replace("ş", "s").replace("ç", "c").replace("ğ", "g"))

    ths = [
        normalise(th.text.strip())
        for th in soup.select("#searchResultsTable thead th.searchResultsAttributeHeader")
    ]
    return next((i for i, h in enumerate(ths) if "oda" in h), None)


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("#searchResultsTable tbody tr.searchResultsItem")
    ri   = get_room_col_index(soup)
    recs = []

    for row in rows:
        try:
            pe = row.select_one(".searchResultsPriceValue")
            pr = normalize_price(pe.text.strip() if pe else None)

            le = row.select_one(".searchResultsLocationValue")
            d  = " / ".join(le.stripped_strings) if le else "N/A"

            attrs = row.select(".searchResultsAttributeValue")
            ro = (
                attrs[ri].text.strip()
                if ri is not None and len(attrs) > ri
                else (attrs[1].text.strip() if len(attrs) > 1 else "N/A")
            )

            if pr and d != "N/A":
                recs.append({"District": d, "Rooms": ro, "Price": pr})
        except Exception as e:
            logger.debug("Satır ayrıştırma hatası: %s", e)

    return recs, soup


def save_incremental(city_name, batch):
    if not batch:
        return
    path = config.get_city_csv_path(city_name)
    os.makedirs(config.get_city_output_dir(city_name), exist_ok=True)
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["District", "Rooms", "Price"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(batch)
    logger.info("   💾 %d kayıt → %s", len(batch), path)


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def load_checkpoint():
    cp = config.get_checkpoint_file()
    if os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                d = json.load(f)
            logger.info(
                "📌 Checkpoint: %s, bracket %s, sayfa %s",
                d.get("city"), d.get("bracket_index"), d.get("page_num"),
            )
            return d
        except Exception:
            logger.warning("⚠️  Checkpoint dosyası bozuk (%s), sıfırdan başlanıyor.", cp)
    return {}


def save_checkpoint(city_slug, bracket_index, page_num):
    """
    FIX: atomic write via temp-file + os.replace() so a mid-write crash
    never corrupts the checkpoint file.
    """
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    target = config.get_checkpoint_file()
    tmp    = target + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "city":          city_slug,
                    "bracket_index": bracket_index,
                    "page_num":      page_num,
                    "saved_at":      datetime.now().isoformat(),
                },
                f,
                indent=2,
            )
        os.replace(tmp, target)  # atomic on all OSes
    except Exception as e:
        logger.debug("Checkpoint kaydetme hatası: %s", e)


def clear_checkpoint():
    cp = config.get_checkpoint_file()
    try:
        if os.path.exists(cp):
            os.remove(cp)
    except Exception as e:
        # FIX: was unguarded — now logs instead of crashing on permission errors
        logger.warning("Checkpoint silinemedi: %s", e)


def get_resume_point(checkpoint, city_slug):
    if checkpoint.get("city") == city_slug:
        return checkpoint.get("bracket_index", 0), checkpoint.get("page_num", 1)
    return 0, 1


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

_COOKIE_DIR_CREATED = False


def get_cookie_path(city_slug):
    """FIX: create cookie directory only once per process, not on every call."""
    global _COOKIE_DIR_CREATED
    cd = os.path.join(config.CHECKPOINT_DIR, "cookies")
    if not _COOKIE_DIR_CREATED:
        os.makedirs(cd, exist_ok=True)
        _COOKIE_DIR_CREATED = True
    return os.path.join(cd, f"{city_slug}_cookies.json")


async def save_cookies(page, city_slug):
    try:
        cookies = await page.context.cookies()
        # FIX: filter out session cookies (no expiry set) — they expire on
        # next browser start anyway and inflate the file pointlessly
        now        = datetime.now(tz=timezone.utc).timestamp()
        persistent = [c for c in cookies if c.get("expires", -1) > now]
        with open(get_cookie_path(city_slug), "w", encoding="utf-8") as f:
            json.dump(persistent, f, indent=2)
        logger.info(
            "🍪 %d kalıcı çerez kaydedildi (%d oturum çerezi atlandı).",
            len(persistent), len(cookies) - len(persistent),
        )
    except Exception as e:
        logger.debug("Çerez kaydetme hatası: %s", e)


async def load_cookies(page, city_slug):
    path = get_cookie_path(city_slug)
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not cookies:
            return False
        # FIX: filter out already-expired cookies before injecting them,
        # so the browser doesn't waste requests with cookies that will be rejected
        now   = datetime.now(tz=timezone.utc).timestamp()
        valid = [c for c in cookies if c.get("expires", now + 1) > now]
        if not valid:
            logger.info("🍪 Tüm çerezlerin süresi dolmuş, atlanıyor.")
            return False
        await page.context.add_cookies(valid)
        logger.info("🍪 %d geçerli çerez yüklendi.", len(valid))
        return True
    except Exception as e:
        logger.debug("Çerez yükleme hatası: %s", e)
        return False


def delete_cookies(city_slug):
    path = get_cookie_path(city_slug)
    # FIX: was logging "silindi" even when the file didn't exist
    if os.path.exists(path):
        try:
            os.remove(path)
            logger.info("🗑️  Çerezler silindi.")
        except Exception as e:
            logger.warning("Çerezler silinemedi: %s", e)


# ---------------------------------------------------------------------------
# Core scraping loop
# ---------------------------------------------------------------------------

async def scrape_city_brackets(
    page, city_slug, city_name, brackets, loop, cmd_queue,
    start_bracket=0, start_page=1,
):
    total       = 0
    done_ranges = set()

    for bi, (mn, mx) in enumerate(brackets):
        check_commands(cmd_queue)
        if bi < start_bracket:
            continue

        logger.info("\n🔍 Ana bracket %d-%d TL", mn, mx)

        if bi > start_bracket:
            await interruptible_sleep(random.uniform(*config.BETWEEN_BRACKETS), cmd_queue)
        if bi > 0 or start_bracket > 0:
            await bracket_safe_clicks(page, count=1)

        count = await scrape_adaptive_bracket(
            page=page,
            city_slug=city_slug,
            city_name=city_name,
            min_price=mn,
            max_price=mx,
            loop=loop,
            cmd_queue=cmd_queue,
            done_ranges=done_ranges,
            depth=0,
        )
        total += count
        logger.info("✅ Bracket %d-%d TL bitti: %d kayıt", mn, mx, count)

    return total


async def scrape_city(city, checkpoint, cmd_queue):
    city_slug = city["url_slug"]
    city_name = city["name"]
    brackets  = city["brackets"]
    loop      = asyncio.get_event_loop()

    start_bracket, start_page = get_resume_point(checkpoint, city_slug)
    last_blocked_bracket = -1

    for attempt in range(1, config.MAX_RESTARTS_PER_CITY + 1):
        logger.info(
            "\n%s\nŞEHİR: %s — Deneme %d/%d\n%s",
            "=" * 50, city_name.upper(), attempt, config.MAX_RESTARTS_PER_CITY, "=" * 50,
        )

        pw      = None
        browser = None

        try:
            ws = rayobrowse.create_browser(
                headless=config.RAYOBROWSE_HEADLESS,
                target_os=config.RAYOBROWSE_TARGET_OS,
                browser_language=config.RAYOBROWSE_BROWSER_LANGUAGE,
                ui_language=config.RAYOBROWSE_UI_LANGUAGE,
            )
            pw      = await async_playwright().start()
            browser = await pw.chromium.connect_over_cdp(ws)

            ctx  = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            # --- Cookie warmup bypass ---
            warmed_up = False
            if await load_cookies(page, city_slug):
                try:
                    await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
                    await asyncio.sleep(2)
                    h = await get_page_content(page)
                    if (
                        not is_protection_page(h, page)[0]
                        and not is_login_page(h, page)
                        and "searchresultstable" in h.lower()
                    ):
                        logger.info("✅ Çerezler geçerli — ısınma atlandı.")
                        warmed_up = True
                    else:
                        delete_cookies(city_slug)
                except Exception as e:
                    logger.debug("Çerez doğrulama hatası: %s", e)
                    delete_cookies(city_slug)

            if not warmed_up:
                await warmup_with_human_surf(page, loop, cmd_queue)
                await save_cookies(page, city_slug)

            await interruptible_sleep(random.uniform(*config.HOMEPAGE_WAIT), cmd_queue)

            total = await scrape_city_brackets(
                page, city_slug, city_name, brackets, loop, cmd_queue,
                start_bracket, start_page,
            )

            logger.info("\n✅ %s tamamlandı — %d kayıt.", city_name, total)
            await save_cookies(page, city_slug)
            break  # clean success — no extra sleep

        except (SkipCitySignal, StopSignal):
            raise

        except SkipBracketSignal:
            start_bracket, start_page = get_resume_point(load_checkpoint(), city_slug)
            start_bracket += 1
            start_page     = 1

        except BrowserBlockedError as e:
            delete_cookies(city_slug)
            logger.error("🔒 Engellendi: %s", e)
            start_bracket, start_page = get_resume_point(load_checkpoint(), city_slug)

            if attempt > 1 and start_bracket == last_blocked_bracket:
                logger.warning("⏭️  Aynı bracket'ta tekrar bloklandı, atlanıyor.")
                start_bracket += 1
                start_page     = 1
            last_blocked_bracket = start_bracket

            if attempt < config.MAX_RESTARTS_PER_CITY:
                wait = random.uniform(30, 60)
                logger.info("⏳ %.1fs bekleniyor...", wait)
                await interruptible_sleep(wait, cmd_queue)
            else:
                logger.error("❌ %s max deneme sayısına ulaştı, atlanıyor.", city_name)
                await interruptible_sleep(30, cmd_queue)

        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass