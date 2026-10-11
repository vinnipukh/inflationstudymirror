"""
main.py — Sarı site kira scraper entry point.

Thin wrapper over engine_selenium (undetected-chromedriver + persistent
profile + manual-solve loop + adaptive pacing — the proven daily pattern).

Usage:
    python main.py --city kayseri --rooms 3+1
    python main.py --resume          # continue from checkpoint after a crash
"""

from engine_selenium import main

if __name__ == "__main__":
    main()
