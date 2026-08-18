#!/usr/bin/env python
"""Verify the Chakra (HomeGoods) scraper output for data-quality regressions.

Run from the repository root with:
    python scripts/verify_chakra_scraper.py            # scan every CSV
    python scripts/verify_chakra_scraper.py --history 7   # only the last 7 files

Checks on each inspected Datas/HomeGoods/chakra_all_categories_*.csv:
  1. unnamed-product share (name == 'İsimsiz Ürün')  -> FAIL if > 2%
  2. empty / zero prices                             -> WARN if > 2%
  3. row count sanity (>= 500 rows)                  -> WARN if below
  4. product-id format (all-digits)                  -> FAIL if > 2% malformed

Background: on 2026-08-13 chakra.com.tr stopped shipping product names in the
JSON-LD ItemList, so the scraper fell back to 'İsimsiz Ürün' for 100% of rows
until Codes/HomeGoods/scraper.py was fixed to read the analytics-data
'productListViewed' payload. This verifier would have caught that cliff.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "Datas" / "HomeGoods"

UNNAMED_FALLBACK = "İsimsiz Ürün"
UNNAMED_FAIL_SHARE = 0.02      # 2% of rows may legitimately lack names
ZERO_WARN_SHARE = 0.02         # sold-out items surface as price '0'
MIN_ROWS = 500
ID_RE = re.compile(r"^\d+$")


def _latest_csv_files(limit: int | None) -> list[Path]:
    files = sorted(DATA_DIR.glob("chakra_all_categories_*.csv"))
    if not files:
        raise SystemExit(f"FAIL: no chakra CSVs found under {DATA_DIR}")
    if limit is not None:
        files = files[-limit:]
    return files


def _check_file(path: Path, verbose: bool) -> list[str]:
    failures: list[str] = []
    warnings: list[str] = []

    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    total = len(rows)
    if total < MIN_ROWS:
        warnings.append(f"row count {total} below {MIN_ROWS}")

    unnamed = sum(1 for r in rows if (r.get("name") or "").strip() == UNNAMED_FALLBACK)
    unnamed_share = unnamed / total if total else 1.0
    zeros = sum(
        1 for r in rows if (r.get("price") or "").strip() in ("", "0", "None")
    )
    zero_share = zeros / total if total else 1.0
    bad_ids = sum(1 for r in rows if not ID_RE.match((r.get("id") or "").strip()))
    bad_id_share = bad_ids / total if total else 1.0

    if unnamed_share > UNNAMED_FAIL_SHARE:
        failures.append(
            f"unnamed products {unnamed}/{total} ({unnamed_share:.1%}) exceeds "
            f"{UNNAMED_FAIL_SHARE:.0%} threshold — scraper lost the name source"
        )
    elif verbose:
        warnings.append(f"unnamed products {unnamed}/{total} ({unnamed_share:.1%})")

    if zero_share > ZERO_WARN_SHARE:
        warnings.append(f"zero/empty prices {zeros}/{total} ({zero_share:.1%})")

    if bad_id_share > UNNAMED_FAIL_SHARE:
        failures.append(
            f"malformed product ids {bad_ids}/{total} ({bad_id_share:.1%})"
        )

    if verbose:
        print(f"  rows={total} unnamed={unnamed} zeros={zeros} bad_ids={bad_ids}")
    for w in warnings:
        print(f"  WARN: {w}")
    for f in failures:
        print(f"  FAIL: {f}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        type=int,
        default=None,
        metavar="N",
        help="only scan the last N CSV files (default: every CSV in the folder)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print per-file row stats"
    )
    args = parser.parse_args()

    files = _latest_csv_files(args.history)
    print(f"Checking {len(files)} file(s) under {DATA_DIR}")
    all_failures: list[str] = []
    for path in files:
        print(f"- {path.name}")
        all_failures.extend(_check_file(path, args.verbose))

    if all_failures:
        print(f"\nFAIL: {len(all_failures)} regression(s) detected")
        return 1
    print(f"\nPASS: all checked files within quality thresholds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
