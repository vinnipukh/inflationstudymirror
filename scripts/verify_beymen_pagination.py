"""Verification harness for Codes/Technology/scraper.py pagination fix.

Runs the real scrape_beymen() end-to-end but replaces the (environment-only)
seleniumbase cookie step with empty cookies: the Beymen API serves the
catalog without cookies, and get_stealth_cookies is untouched by this change.

Usage:
    C:/Users/arhan/AppData/Local/Programs/Python/Python312/python.exe \
        scripts/verify_beymen_pagination.py

It overwrites Datas/Technology/beymen_tech_<today>.csv with the full catalog.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "Codes" / "Technology"))

import scraper  # noqa: E402

scraper.get_stealth_cookies = lambda target_url: {}
scraper.scrape_beymen()
