"""
scraper.py — Sahibinden kira scraper (rayobrowse + Playwright)

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
class RestartBrowserSignal(Exception): pass  # User-triggered hard browser restart


# ---------------------------------------------------------------------------
# Phase 1 — Pause/resume event
#
# _pause_event is set (= running) by default.  When the user types "pause"
# the event is cleared; interruptible_sleep keeps polling the queue but does
# not advance its countdown, effectively freezing the scraper.  When "go"
# arrives the event is set again and normal execution resumes.
# ---------------------------------------------------------------------------

_pause_event = asyncio.Event()
_pause_event.set()  # start in the "running" state


# ---------------------------------------------------------------------------
# Command queue helpers
# ---------------------------------------------------------------------------

async def check_commands(cmd_queue):
    """
    Drain the command queue and raise the appropriate signal.

    Now async so it can sleep in-place for `wait X` and block for `pause`.
    Items in the queue are either plain strings or (\"wait\", seconds) tuples.
    """
    try:
        while True:
            item = cmd_queue.get_nowait()

            # --- Tuple commands ---
            if isinstance(item, tuple) and item[0] == "wait":
                secs = item[1]
                logger.info("⏸  %ds bekleniyor (wait komutu)...", secs)
                await asyncio.sleep(secs)
                logger.info("▶  Bekleme tamamlandı, devam ediliyor.")
                continue

            cmd = item.strip().lower() if isinstance(item, str) else ""

            if cmd in ("skip", "skip city"):
                raise SkipCitySignal()
            elif cmd in ("next", "skip bracket"):
                raise SkipBracketSignal()
            elif cmd == "stop":
                raise StopSignal()
            elif cmd in ("ok", "devam", "continue"):
                logger.info("✅ 'ok' komutu alındı.")
            elif cmd == "pause":
                _pause_event.clear()
                print("\n⏸️  Scraper duraklatıldı.  Devam etmek için 'go' yazın.\n")
            elif cmd == "go":
                _pause_event.set()
                logger.info("▶  'go' alındı — scraper devam ediyor.")
            elif cmd == "restart":
                raise RestartBrowserSignal()

    except queue.Empty:
        pass


async def interruptible_sleep(seconds, cmd_queue):
    """
    Sleep for `seconds`, waking every 0.5 s to honour CLI commands.

    When paused (pause_event cleared), the countdown is frozen: the function
    keeps looping and polling the queue without advancing `end_time`, so the
    scraper is effectively halted until `go` arrives.
    """
    end_time = time.time() + seconds
    while time.time() < end_time:
        if not _pause_event.is_set():
            # Scraper is paused — poll queue but don't advance timer
            await check_commands(cmd_queue)
            await asyncio.sleep(0.5)
            continue
        await check_commands(cmd_queue)
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


async def wait_for_manual_solve(loop, reason, cmd_queue=None, timeout=90, page=None):
    """
    Ask the user to solve a challenge manually.

    Polls cmd_queue only — never calls input().  console_listener is the
    sole owner of stdin, preventing the deadlock that previously caused CLI
    commands to stop working and waits to last indefinitely.

    On timeout (90 s with no user input):
      1. Press F5 to reload the page
      2. Wait 5 s for the challenge page to re-render
      3. Try to auto-solve the Turnstile again (enterprise solver first)
      4. Return True if solved, False if still stuck (caller will re-check)

    This handles the case where Turnstile solved but didn't redirect — a
    reload forces the server to process the token and send the user onwards.
    """
    beep_alert()
    print(f"\n{'=' * 55}")
    print(f"🔒 {reason}")
    print(f"   Konsola 'ok' yazın devam etmek için.")
    print(f"   Veya: skip / next / stop / restart")
    print(f"   {timeout}s içinde yanıt gelmezse sayfa yenilenir ve")
    print(f"   Turnstile otomatik olarak tekrar çözülmeye çalışılır.")
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
                elif cmd == "restart":
                    raise RestartBrowserSignal()
                elif cmd in ("ok", "devam", "continue"):
                    logger.info("✅ Manuel onay alındı.")
                    return True
            except queue.Empty:
                pass

    # ── Timeout reached — reload and re-solve ────────────────────────────
    logger.warning(
        "⏱  Manuel çözüm bekleme süresi doldu (%ds). "
        "Sayfa yenileniyor ve Turnstile tekrar çözülmeye çalışılıyor...",
        timeout,
    )

    if page is None:
        # No page reference — caller will handle
        return False

    try:
        # F5 reload
        logger.info("   🔄 F5 — sayfa yenileniyor...")
        await page.keyboard.press("F5")
        await asyncio.sleep(5)

        # Check if challenge is still present
        try:
            html = await get_page_content(page, 8000)
        except Exception:
            html = ""

        cur_url = _safe_url(page)

        # Already redirected — no re-solve needed
        if (
            "cs/tloading"    not in cur_url.lower()
            and "cs/checkloading" not in cur_url.lower()
            and "tarayıcınızı kontrol ediyoruz" not in html.lower()
        ):
            logger.info("   ✅ Yenileme sonrası yönlendirme gerçekleşti. URL: %s", cur_url)
            return True

        # Re-attempt enterprise solve on the freshly loaded challenge page
        logger.info("   🔐 Turnstile yeniden çözülmeye çalışılıyor (enterprise)...")
        is_enterprise = await _is_enterprise_turnstile(page)
        if is_enterprise:
            solved = await solve_enterprise_turnstile(page, loop, cmd_queue)
        else:
            solved = await _auto_solve_interactive_turnstile(page, loop, cmd_queue)

        if solved:
            logger.info("   ✅ Yenileme sonrası Turnstile çözüldü!")
        else:
            logger.warning("   ❌ Yenileme sonrası Turnstile çözülemedi.")
        return solved

    except (SkipBracketSignal, SkipCitySignal, StopSignal, RestartBrowserSignal):
        raise
    except Exception as e:
        logger.error("   ❌ Sayfa yenileme / yeniden çözme hatası: %s", e)
        return False


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
        "width":  config.FORCE_VIEWPORT_WIDTH,
        "height": config.FORCE_VIEWPORT_HEIGHT,
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
# Issue #2 — Anti-detection JS injection
# ---------------------------------------------------------------------------

async def patch_browser_detection_leaks(page):
    """
    Inject JavaScript to hide the most common browser-automation fingerprints
    that sahibinden.com's bot detection checks for.

    Must be called AFTER page creation but BEFORE the first navigation.
    Rayobrowse already handles many of these at the Chromium level, but
    injecting at the JS layer adds an extra safety net.

    Covered vectors:
      • navigator.webdriver  — Playwright sets this to true; we clear it
      • __playwright__ / _playwright  — framework global markers
      • chrome.runtime       — absent in real Chrome = suspicious; add stub
      • navigator.plugins    — empty in headless; populate with fake list
      • navigator.languages  — must match tr-TR locale we set in rayobrowse
      • permissions.query    — can expose "midi-sysex" automation leak
    """
    if not config.PATCH_BROWSER_DETECTION_LEAKS:
        return

    try:
        await page.evaluate("""() => {
            try {
                // 1. Hide webdriver flag
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });
            } catch(e) {}

            try {
                // 2. Remove Playwright global markers
                delete window.__playwright;
                delete window._playwright;
                delete window.__pw_manual;
                delete window.__pw_functions;
            } catch(e) {}

            try {
                // 3. Remove CDP markers
                ['cdp_', 'cdp$', '__cdp_evaluate', '__cdp_']
                    .forEach(k => { try { delete window[k]; } catch(e){} });
            } catch(e) {}

            try {
                // 4. Add a minimal chrome.runtime stub (absent = instantly detected)
                if (!window.chrome) {
                    window.chrome = {};
                }
                if (!window.chrome.runtime) {
                    window.chrome.runtime = {
                        PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
                        PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
                        PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
                        RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
                        OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
                        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
                        id: undefined,
                    };
                }
            } catch(e) {}

            try {
                // 5. Fake a non-empty plugin list (headless Chrome has 0 plugins)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const arr = [1, 2, 3];
                        arr.__proto__ = PluginArray.prototype;
                        return arr;
                    },
                    configurable: true
                });
            } catch(e) {}

            try {
                // 6. Set languages to match our locale (tr-TR)
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['tr-TR', 'tr', 'en-US', 'en'],
                    configurable: true
                });
            } catch(e) {}

            try {
                // 7. Patch permissions.query to avoid the midi-sysex automation leak
                const origQuery = navigator.permissions.query.bind(navigator.permissions);
                navigator.permissions.query = (params) => {
                    if (params && params.name === 'notifications') {
                        return Promise.resolve({ state: Notification.permission });
                    }
                    return origQuery(params);
                };
            } catch(e) {}
        }""")
        logger.debug("🛡️  Anti-detection JS yaması uygulandı.")
    except Exception as e:
        logger.debug("Anti-detection yaması kısmen başarısız (önemli değil): %s", e)


# ---------------------------------------------------------------------------
# Page classification
#
# ROOT CAUSE of "everything is a login page":
#   sahibinden.com embeds a hidden login modal (type="password" + type="email")
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

    Issue #2 enhancement: All timing, scroll counts, scroll direction, and
    navigation actions are heavily randomised so no two warmup sessions look
    the same.  70% of the time starts on the homepage; 30% skips it to look
    like a confident returning visitor.
    """
    # 30% of the time skip the homepage — looks like a returning user who
    # already knows where they're going
    if random.random() < 0.30:
        logger.info("🧑‍💻 Isınma atlandı (doğrudan başlangıç — dönen kullanıcı davranışı).")
        return

    logger.info("🧑‍💻 Hızlı güven inşası...")
    try:
        await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=60_000)
    except Exception as e:
        raise BrowserBlockedError(f"Ana sayfaya erişilemedi: {e}")

    logger.info("   📍 URL: %s", _safe_url(page))

    # Variable warmup dwell: 8–25 s (not a fixed window)
    warmup_dwell = random.uniform(8, 25)
    logger.info("   ⏱  Isınma bekleme süresi: %.1fs", warmup_dwell)
    await interruptible_sleep(warmup_dwell, cmd_queue)
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
        await wait_for_manual_solve(loop, f"Isınma — {r} | {_safe_url(page)}", cmd_queue, page=page)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 15)
        html = await get_page_content(page)
        if is_login_page(html, page):
            raise BrowserBlockedError("Login (manuel çözüm sonrası)")

    # Randomised scroll: 1–6 scrolls, sometimes UP (humans don't only scroll down)
    num_scrolls = random.randint(1, 6)
    for _ in range(num_scrolls):
        direction = random.choice([-1, 1])  # -1 = up, +1 = down
        distance  = random.randint(100, 800)
        await page.mouse.wheel(0, distance * direction)
        await asyncio.sleep(random.uniform(0.3, 1.0))

    # Random nav hover — skip 25% of the time
    if random.random() < 0.75:
        try:
            nav = page.locator("nav a, .mainNavigation a")
            cnt = await nav.count()
            if cnt > 0:
                target = nav.nth(random.randint(0, min(cnt, 5) - 1))
                box    = await target.bounding_box()
                if box:
                    await human_jittery_move(
                        page,
                        box["x"] + box["width"]  / 2,
                        box["y"] + box["height"] / 2,
                    )
                    # 50% chance to actually click the hovered link
                    if random.random() < 0.50:
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        await page.mouse.click(
                            box["x"] + box["width"]  / 2,
                            box["y"] + box["height"] / 2,
                        )
                        # Brief pause then come back
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        await page.go_back()
                        await asyncio.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            logger.debug("Nav hover hatası: %s", e)

    # Random browsing clicks: 0–3 (sometimes none)
    num_clicks = random.randint(0, 3)
    if num_clicks > 0:
        await human_browsing_clicks(page, count=num_clicks)


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

    # ------------------------------------------------------------------
    # "Devam Et" button handling.
    #
    # From the page HTML (sahibinden_com_Yükleniyor.htm):
    #   <input id="btn-continue" disabled type="button" value="Devam Et">
    #
    # The button starts DISABLED and only becomes enabled once Turnstile
    # reports a successful token.  The old code checked is_visible() which
    # passes on a disabled input — the click silently did nothing.
    #
    # Correct flow:
    #   1. Turnstile widget solves → JS removes the `disabled` attribute
    #   2. We wait up to 30 s for the button to become enabled
    #   3. Move mouse to button with jitter, then click
    # ------------------------------------------------------------------
    try:
        btn = page.locator("#btn-continue")
        if await btn.count() > 0:
            logger.info("   ⏳ 'Devam Et' butonu etkinleşmesi bekleniyor (maks 30s)...")
            try:
                # wait_for(state="enabled") polls until disabled attr is removed
                await btn.wait_for(state="enabled", timeout=30_000)
                logger.info("   ✅ 'Devam Et' butonu etkinleşti.")
            except Exception:
                logger.warning(
                    "   ⚠️  'Devam Et' butonu 30s içinde etkinleşmedi — yine de tıklanıyor."
                )

            bx = await btn.bounding_box()
            if bx:
                await human_jittery_move(
                    page,
                    bx["x"] + bx["width"]  / 2,
                    bx["y"] + bx["height"] / 2,
                )
                await asyncio.sleep(random.uniform(0.3, 0.7))
                await btn.click()
                logger.info("   🖱️  'Devam Et' butonu tıklandı.")
                # Give page time to process the token and redirect
                await asyncio.sleep(3)
    except Exception as e:
        logger.debug("Turnstile 'Devam Et' butonu hatası: %s", e)

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
    """
    Dispatcher: routes to the correct solver based on challenge type.

    sahibinden.com uses Enterprise Turnstile (render=explicit, sitekey starting
    with 0x4AAAAAAA).  The widget must be activated by calling
    turnstile.render('#turnStileWidget') from JS before a checkbox or token
    appears.  Free-tier Turnstile renders automatically.
    """
    managed = "managed" in reason.lower() or "checkloading" in reason.lower()

    if managed:
        success = await _wait_for_managed_redirect(page)
    else:
        is_enterprise = await _is_enterprise_turnstile(page)
        if is_enterprise:
            logger.info("🔐 Enterprise Turnstile algılandı — enterprise çözücü kullanılıyor.")
            success = await solve_enterprise_turnstile(page, loop, cmd_queue)
        else:
            logger.info("🔓 Standart Turnstile — interaktif çözücü kullanılıyor.")
            success = await _auto_solve_interactive_turnstile(page, loop, cmd_queue)

    if success:
        await asyncio.sleep(3)
    return success


