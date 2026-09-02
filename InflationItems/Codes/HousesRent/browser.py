"""Small Selenium lifecycle layer shared by the two housing adapters.

The default path is a visible, ordinary Chrome session.  A caller may attach to
an already-running Chrome relay/CDP endpoint with ``--debugger-address``.  The
scraper deliberately stops on a challenge page; it does not attempt to solve,
bypass, or automate CAPTCHA/anti-bot controls.

CI reliability (2026-09-02):
- The GitHub runner failure mode was a Chrome renderer that stopped answering;
  Selenium's own 120 s wire read timeout then killed the whole job.  Browser
  commands are therefore bounded by a watchdog, and :class:`BrowserSession`
  discards the dead session, starts a fresh driver, and retries the page.
- Launched drivers get container-safe flags (``--disable-dev-shm-usage``,
  ``--no-sandbox``) and the ``eager`` page-load strategy so ``driver.get``
  returns at DOM-interactive instead of waiting on slow trackers/subresources.
"""

from __future__ import annotations

import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

LOGGER = logging.getLogger("houses-rent.browser")

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

# Container/host stability flags.  GitHub runners and Docker hosts provide a
# tiny /dev/shm (Chrome crashes there without --disable-dev-shm-usage), run as
# non-root (--no-sandbox), and do not need GPU rendering.
_STABILITY_ARGS = (
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-sync",
    "--metrics-recording-only",
    "--disable-features=Translate,MediaRouter,OptimizationHints,BackForwardCache",
)

_DEFAULT_COMMAND_TIMEOUT = 90.0  # Selenium wire timeout per command (s)


class ChallengeDetected(RuntimeError):
    """Raised when a target presents a challenge instead of a listing grid."""


