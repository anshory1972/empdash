"""
Build eta_matrices.npz + eta_meta.json from the IndoTERM CGE extract CSVs.

This is the real-CGE counterpart to build_placeholders.py: that script GENERATES
synthetic matrices, this one INGESTS the ones GEMPACK produced.

Input:
  data/elasticity/csv/eta_{key}.csv   — one file per shock, written by
                                        cge/sims/extract.bat
                                        rows s01..s52, columns = province IDs

Output:
  data/elasticity/eta_matrices.npz    — what pipeline/aggregation.py loads
  data/elasticity/eta_meta.json       — labels, provenance, shock definitions

Every CSV is validated against the province order that aggregation.py derives
from lo.csv, so a column reordering in a future extract fails loudly here
instead of silently mislabelling provinces on the dashboard.

Usage:
  python -m pipeline.elasticity.build_from_csv
"""
import os, re, json, glob
from datetime import datetime

import numpy as np
import pandas as pd

from pipeline.config import (
    N_SECTORS, N_PROVINCES,
    EXCLUDED_PROVINCE_IDS, NATIONAL_ID,
)

ROOT    = os.path.join(os.path.dirname(__file__), "..", "..")
CSV_DIR = os.path.join(ROOT, "data", "elasticity", "csv")
OUT_DIR = os.path.join(ROOT, "data", "elasticity")
LO_CSV  = os.path.join(ROOT, "rawdata", "lo.csv")
IO52_CSV = os.path.join(ROOT, "data", "cache", "io52_sectors.csv")

# ── Provenance ───────────────────────────────────────────────────────────────
# Update these when the CGE run behind the CSVs changes.
SOURCE = (
    "IndoTERM CGE (TERM, 58-sector govshift2 database with 0.5% household->"
    "government seed), short-run closure, 1% shocks; xlab_o aggregated 58->52 "
    "with labour-bill weights (agghar)"
)
BUILT_FROM = "data/elasticity/csv/eta_*.csv (extracted with cge/sims/extract.bat)"
SHOCK_DEFINITIONS = {
    "t1": "1% world price of the commodity: fpexp_d and pfimp",
    "t2": "1% export demand shift: fqexp_d, all sec58 children of the IO52 sector",
    "t3": ("1% household demand for the SPE category: fgov_s via seeded "
           "government demand, province-specific PGOV ratios"),
}
KNOWN_CAVEATS = [
    "t1_nickel ~0: NickelOre has no exports/imports in the 2016 IRIO database",
]
NOTE = (
    "Calibrated IndoTERM CGE matrices. Each matrix M[s,p] = % employment change "
    "in sector s, province p per +1 pp shock to the driver. "
    "New 2022 Papua provinces excluded to match IndoTERM 34-province structure."
)


def _province_order():
    """
    Province order exactly as pipeline.aggregation._load_L0 builds it, so the
    CSV columns are checked against what the dashboard will actually assume.
    """
    lo = pd.read_csv(LO_CSV)
    lo = lo[~lo["id"].isin(EXCLUDED_PROVINCE_IDS + [NATIONAL_ID])]
    return sorted(lo["id"].unique().tolist()), lo


def _read_matrix(path, prov_order):
    """Read one extract CSV into a validated (52x34) array."""
    key = os.path.basename(path)[len("eta_"):-len(".csv")]
    df  = pd.read_csv(path, index_col=0)

    # Columns: province IDs, in the order aggregation.py expects
    try:
        cols = [int(c) for c in df.columns]
    except ValueError:
        raise ValueError(f"{key}: non-numeric province column header in {df.columns.tolist()}")
    if cols != list(prov_order):
        extra   = sorted(set(cols) - set(prov_order))
        missing = sorted(set(prov_order) - set(cols))
        raise ValueError(
            f"{key}: province columns do not match lo.csv order.\n"
            f"  extra in csv   : {extra}\n"
            f"  missing in csv : {missing}\n"
            f"  (same set but reordered?) {sorted(cols) == sorted(prov_order)}"
        )

    # Rows: s01..s52, in order
    want = [f"s{i:02d}" for i in range(1, N_SECTORS + 1)]
    got  = [str(i).strip() for i in df.index]
    if got != want:
        raise ValueError(
            f"{key}: sector rows must be {want[0]}..{want[-1]} in order, got "
            f"{got[:3]}...{got[-3:]} ({len(got)} rows)"
        )

    M = df.to_numpy(dtype=np.float64)
    if M.shape != (N_SECTORS, N_PROVINCES):
        raise ValueError(f"{key}: expected {(N_SECTORS, N_PROVINCES)}, got {M.shape}")
    if not np.isfinite(M).all():
        bad = np.argwhere(~np.isfinite(M))
        raise ValueError(f"{key}: {len(bad)} non-finite value(s), first at row/col {bad[0].tolist()}")

    return key, M