async def _is_enterprise_turnstile(page):
    """
    Detect whether the current page uses Enterprise Turnstile (render=explicit).

    Evidence from sahibinden_com_Yükleniyor.htm:
      <input id="sitekeyEnterprise" type="hidden" value="0x4AAAAAAABmOoZylDRT5OZf">
      <script src="...turnstile/v0/api.js?&render=explicit" defer></script>
    """
    try:
        result = await page.evaluate("""() => {
            // Method 1: enterprise sitekey hidden input
            const keyEl = document.querySelector('#sitekeyEnterprise');
            if (keyEl && keyEl.value && keyEl.value.startsWith('0x4AAAAAAA')) {
                return {enterprise: true, reason: 'sitekeyEnterprise'};
            }
            // Method 2: render=explicit in any turnstile script tag
            for (const s of document.querySelectorAll('script[src*="turnstile"]')) {
                if (s.src && s.src.includes('render=explicit')) {
                    return {enterprise: true, reason: 'render=explicit'};
                }
            }
            // Method 3: explicit widget container present
            if (document.querySelector('#turnStileWidget')) {
                return {enterprise: true, reason: 'turnStileWidget div'};
            }
            return {enterprise: false};
        }""")
        if result and result.get("enterprise"):
            logger.info("🔐 Enterprise Turnstile tespit edildi (%s).", result.get("reason"))
            return True
    except Exception as e:
        logger.debug("Enterprise Turnstile tespiti başarısız: %s", e)
    return False


