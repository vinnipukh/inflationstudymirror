"""
scraper.py — sarı site kira scraper (rayobrowse + Playwright)

Fixes applied in this version (see spec doc for full analysis):
  #3 Singleton browser — browser created ONCE per city, not per retry attempt.
                         Retries reuse the same browser; only cookies are cleared.
  #2 Viewport enforcement — viewport forced to 1920×1080 immediately after page
                            creation; JS screen.* properties patched to match.
  #4 Global cookies — one shared cookie file for all cities instead of three
                      per-city files. Same domain = same session = no waste.
  #1 Per-bracket login retry — on BrowserBlockedError the SAME bracket is
                                retried up to MAX_LOGIN_RETRIES_PER_BRACKET times
                                with exponential back-off before being skipped.
"""

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
# Signals (used as structured control-flow exceptions)
# ---------------------------------------------------------------------------

class SkipCitySignal(Exception):      pass
class SkipBracketSignal(Exception):   pass
class StopSignal(Exception):          pass
class BrowserBlockedError(Exception): pass


# ---------------------------------------------------------------------------
# Command queue helpers
# ---------------------------------------------------------------------------

def check_commands(cmd_queue):
    """Drain the command queue without blocking; raise the matching signal."""
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
                logger.info("✅ 'ok' komutu alındı.")
    except queue.Empty:
        pass


async def interruptible_sleep(seconds, cmd_queue):
    """Sleep for `seconds` but wake every 0.5 s to honour CLI commands."""
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
                logger.debug("Ses çalınamadı (%s): %s", s, e)
    except ImportError:
        import sys
        sys.stdout.write("\a\a\a")
        sys.stdout.flush()


