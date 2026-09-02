"""
config.py — Sarı site kira scraper configuration.

Aligned with the proven IstanbulAvrupa pattern (undetected-chromedriver +
persistent profile + adaptive pacing) and the project's compliance scope:
fields are District, Rooms, Price, ilanId ONLY (docs/APPROACH.md B0).
"""

import datetime as _dt
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parent
_ITEMS_ROOT = _SCRIPTS_DIR.parent.parent.parent
_PROJECT_ROOT = _ITEMS_ROOT.parent

# ── City settings ────────────────────────────────────────────────────────────
DEFAULT_BRACKETS = [
    (0, 19_999),
    (20_000, 39_999),
    (40_000, 59_999),
    (60_000, 99_999),
    (100_000, 9_999_999),
]

CITIES = [
    {"url_slug": "kayseri", "name": "Kayseri", "brackets": DEFAULT_BRACKETS},
    {"url_slug": "sivas", "name": "Sivas", "brackets": DEFAULT_BRACKETS},
    {"url_slug": "tokat", "name": "Tokat", "brackets": DEFAULT_BRACKETS},
]

TODAY = _dt.date.today().strftime("%Y-%m-%d")  # noqa: DTZ011 — daily-run date, local tz is intended

OUTPUT_BASE_DIR = str(_ITEMS_ROOT / "Datas" / "HousesRent")
CHECKPOINT_DIR = str(_SCRIPTS_DIR / "checkpoints")


def get_city_output_dir(city_name: str) -> str:
    return str(_Path(OUTPUT_BASE_DIR) / city_name)


def get_city_csv_path(city_name: str) -> str:
    return str(_Path(OUTPUT_BASE_DIR) / city_name / f"{TODAY}.csv")


def get_checkpoint_file() -> str:
    return str(_Path(CHECKPOINT_DIR) / f"checkpoint_{TODAY}.json")


# ── Compliance scope (docs/APPROACH.md B0 — law-faculty confirmed) ───────────
# Only rows whose Rooms cell matches exactly are saved. "3+1" = 3+1 daireler.
# Set to None to collect all room types. Fields NEVER collected: contact info,
# advertiser names, photos (no detail-page crawling).
ROOMS_FILTER = "3+1"

# ── Site / query limits ──────────────────────────────────────────────────────
BASE_URL = "https://www.sahibinden.com"
PAGE_SIZE = 50  # Listings per page (site max)
MAX_PAGES_PER_BRACKET = 20  # Safety page cap per price range
MAX_LISTINGS_PER_QUERY = 1000  # Site query cap (20 pages × 50) — split above
MIN_BRACKET_WIDTH = 50  # Safety valve against infinite splitting
MAX_BRACKET_SPLIT_DEPTH = 6

# ── Timing (friend-tactics adaptive pacing) ──────────────────────────────────
PAGE_LOAD_DELAY = 2.5  # Base wait after page load (s); ±50% jitter
BETWEEN_BRACKET_DELAY_MIN = 1.0  # Random pause between bracket probes (s)
BETWEEN_BRACKET_DELAY_MAX = 2.0

ADAPTIVE_DELAY_ENABLED = True  # Shrink delay on success streaks, grow on errors
ADAPTIVE_MIN_DELAY = 1.5
ADAPTIVE_MAX_DELAY = 8.0
ADAPTIVE_DECREASE_FACTOR = 0.95  # Multiply by this after N consecutive successes
ADAPTIVE_INCREASE_FACTOR = 1.5  # Multiply by this on error
ADAPTIVE_SUCCESS_THRESHOLD = 3  # Consecutive successes before reducing delay

# ── Retry / backoff ──────────────────────────────────────────────────────────
MAX_RETRIES = 3  # Retry attempts for failed page fetches
RETRY_BACKOFF_BASE = 2.0  # Base delay for exponential backoff (s)
RETRY_BACKOFF_MAX = 30.0  # Maximum backoff delay (s)

# ── Persistent profile (cookie-saving trust strategy) ────────────────────────
# The profile carries cf_clearance/_px3 across daily runs. Solve the Turnstile
# manually on day one; every subsequent run is a warm session.
PROFILE_DIR = str(_SCRIPTS_DIR / "SeleniumProfile")