async def solve_enterprise_turnstile(page, loop=None, cmd_queue=None, timeout=90):
    """
    Solve Cloudflare ENTERPRISE Turnstile (render=explicit mode).

    The /cs/tloading page on sahibinden.com works as follows:
      1. api.js loads with `defer` → window.turnstile becomes available
      2. turnstile.render('#turnStileWidget') must be called explicitly
      3. Cloudflare verifies the browser in the background (~2-10 s)
      4. On success: #btn-continue loses its `disabled` attribute
      5. User clicks "Devam Et" → 20-second spinner → redirect to listing

    Phase 1: Wait for window.turnstile to exist
    Phase 2: Call turnstile.render('#turnStileWidget')
    Phase 3: Poll until #btn-continue is enabled OR URL changes
    Phase 4: Click the enabled button
    Phase 5: Wait for spinner to finish and page to redirect

    Returns True on success, False on any failure.
    """
    # ------------------------------------------------------------------
    # Early-exit: challenge is already gone (user solved before we got here)
    # ------------------------------------------------------------------
    try:
        h = await get_page_content(page, 3000)
        if "tarayıcınızı kontrol ediyoruz" not in h.lower():
            logger.info("   ✅ Enterprise Turnstile zaten geçilmiş. URL: %s", _safe_url(page))
            return True
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Phase 1: Wait for the Turnstile API script to load
    # The script tag has `defer`, so it executes after HTML parsing.
    # ------------------------------------------------------------------
    logger.info("   ⏳ Phase 1: Turnstile API scripti bekleniyor...")
    script_loaded = False
    for _ in range(30):  # 15 s max
        try:
            has_ts = await page.evaluate("() => typeof window.turnstile !== 'undefined'")
            if has_ts:
                script_loaded = True
                break
        except Exception:
            pass
        await asyncio.sleep(0.5)

    if not script_loaded:
        logger.warning("   ⚠️  Turnstile API scripti 15s içinde yüklenmedi — interaktif moda geçiliyor.")
        return await _auto_solve_interactive_turnstile(page, loop, cmd_queue)

    logger.info("   ✅ Turnstile API yüklendi.")

    # ------------------------------------------------------------------
    # Phase 2: Explicitly render the widget
    # ------------------------------------------------------------------
    logger.info("   🔧 Phase 2: turnstile.render('#turnStileWidget') çağrılıyor...")
    try:
        render_result = await page.evaluate("""() => {
            try {
                if (typeof turnstile === 'undefined' || typeof turnstile.render !== 'function') {
                    return {error: 'turnstile_not_available'};
                }
                const sitekeyEl = document.querySelector('#sitekeyEnterprise');
                const sitekey   = sitekeyEl ? sitekeyEl.value : null;
                if (!sitekey) {
                    return {error: 'sitekey_not_found'};
                }
                const widgetId = turnstile.render('#turnStileWidget', {
                    sitekey: sitekey,
                    language: 'tr',
                    'refresh-expired': 'never',
                });
                return {ok: true, widgetId: widgetId};
            } catch(e) {
                return {error: e.message};
            }
        }""")
        if render_result and render_result.get("error"):
            logger.warning(
                "   ⚠️  turnstile.render() hatası: %s — interaktif moda geçiliyor.",
                render_result["error"],
            )
            return await _auto_solve_interactive_turnstile(page, loop, cmd_queue)
        logger.info("   ✅ turnstile.render() başarıyla çağrıldı (widgetId=%s).",
                    render_result.get("widgetId") if render_result else "?")
    except Exception as e:
        logger.warning("   ⚠️  turnstile.render() çağrısı başarısız: %s", e)
        return await _auto_solve_interactive_turnstile(page, loop, cmd_queue)

    await asyncio.sleep(2)  # Allow widget to initialise

    # ------------------------------------------------------------------
    # Phase 3: Wait for #btn-continue to become enabled
    # ------------------------------------------------------------------
    logger.info("   ⏳ Phase 3: 'Devam Et' butonu etkinleşmesi bekleniyor (maks %ds)...", timeout)
    btn          = page.locator("#btn-continue")
    verify_start = time.time()

    while time.time() - verify_start < timeout:
        # Check if URL already changed (auto-pass or user solved it)
        try:
            if "cs/tloading" not in _safe_url(page).lower() and "cs/checkloading" not in _safe_url(page).lower():
                logger.info("   ✅ Sayfa yönlendirildi (Turnstile zaten geçildi). URL: %s", _safe_url(page))
                return True
        except Exception:
            pass

        # Check if listing content already appeared
        try:
            content = await get_page_content(page, 2000)
            if "searchresultstable" in content.lower():
                logger.info("   ✅ Sonuç tablosu görüntülendi — Turnstile geçildi.")
                return True
            if is_login_page(content, page):
                logger.error("   ❌ Turnstile sonrası login sayfasına yönlendirildi!")
                return False
        except Exception:
            pass

        # Check for the explicit error message on the page
        try:
            err_el = page.locator("#continueRequestError")
            if await err_el.is_visible():
                err_txt = await err_el.text_content()
                if err_txt and "gerçekleştiremedik" in err_txt.lower():
                    logger.warning("   ❌ Cloudflare doğrulama hatası: %s", err_txt.strip())
                    return False
        except Exception:
            pass

        # Check if button is enabled
        try:
            if await btn.count() > 0 and await btn.is_enabled():
                logger.info("   ✅ 'Devam Et' butonu etkinleşti!")
                break
        except Exception:
            pass

        await asyncio.sleep(1)
    else:
        logger.warning("   ⚠️  'Devam Et' %ds içinde etkinleşmedi.", timeout)
        return False

    # ------------------------------------------------------------------
    # Phase 4: Click the button
    # ------------------------------------------------------------------
    logger.info("   🖱️  Phase 4: 'Devam Et' butonu tıklanıyor...")
    try:
        bx = await btn.bounding_box()
        if bx:
            await human_jittery_move(
                page,
                bx["x"] + bx["width"]  / 2,
                bx["y"] + bx["height"] / 2,
            )
            await asyncio.sleep(random.uniform(0.3, 0.7))

        # One final enabled check before clicking
        if not await btn.is_enabled():
            logger.warning("   ⚠️  Buton tıklama öncesi tekrar devre dışı kaldı!")
            return False

        await btn.click()
        logger.info("   ✅ 'Devam Et' tıklandı.")
    except Exception as e:
        logger.error("   ❌ Buton tıklama hatası: %s", e)
        return False

    # ------------------------------------------------------------------
    # Phase 5: Wait for the post-click loading spinner to finish
    # The page shows a revolving circle for up to ~20 seconds, then
    # redirects to the listing page.
    # ------------------------------------------------------------------
    logger.info("   ⏳ Phase 5: Yükleme spinner'ı bekleniyor (maks 60s)...")
    spinner_start = time.time()
    while time.time() - spinner_start < 60:
        await asyncio.sleep(2)
        try:
            cur_url = _safe_url(page)
            if "cs/tloading" not in cur_url.lower() and "cs/checkloading" not in cur_url.lower():
                logger.info("   ✅ Yönlendirme tamamlandı! URL: %s", cur_url)
                return True
        except Exception:
            pass
        try:
            content = await get_page_content(page, 2000)
            if "searchresultstable" in content.lower():
                logger.info("   ✅ Sonuç tablosu görüntülendi.")
                return True
            if is_login_page(content, page):
                logger.error("   ❌ Spinner sonrası login sayfasına yönlendirildi!")
                return False
            # Check error message again
            if "gerçekleştiremedik" in content.lower():
                logger.warning("   ⚠️  Cloudflare doğrulama başarısız (spinner sonrası).")
                return False
        except Exception:
            pass

    logger.warning("   ❌ Enterprise Turnstile 60s sonra hâlâ geçilemedi. URL: %s", _safe_url(page))
    return False


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
        await wait_for_manual_solve(loop, f"{r} | URL: {final_url}", cmd_queue, page=page)
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
    Extract total listing count from a sahibinden results page.
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
    page_num          = 1
    max_pages         = config.MAX_PAGES_PER_BRACKET
    pages_this_session = getattr(scrape_adaptive_bracket, "_session_page_count", 0)

    while page_num < max_pages:
        await check_commands(cmd_queue)
        next_btn = soup.find("a", title="Sonraki")
        if not next_btn or "href" not in next_btn.attrs:
            logger.info("%s📄 Son sayfa: %d", pad, page_num)
            break

        next_url  = config.BASE_URL + next_btn["href"]
        page_num += 1
        pages_this_session += 1
        scrape_adaptive_bracket._session_page_count = pages_this_session

        # ------------------------------------------------------------------
        # Issue #3 — Rate-limiting / throttle system
        # ------------------------------------------------------------------

        # Cooldown: after COOLDOWN_AFTER_N_PAGES pages take a longer break
        if pages_this_session > 0 and pages_this_session % config.COOLDOWN_AFTER_N_PAGES == 0:
            cooldown = random.uniform(*config.COOLDOWN_DURATION)
            logger.info(
                "🧊 Soğuma: %d sayfa tarandı → %.0fs mola veriliyor...",
                pages_this_session, cooldown,
            )
            await interruptible_sleep(cooldown, cmd_queue)

        # Extra random delay: injected with PROBABILITY_OF_EXTRA_DELAY chance
        elif random.random() < config.PROBABILITY_OF_EXTRA_DELAY:
            extra = random.uniform(*config.EXTRA_DELAY_RANGE)
            logger.info("⏸  Ekstra rastgele gecikme (%.1fs).", extra)
            await interruptible_sleep(extra, cmd_queue)

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
#
# Format: {"city": slug, "bracket_index": int, "page_num": int, "saved_at": iso}
#
# bracket_index = the last FULLY COMPLETED top-level bracket (0–4).
# On resume, scrape_city_brackets starts from bracket_index+1.
#
# When a city finishes completely a separate marker file is written:
#   checkpoints/done_{city_slug}_{date}.json
# This makes it easy to see at a glance what was completed that day.
# ---------------------------------------------------------------------------

