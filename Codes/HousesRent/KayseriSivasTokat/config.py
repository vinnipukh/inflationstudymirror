import datetime as _dt
from pathlib import Path as _Path

_SCRIPTS_DIR  = _Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent.parent.parent

DEFAULT_BRACKETS = [
    (0,       19_999),
    (20_000,  39_999),
    (40_000,  59_999),
    (60_000,  99_999),
    (100_000, 9_999_999),
]

CITIES = [
    {"url_slug": "kayseri", "name": "Kayseri", "brackets": DEFAULT_BRACKETS},
    {"url_slug": "sivas",   "name": "Sivas",   "brackets": DEFAULT_BRACKETS},
    {"url_slug": "tokat",   "name": "Tokat",   "brackets": DEFAULT_BRACKETS},
]

TODAY = _dt.date.today().strftime("%Y-%m-%d")

OUTPUT_BASE_DIR = str(_PROJECT_ROOT / "Datas" / "HousesRent")
CHECKPOINT_DIR  = str(_SCRIPTS_DIR / "checkpoints")

def get_city_output_dir(city_name: str) -> str:
    return str(_Path(OUTPUT_BASE_DIR) / city_name)

def get_city_csv_path(city_name: str) -> str:
    return str(_Path(OUTPUT_BASE_DIR) / city_name / f"{TODAY}.csv")

def get_checkpoint_file() -> str:
    return str(_Path(CHECKPOINT_DIR) / f"checkpoint_{TODAY}.json")

# ---------------------------------------------------------------------------
# Timing (seconds) — all randomised per-call between (min, max)
# ---------------------------------------------------------------------------
PAGE_LOAD_AFTER_GOTO  = (8.0,  12.0)
BETWEEN_BRACKETS      = (4.0,   6.0)
BETWEEN_PAGES         = (8.0,  12.0)
GOTO_RETRY_WAIT       = (13.0, 18.0)
POST_CHECK_WAIT       = (4.0,   6.0)
HOMEPAGE_WAIT         = (3.0,   5.0)
CITY_CLOSE_WAIT       = 30

# ---------------------------------------------------------------------------
# Rayobrowse browser settings (v0.2.1)
#
# Breaking change in v0.2.0: create_browser() is replaced by a plain
# HTTP GET to /connect.  Parameter names updated accordingly:
#   target_os  → os          (same values: "windows", "android", "macos")
#   NEW: browser_name, browser_version_min, browser_version_max
#   browser_language and ui_language still accepted as query params
# ---------------------------------------------------------------------------
RAYOBROWSE_ENDPOINT         = "http://localhost:9222"
RAYOBROWSE_HEADLESS         = False
RAYOBROWSE_TARGET_OS        = "windows"      # Best fingerprint coverage
RAYOBROWSE_BROWSER_NAME     = "chrome"
RAYOBROWSE_BROWSER_VERSION_MIN = 146        # Pin to a specific version range
RAYOBROWSE_BROWSER_VERSION_MAX = 146        # (146 = latest in v0.2.1)
RAYOBROWSE_BROWSER_LANGUAGE = "tr-TR,tr;q=0.9"
RAYOBROWSE_UI_LANGUAGE      = "tr-TR"

# ---------------------------------------------------------------------------
# FIX #2 — Viewport enforcement
# Rayobrowse randomises viewport per fingerprint. Small viewports break the
# Turnstile widget layout and cause click misses. We force a safe desktop
# size immediately after connecting, and optionally patch the JS screen
# object so fingerprint and viewport stay consistent.
# ---------------------------------------------------------------------------
FORCE_VIEWPORT_WIDTH          = 1920   # Enforced viewport width (px)
FORCE_VIEWPORT_HEIGHT         = 1080   # Enforced viewport height (px)
MINIMUM_SAFE_VIEWPORT_WIDTH   = 1200   # Only force if actual width < this
OVERRIDE_SCREEN_JS_PROPERTIES = True   # Patch window.screen.* to match

# ---------------------------------------------------------------------------
# FIX #1 — Per-bracket login retry
# Instead of skipping a bracket immediately after the first login block,
# retry it up to MAX_LOGIN_RETRIES_PER_BRACKET times with exponential
# back-off before giving up and moving to the next bracket.
# ---------------------------------------------------------------------------
MAX_LOGIN_RETRIES_PER_BRACKET = 3    # Retries before permanently skipping
LOGIN_RETRY_BACKOFF_BASE      = 30   # Base wait in seconds (doubles each retry)
LOGIN_RETRY_BACKOFF_MAX       = 120  # Maximum wait cap in seconds

# ---------------------------------------------------------------------------
# Scraping limits
# ---------------------------------------------------------------------------
MAX_RESTARTS_PER_CITY = 3    # Full browser-session restarts per city
MAX_PAGES_PER_BRACKET = 20   # Safety page cap per price range
PAGE_SIZE             = 50   # Listings per page

# ---------------------------------------------------------------------------
# Smart Adaptive Brackets
# ---------------------------------------------------------------------------
MAX_LISTINGS_PER_QUERY = 1000   # Split bracket when listing count exceeds this
MIN_BRACKET_WIDTH      = 500    # Minimum TL width — never split below this
MAX_ADAPTIVE_DEPTH     = 6      # Max recursion depth (prevents stack overflow)

# ---------------------------------------------------------------------------
# Base URL
# ---------------------------------------------------------------------------
BASE_URL = "https://www.sahibinden.com"

# ---------------------------------------------------------------------------
# Issue #3 — Rate limiting / request throttling
# After COOLDOWN_AFTER_N_PAGES pages scraped in one session, the scraper
# takes a longer break before continuing.
# ---------------------------------------------------------------------------
COOLDOWN_AFTER_N_PAGES           = 20      # Pages before forced cooldown
COOLDOWN_DURATION                = (30, 90) # Cooldown length in seconds
PROBABILITY_OF_EXTRA_DELAY       = 0.15    # Chance of a random extra pause
EXTRA_DELAY_RANGE                = (5, 15) # Length of that extra pause

# ---------------------------------------------------------------------------
# Issue #2 — Behavioural randomisation
# Controls "reading simulation" pauses injected randomly between brackets.
# ---------------------------------------------------------------------------
READING_SIMULATION_PROBABILITY   = 0.30    # Chance to simulate reading
READING_SIMULATION_DURATION      = (5, 15) # How long to "read" (seconds)

# ---------------------------------------------------------------------------
# Issue #2 — Anti-detection JS injection
# Whether to call patch_browser_detection_leaks() after page creation.
# Disable only for debugging — should always be True in production.
# ---------------------------------------------------------------------------
PATCH_BROWSER_DETECTION_LEAKS    = True