class DriverStall(RuntimeError):
    """Raised when a browser command exceeds its watchdog budget.

    The session is considered unusable afterwards; callers should discard it
    and start a fresh driver (see :class:`BrowserSession`).
    """


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
    fresh_profile: bool = False,
) -> webdriver.Chrome:
    """Create Chrome or attach to an existing Chrome relay session.

    ``debugger_address`` is the standard Selenium CDP attach value, for
    example ``127.0.0.1:9222``.  When it is supplied, the user's browser is
    never quit by the CLI adapters.

    ``fresh_profile`` launches Chrome with a brand-new temporary user data
    directory.  It is intended for CI/long crawls: every launch (including
    browser restarts) starts from a clean profile and avoids profile-lock
    stalls.  An explicit ``profile_dir`` always wins over ``fresh_profile``.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--lang=tr-TR")
    for argument in _STABILITY_ARGS:
        options.add_argument(argument)
    if headless:
        options.add_argument("--headless=new")
    if profile_dir and not debugger_address:
        options.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")
    elif fresh_profile and not debugger_address:
        options.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='houses-rent-chrome-')}")
    if disable_images:
        options.add_experimental_option(
            "prefs", {"profile.managed_default_content_settings.images": 2}
        )
    if debugger_address:
        options.add_experimental_option("debuggerAddress", debugger_address)
    else:
        # Return at DOM-interactive instead of waiting for every slow
        # subresource; the listing grid is server-rendered, and callers wait
        # explicitly for their selector.
        options.set_capability("pageLoadStrategy", "eager")
    driver = webdriver.Chrome(options=options)
    _configure_driver(driver)
    return driver


def _configure_driver(driver: Any) -> None:
    """Best-effort wire timeouts so a dead session fails fast, not at 120 s."""
    try:
        driver.set_page_load_timeout(_DEFAULT_COMMAND_TIMEOUT)
        driver.set_script_timeout(45.0)
    except Exception:  # pragma: no cover - driver already dying
        pass
    try:
        executor = getattr(driver, "command_executor", None)
        config = getattr(executor, "_client_config", None)
        if config is not None:
            config.timeout = _DEFAULT_COMMAND_TIMEOUT
        elif executor is not None and hasattr(executor, "set_timeout"):
            executor.set_timeout(_DEFAULT_COMMAND_TIMEOUT)
    except Exception:  # pragma: no cover
        pass


def _run_bounded(operation: Callable[[], Any], timeout: float, message: str) -> Any:
    """Run ``operation`` in a daemon thread with an overall deadline.

    Raises :class:`DriverStall` when the deadline expires.  The daemon thread
    keeps whatever Selenium call is stuck (it will surface its own error or be
    reaped with the process), which lets :class:`BrowserSession` move on to a
    fresh driver immediately.
    """
    result: dict[str, Any] = {}

    def _worker() -> None:
        try:
            result["value"] = operation()
            result["ok"] = True
        except BaseException as exc:  # noqa: BLE001 - captured for the caller
            result["error"] = exc

    thread = threading.Thread(target=_worker, name="browser-watchdog", daemon=True)
    thread.start()
    thread.join(max(0.1, timeout))
    if thread.is_alive():
        raise DriverStall(message)
    if result.get("error") is not None:
        raise result["error"]
    return result["value"]


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


def _scroll_to_lazy_content(driver: Any, *, rounds: int = 15, pause: float = 0.3) -> None:
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
    scroll_rounds: int = 15,
    scroll_pause: float = 0.3,
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
        _run_bounded(
            lambda: _scroll_to_lazy_content(driver, rounds=scroll_rounds, pause=scroll_pause),
            timeout=scroll_rounds * (scroll_pause + 2.0) + 10.0,
            message=f"Scrolling {url} did not answer within the watchdog budget",
        )
        html = driver.page_source
        if is_challenge_page(html):
            raise ChallengeDetected(
                f"A challenge appeared while loading {url}; no automated bypass was attempted."
            )
    return html


class BrowserSession:
    """Own one Chrome session and recover it when the browser stalls.

    Every page operation runs under a watchdog.  When the browser stops
    answering (the CI failure mode seen on 2026-09-01), the session is
    discarded, a fresh driver is started through ``driver_factory``, and the
    same URL is retried up to ``max_retries`` times.  Challenge pages are
    re-raised without retrying: they are not a transient failure.
    """

    def __init__(
        self,
        driver_factory: Callable[[], Any] | None = None,
        *,
        max_retries: int = 3,
        page_timeout: float = 45.0,
        scroll: bool = True,
        logger: Any | None = None,
    ) -> None:
        self._factory = driver_factory
        self._max_retries = max(1, max_retries)
        self._page_timeout = max(10.0, page_timeout)
        self._scroll = scroll
        self._log = logger or LOGGER
        self.driver: Any = None
        if self._factory is None:
            self._factory = lambda: create_chrome_driver()

    def start(self) -> Any:
        """Start (or restart with) a fresh driver and make it current."""
        if self.driver is not None:
            self._dispose()
        self.driver = self._factory()
        return self.driver

    def _dispose(self) -> None:
        driver, self.driver = self.driver, None
        if driver is None:
            return
        # Never block recovery on a dead session: quit() best-effort in a
        # short-lived helper thread.
        try:

            def _quit() -> None:
                try:
                    driver.quit()
                except Exception:  # pragma: no cover - driver teardown race
                    pass

            closer = threading.Thread(target=_quit, name="browser-quit", daemon=True)
            closer.start()
            closer.join(10.0)
        except Exception:  # pragma: no cover
            pass

    def restart(self) -> None:
        """Discard the current session and start a brand-new driver."""
        self._dispose()
        self.start()

    def load(
        self,
        url: str,
        *,
        wait_selector: str,
        timeout: float | None = None,
        scroll: bool | None = None,
    ) -> str:
        """Load a page, retrying with a fresh browser when the session dies."""
        timeout = timeout or self._page_timeout
        scroll = self._scroll if scroll is None else scroll
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            if self.driver is None:
                self.start()
            try:
                budget = timeout + (60.0 if scroll else 0.0) + 20.0
                return _run_bounded(
                    lambda: load_rendered_page(
                        self.driver,
                        url,
                        wait_selector=wait_selector,
                        timeout=timeout,
                        scroll=scroll,
                    ),
                    timeout=budget,
                    message=f"Loading {url} did not answer within the watchdog budget",
                )
            except ChallengeDetected:
                raise
            except Exception as exc:
                last_error = exc
                self._log.warning(
                    "Page load failed on attempt %d/%d (%s: %s); restarting browser",
                    attempt,
                    self._max_retries,
                    type(exc).__name__,
                    exc,
                )
                self.restart()
                if attempt < self._max_retries:
                    time.sleep(min(2.0 * attempt, 8.0))
        raise RuntimeError(
            f"Could not load {url} after {self._max_retries} browser restart(s): {last_error}"
        ) from last_error

    def close(self) -> None:
        """Quit the current session (safe to call multiple times)."""
        self._dispose()