def _completion_marker_path(city_slug: str) -> str:
    import datetime as _dt2
    today = _dt2.date.today().strftime("%Y-%m-%d")
    return os.path.join(config.CHECKPOINT_DIR, f"done_{city_slug}_{today}.json")


def mark_city_done(city_slug: str, city_name: str, total_records: int):
    """Write a completion marker so we can see the city finished this day."""
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    path = _completion_marker_path(city_slug)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "city":          city_slug,
                "city_name":     city_name,
                "total_records": total_records,
                "completed_at":  datetime.now().isoformat(),
            }, f, indent=2)
        print(f"\n{'🏁' * 30}")
        print(f"  ✅ {city_name.upper()} TAMAMEN TARANDIIII — {total_records} kayıt")
        print(f"{'🏁' * 30}\n")
    except Exception as e:
        logger.debug("Tamamlama işareti yazılamadı: %s", e)


def is_city_done_today(city_slug: str) -> bool:
    """Return True if this city already has a completion marker for today."""
    return os.path.exists(_completion_marker_path(city_slug))


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
    bracket_index is ALWAYS the enumeration index (0–4) of the last
    FULLY COMPLETED top-level bracket — never a price value.
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
    """
    Returns (last_completed_bracket_index, page_num).

    last_completed_bracket_index is the index of the LAST FULLY COMPLETED
    bracket.  scrape_city_brackets will start from this index + 1.
    Returns (-1, 1) when there is no checkpoint (meaning start from 0).
    """
    if checkpoint.get("city") == city_slug:
        return checkpoint.get("bracket_index", -1), checkpoint.get("page_num", 1)
    return -1, 1