async def wait_for_manual_solve(loop, reason, cmd_queue=None, timeout=90):
    """
    Ask the user to solve a challenge manually.

    Polls cmd_queue only — never calls input().  console_listener is the
    sole owner of stdin, preventing the deadlock that previously caused CLI
    commands to stop working and waits to last indefinitely.
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

def _viewport_size(page):
    """
    FIX #2: Always return the ENFORCED viewport (1920×1080), not the
    dynamic value assigned by rayobrowse's fingerprint engine.

    Rayobrowse randomises viewport for fingerprint diversity, which can
    produce sizes as small as 375×667 (mobile emulation).  Small viewports
    break Turnstile widget layout and cause click misses.  Since we force
    the viewport to 1920×1080 right after page creation (in scrape_city),
    this function simply returns those fixed values.
    """
    return config.FORCE_VIEWPORT_WIDTH, config.FORCE_VIEWPORT_HEIGHT


async def human_jittery_move(page, tx, ty, steps=15):
    """Move the mouse along a jittery curved path to target (tx, ty)."""
    vw, vh = _viewport_size(page)
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
    """Click random safe positions to simulate human reading/browsing."""
    try:
        vw, vh = _viewport_size(page)
        for _ in range(count):
            x = random.uniform(vw * 0.1, vw * 0.9)
            y = random.uniform(vh * 0.2, vh * 0.9)
            await human_jittery_move(page, x, y)
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await page.mouse.click(x, y)
            await asyncio.sleep(random.uniform(0.2, 0.5))
    except Exception as e:
        logger.debug("human_browsing_clicks hatası: %s", e)


# Keep old name as alias so nothing downstream breaks
do_stupid_human_clicks = human_browsing_clicks


async def bracket_safe_clicks(page, count=1):
    """
    Click varied zones between brackets to look human.
    Uses 6 zones (not just screen edges) to avoid a robotic pattern.
    """
    try:
        vw, vh = _viewport_size(page)
        zones = [
            (vw * 0.05, vw * 0.25, vh * 0.05, vh * 0.20),
            (vw * 0.75, vw * 0.95, vh * 0.05, vh * 0.20),
            (vw * 0.05, vw * 0.25, vh * 0.80, vh * 0.95),
            (vw * 0.75, vw * 0.95, vh * 0.80, vh * 0.95),
            (vw * 0.30, vw * 0.70, vh * 0.40, vh * 0.60),
            (vw * 0.05, vw * 0.25, vh * 0.40, vh * 0.60),
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
# FIX #2 — Viewport enforcement helper
# ---------------------------------------------------------------------------

async def enforce_viewport(page):
    """
    Force the page viewport to the configured safe desktop size and,
    optionally, patch the JS screen.* properties to match so that
    fingerprint and actual canvas dimensions stay consistent.

    This must be called immediately after acquiring the page object.
    """
    actual = page.viewport_size
    actual_w = actual["width"]  if actual else 0
    actual_h = actual["height"] if actual else 0

    if actual_w < config.MINIMUM_SAFE_VIEWPORT_WIDTH:
        logger.warning(
            "⚠️  Rayobrowse küçük viewport atadı (%dx%d). %dx%d'e zorlanıyor.",
            actual_w, actual_h,
            config.FORCE_VIEWPORT_WIDTH, config.FORCE_VIEWPORT_HEIGHT,
        )
    else:
        logger.debug(
            "Viewport %dx%d → %dx%d'e standardize ediliyor.",
            actual_w, actual_h,
            config.FORCE_VIEWPORT_WIDTH, config.FORCE_VIEWPORT_HEIGHT,
        )

    await page.set_viewport_size({
        "width":config.FORCE_VIEWPORT_WIDTH,
        "height":config.FORCE_VIEWPORT_HEIGHT,
    })

    if config.OVERRIDE_SCREEN_JS_PROPERTIES:
        w = config.FORCE_VIEWPORT_WIDTH
        h = config.FORCE_VIEWPORT_HEIGHT
        await page.evaluate(f"""() => {{
            try {{
                Object.defineProperty(screen, 'width',       {{value: {w}, configurable: true, writable: false}});
                Object.defineProperty(screen, 'height',      {{value: {h}, configurable: true, writable: false}});
                Object.defineProperty(screen, 'availWidth',  {{value: {w}, configurable: true}});
                Object.defineProperty(screen, 'availHeight', {{value: {h - 40}, configurable: true}});
                Object.defineProperty(window, 'innerWidth',  {{value: {w}, configurable: true}});
                Object.defineProperty(window, 'innerHeight', {{value: {h}, configurable: true}});
            }} catch(e) {{}}
        }}""")

    logger.info("🖥️  Viewport zorlandı: %dx%d", config.FORCE_VIEWPORT_WIDTH, config.FORCE_VIEWPORT_HEIGHT)


# ---------------------------------------------------------------------------
# Page classification
#
# ROOT CAUSE of "everything is a login page":
#   sarı site embeds a hidden login modal (type="password" + type="email")
#   into EVERY page for the header login button.  The old code fired on any
#   page with those fields anywhere in the DOM.
#
# THE FIX: URL-first logic + safe-URL allowlist + require "google ile giriş
#   yap" (only present on the real /giris page) as last-resort discriminator.
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
    Returns True ONLY when the browser is on the actual /giris login page.
    Conservative by design — false negatives are recoverable; false positives
    abort the entire city scrape.
    """
    url = ""
    if page:
        try:
            url = page.url.lower().rstrip("/")
        except Exception:
            pass

    # Definitive LOGIN via URL
    if url and (
        "secure.sahibinden.com/giris" in url
        or url.endswith("/giris")
        or ("/giris?" in url and "sahibinden.com" in url)
    ):
        return True

    # Definitive NOT LOGIN via safe URL allowlist
    if url:
        if any(url == h.lower().rstrip("/") for h in _HOMEPAGE_URLS):
            return False
        if any(f in url for f in _SAFE_URL_FRAGMENTS):
            return False

    l = html.lower()

    if "searchresultstable" in l:
        return False
    if 'class="homepage' in l or 'id="homepage' in l:
        return False

    # Last-resort HTML check — require the Google login button, which only
    # appears on the real /giris page and NOT in the hidden header modal.
    has_password     = 'type="password"' in l
    has_email        = 'type="email"' in l or 'name="email"' in l
    has_google_login = "google ile giriş yap" in l

    if has_password and has_email and has_google_login:
        return True

    return False


def is_protection_page(html, page):
    # Check login first — the real login page embeds hCaptcha; without this
    # guard it would be misreported as hCaptcha instead of a login redirect.
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


def _safe_url(page):
    """Return current page URL safely; empty string if disconnected."""
    try:
        return page.url
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------

