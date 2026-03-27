# 📊 Inflation Study — AI 201 Project
**Özyeğin University · AI 201 · Spring 2026**

> An automated data-collection and analysis pipeline that tracks real-time product prices from Turkish retailers to study inflation patterns across grocery markets, clothing stores, housing rentals, and construction/hardware markets.

---

## 📌 Project Overview

This project builds a web-scraping infrastructure to collect daily price data from online Turkish retailers, with the goal of:

- Monitoring **price changes over time** across product categories
- Comparing inflation trends between **grocery markets** (e.g. Gurmar), **clothing stores** (e.g. Vakko), **housing rentals** (Sahibinden), and **construction/hardware markets** (Yapimaks)
- Creating a structured, date-stamped dataset suitable for downstream AI/ML analysis and an **inflation calculator** (coming soon)

The scrapers run automatically (via GitHub Actions) and append new daily snapshots to the `Datas/` directory.

> ⚠️ **This is an active project.** More retailers (markets, clothing stores, housing, and construction) will be added over time.

---

## 👤 Author

| Name | University | Course |
|------|------------|--------|
| vinnipukh | Özyeğin University | AI 201 — Spring 2026 |

---

## 🗂️ Repository Structure

```
inflationstudymirror/
│
├── Codes/                              # All scraping & processing scripts
│   ├── Markets/
│   │   └── Gurmar/
│   │       └── gurmar_scraper.py       # Selenium-based scraper for gurmar.com.tr
│   │
│   ├── ClothingStores/
│   │   └── Vakko/
│   │       ├── vakko_master_scraper.py # API-based scraper for vakko.com
│   │       ├── categoryfinder.py       # Extracts category IDs from sitemap XML
│   │       └── vakko_categories.xml    # Vakko sitemap (category URLs)
│   │
│   ├── ConstructionMarkets/
│   │   └── yapimaks/
│   │       ├── scraper.py              # Python/XML scraper for yapimaks.com
│   │       └── products1.xml           # Yapimaks product sitemap
│   │
│   ├── HousesRent/
│   │   └── KayseriSivasTokat/
│   │       ├── main.py                 # Orchestrator for Kayseri/Sivas/Tokat cities
│   │       ├── scraper.py              # Async Camoufox-based scraper for sahibinden.com
│   │       ├── run_scraper.py          # Helper runner script
│   │       └── config.py               # City/search configuration
│   │
│   └── sahibinden/
│       └── camoufox_scraper.py         # Sahibinden scraper (legacy; manual-run)
│
├── Datas/                              # Collected price data (CSV, date-stamped)
│   ├── Markets/
│   │   └── Gurmar/
│   │       ├── gurmar_prices_YYYY-MM-DD.csv
│   │       └── ...
│   │
│   ├── ClothingStores/
│   │   └── Vakko/
│   │       ├── vakko_YYYY-MM-DD.csv
│   │       └── ...
│   │
│   ├── yapimaks/
│   │   ├── yapimaks_YYYY-MM-DD.csv
│   │   └── ...
│   │
│   └── HousesRent/
│       ├── Kayseri/
│       ├── Sivas/
│       └── Tokat/
│
├── requirements.txt                    # Python dependencies
└── README.md
```

> More retailer folders will be added under `Codes/Markets/`, `Codes/ClothingStores/`, `Codes/ConstructionMarkets/`, and `Codes/HousesRent/` as the project grows.

---

## 🔍 Data Sources

