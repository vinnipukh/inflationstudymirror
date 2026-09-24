# Price Forecasting Literature — What Products Were Studied & What It Means for Your Scrape

> Compiled 2026-09-05. Sources: Google Scholar (live, stealth browser), OpenAlex API
> (WoS-indexed metadata), arXiv, Exa. Web of Science directly = institutional login wall
> (Clarivate redirect); OpenAlex used as the WoS-compatible index instead.
> Raw captures: scholar-*.txt in this folder.

## 1. TL;DR for your platform
- Academic work exists for: macro inflation from online prices (Billion Prices Project),
  electricity, used cars, food/agriculture, oil/crypto/stock, housing, and a THIN
  slice of generic e-commerce retail products.
- **Product-level daily price forecasting for consumer electronics/appliances is a nearly
  empty niche** ("retail price forecasting" ~= 17 works on OpenAlex). Your 3-year daily
  history from epey + akakce is exactly the dataset the literature lacks (publication +
  product potential).
- Top-cited works prove the method: daily scraped retail prices -> inflation nowcast
  (BPP 2016, Powell 2018, Szafranek 2025 with 250M prices). Same pipeline, product level.

## 2. What products were studied (the map)

### A. Online retail prices -> INFLATION (macro) - your strongest anchor
| Paper | Year | cits | Product/data |
|---|---|---|---|
| The Billion Prices Project (Cavallo & Rigobon, JEP) | 2016 | 562 | ALL retail goods; 5M prices/day, 300+ retailers, 50 countries -> daily price indexes co-moving with CPI, price stickiness |
| Are online and offline prices similar? (Cavallo, AER) | 2017 | 628 | 56 multi-channel retailers, 10 countries |
| Price setting in online markets (Gorodnichenko & Talavera, AER) | 2017 | 276 | ~400 online retailers, cross-country price-change facts |
| Scraped data and sticky prices (Cavallo, REStat) | 2018 | 342 | BPP scraped data -> sticky-price statistics |
| Tracking & modelling prices using web-scraped price microdata -> automated daily CPI forecasting (Powell et al., JRSS-A) | 2018 | 31 | UK web-scraped price microdata -> daily CPI forecasts |
| Food inflation nowcasting with web scraped data (Macias & Stelmasiak, NBP) | 2019 | 20 | Groceries, Poland |
| Measuring food inflation in real time online (Jaworski, BFJ) | 2021 | 42 | Groceries, Poland (COVID) |
| Nowcasting food inflation with a massive amount of online prices (Macias/Stelmasiak/Szafranek) | 2022 | 43 | 250M web-scraped prices |
| **Nowcasting Turkish Food Inflation Using Daily Online Prices (Soybilgen, Yazgan, Kaya)** | 2023 | 4 | TURKEY, daily online prices - closest Turkish precedent |
| Improving disaggregated short-term food inflation forecasts with webscraped data (Beer, Ferstl, Graf) | 2025 | - | Disaggregated food, Austria |

### B. Electricity - the method-transfer goldmine (daily volatile series)
- Forecasting spot electricity prices: DL approaches vs 27 traditional algorithms (Lago et al., Applied Energy) 2018, c:629 - 4 DL models beat 27 classical on daily spot prices
- Hybrid wavelet + ARMA + KELM (2017); Adam-optimized LSTM + wavelet (2019); MIBEL NAR/NARX/LSTM (2020); day-ahead/intraday/balancing reviews (2025-26); probabilistic forecasting UQ (2025)

### C. Used cars - biggest product-specific body (your araba category)
- Car Price Prediction using ML (ANN+SVM+RF ensemble, scraped web portal autopijaca.ba, Bosnia) 2019, c:137
- Used Cars Price Prediction using Supervised Learning 2019, c:56; PSO-GRA-BP NN 2022; ANN+RF India 2022; ANFIS 2009; RandomForest car-worth 2017; Tesla second-hand 2021; ProbSAINT probabilistic tabular 2024; Malaysia 2024
- Lesson: car pricing = cross-sectional regression (mileage, year, fuel, engine, make/model) - NOT time series; epey cars are specs-only, so car forecasting needs feature models on listing data (akakce) or scraped listings

### D. Food / agriculture
- Onion retail price: ARIMA+ANN hybrid (Purohit et al., 2021, c:118); Squid retail by processing type: ARIMA vs SARIMA vs Holt-Winters 2018; Wholesale food index: NAR NN (Xu & Zhang 2023, c:66); Egypt crops ARIMA/GARCH 2023
- Lesson: strong seasonality; SARIMA + hybrids; per-unit prices (TL/kg) matter - akakce already computes these

### E. E-commerce retail products (closest to YOUR core)
- **ARIMA + Google Trends on Amazon prices (Carta et al. 2018, c:66)** - "Price Probe"; demand signals from search trends improve price forecasts
- A smart system for short-term price prediction using time series models (Nguyen et al. 2019, c:110)
- PriceCop - price monitor & prediction (linear regression, LSVM-ABC) 2021, c:62
- FPD TV market price forecasting with technological variance (ESWA 2010) - product generations matter (TV/phone categories)
- Time Series Event Forecasting in Consumer Electronic Markets using Random Forests 2019
- Markdowns in e-commerce fresh retail: counterfactual prediction (KDD 2021); Fashion e-comm price optimization (arXiv 2020); DL retail pricing from sales forecasting (Soft Computing 2024)

### F. Oil / crypto / stock / housing (methods only)
- DL ensemble crude oil (2017, c:377); text-based oil (2018); financial DL review (2023); RF house mass appraisal (2020); NN house price (2021)

## 3. Data features the literature says matter (checklist for your scrape)
**From epey /kat/fg/ (daily history):** daily lowest price per product; 3-year contiguous windows
**From epey product pages (add to scrapes):** variant family links (cross-product prices); spec fields (Cikis Yili = age/lifecycle, RAM/storage/screen = generation); seller count ("N site, N fiyat" = supply proxy); offer freshness; review count+rating (sentiment); Reklam/sponsored flags (exclude from clean signal)
**From akakce API (richer, easier):** dropRatio %, followCount (alarm count = demand signal), countOfPrices, hasSpotCampaign, colorVariants, rating; quickview/get per-vendor prices+shipping -> price spread/volatility; dlquery deal lists -> promotion events; per-unit prices TL/kg for groceries
**External (from papers):** TCMB inflation & USD/TRY (macro drift); Google Trends for product queries (Carta 2018); calendar events (Black Friday, 11.11, year-end, Ramadan, school season); product release events (iPhone launches -> lifecycle)

## 4. Honest gaps & what they mean
- Nobody publishes product-level daily price datasets for consumer electronics -> your dataset is a publishable contribution
- Cars on epey have NO price history -> feature-based regression on listing data, not time series
- Turkish market is FX-driven (price jumps bigger than EU/US studies) -> external regressors (USD/TRY, TCMB CPI) are required

## 5. Recommended initial modeling stack (from the literature)
1. Baseline: ARIMA (log-price) + SARIMA weekly seasonality
2. ML: LightGBM/RF with lags + external features (seller count, age, FX, trends) - nonlinearity is the game changer (Coulombe)
3. DL: LSTM / NARX per category on daily series (Lago recipe) if scale allows
4. Probabilistic: quantile regression for P10/P90 bands (ProbSAINT-style)
5. Validation: RRMSE + Diebold-Mariano test per category (squid paper)