# ---------------------------------------------------------------------------
# Phase 3 — Cookie Pool & Organic Scrubbing
#
# Instead of a single global_sahibinden_cookies.json we maintain a pool of
# 3-5 independent jar files (jar_0.json … jar_4.json).  Each browser session
# randomly picks one jar, making the scraper look like 3-5 different humans
# returning to the site rather than one human scraping thousands of pages.
#
# On login block the active jar is deleted entirely; other jars are unaffected
# so the next attempt can try a different identity.
#
# Organic scrubbing: analytics/ad-tracking cookies (_ga, _fbp, etc.) are
# purged with a 20% probability on each save, mimicking a user who clears
# third-party cookies occasionally.  Cloudflare / security cookies are NEVER
# scrubbed — dropping cf_clearance or _px cookies triggers an instant re-CAPTCHA.
# ---------------------------------------------------------------------------

_COOKIE_POOL_SIZE = 4      # Number of jars in the pool (3-5 recommended)
_ACTIVE_JAR_INDEX = None   # Set at the start of each scrape_city call

# Cookies whose names START WITH any of these prefixes are protected — never scrub
_COOKIE_WHITELIST_PREFIXES = (
    "cf_",        # Cloudflare: cf_clearance, cf_bm, cf_chl_*
    "_px",        # PerimeterX: _px, _pxhd, _pxde, _pxvid
    "__cf",       # Cloudflare internal
    "__Secure-3P",# Google secure session cookies
    "PHPSESSID",  # PHP session
    "sid",        # Generic session id
    "user",       # User auth
    "auth",       # Auth tokens
    "token",      # Any token cookie
)

# Cookies whose names match exactly or start with these are analytics/tracking
# — eligible for random scrubbing
_COOKIE_TRACKING_NAMES = (
    "_ga", "_gid", "_gat",          # Google Analytics
    "_fbp", "_fbc",                  # Facebook Pixel
    "_tt_enable_cookie", "_ttp",     # TikTok
    "IDE", "DSID", "__gads",         # Google Ads
    "fr",                            # Facebook
    "taboola_",                      # Taboola
    "hotjar",                        # Hotjar
)


def _cookie_dir():
    """Ensure and return the cookie pool directory path."""
    cd = os.path.join(config.CHECKPOINT_DIR, "cookie_pools")
    os.makedirs(cd, exist_ok=True)
    return cd


