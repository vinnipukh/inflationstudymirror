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


class SkipCitySignal(Exception):      pass
class SkipBracketSignal(Exception):   pass
class StopSignal(Exception):          pass
class BrowserBlockedError(Exception): pass


def check_commands(cmd_queue):
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
    end_time = time.time() + seconds
    while time.time() < end_time:
        check_commands(cmd_queue)
        await asyncio.sleep(min(0.5, end_time - time.time()))


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


def _viewport_size(page):
    return config.FORCE_VIEWPORT_WIDTH, config.FORCE_VIEWPORT_HEIGHT


async def human_jittery_move(page, tx, ty, steps=15):
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

do_stupid_human_clicks = human_browsing_clicks


async def bracket_safe_clicks(page, count=1):
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


async def enforce_viewport(page):
    actual = page.viewport_size
    actual_w = actual["width"]  if actual else 0
    actual_h = actual["height"] if actual else 0

    if actual_w < config.MINIMUM_SAFE_VIEWPORT_WIDTH:
        logger.warning(
            "⚠️  Rayobrowse küçük viewport atadı (%dx%d). %dx%d'e zorlanıyor.",
            actual_w, actual_h, config.FORCE_VIEWPORT_WIDTH, config.FORCE_VIEWPORT_HEIGHT,
        )
    else:
        logger.debug(
            "Viewport %dx%d → %dx%d'e standardize ediliyor.",
            actual_w, actual_h, config.FORCE_VIEWPORT_WIDTH, config.FORCE_VIEWPORT_HEIGHT,
        )

    await page.set_viewport_size({
        "width": config.FORCE_VIEWPORT_WIDTH,
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


async def patch_browser_detection_leaks(page):
    """Injects anti-detection JavaScript to hide automation markers."""
    logger.info("🛡️  Anti-bot JS patchleri enjekte ediliyor...")
    js_code = """() => {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        delete window.__playwright;
        delete window._playwright;
        delete window.__pw_manual;
        if (window.cdp_) delete window.cdp_;
        if (window.cdp$) delete window.cdp$;
        if (window.__cdp_evaluate) delete window.__cdp_evaluate;
        
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (params) => Promise.resolve({state: 'granted', onchange: null});
        
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5], 
            configurable: true
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['tr-TR', 'tr', 'en-US', 'en'],
            configurable: true
        });
    }"""
    try:
        await page.add_init_script(js_code)
    except Exception as e:
        logger.debug(f"JS patch injection hatası: {e}")


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
    url = ""
    if page:
        try:
            url = page.url.lower().rstrip("/")
        except Exception:
            pass

    if url and (
        "secure.sahibinden.com/giris" in url
        or url.endswith("/giris")
        or ("/giris?" in url and "sahibinden.com" in url)
    ):
        return True

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

    has_password     = 'type="password"' in l
    has_email        = 'type="email"' in l or 'name="email"' in l
    has_google_login = "google ile giriş yap" in l

    if has_password and has_email and has_google_login:
        return True

    return False


def is_protection_page(html, page):
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
        if "/cs/checkloading" in page.url.lower() or "/cs/tloading" in page.url.lower():
            return True, "Managed Challenge"
    except Exception:
        pass

    if "güvenlik doğrulaması" in l or "tarayıcınızı kontrol ediyoruz" in l:
        return True, "Cloudflare"

    if any(s in l for s in ["bir dakika lütfen", "doğrulanıyor"]):
        return True, "Cloudflare Wait"

    return False, ""


def _safe_url(page):
    try:
        return page.url
    except Exception:
        return ""


async def warmup_with_human_surf(page, loop, cmd_queue=None):
    """Enhanced warmup with maximum randomness to bypass behavioral detection."""
    logger.info("🧑‍💻 Randomize ısınma başlatılıyor...")
    try:
        if random.random() < 0.7: 
            await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=60_000)
        else:
            logger.info("⏭️  Ana sayfa atlanıyor (doğrudan giriş simülasyonu)")
            return 
    except Exception as e:
        raise BrowserBlockedError(f"Ana sayfaya erişilemedi: {e}")

    logger.info("   📍 URL: %s", _safe_url(page))
    warmup_duration = random.uniform(8, 25)
    await interruptible_sleep(warmup_duration, cmd_queue)
    
    html = await get_page_content(page)

    if is_login_page(html, page):
        raise BrowserBlockedError(f"Isınma sırasında login yönlendirmesi (URL: {_safe_url(page)})")

    backoff = 2.0
    for attempt in range(3):
        p, r = is_protection_page(html, page)
        if not p:
            break
        logger.info("🛡️  Koruma: %s | URL: %s (deneme %d/3)", r, _safe_url(page), attempt + 1)
        if "turnstile" in r.lower() or "cloudflare" in r.lower() or "managed" in r.lower():
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

    num_scrolls = random.randint(1, 6)
    for _ in range(num_scrolls):
        direction = random.choice([-1, 1])
        distance = random.randint(100, 800)
        await page.mouse.wheel(0, distance * direction)
        await asyncio.sleep(random.uniform(0.3, 1.0))

    if random.random() < 0.75:
        try:
            nav = page.locator("nav a, .mainNavigation a")
            cnt = await nav.count()
            if cnt > 0:
                target = nav.nth(random.randint(0, min(cnt, 5) - 1))
                box = await target.bounding_box()
                if box:
                    await human_jittery_move(
                        page,
                        box["x"] + box["width"]  / 2,
                        box["y"] + box["height"] / 2,
                    )
                    if random.random() < 0.5:
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        except Exception as e:
            logger.debug("Nav hover hatası: %s", e)

    num_stupid = random.randint(0, 3)
    if num_stupid > 0:
        await do_stupid_human_clicks(page, count=num_stupid)


async def _is_enterprise_turnstile(page):
    try:
        has_enterprise_key = await page.evaluate("""() => {
            const input = document.querySelector('input[id="sitekeyEnterprise"]');
            return input !== null && input.value && input.value.startsWith('0x4AAAAAAA');
        }""")
        
        if has_enterprise_key:
            logger.info("🔐 ENTERPRISE Turnstile tespit edildi (sitekeyEnterprise).")
            return True
        
        has_explicit_render = await page.evaluate("""() => {
            const scripts = document.querySelectorAll('script[src*="turnstile"]');
            for (const s of scripts) {
                if (s.src && s.src.includes('render=explicit')) {
                    return true;
                }
            }
            return false;
        }""")
        
        if has_explicit_render:
            logger.info("🔐 EXPLICIT render mode Turnstile tespit edildi.")
            return True
        
        return False
        
    except Exception as e:
        logger.debug(f"Turnstile tipi belirlenemedi: {e}")
        return False


async def solve_enterprise_turnstile(page, loop=None, cmd_queue=None, timeout=90):
    logger.info("⏳ Turnstile API yüklenmesi bekleniyor...")
    has_turnstile = False
    for attempt in range(30): 
        try:
            has_turnstile = await page.evaluate("""() => {
                return typeof window.turnstile !== 'undefined';
            }""")
            if has_turnstile:
                break
        except:
            pass
        await asyncio.sleep(0.5)

    if not has_turnstile:
        logger.warning("⚠️ Turnstile API script'i yüklenmedi.")
        return False

    logger.info("🔧 Turnstile widget aktifleştiriliyor (explicit render)...")
    try:
        render_result = await page.evaluate("""() => {
            if (typeof turnstile === 'undefined' || !turnstile.render) {
                return {error: 'turnstile_not_loaded'};
            }
            try {
                const result = turnstile.render('#turnStileWidget');
                return {status: 'render_called', token: result};
            } catch (e) {
                return {error: e.message};
            }
        }""")
        
        if render_result and render_result.get('error'):
            logger.error(f"❌ turnstile.render() hatası: {render_result['error']}")
            return False
            
        logger.info(f"✅ turnstile.render() başarıyla çağrıldı.")
    except Exception as e:
        logger.error(f"❌ turnstile.render() çağrılırken hata oluştu: {e}")
        return False

    await asyncio.sleep(2)

    logger.info("⏳ Turnstile doğrulaması bekleniyor (maks 30s)...")
    max_verify_wait = 30
    verify_start = time.time()
    
    button_ready = False
    while time.time() - verify_start < max_verify_wait:
        try:
            btn = page.locator('#btn-continue')
            if await btn.count() > 0 and await btn.is_enabled():
                logger.info("✅ 'Devam Et' butonu aktifleşti!")
                button_ready = True
                break
        except Exception as e:
            pass
        
        current_url = page.url
        if '/cs/tloading' not in current_url.lower() and '/cs/checkloading' not in current_url.lower():
            logger.info(f"✅ Doğrulama otomatik geçildi! Yeni URL: {current_url}")
            return True
            
        try:
            content = await get_page_content(page, 2000)
            if 'searchresultstable' in content.lower():
                return True
        except:
            pass
            
        try:
            error_msg = page.locator('#continueRequestError')
            if await error_msg.count() > 0 and await error_msg.is_visible():
                error_text = await error_msg.text_content()
                if error_text and 'gerçekleştiremedik' in error_text.lower():
                    logger.warning(f"⚠️ Turnstile hata mesajı: {error_text}")
                    return False
        except:
            pass
            
        await asyncio.sleep(1)

    if not button_ready:
        logger.warning("⏱ Turnstile doğrulaması zaman aşımına uğradı.")
        return False

    logger.info("🖱️ 'Devam Et' butonuna tıklanıyor...")
    try:
        btn = page.locator('#btn-continue')
        if not await btn.is_enabled():
            await asyncio.sleep(3)
            if not await btn.is_enabled():
                return False 
                
        box = await btn.bounding_box()
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            await human_jittery_move(page, cx, cy)
            await asyncio.sleep(0.5)
            await btn.click()
            logger.info("✅ 'Devam Et' butonu tıklandı!")
    except Exception as e:
        logger.error(f"❌ Butona tıklanamadı: {e}")
        return False

    logger.info("⏳ Yönlendirme bekleniyor (spinner, maks 60s)...")
    post_click_timeout = 60 
    spinner_start = time.time()

    while time.time() - spinner_start < post_click_timeout:
        current_url = page.url
        if '/cs/tloading' not in current_url.lower() and '/cs/checkloading' not in current_url.lower():
            logger.info(f"✅ Yönlendirme başarılı! Yeni URL: {current_url}")
            return True
            
        try:
            content = await get_page_content(page, 2000)
            if 'searchresultstable' in content.lower():
                logger.info("✅ İlan tablosu yüklendi!")
                return True
        except:
            pass
            
        if is_login_page(await get_page_content(page, 5000), page):
            logger.error("❌ Turnstile sonrası login sayfasına yönlendirildi!")
            return False
            
        try:
            error_el = page.locator('#continueRequestError')
            if await error_el.count() > 0 and await error_el.is_visible():
                text = await error_el.text_content()
                if text:
                    if 'gerçekleştirmedi' in text.lower():
                        return False 
        except:
            pass
            
        await asyncio.sleep(2)

    logger.warning("⏱ Post-Turnstile yönlendirmesi zaman aşımına uğradı.")
    return False


async def _wait_for_managed_redirect(page, max_wait=40):
    for _ in range(int(max_wait / 2)):
        await asyncio.sleep(2)
        try:
            if "/cs/checkloading" not in page.url.lower() and "/cs/tloading" not in page.url.lower():
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
        if await btn.count() > 0:
            logger.info("   ⏳ 'Devam Et' butonu etkinleşmesi bekleniyor (maks 30s)...")
            try:
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
    managed = "managed" in reason.lower() or "checkloading" in reason.lower() or "tloading" in reason.lower()
    
    if managed:
        success = await _wait_for_managed_redirect(page)
    else:
        is_enterprise = await _is_enterprise_turnstile(page)
        if is_enterprise:
            logger.info("🔐 ENTERPRISE Turnstile solver kullanılıyor...")
            success = await solve_enterprise_turnstile(page, loop, cmd_queue, timeout=90)
        else:
            logger.info("🔓 FREE TIER Turnstile solver kullanılıyor...")
            success = await _auto_solve_interactive_turnstile(page, loop, cmd_queue)
            
    if success:
        await asyncio.sleep(3)
    return success


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
    base_delay = config.GOTO_RETRY_WAIT[0]
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as e:
            err = str(e).lower()
            if "timeout" in err:
                if attempt < retries:
                    retry_delay = random.uniform(base_delay * 0.8, base_delay * 1.3)
                    logger.warning(
                        "⏱  Timeout (deneme %d/%d), %.1fs sonra tekrar: %s",
                        attempt, retries, retry_delay, url,
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    raise BrowserBlockedError(f"Timeout: {url}") from e
            else:
                raise BrowserBlockedError(f"Goto hatası: {e}") from e


async def safe_goto(page, url, loop, cmd_queue=None):
    await goto_with_retry(page, url)
    await interruptible_sleep(random.uniform(*config.PAGE_LOAD_AFTER_GOTO), cmd_queue)
    html = await get_page_content(page)

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
        if "turnstile" in r.lower() or "cloudflare" in r.lower() or "managed" in r.lower():
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


def extract_total_listings(soup):
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
    page, city_slug, city_name, min_price, max_price, loop, cmd_queue,
    done_ranges=None, depth=0, max_depth=6, session_state=None
):
    if done_ranges is None:
        done_ranges = set()
    if session_state is None:
        session_state = {"pages": 0}

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
        raise 

    soup            = BeautifulSoup(html, "html.parser")
    total_listings  = extract_total_listings(soup)
    max_per_query   = config.MAX_LISTINGS_PER_QUERY
    min_width       = config.MIN_BRACKET_WIDTH

    should_split = (
        total_listings is not None
        and total_listings > max_per_query
        and width > min_width
        and depth < max_depth
    )

    if should_split:
        mid         = (min_price + max_price) // 2
        total_saved = 0

        logger.info("%s→ Sol: %d-%d TL", pad, min_price, mid)
        total_saved += await scrape_adaptive_bracket(
            page, city_slug, city_name, min_price, mid,
            loop, cmd_queue, done_ranges, depth + 1, max_depth, session_state
        )

        await interruptible_sleep(random.uniform(*config.BETWEEN_BRACKETS), cmd_queue)

        if random.random() < config.READING_SIMULATION_PROBABILITY: 
            reading_time = random.uniform(5, 15) 
            logger.info(f"📖 Okuma simülasyonu ({reading_time:.1f}s)...")
            await interruptible_sleep(reading_time, cmd_queue)
            for _ in range(random.randint(1, 3)):
                await page.mouse.wheel(0, random.randint(-300, 300))
                await asyncio.sleep(random.uniform(0.5, 1.5))

        logger.info("%s→ Sağ: %d-%d TL", pad, mid + 1, max_price)
        total_saved += await scrape_adaptive_bracket(
            page, city_slug, city_name, mid + 1, max_price,
            loop, cmd_queue, done_ranges, depth + 1, max_depth, session_state
        )

        done_ranges.add(range_key)
        return total_saved

    records, soup = parse_page(html)
    total_saved   = len(records)
    if records:
        save_incremental(city_name, records)
    else:
        prot, prot_name = is_protection_page(html, page)
        logger.warning(
            "%s⚠️  Sayfa 1'de kayıt yok! URL: %s | Koruma: %s",
            pad, _safe_url(page), prot_name if prot else "yok",
        )

    page_num  = 1
    max_pages = config.MAX_PAGES_PER_BRACKET

    while page_num < max_pages:
        check_commands(cmd_queue)
        next_btn = soup.find("a", title="Sonraki")
        if not next_btn or "href" not in next_btn.attrs:
            break

        next_url  = config.BASE_URL + next_btn["href"]
        page_num += 1
        session_state["pages"] += 1

        delay = random.uniform(*config.MIN_DELAY_BETWEEN_PAGES)
        if random.random() < config.PROBABILITY_OF_EXTRA_DELAY:
            extra = random.uniform(5, 15)
            delay += extra
            logger.info("⏸ Ekstra throttle gecikmesi (%.1fs)", extra)
            
        if session_state["pages"] >= config.COOLDOWN_AFTER_N_PAGES:
            cooldown = random.uniform(*config.COLDOWN_DURATION)
            logger.info("🧊 Cooldown aktifleştirildi (%d sayfa sonrası, %.1fs)", session_state["pages"], cooldown)
            await asyncio.sleep(cooldown)
            session_state["pages"] = 0 
            
        await interruptible_sleep(delay, cmd_queue)

        if random.random() < 0.1: 
            await page.go_back()
            await asyncio.sleep(random.uniform(2, 5))
            await page.go_forward()
            await asyncio.sleep(random.uniform(2, 5))
        elif random.random() < 0.05: 
            await page.goto(page.url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(3, 7))

        try:
            html = await safe_goto(page, next_url, loop, cmd_queue)
        except (SkipBracketSignal, SkipCitySignal, StopSignal):
            raise
        except BrowserBlockedError as e:
            logger.error("%s❌ Sayfa %d'de engellendi: %s", pad, page_num, e)
            raise 

        records, soup = parse_page(html)
        if not records:
            break

        save_incremental(city_name, records)
        total_saved += len(records)
        logger.info("%s✔ Sayfa %d: %d kayıt (toplam: %d)", pad, page_num, len(records), total_saved)

    done_ranges.add(range_key)
    return total_saved


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
    ths = [_normalise_tr(th.text.strip()) for th in soup.select("#searchResultsTable thead th.searchResultsAttributeHeader")]
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
            pass

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

def load_checkpoint():
    cp = config.get_checkpoint_file()
    if os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                d = json.load(f)
            return d
        except Exception:
            pass
    return {}

def save_checkpoint(city_slug, bracket_index, page_num):
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    target = config.get_checkpoint_file()
    tmp    = target + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                    "city":          city_slug,
                    "bracket_index": bracket_index,
                    "page_num":      page_num,
                    "saved_at":      datetime.now().isoformat(),
                }, f, indent=2)
        os.replace(tmp, target)
    except Exception as e:
        pass