async def warmup_with_human_surf(page, loop, cmd_queue=None):
    """
    Visit the homepage and perform human-like actions to build trust.
    Includes exponential back-off between protection-check iterations.
    """
    logger.info("🧑‍💻 Hızlı güven inşası (~10s)...")
    try:
        await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=60_000)
    except Exception as e:
        raise BrowserBlockedError(f"Ana sayfaya erişilemedi: {e}")

    logger.info("   📍 URL: %s", _safe_url(page))
    await interruptible_sleep(random.uniform(*config.HOMEPAGE_WAIT), cmd_queue)
    html = await get_page_content(page)

    if is_login_page(html, page):
        raise BrowserBlockedError(
            f"Isınma sırasında login yönlendirmesi (URL: {_safe_url(page)})"
        )

    backoff = 2.0
    for attempt in range(3):
        p, r = is_protection_page(html, page)
        if not p:
            break
        logger.info("🛡️  Koruma: %s | URL: %s (deneme %d/3)", r, _safe_url(page), attempt + 1)
        if "turnstile" in r.lower() or "cloudflare" in r.lower():
            if await auto_solve_turnstile(page, r, loop, cmd_queue):
                html = await get_page_content(page)
                if is_login_page(html, page):
                    raise BrowserBlockedError("Login (Turnstile sonrası)")
                continue
        await wait_for_manual_solve(loop, f"Isınma — {r} | {_safe_url(page)}", cmd_queue)
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
                logger.info("   ✅ Managed challenge geçildi. URL: %s", _safe_url(page))
                return True
        except Exception:
            pass
        try:
            h = (await get_page_content(page, 3000)).lower()
            if "güvenlik doğrulaması" not in h and "searchresultstable" in h:
                logger.info("   ✅ Sayfa yüklendi (managed). URL: %s", _safe_url(page))
                return True
        except Exception:
            pass
    logger.warning("   ⚠️  Managed redirect bekleme süresi doldu. URL: %s", _safe_url(page))
    return False


