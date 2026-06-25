"""
Aggregation: shocks × elasticity matrices × L0 → ΔL (52×34).

Formula:
  E_{s,p}  = Σ_j x_j · M^(1)_j[s,p]   (Theme 1: commodity prices)
           + Σ_k x_k · M^(2)_k[s,p]   (Theme 2: WEO revision)
           + Σ_i x_i · M^(3)_i[s,p]   (Theme 3: SPE domestic demand)

  ΔL_{s,p} = E_{s,p} × L0_{s,p}       (% change → headcount change)

E  : 52×34 matrix of % employment change
ΔL : 52×34 matrix of absolute employment change (headcount)
"""
import os, json
import numpy as np
import pandas as pd

from pipeline.config import (
    N_SECTORS, N_PROVINCES,
    EXCLUDED_PROVINCE_IDS, NATIONAL_ID,
)

ROOT       = os.path.join(os.path.dirname(__file__), "..")
ETA_NPZ    = os.path.join(ROOT, "data", "elasticity", "eta_matrices.npz")
ETA_META   = os.path.join(ROOT, "data", "elasticity", "eta_meta.json")
LO_CSV     = os.path.join(ROOT, "rawdata", "lo.csv")
OUT_DIR    = os.path.join(ROOT, "data", "output")
os.makedirs(OUT_DIR, exist_ok=True)


# ─── Load L0 once ────────────────────────────────────────────────────────────
def _load_L0():
    """
    Returns L0 as a (52×34) numpy array.
    Rows = sectors 1..52, Cols = 34 provinces (new Papua splits excluded).
    """
    lo = pd.read_csv(LO_CSV)
    lo = lo[~lo["id"].isin(EXCLUDED_PROVINCE_IDS + [NATIONAL_ID])]
    prov_order = sorted(lo["id"].unique())
    sect_order = list(range(1, N_SECTORS + 1))
    pivot = (lo.pivot_table(index="sector_52", columns="id",
                            values="emp", aggfunc="sum")
               .reindex(index=sect_order, columns=prov_order)
               .fillna(0))
    return pivot.values, prov_order, sect_order


def _load_eta():
    """Returns dict of {key: (52×34) array} and metadata."""
    eta   = dict(np.load(ETA_NPZ))
    with open(ETA_META) as f:
        meta = json.load(f)
    return eta, meta


# ─── Shock key builders ───────────────────────────────────────────────────────
def _t1_key(code):   return f"t1_{code}"
def _t2_key(name):   return f"t2_{name}"
def _t3_key(cat):    return f"t3_{cat}"