def build(verbose=True):
    def log(msg):
        if verbose: print(msg)

    paths = sorted(glob.glob(os.path.join(CSV_DIR, "eta_*.csv")))
    if not paths:
        raise FileNotFoundError(f"No eta_*.csv found in {CSV_DIR}")

    prov_order, lo = _province_order()
    if len(prov_order) != N_PROVINCES:
        raise ValueError(f"lo.csv yields {len(prov_order)} provinces, expected {N_PROVINCES}")
    prov_labels = (lo.drop_duplicates("id").set_index("id")["id_label"]
                     .reindex(prov_order).tolist())

    log(f"Reading {len(paths)} CSV files from data/elasticity/csv/")
    matrices = {}
    for p in paths:
        key, M = _read_matrix(p, prov_order)
        if key in matrices:
            raise ValueError(f"duplicate matrix key: {key}")
        matrices[key] = M

    # Every key must be t1_/t2_/t3_ prefixed — aggregation.py dispatches on that
    unknown = [k for k in matrices if not re.match(r"^t[123]_", k)]
    if unknown:
        raise ValueError(f"unrecognised matrix key prefix (expected t1_/t2_/t3_): {unknown}")

    npz_path = os.path.join(OUT_DIR, "eta_matrices.npz")
    np.savez_compressed(npz_path, **matrices)
    log(f"Saved: eta_matrices.npz  ({len(matrices)} matrices, each {N_SECTORS}x{N_PROVINCES})")

    sect_order = list(range(1, N_SECTORS + 1))
    io52       = pd.read_csv(IO52_CSV)
    sect_names = io52.set_index("io52_idx")["io52_name"].to_dict()

    keys = list(matrices.keys())
    meta = {
        "n_sectors":       N_SECTORS,
        "n_provinces":     N_PROVINCES,
        "province_order":  prov_order,
        "province_labels": prov_labels,
        "sector_order":    sect_order,
        "sector_labels":   [sect_names.get(i, f"s{i:02d}") for i in sect_order],
        "matrix_keys":     keys,
        "note":            NOTE,
        "theme1_shocks":   [k for k in keys if k.startswith("t1_")],
        "theme2_shocks":   [k for k in keys if k.startswith("t2_")],
        "theme3_shocks":   [k for k in keys if k.startswith("t3_")],
        "source":            SOURCE,
        "placeholder":       False,
        "built_at":          datetime.now().isoformat(timespec="seconds"),
        "built_from":        BUILT_FROM,
        "shock_definitions": SHOCK_DEFINITIONS,
        "known_caveats":     KNOWN_CAVEATS,
    }
    with open(os.path.join(OUT_DIR, "eta_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    log("Saved: eta_meta.json")

    # ── Summary ──────────────────────────────────────────────────────────────
    log(f"\n  {'Key':<24}  {'min':>9}  {'max':>9}  {'mean':>9}")
    log("  " + "-" * 56)
    for key in keys:
        M = matrices[key]
        log(f"  {key:<24}  {M.min():>9.4f}  {M.max():>9.4f}  {M.mean():>9.4f}")

    near_zero = [k for k, M in matrices.items() if np.abs(M).max() < 1e-6]
    if near_zero:
        log(f"\n  NOTE: all-zero matrices (no effect will be applied): {near_zero}")

    return matrices, meta


if __name__ == "__main__":
    build(verbose=True)
