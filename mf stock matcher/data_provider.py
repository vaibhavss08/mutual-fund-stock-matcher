"""Data provider backed by the shared SQLite database."""

import os
import sqlite3
import sys


APP_DIR = os.path.dirname(__file__)
WORKSPACE_ROOT = os.path.abspath(os.path.join(APP_DIR, ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from common.shared_paths import DB_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def search_stocks(query):
    if not query or len(query) < 1:
        return []
    q = query.strip().upper()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol, name, sector, market_cap FROM stocks WHERE UPPER(symbol) = ?", (q,))
    exact = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT symbol, name, sector, market_cap FROM stocks WHERE UPPER(symbol) LIKE ? AND UPPER(symbol) != ? ORDER BY LENGTH(symbol), symbol LIMIT 20",
        (q + "%", q),
    )
    starts_sym = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT symbol, name, sector, market_cap FROM stocks WHERE UPPER(name) LIKE ? ORDER BY LENGTH(symbol), symbol LIMIT 20",
        ("%" + q + "%",),
    )
    contains_name = [dict(r) for r in cur.fetchall()]
    conn.close()
    seen = set()
    results = []
    for row in exact + starts_sym + contains_name:
        if row["symbol"] not in seen:
            seen.add(row["symbol"])
            results.append(row)
        if len(results) >= 15:
            break
    return results


def get_all_stocks():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol, name, sector, market_cap FROM stocks ORDER BY symbol")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_stock_sectors():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT sector FROM stocks ORDER BY sector")
    sectors = [r[0] for r in cur.fetchall()]
    conn.close()
    return sectors


def get_all_mutual_funds():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, scheme_name, category, amc, aum_cr, risk_level FROM mutual_funds ORDER BY scheme_name")
    funds = []
    for row in cur.fetchall():
        fund = dict(row)
        cur.execute("SELECT symbol, weight FROM holdings WHERE fund_id = ? ORDER BY weight DESC", (fund["id"],))
        fund["holdings"] = [{"symbol": h["symbol"], "weight": h["weight"]} for h in cur.fetchall()]
        funds.append(fund)
    conn.close()
    return funds


def get_fund_categories():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM mutual_funds ORDER BY category")
    cats = [r[0] for r in cur.fetchall()]
    conn.close()
    return cats


def get_fund_amcs():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT amc FROM mutual_funds ORDER BY amc")
    amcs = [r[0] for r in cur.fetchall()]
    conn.close()
    return amcs