# ─── Main aggregation ─────────────────────────────────────────────────────────
def compute(refresh_result, verbose=True):
    """
    Compute E (% change) and ΔL (headcount change) from pipeline refresh output.

    Parameters
    ----------
    refresh_result : dict returned by pipeline.refresh.run()

    Returns
    -------
    dict with keys:
      E          : (52×34) ndarray — % employment change
      dL         : (52×34) ndarray — absolute employment change (headcount)
      L0         : (52×34) ndarray — baseline employment
      prov_order : list of province IDs (length 34)
      sect_order : list of sector indices (length 52)
      shocks_used: dict of {matrix_key: shock_value} actually applied
      missing    : list of matrix keys with no shock value (set to 0)
      periods    : dict of data periods per theme
      placeholder: bool — True if using placeholder elasticity matrices
    """
    def log(msg):
        if verbose: print(msg)

    eta, meta     = _load_eta()
    L0, prov_order, sect_order = _load_L0()
    E             = np.zeros((N_SECTORS, N_PROVINCES))
    shocks_used   = {}
    missing       = []

    # ── Theme 1 ──────────────────────────────────────────────────────────────
    t1 = refresh_result.get("theme1")
    if t1:
        for code, val in t1["x_j"].items():
            key = _t1_key(code)
            if np.isnan(val):
                missing.append(key)
                continue
            if key in eta:
                E += val * eta[key]
                shocks_used[key] = val
            else:
                missing.append(key)
    else:
        log("  WARNING: Theme 1 result missing")

    # ── Theme 2 ──────────────────────────────────────────────────────────────
    t2 = refresh_result.get("theme2")
    if t2 and t2.get("x_k") is not None:
        xk = t2["x_k"]
        for idx, val in xk.items():
            sector_name = idx[1] if isinstance(idx, tuple) else str(idx)
            key = _t2_key(sector_name)
            if np.isnan(val):
                missing.append(key)
                continue
            if key in eta:
                E += val * eta[key]
                shocks_used[key] = val
            else:
                missing.append(key)
    else:
        log("  WARNING: Theme 2 result missing")

    # ── Theme 3 ──────────────────────────────────────────────────────────────
    t3 = refresh_result.get("theme3")
    if t3:
        for cat, val in t3["x_i"].items():
            if cat == "total_index":
                continue   # excluded: composite of sub-categories
            key = _t3_key(cat)
            if np.isnan(val):
                missing.append(key)
                continue
            if key in eta:
                E += val * eta[key]
                shocks_used[key] = val
            else:
                missing.append(key)
    else:
        log("  WARNING: Theme 3 result missing")

    # ── ΔL = E × L0 ──────────────────────────────────────────────────────────
    dL = (E / 100.0) * L0    # E is in %, L0 is headcount

    # ── Summary ───────────────────────────────────────────────────────────────
    log(f"\n  Shocks applied : {len(shocks_used)}/38")
    if missing:
        log(f"  Missing/skipped: {missing}")
    log(f"  E  range : {E.min():+.4f}% to {E.max():+.4f}%")
    log(f"  ΔL range : {dL.min():+,.0f} to {dL.max():+,.0f} workers")
    log(f"  ΔL total : {dL.sum():+,.0f} workers (net across all sectors/provinces)")

    # ── Save outputs ──────────────────────────────────────────────────────────
    np.save(os.path.join(OUT_DIR, "E_matrix.npy"),  E)
    np.save(os.path.join(OUT_DIR, "dL_matrix.npy"), dL)
    np.save(os.path.join(OUT_DIR, "L0_matrix.npy"), L0)

    result = {
        "E":           E,
        "dL":          dL,
        "L0":          L0,
        "prov_order":  prov_order,
        "sect_order":  sect_order,
        "shocks_used": shocks_used,
        "missing":     missing,
        "periods": {
            "theme1": t1["period"] if t1 else None,
            "theme2": t2.get("vintages") if t2 else None,
            "theme3": t3["period"] if t3 else None,
        },
        "placeholder": True,   # set to False when real CGE matrices loaded
    }

    with open(os.path.join(OUT_DIR, "aggregation_meta.json"), "w") as f:
        json.dump({
            "shocks_used":  shocks_used,
            "missing":      missing,
            "periods":      result["periods"],
            "E_min":        float(E.min()),
            "E_max":        float(E.max()),
            "dL_total":     float(dL.sum()),
            "placeholder":  True,
        }, f, indent=2)

    return result


# ─── Simulator aggregation ───────────────────────────────────────────────────
def compute_custom(t1_shocks, partner_dg, t3_shocks):
    """
    Compute E and ΔL from user-specified shocks (for simulator mode).

    Parameters
    ----------
    t1_shocks  : dict {commodity_code: pp}   e.g. {"coal": 10.0, "cpo": 5.0}
    partner_dg : dict {country_iso: pp}      e.g. {"CHN": 1.0, "USA": -0.5}
    t3_shocks  : dict {spe_category: pp}     e.g. {"fuel": -3.0}

    Returns
    -------
    dict with E (52×34), dL (52×34), shocks_used
    """
    import sys, os as _os
    _root = _os.path.join(_os.path.dirname(__file__), "..")
    sys.path.insert(0, _root)
    from pipeline.config import K_SECTORS

    eta, _  = _load_eta()
    L0, prov_order, sect_order = _load_L0()
    E       = np.zeros((N_SECTORS, N_PROVINCES))
    shocks_used = {}

    # Theme 1
    for code, val in t1_shocks.items():
        key = _t1_key(code)
        if key in eta and not np.isnan(val):
            E += val * eta[key]
            shocks_used[key] = val

    # Theme 2 — compute x_k from partner d^g_c
    w_path = _os.path.join(_root, "data", "cache", "theme2",
                           "export_weights_52_2023.csv")
    if _os.path.exists(w_path):
        w = pd.read_csv(w_path)
        w["d_g_c"] = w["country_iso"].map(partner_dg).fillna(0)
        w["weighted"] = w["w_kc"] * w["d_g_c"]
        w_k = w[w["sector_52"].isin(K_SECTORS)]
        x_k = w_k.groupby(["sector_52", "sector_name"])["weighted"].sum()
        for (_, sector_name), val in x_k.items():
            key = _t2_key(sector_name)
            if key in eta and not np.isnan(val):
                E += val * eta[key]
                shocks_used[key] = round(val, 4)

    # Theme 3
    for cat, val in t3_shocks.items():
        if cat == "total_index":
            continue
        key = _t3_key(cat)
        if key in eta and not np.isnan(val):
            E += val * eta[key]
            shocks_used[key] = val

    dL = (E / 100.0) * L0
    return {"E": E, "dL": dL, "L0": L0,
            "prov_order": prov_order, "sect_order": sect_order,
            "shocks_used": shocks_used,
            "e_overall": E}


