# Vakko Inflation Calculator

Calculates matched-product inflation and TÜİK-style weighted metrics for Vakko price snapshots.

## Metrics

- basic/basket inflation;
- average per-product inflation;
- TÜİK-weighted average normalized over categories present in the run;
- standard 1d, 7d, 15d and 30d comparisons, or an explicit comparison date.

## Paths

- Input: `InflationItems/Datas/ClothingStores/Vakko/vakko_YYYY-MM-DD.csv`
- Long-form detail output: `Inflations/Datas/ClothingStores/Vakko/vakko_inflation.csv`
- Summary output: `Inflations/Datas/ClothingStores/Vakko/inflation_summary.csv`
- Script/config: `Inflations/Codes/ClothingStores/Vakko/`

## Input schema

The calculator recognizes common source columns and normalizes them to:

- stable product identifier (`Stok Kodu`);
- product name (`product-name` / `Ürün Adı`);
- numeric price (`product-price` / `Fiyat`).

Turkish currency symbols, dot thousands separators and decimal commas are normalized before comparison.

## Usage

From the repository root:

```bash
# Standard intervals for a target date
python Inflations/Codes/ClothingStores/Vakko/vakko_inflation.py --date 2026-09-24

# Explicit comparison date
python Inflations/Codes/ClothingStores/Vakko/vakko_inflation.py \
  --date 2026-09-24 \
  --compare 2026-09-10
```

## Category consistency warning

`vakko_tuik_config.py` is a legacy calculator-specific configuration and currently maps cosmetics/perfume to code `12`. The repository-wide canonical 2026 basket configuration uses `13` for personal care and `12` for insurance/finance. Reconcile this mapping before directly merging Vakko category codes with canonical national-calculator output; changing it requires regenerating affected Vakko detail/summary artifacts.

## Output behavior

`Inflations/Codes/detail_store.py` appends/replaces target-date rows in the long-format detail CSV. The summary CSV is updated by target/comparison date, avoiding the retired per-date detail snapshot layout.