def _jar_path(index: int) -> str:
    return os.path.join(_cookie_dir(), f"jar_{index}.json")


def _is_protected_cookie(name: str) -> bool:
    """Return True if this cookie must NEVER be scrubbed."""
    nl = name.lower()
    return any(nl.startswith(p.lower()) for p in _COOKIE_WHITELIST_PREFIXES)


def _is_tracking_cookie(name: str) -> bool:
    """Return True if this cookie is analytics/ad-tracking and eligible for scrubbing."""
    nl = name.lower()
    return any(nl == t.lower() or nl.startswith(t.lower()) for t in _COOKIE_TRACKING_NAMES)


def scrub_tracking_cookies(cookie_list: list) -> list:
    """
    Organically purge analytics/tracking cookies before saving a jar.

    Called with a 20% probability on each save so the same tracking IDs
    are not associated with thousands of page views — mimicking a real user
    who occasionally clears third-party cookies.

    NEVER removes protected cookies (Cloudflare, PerimeterX, session tokens).
    """
    protected = [c for c in cookie_list if _is_protected_cookie(c.get("name", ""))]
    others    = [c for c in cookie_list if not _is_protected_cookie(c.get("name", ""))]

    kept    = [c for c in others if not _is_tracking_cookie(c.get("name", ""))]
    scrubbed = [c for c in others if  _is_tracking_cookie(c.get("name", ""))]

    if scrubbed:
        logger.info(
            "🧹 Takip çerezleri temizlendi (%d adet): %s",
            len(scrubbed),
            ", ".join(c["name"] for c in scrubbed),
        )

    return protected + kept


def pick_active_jar() -> int:
    """
    Randomly select a jar index from the pool.
    Prefers jars that already have cookies, falls back to any index.
    Called once per scrape_city invocation.
    """
    existing = [i for i in range(_COOKIE_POOL_SIZE) if os.path.exists(_jar_path(i))]
    if existing:
        chosen = random.choice(existing)
        logger.info("🍪 Çerez havuzundan jar_%d seçildi (%d mevcut jar).",
                    chosen, len(existing))
    else:
        chosen = random.randint(0, _COOKIE_POOL_SIZE - 1)
        logger.info("🍪 Yeni jar_%d oluşturulacak (havuz boş).", chosen)
    return chosen


async def save_pooled_cookies(page, jar_index: int):
    """Save current browser cookies into the active pool jar."""
    try:
        cookies    = await page.context.cookies()
        now        = datetime.now(tz=timezone.utc).timestamp()
        persistent = [c for c in cookies if c.get("expires", -1) > now]

        # 20% chance to scrub tracking cookies before saving
        if random.random() < 0.20:
            persistent = scrub_tracking_cookies(persistent)

        path = _jar_path(jar_index)
        tmp  = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(persistent, f, indent=2)
        os.replace(tmp, path)
        logger.info(
            "🍪 jar_%d: %d kalıcı çerez kaydedildi (%d oturum çerezi atlandı).",
            jar_index, len(persistent), len(cookies) - len(persistent),
        )
    except Exception as e:
        logger.debug("Çerez kaydetme hatası (jar_%d): %s", jar_index, e)


async def load_pooled_cookies(page, jar_index: int) -> bool:
    """Load cookies from the active pool jar into the browser context."""
    path = _jar_path(jar_index)
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
            logger.info("🍪 jar_%d: tüm çerezlerin süresi dolmuş.", jar_index)
            return False
        await page.context.add_cookies(valid)
        logger.info("🍪 jar_%d: %d geçerli çerez yüklendi.", jar_index, len(valid))
        return True
    except Exception as e:
        logger.debug("Çerez yükleme hatası (jar_%d): %s", jar_index, e)
        return False


def delete_pooled_cookies(jar_index: int):
    """Delete only the active jar (not the whole pool)."""
    path = _jar_path(jar_index)
    if os.path.exists(path):
        try:
            os.remove(path)
            logger.info("🗑️  jar_%d silindi.", jar_index)
        except Exception as e:
            logger.warning("jar_%d silinemedi: %s", jar_index, e)


def delete_all_pool_cookies():
    """Delete every jar in the pool (used on hard-reset login blocks)."""
    deleted = 0
    for i in range(_COOKIE_POOL_SIZE):
        path = _jar_path(i)
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted += 1
            except Exception:
                pass
    if deleted:
        logger.info("🗑️  Tüm çerez havuzu silindi (%d jar).", deleted)


def _migrate_legacy_cookies():
    """
    One-time migration: move the old global_sahibinden_cookies.json into
    jar_0 of the new pool.  Silent no-op if already migrated or no legacy file.
    """
    cd = os.path.join(config.CHECKPOINT_DIR, "cookies")
    legacy = os.path.join(cd, "global_sahibinden_cookies.json")
    if not os.path.exists(legacy):
        return

    target = _jar_path(0)
    if os.path.exists(target):
        return  # Pool already populated, don't overwrite

    try:
        import shutil
        shutil.copy2(legacy, target)
        logger.info("🍪 Eski global çerez dosyası jar_0'a taşındı.")
    except Exception as e:
        logger.debug("Legacy cookie taşıma hatası: %s", e)


# ---------------------------------------------------------------------------
# Thin compatibility shims so any code that still calls the old names works
# ---------------------------------------------------------------------------

async def save_global_cookies(page):
    """Shim: save to whichever jar is currently active."""
    global _ACTIVE_JAR_INDEX
    idx = _ACTIVE_JAR_INDEX if _ACTIVE_JAR_INDEX is not None else 0
    await save_pooled_cookies(page, idx)


async def load_global_cookies(page) -> bool:
    """Shim: load from whichever jar is currently active."""
    global _ACTIVE_JAR_INDEX
    idx = _ACTIVE_JAR_INDEX if _ACTIVE_JAR_INDEX is not None else 0
    return await load_pooled_cookies(page, idx)


