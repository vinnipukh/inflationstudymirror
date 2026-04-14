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
PAGE_LOAD_AFTER_GOTO  = (8.3,  12.4)
BETWEEN_BRACKETS      = (7.2,   8.1)
BETWEEN_PAGES         = (9.7,  12.5)
GOTO_RETRY_WAIT       = (14.7, 17.9)
POST_CHECK_WAIT       = (5.5,   7.7)
HOMEPAGE_WAIT         = (25.5,   35.6)
CITY_CLOSE_WAIT       = 30

# ---------------------------------------------------------------------------
# Rate Limiting & Throttling (Issue #3)
# ---------------------------------------------------------------------------
MIN_DELAY_BETWEEN_PAGES        = (6, 8)      # 3-8 seconds between pages
MAX_DELAY_BETWEEN_PAGES        = (12, 20)    # Max occasional delay
DELAY_BETWEEN_BRACKETS         = (15, 35)    # Between brackets
COOLDOWN_AFTER_N_PAGES         = 20          # After 20 pages, take longer break
COLDOWN_DURATION               = (30, 90)    # Break duration
PROBABILITY_OF_EXTRA_DELAY     = 0.15        # 15% chance of extra delay
READING_SIMULATION_PROBABILITY = 0.25        # 25% chance of "reading time"

# ---------------------------------------------------------------------------
# Rayobrowse browser settings
# ---------------------------------------------------------------------------
RAYOBROWSE_HEADLESS         = False
RAYOBROWSE_TARGET_OS        = "windows"
RAYOBROWSE_BROWSER_LANGUAGE = "tr-TR,tr;q=0.9"
RAYOBROWSE_UI_LANGUAGE      = "tr-TR"

# ---------------------------------------------------------------------------
# Viewport enforcement
# ---------------------------------------------------------------------------
FORCE_VIEWPORT_WIDTH          = 1920
FORCE_VIEWPORT_HEIGHT         = 1080
MINIMUM_SAFE_VIEWPORT_WIDTH   = 1200
OVERRIDE_SCREEN_JS_PROPERTIES = True

# ---------------------------------------------------------------------------
# Per-bracket login retry
# ---------------------------------------------------------------------------
MAX_LOGIN_RETRIES_PER_BRACKET = 3
LOGIN_RETRY_BACKOFF_BASE      = 30
LOGIN_RETRY_BACKOFF_MAX       = 120

# ---------------------------------------------------------------------------
# Scraping limits
# ---------------------------------------------------------------------------
MAX_RESTARTS_PER_CITY = 5
MAX_PAGES_PER_BRACKET = 30
PAGE_SIZE             = 50

# ---------------------------------------------------------------------------
# Smart Adaptive Brackets
# ---------------------------------------------------------------------------
MAX_LISTINGS_PER_QUERY = 1000
MIN_BRACKET_WIDTH      = 500
MAX_ADAPTIVE_DEPTH     = 6

BASE_URL = "https://www.sahibinden.com"