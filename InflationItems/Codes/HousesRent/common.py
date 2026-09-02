"""Shared contracts and normalization helpers for residential rental scrapers.

The site adapters intentionally extract only public, structured listing fields.
They do not open detail pages or collect advertiser names, telephone numbers,
photos, descriptions, or other contact information.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

OUTPUT_FIELDS = (
    "District",
    "Rooms",
    "Price",
    "ilanId",
    "ListingURL",
    "Province",
    "Neighborhood",
    "PropertyType",
    "AreaM2",
    "Currency",
    "ListingDate",
    "CollectedAt",
)

_TR_TRANSLATION = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
    }
)


def clean_text(value: str | None) -> str:
    """Collapse browser whitespace while preserving meaningful punctuation."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def normalize_turkish(value: str | None) -> str:
    """Return a case-insensitive ASCII-ish representation for comparisons."""
    return clean_text(value).translate(_TR_TRANSLATION).casefold()


def normalize_price(value: str | None) -> int | float | None:
    """Parse Turkish-formatted listing prices.

    Examples::

        35.000 TL      -> 35000
        3.875.000 ₺    -> 3875000
        1.250,50 TL    -> 1250.5

    The return value is an ``int`` when no fractional amount is present, which
    keeps CSV output pleasant to read without losing decimal values when a
    site exposes them.
    """
    if not value:
        return None

    compact = clean_text(value)
    if not compact or normalize_turkish(compact) in {"n/a", "fiyat sorunuz"}:
        return None
    digits = re.sub(r"[^0-9,.]", "", compact)
    if not digits:
        return None

    if "." in digits and "," in digits:
        # Turkish prices conventionally use dots for thousands and commas for
        # decimals.  Keeping the right-most separator as the decimal marker
        # also handles an occasional reversed/foreign-formatted value.
        if digits.rfind(",") > digits.rfind("."):
            normalized = digits.replace(".", "").replace(",", ".")
        else:
            normalized = digits.replace(",", "")
    elif "." in digits:
        parts = digits.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            normalized = "".join(parts)
        else:
            normalized = digits
    elif "," in digits:
        parts = digits.split(",")
        if len(parts) > 1 and len(parts[-1]) == 3:
            normalized = "".join(parts)
        else:
            normalized = digits.replace(",", ".")
    else:
        normalized = digits

    try:
        number = float(normalized)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def format_price_tl(value: int | float | str | None) -> str:
    """Format a numeric price using the legacy rental CSV convention."""
    if value is None or value == "":
        return ""
    number = normalize_price(str(value)) if isinstance(value, str) else value
    if number is None:
        return ""
    number = float(number)
    if number.is_integer():
        integer = f"{int(number):,}".replace(",", ".")
        return f"{integer} TL"
    integer, fraction = f"{number:,.2f}".split(".")
    integer = integer.replace(",", ".")
    return f"{integer},{fraction} TL"


def parse_area_m2(value: str | None) -> int | float | None:
    """Extract a square-metre value from a card spec string."""
    if not value:
        return None
    match = re.search(r"([\d.,]+)\s*m(?:²|2)", value, flags=re.IGNORECASE)
    return normalize_price(match.group(1)) if match else None


def parse_listing_date(value: str | None) -> str:
    """Normalize the date formats currently shown on both listing grids."""
    if not value:
        return ""
    candidate = clean_text(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def parse_location(value: str | None) -> tuple[str, str, str]:
    """Split a public card location into province, district, neighborhood."""
    parts = [part.strip() for part in re.split(r"\s*(?:/|,)\s*", clean_text(value)) if part.strip()]
    if not parts:
        return "", "", ""
    province = parts[0]
    district = parts[1] if len(parts) > 1 else ""
    neighborhood = " / ".join(parts[2:]) if len(parts) > 2 else ""
    return province, district, neighborhood


def is_explicitly_sale_listing(title: str | None, url: str | None) -> bool:
    """Reject cards that visibly identify themselves as sale listings.

    The rental routes are the source of truth, but both sites have shown stale
    or promoted cards whose text/slug says ``satılık``.  Rejecting only an
    explicit sale marker avoids guessing from price thresholds.
    """
    haystack = f"{normalize_turkish(title)} {normalize_turkish(url)}"
    return "satilik" in haystack or "satlik" in haystack


def absolute_url(base_url: str, href: str | None) -> str:
    return urljoin(base_url, href or "")


def collected_timestamp(value: str | None = None) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _display_district(district: str, neighborhood: str) -> str:
    district_value = clean_text(district)
    neighborhood_value = clean_text(neighborhood)
    neighborhood_value = re.sub(
        r"\s+(?:mahallesi|mah\.)$", "", neighborhood_value, flags=re.IGNORECASE
    )
    if district_value and neighborhood_value:
        return f"{district_value} / {neighborhood_value}"
    return district_value or neighborhood_value


def make_listing_row(
    *,
    ilan_id: str,
    listing_url: str,
    province: str,
    district: str,
    neighborhood: str,
    property_type: str,
    rooms: str,
    area_m2: int | float | None,
    price: int | float,
    listing_date: str,
    collected_at: str | None = None,
) -> dict[str, Any]:
    """Build the stable public-data CSV contract used by both adapters."""
    return {
        "District": _display_district(district, neighborhood),
        "Rooms": clean_text(rooms),
        "Price": format_price_tl(price),
        "ilanId": ilan_id,
        "ListingURL": listing_url,
        "Province": province,
        "Neighborhood": clean_text(neighborhood),
        "PropertyType": clean_text(property_type),
        "AreaM2": area_m2,
        "Currency": "TRY",
        "ListingDate": listing_date,
        "CollectedAt": collected_timestamp(collected_at),
    }


class CsvSink:
    """Append-only, ID-deduplicating sink for one source/day CSV."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.seen_ids: set[str] = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    identifier = clean_text(row.get("ilanId"))
                    if identifier:
                        self.seen_ids.add(identifier)

    def write(self, rows: list[dict[str, Any]]) -> int:
        fresh: list[dict[str, Any]] = []
        batch_ids = set(self.seen_ids)
        for row in rows:
            identifier = clean_text(str(row.get("ilanId", "")))
            if not identifier or identifier in batch_ids:
                continue
            fresh.append(row)
            batch_ids.add(identifier)
        if not fresh:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_FIELDS), extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for row in fresh:
                writer.writerow({field: row.get(field, "") for field in OUTPUT_FIELDS})
                self.seen_ids.add(clean_text(str(row.get("ilanId", ""))))
        return len(fresh)


def load_checkpoint(path: str | Path) -> dict[str, Any]:
    checkpoint = Path(path)
    if not checkpoint.exists():
        return {}
    try:
        with checkpoint.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_checkpoint(path: str | Path, state: dict[str, Any]) -> None:
    checkpoint = Path(path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    temporary = checkpoint.with_suffix(checkpoint.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
    temporary.replace(checkpoint)
