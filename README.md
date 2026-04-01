# MF Stock Matcher

Find mutual funds that maximise exposure to your selected stocks.

See [`mf stock matcher/README.md`](mf%20stock%20matcher/README.md) for full documentation.

## Quick Start (local)

```bash
cd "mf stock matcher"
pip install -r requirements.txt
python3 app.py
# Open http://127.0.0.1:5000
```

## Deploy to Render

One-click deployment via `render.yaml`. The service reads data from `shared-data/` at:
- `mf_matcher.db` — SQLite holdings database
- `real_data.json` — scheme catalog
- `real_holdings.json` — imported fund holdings
# mutual-fund-stock-matcher