async def _auto_solve_interactive_turnstile(page, loop, cmd_queue=None):
    """
    Attempt to solve an interactive Cloudflare Turnstile challenge.

    FIX (pre-solve stray click): checks whether the challenge is still
    present BEFORE touching the mouse.  If the user already solved it,
    we return True immediately without clicking the (now-loaded results) page.
    """
    # --- Early-exit: challenge already gone ---
    try:
        h = await get_page_content(page, 3000)
        if "tarayıcınızı kontrol ediyoruz" not in h.lower():
            logger.info(
                "   ✅ Turnstile zaten çözülmüş (kullanıcı tarafından). URL: %s",
                _safe_url(page),
            )
            return True
    except Exception:
        pass

    # --- Find Cloudflare iframe ---
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
        # Re-check between waits — user may solve while we're looking
        try:
            h = await get_page_content(page, 2000)
            if "tarayıcınızı kontrol ediyoruz" not in h.lower():
                logger.info(
                    "   ✅ Turnstile iframe bekleme sırasında çözüldü. URL: %s",
                    _safe_url(page),
                )
                return True
        except Exception:
            pass
        await asyncio.sleep(1)

    if not bb:
        logger.warning("   ⚠️  Turnstile iframe bulunamadı. URL: %s", _safe_url(page))
        await asyncio.sleep(25)
        result = "tarayıcınızı kontrol ediyoruz" not in (await get_page_content(page)).lower()
        logger.info(
            "   %s Turnstile iframe-sız bekleme sonucu: %s. URL: %s",
            "✅" if result else "❌", result, _safe_url(page),
        )
        return result

    logger.info("   🖱️  Turnstile iframe bulundu, tıklanıyor...")
    cx   = bb["x"] + 14
    cy   = bb["y"] + bb["height"] / 2
    wait = random.uniform(20.0, 30.0)

    await human_jittery_move(page, cx + random.uniform(30, 60), cy + random.uniform(-10, 10))
    for _ in range(random.randint(4, 6)):
        # Check again during hover — user may solve while we're moving
        try:
            h = await get_page_content(page, 1000)
            if "tarayıcınızı kontrol ediyoruz" not in h.lower():
                logger.info(
                    "   ✅ Turnstile hover sırasında çözüldü. URL: %s", _safe_url(page)
                )
                return True
        except Exception:
            pass
        await asyncio.sleep(wait / 5)
        await page.mouse.move(cx + random.uniform(-5, 5), cy + random.uniform(-3, 3))

    # Final pre-click check
    try:
        h = await get_page_content(page, 2000)
        if "tarayıcınızı kontrol ediyoruz" not in h.lower():
            logger.info(
                "   ✅ Turnstile tıklama öncesi çözüldü. URL: %s", _safe_url(page)
            )
            return True
    except Exception:
        pass

    await human_jittery_move(page, cx, cy)
    await asyncio.sleep(0.5)
    await page.mouse.click(cx, cy)
    logger.info("   🖱️  Turnstile checkbox tıklandı.")
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
                logger.info("   🖱️  'Devam' butonu tıklandı.")
    except Exception as e:
        logger.debug("Turnstile devam butonu hatası: %s", e)

    for i in range(10):
        await asyncio.sleep(2)
        try:
            h = await get_page_content(page, 3000)
            if "tarayıcınızı kontrol ediyoruz" not in h.lower():
                logger.info(
                    "   ✅ Turnstile geçildi (%d. kontrol). URL: %s",
                    i + 1, _safe_url(page),
                )
                return True
        except Exception:
            pass

    logger.warning("   ❌ Turnstile geçilemedi. URL: %s", _safe_url(page))
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
        logger.debug("page.content() ilk denemede hata: %s — tekrar deneniyor", e)
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
                    logger.warning(
                        "⏱  Timeout (deneme %d/%d), %.1fs sonra tekrar: %s",
                        attempt, retries, wait, url,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise BrowserBlockedError(f"Timeout: {url}") from e
            else:
                # Non-timeout errors are not recoverable by retrying
                raise BrowserBlockedError(f"Goto hatası: {e}") from e


async def safe_goto(page, url, loop, cmd_queue=None):
    await goto_with_retry(page, url)
    await interruptible_sleep(random.uniform(*config.PAGE_LOAD_AFTER_GOTO), cmd_queue)
    html = await get_page_content(page)

    # Log final URL — makes unexpected redirects immediately visible
    final_url = _safe_url(page)
    if final_url and "sahibinden.com" not in final_url.lower():
        logger.warning(
            "⚠️  Beklenmeyen yönlendirme! İstenen: %s → Gelen: %s", url, final_url
        )

    if is_login_page(html, page):
        raise BrowserBlockedError(
            f"Login yönlendirmesi: {final_url} (istenen: {url})"
        )

    backoff = 2.0
    for _ in range(3):
        p, r = is_protection_page(html, page)
        if not p:
            break
        logger.info("🛡️  Koruma: %s | URL: %s", r, final_url)
        if "turnstile" in r.lower() or "cloudflare" in r.lower():
            if await auto_solve_turnstile(page, r, loop, cmd_queue):
                html      = await get_page_content(page)
                final_url = _safe_url(page)
                logger.info("   📍 Turnstile sonrası URL: %s", final_url)
                if is_login_page(html, page):
                    raise BrowserBlockedError(
                        f"Login (Turnstile sonrası, URL: {final_url})"
                    )
                continue
        await wait_for_manual_solve(loop, f"{r} | URL: {final_url}", cmd_queue)
        await asyncio.sleep(backoff)
        backoff   = min(backoff * 2, 15)
        html      = await get_page_content(page)
        final_url = _safe_url(page)
        if is_login_page(html, page):
            raise BrowserBlockedError(
                f"Login (manuel çözüm sonrası, URL: {final_url})"
            )

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
    Extract total listing count from a sarı site results page.
    Tries three strategies in order of reliability.
    Returns int or None.
    """
    res_elem = soup.select_one(".result-text, .search-result-title, [class*='resultCount']")
    if res_elem:
        text = res_elem.get_text(strip=True).replace(".", "").replace(",", "")
        m = re.search(r"(\d+)\s*ilan", text, re.IGNORECASE)
        if m:
            return int(m.group(1))

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

    Peeks at total listing count and splits the range in half when too
    dense, up to max_depth=6 recursion levels.

    Does NOT call save_checkpoint — that is the responsibility of the
    caller (scrape_city_brackets) so checkpoint format stays consistent.
    """
    if done_ranges is None:
        done_ranges = set()

    range_key = (city_slug, min_price, max_price)
    pad = "  " * depth

    if range_key in done_ranges:
        logger.info("%s↩️  Zaten tamamlandı: %d-%d TL", pad, min_price, max_price)
        return 0

    width = max_price - min_price
    logger.info("%s🔍 Aralık: %d-%d TL [%s]", pad, min_price, max_price, city_slug)

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
        raise  # Re-raise so scrape_city can apply per-bracket retry logic (#1)

    soup            = BeautifulSoup(html, "html.parser")
    total_listings  = extract_total_listings(soup)
    max_per_query   = config.MAX_LISTINGS_PER_QUERY
    min_width       = config.MIN_BRACKET_WIDTH

    if total_listings is not None:
        logger.info("%s📊 %d ilan (%d-%d TL)", pad, total_listings, min_price, max_price)
    else:
        logger.info(
            "%s❓ İlan sayısı bilinmiyor, taranıyor (%d-%d TL)", pad, min_price, max_price
        )

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
        mid         = (min_price + max_price) // 2
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

        logger.info(
            "%s✅ Bölme bitti: %d-%d TL → %d kayıt", pad, min_price, max_price, total_saved
        )
        done_ranges.add(range_key)
        return total_saved

    if total_listings is not None and total_listings > max_per_query:
        logger.warning(
            "%s⚠️  Min genişlik (%d TL) aşıldı ama sayı (%d) hâlâ yüksek, yine taranıyor.",
            pad, width, total_listings,
        )

    # --- Scrape page 1 (already loaded) ---
    records, soup = parse_page(html)
    total_saved   = len(records)
    if records:
        save_incremental(city_name, records)
        logger.info("%s💾 Sayfa 1: %d kayıt", pad, len(records))
    else:
        prot, prot_name = is_protection_page(html, page)
        logger.warning(
            "%s⚠️  Sayfa 1'de kayıt yok! URL: %s | Koruma: %s | HTML: %d karakter",
            pad, _safe_url(page), prot_name if prot else "yok", len(html),
        )

    # --- Paginate ---
    page_num  = 1
    max_pages = config.MAX_PAGES_PER_BRACKET

    while page_num < max_pages:
        check_commands(cmd_queue)
        next_btn = soup.find("a", title="Sonraki")
        if not next_btn or "href" not in next_btn.attrs:
            logger.info("%s📄 Son sayfa: %d", pad, page_num)
            break

        next_url  = config.BASE_URL + next_btn["href"]
        page_num += 1

        await human_jittery_move(
            page, random.uniform(300, 600), random.uniform(300, 600), steps=5
        )
        await asyncio.sleep(0.5)
        await interruptible_sleep(random.uniform(*config.BETWEEN_PAGES), cmd_queue)

        try:
            html = await safe_goto(page, next_url, loop, cmd_queue)
        except (SkipBracketSignal, SkipCitySignal, StopSignal):
            raise
        except BrowserBlockedError as e:
            logger.error("%s❌ Sayfa %d'de engellendi: %s", pad, page_num, e)
            raise  # propagate so scrape_city can retry

        records, soup = parse_page(html)
        if not records:
            prot, prot_name = is_protection_page(html, page)
            logger.warning(
                "%s⚠️  Sayfa %d'de kayıt yok. URL: %s | Koruma: %s | HTML: %d karakter",
                pad, page_num, _safe_url(page), prot_name if prot else "yok", len(html),
            )
            break

        save_incremental(city_name, records)
        total_saved += len(records)
        logger.info(
            "%s✔ Sayfa %d: %d kayıt (toplam: %d)", pad, page_num, len(records), total_saved
        )

    if page_num >= max_pages:
        logger.warning(
            "%s⚠️  Max sayfa sınırına (%d) ulaşıldı (%d-%d TL). Veri eksik olabilir!",
            pad, max_pages, min_price, max_price,
        )

    done_ranges.add(range_key)
    logger.info(
        "%s🎉 %d-%d TL bitti: %d kayıt [%s]", pad, min_price, max_price, total_saved, city_slug
    )
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
        if (len(parts) > 1
                and all(d.isdigit() for d in parts)
                and all(len(d) == 3 for d in parts[1:])):
            c = "".join(parts)
    try:
        return float(c)
    except ValueError:
        return None


def _normalise_tr(s):
    return (s.lower()
            .replace("ı", "i").replace("ö", "o").replace("ü", "u")
            .replace("ş", "s").replace("ç", "c").replace("ğ", "g"))


def get_room_col_index(soup):
    ths = [
        _normalise_tr(th.text.strip())
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
                "📌 Checkpoint: %s, bracket_index=%s, page_num=%s",
                d.get("city"), d.get("bracket_index"), d.get("page_num"),
            )
            return d
        except Exception:
            logger.warning(
                "⚠️  Checkpoint dosyası bozuk (%s), sıfırdan başlanıyor.", cp
            )
    return {}


def save_checkpoint(city_slug, bracket_index, page_num):
    """
    Atomic write via temp-file + os.replace().
    bracket_index is ALWAYS the enumeration index (0–4), never a price.
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
        os.replace(tmp, target)
    except Exception as e:
        logger.debug("Checkpoint kaydetme hatası: %s", e)


def clear_checkpoint():
    cp = config.get_checkpoint_file()
    try:
        if os.path.exists(cp):
            os.remove(cp)
    except Exception as e:
        logger.warning("Checkpoint silinemedi: %s", e)


def get_resume_point(checkpoint, city_slug):
    if checkpoint.get("city") == city_slug:
        return checkpoint.get("bracket_index", 0), checkpoint.get("page_num", 1)
    return 0, 1


# ---------------------------------------------------------------------------
# FIX #4 — Global cookie store
#
# All three cities share the same domain (sarı site.com), so their cookies
# are domain-scoped and interchangeable.  Per-city files were artificial,
# caused warmup to repeat unnecessarily for each city, and left orphaned
# stale files when a login block deleted only one city's cookies.
#
# THE FIX: one file — global_sarı_site_cookies.json — for all cities.
# ---------------------------------------------------------------------------

_COOKIE_DIR_CREATED = False


def _ensure_cookie_dir():
    global _COOKIE_DIR_CREATED
    cd = os.path.join(config.CHECKPOINT_DIR, "cookies")
    if not _COOKIE_DIR_CREATED:
        os.makedirs(cd, exist_ok=True)
        _COOKIE_DIR_CREATED = True
    return cd


def get_global_cookie_path():
    """Path to the single shared cookie file for all cities."""
    return os.path.join(_ensure_cookie_dir(), "global_sahibinden_cookies.json")


def _migrate_legacy_cookies():
    """
    One-time migration: merge old per-city cookie files into the global file.
    Runs silently at startup; no-ops if global file already exists.
    """
    cd          = _ensure_cookie_dir()
    global_path = get_global_cookie_path()
    if os.path.exists(global_path):
        return  # Already migrated

    merged = {}
    for fn in os.listdir(cd):
        if fn.endswith("_cookies.json") and fn != "global_sahibinden_cookies.json":
            fp = os.path.join(cd, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for c in json.load(f):
                        merged[c["name"]] = c  # Later file wins on name collision
                logger.info("🍪 Eski çerez dosyası taşındı: %s", fn)
            except Exception as e:
                logger.debug("Eski çerez dosyası okunamadı (%s): %s", fn, e)

    if merged:
        tmp = global_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(merged.values()), f, indent=2)
        os.replace(tmp, global_path)
        logger.info("🍪 %d çerez global dosyaya taşındı.", len(merged))


async def save_global_cookies(page):
    """Save current browser cookies to the global shared file."""
    try:
        cookies    = await page.context.cookies()
        now        = datetime.now(tz=timezone.utc).timestamp()
        persistent = [c for c in cookies if c.get("expires", -1) > now]
        tmp        = get_global_cookie_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(persistent, f, indent=2)
        os.replace(tmp, get_global_cookie_path())
        logger.info(
            "🍪 %d kalıcı çerez kaydedildi (%d oturum çerezi atlandı).",
            len(persistent), len(cookies) - len(persistent),
        )
    except Exception as e:
        logger.debug("Global çerez kaydetme hatası: %s", e)


async def load_global_cookies(page):
    """Load the global cookie file into the browser context."""
    path = get_global_cookie_path()
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not cookies:
            return False
        now   = datetime.now(tz=timezone.utc).timestamp()
        valid = [c for c in cookies if c.get("expires", now + 1) > now]
        if not valid:
            logger.info("🍪 Tüm global çerezlerin süresi dolmuş, atlanıyor.")
            return False
        await page.context.add_cookies(valid)
        logger.info("🍪 %d geçerli global çerez yüklendi.", len(valid))
        return True
    except Exception as e:
        logger.debug("Global çerez yükleme hatası: %s", e)
        return False


def delete_global_cookies():
    """Delete the global cookie file and log clearly."""
    path = get_global_cookie_path()
    if os.path.exists(path):
        try:
            os.remove(path)
            logger.info("🗑️  Global çerezler silindi.")
        except Exception as e:
            logger.warning("Global çerezler silinemedi: %s", e)
    else:
        logger.debug("Global çerez dosyası zaten yok, silme atlandı.")


# ---------------------------------------------------------------------------
# Core scraping loop
# ---------------------------------------------------------------------------

async def scrape_city_brackets(
    page, city_slug, city_name, brackets, loop, cmd_queue,
    start_bracket=0, start_page=1,
):
    """
    Iterates top-level price brackets and delegates each to
    scrape_adaptive_bracket.

    This is the ONLY place save_checkpoint is called (using the correct
    bracket enumeration index, not a price value).

    On resume: the interrupted bracket is skipped to avoid duplicate CSV
    rows, with a console warning explaining why.
    """
    total       = 0
    done_ranges = set()

    if start_bracket > 0 and start_bracket < len(brackets):
        mn_skip, mx_skip = brackets[start_bracket]
        logger.warning(
            "⏭️  Yarım kalan bracket atlanıyor (%d-%d TL) — CSV'de mükerrer kayıt "
            "oluşmaması için.  Bu aralıktan eksik veri olabilir.",
            mn_skip, mx_skip,
        )
        start_bracket += 1

    for bi, (mn, mx) in enumerate(brackets):
        check_commands(cmd_queue)
        if bi < start_bracket:
            continue

        logger.info("\n🔍 Ana bracket [%d/%d]: %d-%d TL", bi + 1, len(brackets), mn, mx)

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
        save_checkpoint(city_slug, bi, 1)
        logger.info(
            "✅ Bracket %d-%d TL bitti: %d kayıt | Checkpoint: bracket_index=%d",
            mn, mx, count, bi,
        )

    return total


# ---------------------------------------------------------------------------
# FIX #3 — Singleton browser + FIX #1 — Per-bracket login retry
#
# FIX #3: browser is created ONCE before the retry loop and destroyed in the
#   outer finally block after all attempts are exhausted or the city succeeds.
#   Between retries, only cookies are cleared (instant) and warmup re-runs;
#   no new Chromium process is spawned.  This reduces token creation from
#   9–15 per run to 1, and cuts init time from 45–75 s to ~10 s.
#
# FIX #1: bracket_login_blocks tracks how many consecutive BrowserBlockedErrors
#   each bracket has produced.  While the count is below
#   MAX_LOGIN_RETRIES_PER_BRACKET, start_bracket is NOT incremented and the
#   same bracket is retried with exponential back-off.  Only after exceeding
#   the threshold is the bracket permanently skipped.
# ---------------------------------------------------------------------------

async def scrape_city(city, checkpoint, cmd_queue):
    city_slug = city["url_slug"]
    city_name = city["name"]
    brackets  = city["brackets"]
    loop      = asyncio.get_event_loop()

    # One-time migration of old per-city cookie files → global file
    _migrate_legacy_cookies()

    start_bracket, start_page = get_resume_point(checkpoint, city_slug)

    # FIX #1: per-bracket failure counter (bracket_index → consecutive_failures)
    bracket_login_blocks: dict = {}
    max_bracket_retries  = config.MAX_LOGIN_RETRIES_PER_BRACKET
    backoff_base         = config.LOGIN_RETRY_BACKOFF_BASE
    backoff_max          = config.LOGIN_RETRY_BACKOFF_MAX

    # ------------------------------------------------------------------
    # FIX #3: Create the browser ONCE, outside the retry loop.
    # The browser lives for the entire city scrape; only session state
    # (cookies, page URL) is reset between attempts.
    # ------------------------------------------------------------------
    pw      = None
    browser = None
    ctx     = None
    page    = None

    try:
        logger.info(
            "\n%s\nŞEHİR: %s — tarayıcı başlatılıyor (singleton)\n%s",
            "=" * 50, city_name.upper(), "=" * 50,
        )
        ws      = rayobrowse.create_browser(
            headless=config.RAYOBROWSE_HEADLESS,
            target_os=config.RAYOBROWSE_TARGET_OS,
            browser_language=config.RAYOBROWSE_BROWSER_LANGUAGE,
            ui_language=config.RAYOBROWSE_UI_LANGUAGE,
        )
        pw      = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(ws)

        ctx  = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # FIX #2: enforce viewport immediately after page creation
        await enforce_viewport(page)

        # ------------------------------------------------------------------
        # Retry loop — reuses the browser created above.
        # Each attempt may:
        #   • succeed → break
        #   • hit a recoverable block → clear cookies, sleep, retry same bracket
        #   • exhaust per-bracket retries → skip bracket, retry city loop
        #   • receive SkipCitySignal / StopSignal → propagate up
        # ------------------------------------------------------------------
        for attempt in range(1, config.MAX_RESTARTS_PER_CITY + 1):
            logger.info(
                "\n%s\nŞEHİR: %s — Deneme %d/%d\n%s",
                "-" * 50, city_name.upper(),
                attempt, config.MAX_RESTARTS_PER_CITY, "-" * 50,
            )

            try:
                # FIX #3: between retries reset session state, not the browser
                if attempt > 1:
                    logger.info("🔄 Oturum sıfırlanıyor (tarayıcı korunuyor)...")
                    await ctx.clear_cookies()
                    try:
                        await page.goto("about:blank", timeout=10_000)
                    except Exception:
                        pass

                # --- Cookie warmup bypass ---
                warmed_up = False
                if await load_global_cookies(page):
                    try:
                        await page.goto(
                            config.BASE_URL,
                            wait_until="domcontentloaded",
                            timeout=30_000,
                        )
                        await asyncio.sleep(2)
                        h = await get_page_content(page)
                        if (
                            not is_protection_page(h, page)[0]
                            and not is_login_page(h, page)
                            and "searchresultstable" in h.lower()
                        ):
                            logger.info("✅ Global çerezler geçerli — ısınma atlandı.")
                            warmed_up = True
                        else:
                            logger.info(
                                "   Çerezler geçersiz (URL: %s), silinip ısınılıyor.",
                                _safe_url(page),
                            )
                            delete_global_cookies()
                            await ctx.clear_cookies()
                    except Exception as e:
                        logger.debug("Çerez doğrulama hatası: %s", e)
                        delete_global_cookies()
                        await ctx.clear_cookies()

                if not warmed_up:
                    await warmup_with_human_surf(page, loop, cmd_queue)
                    await save_global_cookies(page)

                await interruptible_sleep(random.uniform(*config.HOMEPAGE_WAIT), cmd_queue)

                total = await scrape_city_brackets(
                    page, city_slug, city_name, brackets, loop, cmd_queue,
                    start_bracket, start_page,
                )

                logger.info("\n✅ %s tamamlandı — %d kayıt.", city_name, total)
                await save_global_cookies(page)
                break  # Clean success — exit retry loop (browser closed in outer finally)

            except (SkipCitySignal, StopSignal):
                raise  # Propagate immediately

            except SkipBracketSignal:
                start_bracket += 1
                start_page     = 1
                bracket_login_blocks.pop(start_bracket - 1, None)

            except BrowserBlockedError as e:
                # -------------------------------------------------------
                # FIX #1: Per-bracket retry with exponential back-off.
                #
                # We count failures against start_bracket (the bracket
                # that was being attempted when the block occurred).
                # If we haven't hit the max yet, retry the SAME bracket.
                # Only after exhausting retries do we skip it.
                # -------------------------------------------------------
                blocked_bi = start_bracket
                bracket_login_blocks[blocked_bi] = (
                    bracket_login_blocks.get(blocked_bi, 0) + 1
                )
                failures = bracket_login_blocks[blocked_bi]

                delete_global_cookies()
                await ctx.clear_cookies()
                logger.error(
                    "🔒 Engellendi (bracket %d, başarısızlık %d/%d): %s",
                    blocked_bi, failures, max_bracket_retries, e,
                )

                if failures < max_bracket_retries:
                    # Retry same bracket — do NOT increment start_bracket
                    backoff = min(backoff_base * (2 ** (failures - 1)), backoff_max)
                    logger.info(
                        "🔁 Bracket %d için yeniden deneniyor (%d/%d) — %.0fs bekleniyor...",
                        blocked_bi, failures, max_bracket_retries, backoff,
                    )
                    await interruptible_sleep(backoff, cmd_queue)
                    # Loop continues with same start_bracket

                else:
                    # Exceeded per-bracket retry budget — skip this bracket
                    logger.warning(
                        "⏭️  Bracket %d kalıcı olarak bloklandı (%d deneme sonrası), "
                        "bir sonraki bracket'a geçiliyor.",
                        blocked_bi, failures,
                    )
                    bracket_login_blocks.pop(blocked_bi, None)
                    start_bracket += 1
                    start_page     = 1

                    if start_bracket >= len(brackets):
                        logger.error(
                            "❌ %s için tüm bracket'lar bloklandı, şehir atlanıyor.",
                            city_name,
                        )
                        break  # All brackets exhausted

                    # Wait before trying next bracket with fresh session
                    wait = random.uniform(30, 60)
                    logger.info("⏳ %.1fs bekleniyor...", wait)
                    await interruptible_sleep(wait, cmd_queue)

    except (SkipCitySignal, StopSignal):
        raise  # Propagate through the outer try

    finally:
        # FIX #3: Browser destroyed ONCE here, after ALL attempts for this city
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
        logger.info("🗑️  Tarayıcı kapatıldı (%s).", city_name)