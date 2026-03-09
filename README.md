# 📊 Inflation Study — AI 201 Project
**Özyeğin University · AI 201 · Spring 2026**

> An automated data-collection and analysis pipeline that tracks real-time product prices from Turkish retailers to study inflation patterns across grocery markets and clothing stores.

---

## 📌 Project Overview

This project builds a web-scraping infrastructure to collect daily price data from online Turkish retailers, with the goal of:

- Monitoring **price changes over time** across product categories
- Comparing inflation trends between **grocery markets** (e.g. Gurmar) and **clothing stores** (e.g. Vakko)
- Creating a structured, date-stamped dataset suitable for downstream AI/ML analysis and an **inflation calculator** (coming soon)

The scrapers run automatically (via GitHub Actions) and append new daily snapshots to the `Datas/` directory.

> ⚠️ **This is an active project.** More retailers (markets and clothing stores) will be added over time.

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
├── Codes/                        # All scraping & processing scripts
│   ├── Markets/
│   │   └── Gurmar/
│   │       └── gurmar_scraper.py      # Selenium-based scraper for gurmar.com.tr
│   └── ClothingStores/
│       └── Vakko/
│           ├── vakko_master_scraper.py  # API-based scraper for vakko.com
│           ├── categoryfinder.py        # Extracts category IDs from sitemap XML
│           └── vakko_categories.xml     # Vakko sitemap (category URLs)
│
├── Datas/                        # Collected price data (CSV, date-stamped)
│   └── Markets/
│       └── Gurmar/
│           ├── gurmar_prices_YYYY-MM-DD.csv
│           └── ...
│
├── requirements.txt              # Python dependencies
└── README.md
```

> More retailer folders will be added under `Codes/Markets/` and `Codes/ClothingStores/` as the project grows.

---

## 🔍 Data Sources

| Source | Type | Method | Categories |
|--------|------|--------|------------|
| [Gurmar](https://www.gurmar.com.tr) | Grocery market | Selenium (headless Chrome) | Fruits & Veg, Meat & Poultry, Dairy, Beverages, Snacks, Baby Products, Cleaning, Personal Care, Home & Living, Books & Stationery, Petshop |
| [Vakko](https://www.vakko.com) | Clothing store | REST API (`api.vakko.com`) | Women's, Men's, Shoes & Bags |
| _More coming soon_ | — | — | — |

### CSV Schema (Markets)
```
kategori, product_name, product_price
```
Each file is named `<source>_prices_YYYY-MM-DD.csv` and contains a full snapshot of available products and their prices on that date.

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

> ⚠️ Never commit your `.env` file. It is already in `.gitignore`. 

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
Outputs a CSV to `Datas/ClothingStores/Vakko/vakko_prices_<today>.csv`.

---

## 📦 Dependencies

```
certifi==2026.1.4
charset-normalizer==3.4.4
idna==3.11
packaging==26.0
python-dotenv==1.2.1
requests==2.32.3
urllib3==2.6.3
wheel==0.46.3
```

Install all at once:
```bash
pip install -r requirements.txt
```

---

## 🤖 Automation (GitHub Actions)

The repository includes a GitHub Actions workflow (`.github/`) that runs the scrapers on a scheduled basis and automatically commits new daily price snapshots to the `Datas/` directory.

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
