"""Small Selenium lifecycle layer shared by the two housing adapters.

The default path is a visible, ordinary Chrome session.  A caller may attach to
an already-running Chrome relay/CDP endpoint with ``--debugger-address``.  The
scraper deliberately stops on a challenge page; it does not attempt to solve,
bypass, or automate CAPTCHA/anti-bot controls.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "verify you are human",
    "enable javascript and cookies",
    "cf-chl-",
    "cf-turnstile",
    "/cs/tloading",
    "access denied",
)
_EMPTY_MARKERS = (
    "ilan bulunamadı",
    "ilan bulunamadi",
    "sonuç bulunamadı",
    "sonuc bulunamadi",
    "aradığınız kriterlere uygun",
    "aradiginiz kriterlere uygun",
)


class ChallengeDetected(RuntimeError):
    """Raised when a target presents a challenge instead of a listing grid."""


def is_challenge_page(html: str | None) -> bool:
    """Return true for recognizable challenge/interstitial documents only."""
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


def _is_empty_listing_page(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _EMPTY_MARKERS)


def create_chrome_driver(
    *,
    debugger_address: str | None = None,
    profile_dir: str | Path | None = None,
    headless: bool = False,
    disable_images: bool = True,
) -> webdriver.Chrome:
    """Create Chrome or attach to an existing Chrome relay session.

    ``debugger_address`` is the standard Selenium CDP attach value, for
    example ``127.0.0.1:9222``.  When it is supplied, the user's browser is
    never quit by the CLI adapters.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if headless:
        options.add_argument("--headless=new")
    if profile_dir and not debugger_address:
        options.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")
    if disable_images:
        options.add_experimental_option(
            "prefs", {"profile.managed_default_content_settings.images": 2}
        )
    if debugger_address:
        options.add_experimental_option("debuggerAddress", debugger_address)
    return webdriver.Chrome(options=options)


def _document_ready(driver: Any) -> bool:
    try:
        return driver.execute_script("return document.readyState") in {"interactive", "complete"}
    except Exception:  # pragma: no cover - browser teardown race
        return False


def _rows_ready(driver: Any, selector: str) -> bool:
    try:
        html = driver.page_source
        if is_challenge_page(html):
            return True
        if selector == "body":
            return _document_ready(driver)
        if driver.find_elements(By.CSS_SELECTOR, selector):
            return True
        return _is_empty_listing_page(html)
    except Exception:  # pragma: no cover - browser teardown race
        return False


def _scroll_to_lazy_content(driver: Any, *, rounds: int = 30, pause: float = 0.2) -> None:
    """Trigger normal intersection-observer hydration without opening cards."""
    stable = 0
    previous_height = 0
    for _ in range(rounds):
        height = int(
            driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
            )
            or 0
        )
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(max(0.0, pause))
        new_height = int(
            driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
            )
            or 0
        )
        if new_height == height == previous_height:
            stable += 1
        else:
            stable = 0
        previous_height = new_height
        if stable >= 2:
            break
    driver.execute_script("window.scrollTo(0, 0);")


def load_rendered_page(
    driver: Any,
    url: str,
    *,
    wait_selector: str,
    timeout: float = 30.0,
    scroll: bool = True,
) -> str:
    """Navigate, wait for the public grid, hydrate lazy cards, return HTML."""
    driver.get(url)
    try:
        WebDriverWait(driver, timeout).until(lambda current: _rows_ready(current, wait_selector))
    except TimeoutException as exc:
        html = driver.page_source
        if is_challenge_page(html):
            raise ChallengeDetected(
                f"A challenge was presented at {url}; solve it manually and rerun with --resume."
            ) from exc
        raise RuntimeError(f"Timed out waiting for {wait_selector} at {url}") from exc

    html = driver.page_source
    if is_challenge_page(html):
        raise ChallengeDetected(
            f"A challenge was presented at {url}; no automated bypass was attempted."
        )
    if scroll and wait_selector != "body":
        _scroll_to_lazy_content(driver)
        html = driver.page_source
        if is_challenge_page(html):
            raise ChallengeDetected(
                f"A challenge appeared while loading {url}; no automated bypass was attempted."
            )
    return html
