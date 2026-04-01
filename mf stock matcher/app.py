"""
MF Stock Matcher - Flask Application
Find mutual funds that maximize exposure to your selected stocks.
"""

import json
import logging
import os
import sys
import time

from flask import Flask, render_template, request, jsonify


APP_DIR = os.path.dirname(__file__)
WORKSPACE_ROOT = os.path.abspath(os.path.join(APP_DIR, ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from data_provider import (
    search_stocks, get_all_mutual_funds, get_all_stocks,
    get_fund_categories, get_fund_amcs, get_stock_sectors,
)
from optimizer import find_best_single_funds, find_optimal_bundles
from common.shared_paths import REAL_DATA_PATH, REAL_HOLDINGS_PATH

app = Flask(__name__)

# ── Production config ────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


@app.after_request
def _add_headers(response):
    origin = request.headers.get("Origin", "")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.errorhandler(Exception)
def _handle_error(exc):
    log.exception("Unhandled error")
    return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "stock-matcher", "ts": int(time.time())})


def _load_data_source():
    data_source = {
        "fund_names": "catalog only",
        "fetched_at": None,
        "scheme_count": 0,
        "holdings": {
            "source": "unavailable",
            "as_of": None,
            "fund_count": 0,
        },
    }

    if os.path.exists(REAL_DATA_PATH):
        try:
            with open(REAL_DATA_PATH) as f:
                rd = json.load(f)
            data_source.update({
                "fund_names": "mfapi.in",
                "fetched_at": rd.get("fetched_at"),
                "scheme_count": len(rd.get("schemes", [])),
            })
        except Exception:
            pass

    if os.path.exists(REAL_HOLDINGS_PATH):
        try:
            with open(REAL_HOLDINGS_PATH) as f:
                rh = json.load(f)
            data_source["holdings"] = {
                "source": rh.get("source", "imported disclosures"),
                "as_of": rh.get("as_of") or rh.get("generated_at"),
                "fund_count": len(rh.get("funds", [])),
            }
        except Exception:
            pass
    return data_source


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stocks/search")
def api_stock_search():
    query = request.args.get("q", "").strip()
    if len(query) < 1:
        return jsonify([])
    results = search_stocks(query)
    return jsonify(results)


@app.route("/api/stocks/all")
def api_all_stocks():
    return jsonify(get_all_stocks())


@app.route("/api/meta")
def api_meta():
    """Return metadata for filters: categories, AMCs, sectors, counts."""
    all_funds = get_all_mutual_funds()
    verified_funds = sum(1 for fund in all_funds if fund["holdings"])

    return jsonify({
        "categories": get_fund_categories(),
        "amcs": get_fund_amcs(),
        "sectors": get_stock_sectors(),
        "total_stocks": len(get_all_stocks()),
        "total_funds": len(all_funds),
        "verified_funds": verified_funds,
        "data_source": _load_data_source(),
    })


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    selected_symbols = data.get("stocks", [])
    if not selected_symbols:
        return jsonify({"error": "No stocks selected"}), 400

    selected_symbols = selected_symbols[:30]

    all_funds = [fund for fund in get_all_mutual_funds() if fund["holdings"]]
    if not all_funds:
        return jsonify({
            "selected_stocks": selected_symbols,
            "total_stocks": len(selected_symbols),
            "single_funds": [],
            "has_full_cover": False,
            "bundles": [],
            "total_funds_scanned": 0,
            "overlap_matrix": {},
            "warning": "No verified mutual fund holdings have been imported yet. Add AMC or AMFI disclosure CSV files to ../scripts/data-pipeline/portfolio_disclosures/, run the centralized pipeline there, then rebuild the shared database.",
        })

    # Apply category filter if provided
    category_filter = data.get("category")
    if category_filter:
        funds = [f for f in all_funds if f["category"] == category_filter]
    else:
        funds = all_funds

    single_results = find_best_single_funds(funds, selected_symbols, top_n=30)

    has_full_cover = any(
        r["matched_count"] == len(selected_symbols) for r in single_results
    )

    max_funds = data.get("max_funds")
    if isinstance(max_funds, int) and 1 <= max_funds <= 10:
        bundles = find_optimal_bundles(funds, selected_symbols, max_bundle_size=max_funds)
    else:
        bundles = find_optimal_bundles(funds, selected_symbols)

    # Compute overlap data for top funds
    overlap = _compute_overlap(single_results[:10], selected_symbols)

    return jsonify({
        "selected_stocks": selected_symbols,
        "total_stocks": len(selected_symbols),
        "single_funds": single_results,
        "has_full_cover": has_full_cover,
        "bundles": bundles,
        "total_funds_scanned": len(funds),
        "overlap_matrix": overlap,
    })


def _compute_overlap(top_funds, selected_symbols):
    """Compute which funds share which selected stocks."""
    stock_to_funds = {}
    for s in selected_symbols:
        stock_to_funds[s] = []
        for f in top_funds:
            for m in f["matched_stocks"]:
                if m["symbol"] == s:
                    stock_to_funds[s].append({
                        "fund": f["scheme_name"],
                        "weight": m["weight"],
                    })
                    break
    return stock_to_funds


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
