"""
Theme 2 ingestion: IMF WEO trading-partner growth revision shocks.

SOP:
  - Download current WEO via DataMapper API on each refresh run
  - If the download differs from the latest saved vintage, register it as a new vintage
  - d^g_c = current_vintage[FCAST_YR] - prior_vintage[FCAST_YR]
  - x_k   = Σ_c w_{k,c} * d^g_c   (only for K=23 tradable sectors)

Vintage cadence: WEO releases ~April and ~October each year.
Between releases, d^g_c = 0 (no revision).

Bootstrap (one-time):
  - April 2025 SDMX ZIP → already parsed → weo_v202504.csv
  - April 2026 DataMapper → already saved  → weo_v202604.csv
  - Future releases auto-detected and saved.
"""
import os, json, glob, requests
from datetime import datetime, timezone
import pandas as pd
import numpy as np

CACHE       = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache", "theme2")
VINTAGE_DIR = os.path.join(CACHE, "vintages")
RAWDATA     = os.path.join(os.path.dirname(__file__), "..", "..", "rawdata")
os.makedirs(VINTAGE_DIR, exist_ok=True)

FCAST_YR  = 2026   # near-term forecast year for revision comparison
K_SECTORS = [2,3,6,7,8,9,10,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27]

DATAMAPPER_URL = "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH"


# ─────────────────────────────────────────────────────────────────────────────
def _load_vintages():
    """Return list of vintage metadata dicts, sorted oldest → newest."""
    metas = []
    for mf in glob.glob(os.path.join(VINTAGE_DIR, "*_meta.json")):
        with open(mf) as f:
            metas.append(json.load(f))
    return sorted(metas, key=lambda m: m["vintage_id"])


def _vintage_csv(vintage_id):
    return os.path.join(VINTAGE_DIR, f"weo_v{vintage_id}.csv")


