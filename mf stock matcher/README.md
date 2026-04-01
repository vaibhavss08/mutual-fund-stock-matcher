# MF Stock Matcher

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Flask](https://img.shields.io/badge/Flask-3.1-green) ![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey)

**Find mutual funds that maximise exposure to your selected stocks.**

Select any combination of NSE stocks and the app returns ranked individual funds plus optimised multi-fund bundles across three strategies — with per-stock effective exposure and allocation splits shown for every result.

> Screenshot: *(add a screenshot of the dashboard here)*

---

## Quick Start

```bash
pip install -r requirements.txt
python3 app.py
# Open http://127.0.0.1:5000
```

To rebuild the shared database, see [`../scripts/data-pipeline/REFRESH_GUIDE.md`](../scripts/data-pipeline/REFRESH_GUIDE.md).

---

## Features

- **Stock search with autocomplete** — 926 NSE-listed stocks spanning Nifty 50, Next 50, Midcap 150, Smallcap 250, and the broader market.
- **Three optimised bundle strategies** — Balanced Exposure, Maximum Exposure, and Most Compact, each with distinct scoring tuples and meaningful deduplication.
- **Per-stock effective exposure** — allocation-weighted exposure, not a raw sum. When two funds each hold a stock, the displayed figure reflects exactly how much of your split capital reaches that stock.
- **Allocation split per fund** — e.g. `TATA 31.5% / DSP 68.5%`, showing how the optimizer divides capital across funds in a bundle.
- **Stock overlap matrix** — cross-fund comparison of which top funds share which selected stocks.
- **Category filter and max-funds slider** — narrow results to a specific category or cap the bundle size.

---

## How It Works

### Scoring a Single Fund

For each candidate fund the optimizer computes:

- **Coverage** — `matched stocks / selected stocks` as a percentage.
- **Exposure** — sum of the portfolio weights of all matched stocks.

Funds are ranked by coverage first, then exposure.

### Bundle Optimization

The optimizer finds the best combination of funds to cover all selected stocks. Bundle size scales with the number of selected stocks (`min(n_stocks, 5)`).

1. Pre-filter to funds holding at least one selected stock.
2. Build a merged candidate pool from three sources: top funds by coverage, top funds by total exposure, and per-stock specialists (top funds per individual stock by weight).
3. Exhaustively enumerate all combinations for bundle sizes 1 through max.
4. Score each combination by per-stock exposure sums.
5. Frank-Wolfe optimal allocation runs once per winning bundle, not per combination — keeping enumeration tractable.

For full algorithmic detail, see [`LOGIC.md`](LOGIC.md) *(if present)*.

### Three Strategies

| Strategy | Goal | Sort key |
|----------|------|----------|
| **Balanced Exposure** | No weak links — maximise the lowest single-stock exposure | coverage → min-stock-exposure → total-exposure → fewest funds |
| **Maximum Exposure** | Maximum aggregate weight across all stocks | coverage → total-exposure → fewest funds |
| **Most Compact** | Best coverage with the fewest funds | coverage → fewest funds → min-stock-exposure → total-exposure |

Notes:
- For a single stock, **Most Compact** returns the fund with the highest weight in that stock.
- **Most Compact** is only surfaced when it produces a genuinely different bundle from the other two strategies.
- Duplicate bundles (identical fund sets) are deduplicated across strategies.

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/meta` | Categories, AMCs, sectors, record counts |
| `GET` | `/api/stocks/search?q=rel` | Autocomplete stock search |
| `GET` | `/api/stocks/all` | Full stock list |
| `POST` | `/api/search` | `{"stocks": ["RELIANCE", "TCS"]}` → singles + bundles + overlap matrix |

---

## Data Sources

| Data | Source |
|------|--------|
| Holdings (primary) | Rupeevest — `/home/get_search_data` + `/home/get_mf_portfolio_tracker` |
| Holdings (fallback) | Adityaraj Capital — `/mutual-funds-research/autoSuggestAllMfSchemes` + `/mutual-funds-research/getPortfolioAnalysis` |
| Holdings (optional) | Local CSV/TSV/JSON in `../scripts/data-pipeline/portfolio_disclosures/` |
| Scheme catalog | All scheme names + AMFI codes from mfapi.in |
| Stocks | 926 NSE stocks — symbol, name, sector, market cap tier |

Holdings for every fund included in `mf_matcher.db` are stored in full — the database does not trim any fund to its top 10 holdings.

---

## Project Structure

| File | Purpose |
|------|---------|
| `app.py` | Flask routes and API handlers |
| `optimizer.py` | Bundle optimization engine (scoring, enumeration, FW allocation) |
| `data_provider.py` | SQLite data access layer |
| `templates/index.html` | Single-page frontend |
| `../shared-data/mf_matcher.db` | Shared SQLite database (read-only) |
| `../shared-data/real_data.json` | Fetched scheme catalog (read-only) |
| `../scripts/data-pipeline/` | Pipeline that generates all shared data |

---

## Tech Stack

Python 3.10+ / Flask 3.1 / SQLite 3 / Vanilla JS frontend