def delete_global_cookies():
    """Shim: delete only the active jar."""
    global _ACTIVE_JAR_INDEX
    idx = _ACTIVE_JAR_INDEX if _ACTIVE_JAR_INDEX is not None else 0
    delete_pooled_cookies(idx)


# ---------------------------------------------------------------------------
# Human-like scroll to bottom
# ---------------------------------------------------------------------------

async def scroll_to_bottom_humanlike(page):
    """
    Scroll the current page to the bottom in a human-like way before
    moving to the next bracket.

    Mimics the Windows middle-click auto-scroll behavior: starts slow,
    accelerates, and finishes with a final JS snap to the very bottom.
    Uses page.mouse.wheel() so Playwright routes it through the browser's
    native input pipeline (same as a real wheel event).
    """
    try:
        # Get total scrollable height via JS
        doc_height = await page.evaluate(
            "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )
        viewport_h = config.FORCE_VIEWPORT_HEIGHT

        if doc_height <= viewport_h:
            logger.debug("Sayfa viewport'tan küçük, kaydırma atlandı.")
            return

        logger.info("   📜 Sayfa sonuna kaydırılıyor...")

        # How far we need to travel
        remaining = doc_height - viewport_h

        # Build a list of wheel delta values that feel like a gradually
        # accelerating then decelerating auto-scroll.
        # Total number of wheel events: aim for ~2-3 seconds of scrolling.
        num_steps = random.randint(8, 14)
        # Generate a bell-curve-ish distribution of step sizes
        step_sizes = []
        for i in range(num_steps):
            # ramp up then ramp down
            t = i / max(num_steps - 1, 1)
            weight = 4 * t * (1 - t)   # parabola: 0 → 1 → 0
            # Add jitter so it doesn't look mechanical
            weight = max(0.1, weight + random.uniform(-0.1, 0.1))
            step_sizes.append(weight)

        # Normalise so the steps sum to the total scroll distance
        total_weight = sum(step_sizes)
        deltas = [int(remaining * w / total_weight) for w in step_sizes]

        # Fix rounding drift so we hit exactly the right total
        delta_diff = remaining - sum(deltas)
        deltas[-1] += delta_diff

        for delta in deltas:
            if delta <= 0:
                continue
            await page.mouse.wheel(0, delta)
            # Variable pause between wheel events: faster in the middle
            await asyncio.sleep(random.uniform(0.08, 0.28))

        # Final JS snap to guarantee we are at the very bottom
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(0.4, 0.8))

        logger.info("   📜 Sayfa sonuna ulaşıldı.")
    except Exception as e:
        logger.debug("scroll_to_bottom_humanlike hatası: %s", e)


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
        await check_commands(cmd_queue)
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

        # Scroll to the bottom of the last results page before moving to the
        # next bracket — looks like a human reading through the listings
        await scroll_to_bottom_humanlike(page)

        # Issue #2 — Reading simulation: 30% chance of a random "dwell" pause
        # between brackets, mimicking a user reading through results
        if random.random() < config.READING_SIMULATION_PROBABILITY:
            reading_time = random.uniform(*config.READING_SIMULATION_DURATION)
            logger.info("📖 Okuma simülasyonu (%.1fs)...", reading_time)
            await interruptible_sleep(reading_time, cmd_queue)
            # Also scroll around a bit while "reading"
            for _ in range(random.randint(1, 3)):
                direction = random.choice([-1, 1])
                await page.mouse.wheel(0, random.randint(100, 400) * direction)
                await asyncio.sleep(random.uniform(0.4, 1.0))

    return total


# ---------------------------------------------------------------------------
# Phase 2 — Hard-reset on login block  +  Phase 3 cookie pool wiring
#
# The browser is still a singleton within a city — it is reused across soft
# retries (protection pages, timeouts) to save the 10-15 s startup cost.
# But a login-redirect block ("Login yönlendirmesi" in the error message)
# indicates the site has flagged the current identity.  In that case we:
#   1. Close the browser completely (kill the Chromium process)
#   2. Delete the active cookie jar so the new session is stateless
#   3. Spin up a brand-new browser (fresh fingerprint from rayobrowse)
#   4. Run warmup again with the new identity
# ---------------------------------------------------------------------------

async def _spawn_browser():
    """Create a fresh rayobrowse browser and return (pw, browser, ctx, page)."""
    ws      = rayobrowse.create_browser(
        headless=config.RAYOBROWSE_HEADLESS,
        target_os=config.RAYOBROWSE_TARGET_OS,
        browser_language=config.RAYOBROWSE_BROWSER_LANGUAGE,
        ui_language=config.RAYOBROWSE_UI_LANGUAGE,
    )
    pw      = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(ws)
    ctx     = browser.contexts[0]
    page    = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await enforce_viewport(page)
    await patch_browser_detection_leaks(page)
    return pw, browser, ctx, page


async def _close_browser(pw, browser):
    """Safely close a browser + playwright instance."""
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