def clear_checkpoint():
    cp = config.get_checkpoint_file()
    try:
        if os.path.exists(cp):
            os.remove(cp)
    except Exception:
        pass

def get_resume_point(checkpoint, city_slug):
    if checkpoint.get("city") == city_slug:
        return checkpoint.get("bracket_index", 0), checkpoint.get("page_num", 1)
    return 0, 1

_COOKIE_DIR_CREATED = False
def _ensure_cookie_dir():
    global _COOKIE_DIR_CREATED
    cd = os.path.join(config.CHECKPOINT_DIR, "cookies")
    if not _COOKIE_DIR_CREATED:
        os.makedirs(cd, exist_ok=True)
        _COOKIE_DIR_CREATED = True
    return cd

def get_global_cookie_path():
    return os.path.join(_ensure_cookie_dir(), "global_sahibinden_cookies.json")

def _migrate_legacy_cookies():
    cd          = _ensure_cookie_dir()
    global_path = get_global_cookie_path()
    if os.path.exists(global_path):
        return  

    merged = {}
    for fn in os.listdir(cd):
        if fn.endswith("_cookies.json") and fn != "global_sahibinden_cookies.json":
            fp = os.path.join(cd, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for c in json.load(f):
                        merged[c["name"]] = c  
            except Exception:
                pass

    if merged:
        tmp = global_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(merged.values()), f, indent=2)
        os.replace(tmp, global_path)

