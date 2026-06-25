"""
Master pipeline refresh: updates all three themes and returns combined shock vectors.

Themes:
  1 — Commodity price shocks (World Bank Pink Sheet + FRED)
  2 — WEO growth revision shocks (IMF DataMapper)
  3 — Domestic demand shocks (BI SPE)

Each theme module:
  - Checks for new data and downloads if available
  - Falls back to cached data if the source is unreachable
  - Returns shocks in their respective units (pp deviation from baseline)

Usage:
  python -m pipeline.refresh              # update + print summary
  from pipeline.refresh import run        # programmatic use
"""
import sys, os, json, traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.ingestion.theme1_commodity import refresh as refresh_t1
from pipeline.ingestion.theme2_partner   import refresh as refresh_t2
from pipeline.ingestion.theme3_domestic  import refresh as refresh_t3

CACHE     = os.path.join(os.path.dirname(__file__), "..", "data", "cache")
STATE_JSON = os.path.join(CACHE, "last_refresh.json")


def run(verbose=True):
    """
    Run all three theme refreshes and return a combined results dict.

    Returns:
      {
        "refreshed_at": ISO timestamp,
        "theme1": {"x_j": {...}, "period": "YYYYMNN"},
        "theme2": {"x_k": Series, "d_g": {...}, "vintages": {...}, "fcast_year": int},
        "theme3": {"x_i": {...}, "period": "YYYY-MM"},
        "errors": {"theme1": None | str, ...}
      }
    """
    def log(msg):
        if verbose: print(msg)

    SEP = "=" * 65
    log(SEP)
    log(f"empdash pipeline refresh  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(SEP)

    results = {"refreshed_at": datetime.now(timezone.utc).isoformat(), "errors": {}}

    # ── Theme 1: commodity prices ─────────────────────────────────────────────
    log(f"\n[1/3] Theme 1: commodity prices")
    try:
        results["theme1"] = refresh_t1(verbose=verbose)
        results["errors"]["theme1"] = None
    except Exception as e:
        log(f"  ERROR in Theme 1: {e}")
        results["theme1"]            = None
        results["errors"]["theme1"]  = traceback.format_exc()

    # ── Theme 2: WEO revision ─────────────────────────────────────────────────
    log(f"\n[2/3] Theme 2: WEO growth revision")
    try:
        results["theme2"] = refresh_t2(verbose=verbose)
        results["errors"]["theme2"] = None
    except Exception as e:
        log(f"  ERROR in Theme 2: {e}")
        results["theme2"]            = None
        results["errors"]["theme2"]  = traceback.format_exc()

    # ── Theme 3: BI SPE ───────────────────────────────────────────────────────
    log(f"\n[3/3] Theme 3: BI SPE domestic demand")
    try:
        results["theme3"] = refresh_t3(verbose=verbose)
        results["errors"]["theme3"] = None
    except Exception as e:
        log(f"  ERROR in Theme 3: {e}")
        results["theme3"]            = None
        results["errors"]["theme3"]  = traceback.format_exc()

    # ── Summary ───────────────────────────────────────────────────────────────
    log(f"\n{SEP}")
    log("SHOCK SUMMARY")
    log(SEP)

    t1 = results.get("theme1")
    if t1:
        log(f"\n  Theme 1  x_j  commodity prices  [{t1['period']}]")
        for k, v in sorted(t1["x_j"].items()):
            log(f"    {k:<16}  {v:+.2f} pp")

    t2 = results.get("theme2")
    if t2 and t2.get("x_k") is not None:
        xk = t2["x_k"]
        vinfo = t2.get("vintages", {})
        log(f"\n  Theme 2  x_k  WEO revision  "
            f"[{vinfo.get('current','?')} − {vinfo.get('prior','?')}]")
        for idx, val in xk.sort_values().items():
            name = idx[1] if isinstance(idx, tuple) else str(idx)
            log(f"    {name:<20}  {val:+.4f} pp")

    t3 = results.get("theme3")
    if t3:
        log(f"\n  Theme 3  x_i  BI SPE domestic  [{t3['period']}]")
        for k, v in sorted(t3["x_i"].items()):
            log(f"    {k:<28}  {v:+.2f} pp")

    log(f"\n{SEP}")
    errors = {k: v for k, v in results["errors"].items() if v}
    if errors:
        log(f"  Errors: {list(errors.keys())}")
    else:
        log("  All themes OK.")
    log(SEP)

    # Persist lightweight state (no pandas objects)
    state = {
        "refreshed_at": results["refreshed_at"],
        "theme1_period": t1["period"] if t1 else None,
        "theme2_vintages": t2.get("vintages") if t2 else None,
        "theme3_period": t3["period"] if t3 else None,
        "errors": {k: bool(v) for k, v in results["errors"].items()},
    }
    os.makedirs(CACHE, exist_ok=True)
    with open(STATE_JSON, "w") as f:
        json.dump(state, f, indent=2)

    return results


if __name__ == "__main__":
    run(verbose=True)