async def scrape_city(city, checkpoint, cmd_queue):
    global _ACTIVE_JAR_INDEX

    city_slug = city["url_slug"]
    city_name = city["name"]
    brackets  = city["brackets"]
    loop      = asyncio.get_event_loop()

    # One-time migration of legacy cookie files into the pool
    _migrate_legacy_cookies()

    # Pick a random jar for this city's session
    _ACTIVE_JAR_INDEX = pick_active_jar()

    start_bracket, start_page = get_resume_point(checkpoint, city_slug)

    # Per-bracket failure counter
    bracket_login_blocks: dict = {}
    max_bracket_retries  = config.MAX_LOGIN_RETRIES_PER_BRACKET
    backoff_base         = config.LOGIN_RETRY_BACKOFF_BASE
    backoff_max          = config.LOGIN_RETRY_BACKOFF_MAX

    pw = browser = ctx = page = None
    need_new_browser = True  # always spawn on first attempt

    try:
        for attempt in range(1, config.MAX_RESTARTS_PER_CITY + 1):
            logger.info(
                "\n%s\nŞEHİR: %s — Deneme %d/%d (jar_%d)\n%s",
                "=" * 50, city_name.upper(),
                attempt, config.MAX_RESTARTS_PER_CITY,
                _ACTIVE_JAR_INDEX, "=" * 50,
            )

            try:
                # ── Browser management ──────────────────────────────────
                if need_new_browser:
                    await _close_browser(pw, browser)
                    logger.info("🚀 Yeni tarayıcı oluşturuluyor...")
                    pw, browser, ctx, page = await _spawn_browser()
                    need_new_browser = False
                else:
                    # Soft retry: reuse existing browser, just clear cookies
                    logger.info("🔄 Oturum sıfırlanıyor (tarayıcı korunuyor)...")
                    await ctx.clear_cookies()
                    try:
                        await page.goto("about:blank", timeout=10_000)
                    except Exception:
                        pass

                # ── Cookie warmup bypass ─────────────────────────────────
                warmed_up = False
                if await load_pooled_cookies(page, _ACTIVE_JAR_INDEX):
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
                            logger.info("✅ jar_%d çerezleri geçerli — ısınma atlandı.",
                                        _ACTIVE_JAR_INDEX)
                            warmed_up = True
                        else:
                            logger.info(
                                "   Çerezler geçersiz (URL: %s), silinip ısınılıyor.",
                                _safe_url(page),
                            )
                            delete_pooled_cookies(_ACTIVE_JAR_INDEX)
                            await ctx.clear_cookies()
                    except Exception as e:
                        logger.debug("Çerez doğrulama hatası: %s", e)
                        delete_pooled_cookies(_ACTIVE_JAR_INDEX)
                        await ctx.clear_cookies()

                if not warmed_up:
                    await warmup_with_human_surf(page, loop, cmd_queue)
                    await save_pooled_cookies(page, _ACTIVE_JAR_INDEX)

                await interruptible_sleep(random.uniform(*config.HOMEPAGE_WAIT), cmd_queue)

                total = await scrape_city_brackets(
                    page, city_slug, city_name, brackets, loop, cmd_queue,
                    start_bracket, start_page,
                )

                logger.info("\n✅ %s tamamlandı — %d kayıt.", city_name, total)
                await save_pooled_cookies(page, _ACTIVE_JAR_INDEX)
                break  # Clean success

            except (SkipCitySignal, StopSignal):
                raise

            except RestartBrowserSignal:
                # User typed 'restart' — kill the current browser and spawn fresh
                logger.warning(
                    "🔁 RESTART komutu alındı — tarayıcı yeniden başlatılıyor..."
                )
                need_new_browser = True
                # Pick a fresh jar so the new session starts with a different identity
                old_jar = _ACTIVE_JAR_INDEX
                candidates = [i for i in range(_COOKIE_POOL_SIZE) if i != old_jar]
                _ACTIVE_JAR_INDEX = random.choice(candidates)
                logger.info(
                    "🍪 Restart sonrası yeni jar: jar_%d → jar_%d", old_jar, _ACTIVE_JAR_INDEX
                )
                # No backoff needed — user explicitly requested this

            except SkipBracketSignal:
                start_bracket += 1
                start_page     = 1
                bracket_login_blocks.pop(start_bracket - 1, None)

            except BrowserBlockedError as e:
                error_str     = str(e).lower()
                is_login_block = "login" in error_str or "giris" in error_str

                blocked_bi = start_bracket
                bracket_login_blocks[blocked_bi] = (
                    bracket_login_blocks.get(blocked_bi, 0) + 1
                )
                failures = bracket_login_blocks[blocked_bi]

                if is_login_block:
                    # ── Phase 2: HARD RESET ──────────────────────────────
                    # Login block = site flagged our identity. Kill browser,
                    # delete the active jar, pick a new jar, spawn fresh.
                    logger.error(
                        "🔒 LOGIN BLOĞU — Tarayıcı ve çerezler tamamen sıfırlanıyor! "
                        "(bracket %d, hata: %s)",
                        blocked_bi, e,
                    )
                    delete_pooled_cookies(_ACTIVE_JAR_INDEX)
                    await ctx.clear_cookies()
                    need_new_browser = True  # forces _spawn_browser() next iteration

                    # Pick a DIFFERENT jar for the next attempt
                    old_jar = _ACTIVE_JAR_INDEX
                    candidates = [i for i in range(_COOKIE_POOL_SIZE) if i != old_jar]
                    _ACTIVE_JAR_INDEX = random.choice(candidates)
                    logger.info("🍪 Yeni jar seçildi: jar_%d → jar_%d",
                                old_jar, _ACTIVE_JAR_INDEX)

                else:
                    # ── Soft block: keep browser, clear cookies ──────────
                    logger.error(
                        "🔒 Engellendi (bracket %d, başarısızlık %d/%d): %s",
                        blocked_bi, failures, max_bracket_retries, e,
                    )
                    delete_pooled_cookies(_ACTIVE_JAR_INDEX)
                    await ctx.clear_cookies()
                    need_new_browser = False

                if failures < max_bracket_retries:
                    backoff = min(backoff_base * (2 ** (failures - 1)), backoff_max)
                    logger.info(
                        "🔁 Bracket %d yeniden deneniyor (%d/%d) — %.0fs bekleniyor...",
                        blocked_bi, failures, max_bracket_retries, backoff,
                    )
                    await interruptible_sleep(backoff, cmd_queue)

                else:
                    logger.warning(
                        "⏭️  Bracket %d kalıcı blok (%d deneme), bir sonrakine geçiliyor.",
                        blocked_bi, failures,
                    )
                    bracket_login_blocks.pop(blocked_bi, None)
                    start_bracket += 1
                    start_page     = 1

                    if start_bracket >= len(brackets):
                        logger.error("❌ %s tüm bracket'lar bloklandı, atlanıyor.", city_name)
                        break

                    wait = random.uniform(30, 60)
                    logger.info("⏳ %.1fs bekleniyor...", wait)
                    await interruptible_sleep(wait, cmd_queue)

    except (SkipCitySignal, StopSignal):
        raise

    finally:
        await _close_browser(pw, browser)
        logger.info("🗑️  Tarayıcı kapatıldı (%s).", city_name)