async def save_global_cookies(page):
    try:
        cookies    = await page.context.cookies()
        now        = datetime.now(tz=timezone.utc).timestamp()
        persistent = [c for c in cookies if c.get("expires", -1) > now]
        tmp        = get_global_cookie_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(persistent, f, indent=2)
        os.replace(tmp, get_global_cookie_path())
    except Exception as e:
        pass

async def load_global_cookies(page):
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
            return False
        await page.context.add_cookies(valid)
        return True
    except Exception as e:
        return False

def delete_global_cookies():
    path = get_global_cookie_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

async def inject_realistic_cookies(ctx):
    """Adds normal browser cookies that scrapers often miss."""
    await ctx.add_cookies([
        {"name": "__Secure-3PSID", "value": "abc123mockvalue", "domain": ".sahibinden.com", "path": "/", "secure": True},
        {"name": "_ga", "value": "GA1.2.123456789.101112234", "domain": ".sahibinden.com", "path": "/"},
        {"name": "_fbp", "value": "fb.1.123456789.101112234", "domain": ".sahibinden.com", "path": "/"},
    ])


async def scroll_to_bottom_humanlike(page):
    try:
        doc_height = await page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        viewport_h = config.FORCE_VIEWPORT_HEIGHT

        if doc_height <= viewport_h:
            return

        remaining = doc_height - viewport_h
        num_steps = random.randint(8, 14)
        step_sizes = []
        for i in range(num_steps):
            t = i / max(num_steps - 1, 1)
            weight = 4 * t * (1 - t)   
            weight = max(0.1, weight + random.uniform(-0.1, 0.1))
            step_sizes.append(weight)

        total_weight = sum(step_sizes)
        deltas = [int(remaining * w / total_weight) for w in step_sizes]

        delta_diff = remaining - sum(deltas)
        deltas[-1] += delta_diff

        for delta in deltas:
            if delta <= 0:
                continue
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(random.uniform(0.08, 0.28))

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(0.4, 0.8))
    except Exception as e:
        pass


