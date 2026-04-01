"""
MF Stock Matcher Optimization Engine.

Finds mutual funds that maximize exposure to user-selected stocks.
Supports single-fund matching and multi-fund bundle optimization.
"""

from itertools import combinations


def score_fund(fund, selected_symbols):
    """
    Score a mutual fund based on how well it matches the selected stocks.

    Returns a dict with:
      - matched_stocks: list of matched holdings with weights
      - matched_count: number of selected stocks found in fund
      - total_exposure: sum of weights of matched stocks
      - coverage: fraction of selected stocks covered (0 to 1)
    """
    selected_set = set(selected_symbols)
    matched = []
    for h in fund["holdings"]:
        if h["symbol"] in selected_set:
            matched.append({"symbol": h["symbol"], "weight": h["weight"]})
    total_exposure = sum(m["weight"] for m in matched)
    coverage = len(matched) / len(selected_symbols) if selected_symbols else 0
    return {
        "scheme_name": fund["scheme_name"],
        "category": fund["category"],
        "amc": fund["amc"],
        "aum_cr": fund.get("aum_cr", 0),
        "matched_stocks": matched,
        "matched_count": len(matched),
        "total_stocks": len(selected_symbols),
        "total_exposure": round(total_exposure, 2),
        "coverage": round(coverage * 100, 1),
        "all_holdings": fund["holdings"],
    }


def find_best_single_funds(funds, selected_symbols, top_n=20):
    """
    Find the best individual mutual funds that maximize exposure
    to the selected stocks. Sorted by coverage first, then by total exposure.
    """
    if not selected_symbols:
        return []

    scored = []
    for fund in funds:
        result = score_fund(fund, selected_symbols)
        if result["matched_count"] > 0:
            scored.append(result)

    # Sort by: matched_count DESC, total_exposure DESC
    scored.sort(key=lambda x: (x["matched_count"], x["total_exposure"]), reverse=True)
    return scored[:top_n]


def _balanced_alloc(combo, stocks):
    """
    Find allocation weights α (summing to 1) that maximise the minimum
    per-stock effective exposure:  max_α  min_s  Σᵢ αᵢ · wᵢₛ

    Uses the Frank–Wolfe projected subgradient method.
    At each step it shifts weight toward whichever fund best covers the
    currently weakest stock — naturally equalising exposure across stocks.
    100 iterations is more than enough for ≤5 funds and ≤30 stocks.
    """
    k = len(combo)
    if k == 1:
        return [1.0]

    # W[fi][si] = weight of stocks[si] in fund fi
    W = [[fd["weights"].get(s, 0.0) for s in stocks] for fd in combo]
    # Only optimise over stocks at least one fund covers
    coverable = [any(W[fi][si] > 0 for fi in range(k)) for si in range(len(stocks))]

    alpha = [1.0 / k] * k

    for t in range(1, 101):
        eff = [sum(alpha[fi] * W[fi][si] for fi in range(k)) for si in range(len(stocks))]

        # Weakest coverable stock
        min_si, min_eff = -1, float("inf")
        for si, e in enumerate(eff):
            if coverable[si] and e < min_eff:
                min_eff = e
                min_si = si
        if min_si < 0:
            break

        # FW oracle: move toward fund with highest weight in weakest stock
        best_fi = max(range(k), key=lambda fi: W[fi][min_si])

        gamma = 2.0 / (t + 2)
        alpha = [
            a * (1 - gamma) + (gamma if i == best_fi else 0)
            for i, a in enumerate(alpha)
        ]

    return alpha


def _eff_per_stock(combo, alpha, selected_set):
    """Effective per-stock exposure: Σᵢ αᵢ · wᵢₛ for each stock s."""
    return {
        sym: sum(alpha[i] * combo[i]["weights"].get(sym, 0.0) for i in range(len(combo)))
        for sym in selected_set
    }


