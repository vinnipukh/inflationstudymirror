from __future__ import annotations

import re

import pandas as pd

PRICE_COLUMNS = [
    "member_price",
    "original_price",
    "shown_price",
    "product-price",
    "product_price",
    "price",
    "Price",
    "median_price",
    "Fiyat",
]
ID_COLUMNS = ["Stok Kodu", "sku", "product_id", "UrunID", "id", "Kategori ID"]
NAME_COLUMNS = ["product-name", "name", "Product Name", "brand", "District"]
CATEGORY_COLUMNS = ["category", "Category", "Ana Kategori", "Rooms"]
DATE_PATTERN = re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})")
HISTORY_COLUMNS = ["date", "retailer", "product_id", "product_name", "category", "price", "source_file"]


def parse_date_from_name(name: str) -> pd.Timestamp | pd.NaT:
    match = DATE_PATTERN.search(name)
    if not match:
        return pd.NaT
    return pd.to_datetime("-".join(match.groups()), errors="coerce")


def coerce_price(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return None

    text = (
        text.replace("₺", "")
        .replace("TL", "")
        .replace("TRY", "")
        .replace('"', "")
        .replace("\xa0", " ")
        .strip()
    )
    text = re.sub(r"[^0-9,.-]", "", text)

    if not text or text in {"-", ".", ","}:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if re.search(r",\d{1,2}$", text):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "." in text:
        decimal_places = len(text.rsplit(".", 1)[-1])
        if decimal_places == 3 and text.count(".") >= 1:
            text = text.replace(".", "")

    try:
        return float(text)
    except ValueError:
        return None


def first_non_empty_column(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="string")
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column].astype("string").str.strip().replace("", pd.NA)
        result = result.combine_first(values)
    return result


def build_product_frame(
    frame: pd.DataFrame,
    retailer: str,
    price_column: str,
    date_value: pd.Timestamp,
    source_file: str,
) -> pd.DataFrame:
    if retailer.startswith("HousesRent /"):
        district = first_non_empty_column(frame, ["District"])
        rooms = first_non_empty_column(frame, ["Rooms"])
        product_name = district.str.cat(rooms.fillna(""), sep=" - ").str.strip(" -")
        product_id = product_name
        category = rooms.fillna("Uncategorized")
    elif retailer == "Cosmetics / Watson":
        brand = first_non_empty_column(frame, ["brand"])
        sku = first_non_empty_column(frame, ["sku"])
        product_id = sku.combine_first(brand)
        product_name = brand.fillna("").str.cat(" (" + sku.fillna("") + ")").str.strip()
        product_name = product_name.str.replace(r"^\s*\((.*)\)$", r"\1", regex=True)
        category = brand.fillna("Uncategorized")
    else:
        product_id = first_non_empty_column(frame, ID_COLUMNS)
        product_name = first_non_empty_column(frame, NAME_COLUMNS).combine_first(product_id)
        product_id = product_id.combine_first(product_name)
        category = first_non_empty_column(frame, CATEGORY_COLUMNS).fillna("Uncategorized")

    prices = frame[price_column].map(coerce_price)
    product_data = pd.DataFrame(
        {
            "date": date_value,
            "retailer": retailer,
            "product_id": product_id,
            "product_name": product_name,
            "category": category,
            "price": prices,
            "source_file": source_file,
        }
    )
    product_data = product_data.dropna(subset=["product_id", "product_name", "price"])
    product_data = product_data[
        (product_data["product_id"].astype(str).str.strip() != "")
        & (product_data["product_name"].astype(str).str.strip() != "")
    ]
    return product_data[HISTORY_COLUMNS]