# ─── Decomposed outputs ───────────────────────────────────────────────────────
def decompose(refresh_result, verbose=False):
    """
    Returns 19 component ΔL matrices AND their corresponding E (%) matrices.

    dL keys  (headcount change):  overall, t1_total, t2_total, t3_total,
                                   t1_{code}×7, t3_{cat}×7
    E  keys  (% employment chg):  e_overall, e_t1_total, e_t2_total, e_t3_total,
                                   e_t1_{code}×7, e_t3_{cat}×7
    Also: L0, prov_order, sect_order, shocks, periods
    """
    from pipeline.config import K_SECTORS

    eta, _  = _load_eta()
    L0, prov_order, sect_order = _load_L0()

    t1 = refresh_result.get("theme1") or {}
    t2 = refresh_result.get("theme2") or {}
    t3 = refresh_result.get("theme3") or {}

    def _dL(E):
        return (E / 100.0) * L0

    E_overall = np.zeros((N_SECTORS, N_PROVINCES))
    E_t1 = np.zeros((N_SECTORS, N_PROVINCES))
    E_t2 = np.zeros((N_SECTORS, N_PROVINCES))
    E_t3 = np.zeros((N_SECTORS, N_PROVINCES))

    out = {"L0": L0, "prov_order": prov_order, "sect_order": sect_order,
           "shocks": {}, "periods": {
               "theme1": t1.get("period"),
               "theme2": t2.get("vintages"),
               "theme3": t3.get("period"),
           }}

    # Theme 1
    for code, val in (t1.get("x_j") or {}).items():
        if np.isnan(val): continue
        key = _t1_key(code)
        if key not in eta: continue
        contrib = val * eta[key]
        E_t1 += contrib
        E_overall += contrib
        out[f"t1_{code}"]   = _dL(contrib)
        out[f"e_t1_{code}"] = contrib          # E % matrix
        out["shocks"][key]  = val

    # Theme 2
    xk = t2.get("x_k")
    if xk is not None:
        for idx, val in xk.items():
            sector_name = idx[1] if isinstance(idx, tuple) else str(idx)
            key = _t2_key(sector_name)
            if key not in eta or np.isnan(val): continue
            contrib = val * eta[key]
            E_t2 += contrib
            E_overall += contrib
            out["shocks"][key] = val

    # Theme 3
    for cat, val in (t3.get("x_i") or {}).items():
        if cat == "total_index" or np.isnan(val): continue
        key = _t3_key(cat)
        if key not in eta: continue
        contrib = val * eta[key]
        E_t3 += contrib
        E_overall += contrib
        out[f"t3_{cat}"]   = _dL(contrib)
        out[f"e_t3_{cat}"] = contrib           # E % matrix
        out["shocks"][key] = val

    out["overall"]    = _dL(E_overall);  out["e_overall"]    = E_overall
    out["t1_total"]   = _dL(E_t1);      out["e_t1_total"]   = E_t1
    out["t2_total"]   = _dL(E_t2);      out["e_t2_total"]   = E_t2
    out["t3_total"]   = _dL(E_t3);      out["e_t3_total"]   = E_t3

    save_dir = os.path.join(os.path.dirname(__file__), "..", "data", "output")
    os.makedirs(save_dir, exist_ok=True)
    np.save(os.path.join(save_dir, "L0_matrix.npy"), L0)
    for key in ["overall","t1_total","t2_total","t3_total"]:
        np.save(os.path.join(save_dir, f"{key}.npy"), out[key])
        np.save(os.path.join(save_dir, f"e_{key}.npy"), out[f"e_{key}"])
    for code in (t1.get("x_j") or {}):
        if f"t1_{code}" in out:
            np.save(os.path.join(save_dir, f"t1_{code}.npy"), out[f"t1_{code}"])
            np.save(os.path.join(save_dir, f"e_t1_{code}.npy"), out[f"e_t1_{code}"])
    for cat in (t3.get("x_i") or {}):
        if cat != "total_index" and f"t3_{cat}" in out:
            np.save(os.path.join(save_dir, f"t3_{cat}.npy"), out[f"t3_{cat}"])
            np.save(os.path.join(save_dir, f"e_t3_{cat}.npy"), out[f"e_t3_{cat}"])

    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from pipeline.refresh import run as refresh_run
    res = refresh_run(verbose=True)
    print("\n" + "="*65)
    print("AGGREGATION")
    print("="*65)
    agg = compute(res, verbose=True)