async def scrape_city_brackets(
    page, city_slug, city_name, brackets, loop, cmd_queue,
    start_bracket=0, start_page=1,
):
    total       = 0
    done_ranges = set()
    session_state = {"pages": 0} 

    if start_bracket > 0 and start_bracket < len(brackets):
        mn_skip, mx_skip = brackets[start_bracket]
        logger.warning(
            "⏭️  Yarım kalan bracket atlanıyor (%d-%d TL)", mn_skip, mx_skip,
        )
        start_bracket += 1

    for bi, (mn, mx) in enumerate(brackets):
        check_commands(cmd_queue)
        if bi < start_bracket:
            continue

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
            session_state=session_state
        )
        total += count
        save_checkpoint(city_slug, bi, 1)
        
        await scroll_to_bottom_humanlike(page)

    return total


async def scrape_city(city, checkpoint, cmd_queue):
    city_slug = city["url_slug"]
    city_name = city["name"]
    brackets = city["brackets"]
    loop = asyncio.get_event_loop()

    _migrate_legacy_cookies()
    start_bracket, start_page = get_resume_point(checkpoint, city_slug)

    bracket_login_blocks: dict = {}
    max_bracket_retries = config.MAX_LOGIN_RETRIES_PER_BRACKET
    backoff_base = config.LOGIN_RETRY_BACKOFF_BASE
    backoff_max = config.LOGIN_RETRY_BACKOFF_MAX

    pw = None
    browser = None
    ctx = None
    page = None

    try:
        logger.info("\n%s\nŞEHİR: %s\n%s", "=" * 50, city_name.upper(), "=" * 50)
        ws = rayobrowse.create_browser(
            headless=config.RAYOBROWSE_HEADLESS,
            target_os=config.RAYOBROWSE_TARGET_OS,
            browser_language=config.RAYOBROWSE_BROWSER_LANGUAGE,
            ui_language=config.RAYOBROWSE_UI_LANGUAGE,
        )
        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(ws)

        ctx = browser.contexts[0]

        # FIX VIEWPORT: Use no_viewport=True so the page maps exactly to the OS window size
        # This prevents the Captcha from being pushed off-screen in VNC.
        if not ctx.pages:
            page = await ctx.new_page(no_viewport=True)
        else:
            page = ctx.pages[0]

        for attempt in range(1, config.MAX_RESTARTS_PER_CITY + 1):
            try:
                if attempt > 1:
                    await ctx.clear_cookies()
                    try:
                        await page.goto("about:blank", timeout=10_000)
                    except Exception:
                        pass

                warmed_up = False
                if await load_global_cookies(page):
                    try:
                        await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
                        await asyncio.sleep(2)
                        h = await get_page_content(page)
                        if (
                                not is_protection_page(h, page)[0]
                                and not is_login_page(h, page)
                                and "searchresultstable" in h.lower()
                        ):
                            warmed_up = True
                        else:
                            delete_global_cookies()
                            await ctx.clear_cookies()
                    except Exception:
                        delete_global_cookies()
                        await ctx.clear_cookies()

                if not warmed_up:
                    await warmup_with_human_surf(page, loop, cmd_queue)
                    await save_global_cookies(page)

                total = await scrape_city_brackets(
                    page, city_slug, city_name, brackets, loop, cmd_queue,
                    start_bracket, start_page,
                )

                logger.info("\n✅ %s tamamlandı — %d kayıt.", city_name, total)
                await save_global_cookies(page)
                break

            except (SkipCitySignal, StopSignal):
                raise

            except SkipBracketSignal:
                start_bracket += 1
                start_page = 1
                bracket_login_blocks.pop(start_bracket - 1, None)

            except BrowserBlockedError as e:
                blocked_bi = start_bracket
                bracket_login_blocks[blocked_bi] = bracket_login_blocks.get(blocked_bi, 0) + 1
                failures = bracket_login_blocks[blocked_bi]

                delete_global_cookies()
                await ctx.clear_cookies()
                logger.error("🔒 Engellendi (bracket %d, deneme %d/%d): %s", blocked_bi, failures, max_bracket_retries,
                             e)

                if failures < max_bracket_retries:
                    backoff = min(backoff_base * (2 ** (failures - 1)), backoff_max)
                    await interruptible_sleep(backoff, cmd_queue)
                else:
                    bracket_login_blocks.pop(blocked_bi, None)
                    start_bracket += 1
                    start_page = 1

                    if start_bracket >= len(brackets):
                        break
                    await interruptible_sleep(random.uniform(30, 60), cmd_queue)

    except (SkipCitySignal, StopSignal):
        raise

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