def _fetch_datamapper():
    """Download NGDP_RPCH from IMF DataMapper → long DataFrame (country, year, ngdp_rpch)."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    r = requests.get(DATAMAPPER_URL, headers=headers, timeout=60)
    r.raise_for_status()
    raw = r.json()
    values = raw.get("values", {}).get("NGDP_RPCH", {})
    rows = []
    for iso3, yr_dict in values.items():
        for yr_str, val in yr_dict.items():
            try:
                rows.append({"country": iso3, "year": int(yr_str), "ngdp_rpch": float(val)})
            except (ValueError, TypeError):
                pass
    return pd.DataFrame(rows)


def _is_new_vintage(df_new, latest_meta):
    """Return True if df_new looks like a different WEO release than the latest saved vintage."""
    latest_df = pd.read_csv(_vintage_csv(latest_meta["vintage_id"]))
    # Compare 2026 forecast for a stable set of key countries
    KEY = ["CHN", "USA", "JPN", "IND", "SGP", "MYS", "IDN"]
    curr_vals  = df_new[df_new["year"] == FCAST_YR].set_index("country")["ngdp_rpch"]
    saved_vals = latest_df[latest_df["year"] == FCAST_YR].set_index("country")["ngdp_rpch"]
    common = [c for c in KEY if c in curr_vals.index and c in saved_vals.index]
    if not common:
        return False
    diff = abs(curr_vals[common] - saved_vals[common]).mean()
    return diff > 0.05   # >0.05pp mean change across key countries → new release


def _save_vintage(df, vintage_id, source="IMF DataMapper API"):
    df.to_csv(_vintage_csv(vintage_id), index=False)
    release_year  = int(vintage_id[:4])
    release_month = int(vintage_id[4:])
    with open(os.path.join(VINTAGE_DIR, f"weo_v{vintage_id}_meta.json"), "w") as f:
        json.dump({
            "vintage_id":     vintage_id,
            "label":          f"WEO {'April' if release_month <= 6 else 'October'} {release_year}",
            "release_year":   release_year,
            "release_month":  release_month,
            "source":         source,
            "imported_at":    datetime.now(timezone.utc).isoformat(),
            "rows":           len(df),
            "countries":      int(df["country"].nunique()),
        }, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
def refresh(verbose=True):
    """
    Main entry point. Downloads current WEO, detects new vintages, computes
    d^g_c and x_k. Returns dict with x_k Series and metadata.
    """
    def log(msg):
        if verbose: print(msg)

    # 1. Download current vintage from DataMapper
    log("Theme 2: downloading current WEO from DataMapper...")
    try:
        df_curr = _fetch_datamapper()
        log(f"  {df_curr['country'].nunique()} countries, "
            f"years {df_curr['year'].min()}–{df_curr['year'].max()}")
    except Exception as e:
        log(f"  WARNING: DataMapper download failed ({e}) — using cached vintage")
        df_curr = None

    # 2. Check if this is a new vintage
    vintages = _load_vintages()
    if not vintages:
        log("  No vintages found — this should not happen after bootstrap.")
        return None

    latest = vintages[-1]
    if df_curr is not None and _is_new_vintage(df_curr, latest):
        now = datetime.now(timezone.utc)
        new_id = f"{now.year}{now.month:02d}"
        log(f"  New WEO vintage detected — saving as {new_id}")
        _save_vintage(df_curr, new_id)
        vintages = _load_vintages()   # reload with new entry
    else:
        log(f"  No new vintage (latest: {latest['label']})")

    # 3. Compute d^g_c
    vintages = _load_vintages()
    if len(vintages) < 2:
        log("  Only one vintage available — d^g_c = 0 for all countries")
        d_g = {}
        vintage_info = {"current": vintages[-1]["label"], "prior": None}
    else:
        curr_meta  = vintages[-1]
        prior_meta = vintages[-2]
        log(f"  Revision: {curr_meta['label']} − {prior_meta['label']}, year={FCAST_YR}")

        curr_f  = pd.read_csv(_vintage_csv(curr_meta["vintage_id"]))
        prior_f = pd.read_csv(_vintage_csv(prior_meta["vintage_id"]))

        curr_yr  = curr_f[curr_f["year"] == FCAST_YR].set_index("country")["ngdp_rpch"]
        prior_yr = prior_f[prior_f["year"] == FCAST_YR].set_index("country")["ngdp_rpch"]

        revisions = (curr_yr - prior_yr).dropna().rename("d_g")
        d_g = revisions.to_dict()

        n_revised = (revisions.abs() > 0.05).sum()
        log(f"  Countries with |revision| > 0.05pp: {n_revised}/{len(revisions)}")
        log(f"  Mean revision: {revisions.mean():+.3f}pp")

        # Save canonical d^g_c file
        revisions.reset_index().rename(columns={"index":"country"}).to_csv(
            os.path.join(CACHE, "weo_revision_dgc.csv"), index=False)
        vintage_info = {"current": curr_meta["label"], "prior": prior_meta["label"]}

    # 4. Compute x_k
    w = pd.read_csv(os.path.join(CACHE, "export_weights_52_2023.csv"))
    w["d_g_c"] = w["country_iso"].map(d_g).fillna(0)
    w["weighted_dg"] = w["w_kc"] * w["d_g_c"]

    w_k = w[w["sector_52"].isin(K_SECTORS)]
    x_k = w_k.groupby(["sector_52","sector_name"])["weighted_dg"].sum().rename("x_k")

    # Save
    x_k.reset_index().to_csv(os.path.join(CACHE, "theme2_shocks_real.csv"), index=False)

    return {
        "x_k":        x_k,
        "d_g":        d_g,
        "vintages":   vintage_info,
        "fcast_year": FCAST_YR,
    }


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = refresh(verbose=True)
    if result:
        print("\n  x_k vector:")
        xk = result["x_k"].sort_values()
        for name, val in xk.items():
            sector_name = name[1] if isinstance(name, tuple) else str(name)
            print(f"    {sector_name:<18} {val:+.4f} pp")