def find_optimal_bundles(funds, selected_symbols, max_bundle_size=None):
    """
    Find optimal bundles via exhaustive enumeration on pre-filtered candidates.

    Effective exposure per stock = Σᵢ αᵢ · wᵢₛ  (allocation-weighted, NOT a raw sum).
    For a k-fund equal split αᵢ = 1/k, so effective = raw_sum / k.
    For the Balanced strategy the optimal αᵢ are found via Frank–Wolfe so that
    the weakest stock's exposure is maximised.

    Strategies:
      1. Balanced Exposure – maximise the weakest stock's effective exposure
         (uses optimal allocation, not necessarily equal split).
      2. Maximum Exposure  – maximise total effective exposure (equal split).
      3. Most Compact      – fewest funds, then balanced scoring (equal split).
    """
    if not selected_symbols:
        return []

    selected_set = set(selected_symbols)
    n_stocks = len(selected_set)
    if max_bundle_size is None:
        max_bundle_size = min(n_stocks, 5)

    # Pre-compute per-fund coverage and exposure for selected stocks
    fund_data = []
    for i, fund in enumerate(funds):
        holdings_map = {h["symbol"]: h["weight"] for h in fund["holdings"]}
        covered = selected_set & set(holdings_map.keys())
        if covered:
            fund_data.append({
                "index": i,
                "fund": fund,
                "covered": covered,
                "covered_count": len(covered),
                "weights": {s: holdings_map[s] for s in covered},
                "total_exposure": sum(holdings_map[s] for s in covered),
            })

    if not fund_data:
        return []

    # ── Three independent candidate rankings ──
    by_coverage = sorted(
        fund_data,
        key=lambda x: (x["covered_count"], x["total_exposure"]),
        reverse=True,
    )
    by_exposure = sorted(
        fund_data,
        key=lambda x: (x["total_exposure"], x["covered_count"]),
        reverse=True,
    )

    # Per-stock best: for each selected stock, include top-10 funds by weight
    per_stock_top = []
    _ps_seen = set()
    for sym in selected_set:
        best_for = sorted(
            (fd for fd in fund_data if sym in fd["covered"]),
            key=lambda fd: fd["weights"][sym],
            reverse=True,
        )
        for fd in best_for[:10]:
            if fd["index"] not in _ps_seen:
                _ps_seen.add(fd["index"])
                per_stock_top.append(fd)

    # Tighter pool limits keep enumeration fast without losing quality.
    # Per-stock specialists are capped at 5 per stock (not 10) so the merged
    # pool stays small even when many stocks are selected.
    SIZE_LIMITS = {1: len(fund_data), 2: 60, 3: 25, 4: 15, 5: 10}
    PER_STOCK_SPECIALISTS = 4

    stocks_list = sorted(selected_set)

    # Rebuild per_stock_top with the tighter cap
    per_stock_top = []
    _ps_seen2 = set()
    for sym in selected_set:
        best_for = sorted(
            (fd for fd in fund_data if sym in fd["covered"]),
            key=lambda fd: fd["weights"][sym],
            reverse=True,
        )
        for fd in best_for[:PER_STOCK_SPECIALISTS]:
            if fd["index"] not in _ps_seen2:
                _ps_seen2.add(fd["index"])
                per_stock_top.append(fd)

    # Trackers: (sort_key, combo, covered_set, raw_per_stock)
    # NOTE: Frank-Wolfe (balanced alloc) is NOT run inside the loop —
    # we use equal-allocation scoring for fast comparison across all combos,
    # then run FW exactly once on each strategy winner at the end.
    # This cuts runtime from O(C(n,k) × FW_iters) down to O(C(n,k) + 3 × FW_iters).
    best_balanced = None
    best_exp = None
    best_compact = None

    for size in range(1, max_bundle_size + 1):
        lim = SIZE_LIMITS.get(size, 15)

        # Merge three pools, deduplicate
        seen_idx = set()
        merged = []
        for fd in by_coverage[:lim] + by_exposure[:lim] + per_stock_top:
            if fd["index"] not in seen_idx:
                seen_idx.add(fd["index"])
                merged.append(fd)

        # Pre-compute per-fund coverage bitmask for fast union-coverage estimation.
        # A combo's max possible coverage = union of individual covered sets.
        # Upper-bound shortcut: if the sum of individual covered_counts is less
        # than the best coverage seen so far, the combo can't possibly win on the
        # first (most important) scoring dimension — skip it immediately.
        best_cov_so_far = max(
            (best_balanced[0][0] if best_balanced else 0),
            (best_exp[0][0]      if best_exp      else 0),
            (best_compact[0][0]  if best_compact  else 0),
        )

        for combo in combinations(merged, size):
            # Fast upper-bound check: skip if no chance of beating best coverage
            if size > 1:
                upper = min(sum(fd["covered_count"] for fd in combo), n_stocks)
                if upper < best_cov_so_far:
                    continue

            # Raw per-stock: sum of weights across all funds in combo
            raw = {}
            covered = set()
            for fd in combo:
                covered |= fd["covered"]
                for sym, w in fd["weights"].items():
                    raw[sym] = raw.get(sym, 0) + w

            cov_count = len(covered)

            # Update best coverage seen (used by the upper-bound check next iteration)
            if cov_count > best_cov_so_far:
                best_cov_so_far = cov_count

            # Equal-allocation effective exposure (fast, used for all comparisons)
            eq_vals = [raw.get(s, 0) / size for s in selected_set]
            eq_min = min(eq_vals) if eq_vals else 0
            eq_total = sum(eq_vals)

            # All three strategies scored with equal allocation (O(n) per combo)
            k_bal = (cov_count, eq_min, eq_total, -size)
            if best_balanced is None or k_bal > best_balanced[0]:
                best_balanced = (k_bal, combo, covered, raw)

            k_exp = (cov_count, eq_total, -size)
            if best_exp is None or k_exp > best_exp[0]:
                best_exp = (k_exp, combo, covered, raw)

            k_comp = (cov_count, -size, eq_min, eq_total)
            if best_compact is None or k_comp > best_compact[0]:
                best_compact = (k_comp, combo, covered, raw)

    # ── Run Frank-Wolfe exactly once per strategy winner ──────────────────────
    # For Balanced: find the optimal (non-equal) allocation that maximises the
    # minimum per-stock exposure. This is the expensive step, but now it only
    # runs 3 times regardless of how many combos were enumerated.
    def _finalise(entry, strategy):
        if entry is None:
            return None
        _, combo, covered, raw = entry
        if strategy == "balanced":
            alpha = _balanced_alloc(combo, stocks_list)
        else:
            k = len(combo)
            alpha = [1.0 / k] * k
        return (entry[0], combo, covered, raw, alpha)

    best_balanced = _finalise(best_balanced, "balanced")
    best_exp      = _finalise(best_exp,      "equal")
    best_compact  = _finalise(best_compact,  "equal")

    # ── Assemble results, skip duplicates ──
    bundles = []
    seen_names = set()

    candidates = [
        ("Balanced Exposure",
         "Optimises allocation across funds to maximise the weakest stock\u2019s exposure \u2014 no weak links",
         best_balanced),
        ("Maximum Exposure",
         "Maximises total effective exposure across all your stocks (equal split)",
         best_exp),
    ]

    # Only show Most Compact if it uses fewer funds than the others or is different
    if best_compact is not None:
        compact_size = len(best_compact[1])
        other_sizes = set()
        if best_balanced:
            other_sizes.add(len(best_balanced[1]))
        if best_exp:
            other_sizes.add(len(best_exp[1]))
        if compact_size < max(other_sizes, default=compact_size + 1) or \
           frozenset(fd["fund"]["scheme_name"] for fd in best_compact[1]) not in {
               frozenset(fd["fund"]["scheme_name"] for fd in best_balanced[1]) if best_balanced else frozenset(),
               frozenset(fd["fund"]["scheme_name"] for fd in best_exp[1]) if best_exp else frozenset(),
           }:
            n_funds = len(best_compact[1])
            desc = (
                "Single fund with highest balanced exposure"
                if n_funds == 1
                else f"Best {n_funds}-fund combination with balanced exposure"
            )
            candidates.append(("Most Compact", desc, best_compact))

    for label, desc, result in candidates:
        if result is None:
            continue
        _, combo, covered, raw, alpha = result
        names = frozenset(fd["fund"]["scheme_name"] for fd in combo)
        if names in seen_names:
            continue
        seen_names.add(names)

        # Drop funds whose allocation is negligible (< 2%) — these are
        # optimisation artefacts where Frank-Wolfe assigned ~0 weight.
        # Re-normalise the remaining funds so allocations still sum to 100%.
        ALLOC_THRESHOLD = 0.02
        active = [(fd, a) for fd, a in zip(combo, alpha) if a >= ALLOC_THRESHOLD]
        if not active:
            active = list(zip(combo, alpha))  # fallback: keep all
        active_fds, active_alpha = zip(*active)
        alpha_sum = sum(active_alpha)
        active_alpha = [a / alpha_sum for a in active_alpha]

        # Effective per-stock exposure under the trimmed allocation
        eff = _eff_per_stock(active_fds, active_alpha, selected_set)
        eff_vals = [eff.get(s, 0) for s in selected_set]
        total_exp = round(sum(eff_vals), 2)
        min_exp = round(min(eff_vals), 2) if eff_vals else 0

        per_stock_list = [
            {
                "symbol": sym,
                # Effective: what % of your bundle portfolio goes into this stock
                # For a 2-fund equal split this is (w₁ + w₂) / 2, NOT w₁ + w₂
                "exposure": round(eff.get(sym, 0), 2),
            }
            for sym in sorted(selected_set)
        ]

        allocation_pct = [round(a * 100, 1) for a in active_alpha]

        bundle_funds = []
        for i, fd in enumerate(active_fds):
            fund_score = score_fund(fd["fund"], list(selected_set))
            fund_score["allocation_pct"] = allocation_pct[i]
            bundle_funds.append(fund_score)

        # Recompute covered/missing from the active (trimmed) funds only
        active_covered = set()
        for fd in active_fds:
            active_covered |= fd["covered"]

        bundles.append({
            "strategy": label,
            "description": desc,
            "funds": bundle_funds,
            "allocation": [
                {"scheme_name": fd["fund"]["scheme_name"], "allocation_pct": allocation_pct[i]}
                for i, fd in enumerate(active_fds)
            ],
            "total_coverage": round(len(active_covered) / n_stocks * 100, 1),
            "total_exposure": total_exp,
            "min_stock_exposure": min_exp,
            "per_stock_exposure": per_stock_list,
            "stocks_covered": sorted(active_covered),
            "stocks_missing": sorted(selected_set - active_covered),
            "bundle_size": len(active_fds),
        })

    return bundles