| Source | Type | Method | Categories |
|--------|------|--------|------------|
| [Gurmar](https://www.gurmar.com.tr) | Grocery market | Selenium (headless Chrome) | Fruits & Veg, Meat & Poultry, Dairy, Beverages, Snacks, Baby Products, Cleaning, Personal Care, Home & Living, Books & Stationery, Petshop |
| [Vakko](https://www.vakko.com) | Clothing store | REST API (`api.vakko.com`) | Women's, Men's, Shoes & Bags |
| [Yapimaks](https://www.yapimaks.com) | Construction market / hardware | Python + XML sitemap parsing | Building materials, hardware, tools |
| [Sahibinden](https://www.sahibinden.com) | Houses rent | Async Camoufox-based scraper | Residential rentals in Kayseri, Sivas, Tokat |
| _More coming soon_ | — | — | — |

### CSV Schema (Markets)
```
kategori, product_name, product_price
```
Each file is named `<source>_prices_YYYY-MM-DD.csv` and contains a full snapshot of available products and their prices on that date.

### CSV Schema (Construction Markets — Yapimaks)
```
kategori, product_name, product_price
```
Files are saved to `Datas/yapimaks/` and track construction material and hardware prices.

### CSV Schema (Houses Rent — Sahibinden)
Housing rental data tracks different metrics from product prices:
```
city, district, title, price, rooms, area, listing_date, url
```
Files are saved to `Datas/HousesRent/<City>/` and contain daily snapshots of rental listings per city.

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Google Chrome + [ChromeDriver](https://chromedriver.chromium.org/) (for Gurmar scraper)

### 1. Clone the repository
```bash
git clone https://github.com/vinnipukh/inflationstudymirror.git
cd inflationstudymirror
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

> **Note:** The Vakko scraper additionally requires `pandas` and `selenium`:
> ```bash
> pip install pandas selenium
> ```

### 3. Configure environment variables (Vakko only)
The Vakko scraper uses session credentials stored in a `.env` file. Create one in `Codes/ClothingStores/Vakko/`:

```env
VAKKO_COOKIE=<your_session_cookie>
VAKKO_USER_AGENT=<your_user_agent_string>
```

> ⚠️ Never commit your `.env` file. It is in `.gitignore`.

---

## 🚀 Running the Scrapers

### Gurmar (Grocery Market)
```bash
cd Codes/Markets/Gurmar
python gurmar_scraper.py
```
Outputs a CSV to `Datas/Markets/Gurmar/gurmar_prices_<today>.csv`.

### Vakko (Clothing Store)

**Step 1 – (Optional) Refresh category list:**
```bash
cd Codes/ClothingStores/Vakko
python categoryfinder.py
```

**Step 2 – Run the master scraper:**
```bash
python vakko_master_scraper.py
```
Outputs a CSV to `Datas/ClothingStores/Vakko/vakko_<today>.csv`.

### Sahibinden — KayseriSivasTokat (Houses Rent)
This scraper uses an async Camoufox-based approach and is **manual-run only**. Sahibinden may require login / extra verification when accessed from IPs outside Turkey, so GitHub Actions runners (typically outside Turkey) are not suitable for running it on a daily schedule.

```bash
cd Codes/HousesRent/KayseriSivasTokat
python main.py
```
Outputs rental listing CSVs to `Datas/HousesRent/<City>/`.

### Yapimaks (Construction Market)
```bash
cd Codes/ConstructionMarkets/yapimaks
python scraper.py
```
Outputs a CSV to `Datas/yapimaks/`.

---

## 📦 Dependencies

Install all at once:
```bash
pip install -r requirements.txt
```

---

## 🤖 Automation (GitHub Actions)

This repository includes scheduled GitHub Actions workflows that run scrapers and commit new daily snapshots to `Datas/`:

- `/.github/workflows/gurmar.yml` — runs the Gurmar market scraper and commits new `Datas/Markets/Gurmar/*.csv`
- `/.github/workflows/vakko_scraper.yml` — runs the Vakko scraper using GitHub Actions secrets and commits new `Datas/ClothingStores/Vakko/*.csv`

---

## 📈 Analysis Goals

- Track day-over-day and week-over-week price changes per product
- Identify categories with the highest inflation rate
- Compare price volatility between food and clothing sectors
- Visualize trends over the data collection period
- **Inflation Calculator** — a tool to compute personal inflation rates based on a custom basket of goods *(in development)*

---

## 🎓 Academic Context

| Field | Detail |
|-------|--------|
| University | Özyeğin University |
| Course | AI 201 |
| Term | Spring 2026 |
| Topic | Real-world inflation monitoring using automated data collection and AI-driven analysis |

---

## ⚠️ Disclaimer

This project is for **academic and educational purposes only**. All scrapers are rate-limited and respect website structure. Credentials (cookies, user-agent strings) are stored locally via `.env` and are never committed to the repository.
