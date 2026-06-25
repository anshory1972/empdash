"""
Theme 3 ingestion: domestic demand shocks from BI SPE.

Source: Bank Indonesia Survei Penjualan Eceran (SPE)
  URL: https://www.bi.go.id/id/publikasi/laporan/Documents/Data-Series-SPE-{Month}-{Year}.zip
  No authentication required.

Auto-update:
  On each refresh, probe backwards from current month for the latest available ZIP.
  If newer than the cached vintage, download, parse, deduplicate, and save panel.

Shock formula (consistent with Theme 1):
  x_i = g_yoy(t) − g_bar_48(t)
  where g_bar_48 = rolling 48-month trailing avg of g_yoy, lagged 1 period

Note: BI releases preliminary data with 2 rows per (category, month) for recent months.
Dedup rule: keep LAST row per (category_code, year, month) — that's the latest revision.
"""
import os, io, json, zipfile, requests
from datetime import datetime, timezone
import pandas as pd
import numpy as np

CACHE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache", "theme3")
os.makedirs(CACHE, exist_ok=True)

PANEL_CSV  = os.path.join(CACHE, "spe_yoy_panel.csv")
META_JSON  = os.path.join(CACHE, "spe_meta.json")
SHOCKS_CSV = os.path.join(CACHE, "theme3_shocks.csv")

BASE_URL = (
    "https://www.bi.go.id/id/publikasi/laporan/Documents/"
    "Data-Series-SPE-{month}-{year}.zip"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MONTHS_EN = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December",
]
MONTHS_ID = [
    "Januari","Februari","Maret","April","Mei","Juni",
    "Juli","Agustus","September","Oktober","November","Desember",
]

MONTH_NAME_TO_NUM = {m.lower(): i+1 for i, m in enumerate(MONTHS_EN)}
MONTH_NAME_TO_NUM.update({m.lower(): i+1 for i, m in enumerate(MONTHS_ID)})

# Short month labels used INSIDE the XLSX header row
MONTH_SHORT = ["Jan","Feb","Mar","Apr","Mei","Juni","Juli","Agst","Sept","Okt","Nov","Des"]

CAT_LABELS = {
    "Suku Cadang dan Aksesori":           "spare_parts",
    "Makanan, Minuman, & Tembakau":       "food_bev_tobacco",
    "Bahan Bakar Kendaraan Bermotor":     "fuel",
    "Peralatan Informasi dan Komunikasi": "ict_equipment",
    "Perlengkapan Rumah Tangga Lainnya":  "household_equip",
    "Barang Budaya dan Rekreasi":         "cultural_rec",
    "Barang Lainnya":                     "other_goods",
    "- o/w Sandang":                      "sandang",
    "INDEKS TOTAL":                       "total_index",
}


# ─────────────────────────────────────────────────────────────────────────────
def _probe_latest(verbose=True):
    """
    Probe BI site backwards from today for the latest SPE ZIP.
    Tries English month names first, then Indonesian, for each month.
    Returns (url, month_name, year) or (None, None, None).
    """
    def log(msg):
        if verbose: print(msg)

    now = datetime.now()
    log("Theme 3 (BI SPE): probing for latest ZIP...")

    for delta in range(0, 4):
        year  = now.year
        month = now.month - delta
        if month <= 0:
            month += 12
            year  -= 1

        for month_name in [MONTHS_EN[month-1], MONTHS_ID[month-1]]:
            url = BASE_URL.format(month=month_name, year=year)
            try:
                r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
                if r.status_code == 200:
                    chunk = b""
                    for c in r.iter_content(4):
                        chunk = c
                        break
                    if chunk[:2] == b"PK":
                        log(f"  Found: {month_name} {year}  ({url.split('/')[-1]})")
                        return url, month_name, year
            except requests.exceptions.Timeout:
                log(f"  Timeout on {month_name} {year} — BI may be slow")
            except Exception as e:
                log(f"  Error on {month_name} {year}: {type(e).__name__}")

    log("  WARNING: no SPE ZIP found — will use cached data")
    return None, None, None


def _cached_vintage():
    """Return (month_name, year) of the currently cached SPE vintage, or (None, None)."""
    if not os.path.exists(META_JSON):
        return None, None
    with open(META_JSON) as f:
        meta = json.load(f)
    return meta.get("vintage_month"), meta.get("vintage_year")


def _is_newer(month_name, year):
    """Return True if (month_name, year) is strictly newer than the cached vintage."""
    cached_month, cached_year = _cached_vintage()
    if cached_month is None:
        return True
    new_num    = MONTH_NAME_TO_NUM.get(month_name.lower(), 0)
    cached_num = MONTH_NAME_TO_NUM.get(cached_month.lower(), 0)
    if year != cached_year:
        return year > cached_year
    return new_num > cached_num


def _parse_tabel2(xlsx_bytes):
    """
    Parse Tabel 2 (YoY growth) from SPE XLSX bytes.
    Returns long DataFrame: year, month, category_code, category_name, yoy_growth, is_preliminary
    """
    xl       = pd.ExcelFile(io.BytesIO(xlsx_bytes))
    df       = xl.parse("Tabel 2", header=None)
    year_row  = df.iloc[3, 1:].tolist()
    month_row = df.iloc[4, 1:].tolist()

    # Build period index: (year, month_num, is_preliminary)
    periods, current_year = [], None
    for y, m in zip(year_row, month_row):
        if pd.notna(y) and str(y).strip() not in ("", "nan"):
            try:
                current_year = int(float(str(y).strip()))
            except Exception:
                pass
        if pd.notna(m) and current_year and str(m).strip() not in ("", "nan"):
            m_raw     = str(m).strip()
            is_prelim = m_raw.endswith("*")
            m_clean   = m_raw.rstrip("*").strip()
            month_num = next(
                (i+1 for i, s in enumerate(MONTH_SHORT) if s.lower() == m_clean.lower()),
                None
            )
            periods.append((current_year, month_num, is_prelim) if month_num else None)
        else:
            periods.append(None)

    # Extract rows for known categories
    rows = []
    for row_idx in range(df.shape[0]):
        cat_name = str(df.iloc[row_idx, 0]).strip()
        if cat_name not in CAT_LABELS:
            continue
        cat_code = CAT_LABELS[cat_name]
        for period, val in zip(periods, df.iloc[row_idx, 1:].tolist()):
            if period is None:
                continue
            yr, mo, prelim = period
            v = str(val).strip().rstrip("*")
            if v in ("", "nan"):
                continue
            try:
                rows.append({
                    "year": yr, "month": mo,
                    "category_code": cat_code,
                    "category_name": cat_name,
                    "yoy_growth": float(v),
                    "is_preliminary": prelim,
                })
            except ValueError:
                pass

    return pd.DataFrame(rows).sort_values(["category_code","year","month"]).reset_index(drop=True)


def refresh_spe(verbose=True):
    """
    Check for a new SPE release and download if found.
    Returns the parsed long DataFrame (from cache or fresh download).
    """
    def log(msg):
        if verbose: print(msg)

    url, month_name, year = _probe_latest(verbose)

    if url is not None and _is_newer(month_name, year):
        log(f"  New SPE release: {month_name} {year} — downloading...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=90)
            r.raise_for_status()
            log(f"  Downloaded {len(r.content)/1024:.0f} KB")

            zip_filename = f"SPE-{month_name}-{year}.zip"
            with open(os.path.join(CACHE, zip_filename), "wb") as f:
                f.write(r.content)

            zf        = zipfile.ZipFile(io.BytesIO(r.content))
            xlsx_name = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
            log(f"  Parsing: {xlsx_name}")

            df = _parse_tabel2(zf.read(xlsx_name))
            df.to_csv(PANEL_CSV, index=False)
            log(f"  Panel saved: {len(df)} rows, "
                f"{df['year'].min()}-{df['month'].min():02d} to "
                f"{df['year'].max()}-{df['month'].max():02d}")

            with open(META_JSON, "w", encoding="utf-8") as f:
                json.dump({
                    "source_url":      url,
                    "zip_filename":    zip_filename,
                    "vintage_month":   month_name,
                    "vintage_year":    int(year),
                    "downloaded_at":   datetime.now(timezone.utc).isoformat(),
                    "xlsx_inside_zip": xlsx_name,
                    "yoy_sheet":       "Tabel 2",
                    "mtm_sheet":       "Tabel 3 (NOT used — yoy only per spec §6.6)",
                    "categories":      CAT_LABELS,
                    "note_sandang":    (
                        "Sandang is '- o/w Sandang' sub-item of 'Barang Lainnya', "
                        "not a standalone top-level category."
                    ),
                    "period_start":    f"{int(df['year'].min())}-{int(df['month'].min()):02d}",
                    "period_end":      f"{int(df['year'].max())}-{int(df['month'].max()):02d}",
                    "total_rows":      len(df),
                }, f, indent=2, ensure_ascii=False)

            return df

        except Exception as e:
            log(f"  WARNING: download/parse failed ({e}) — using cached panel")
    else:
        cached_month, cached_year = _cached_vintage()
        if cached_month:
            log(f"  No new SPE (cached: {cached_month} {cached_year})")
        else:
            log("  No cached SPE and probe failed — no data available")

    if os.path.exists(PANEL_CSV):
        return pd.read_csv(PANEL_CSV)
    raise FileNotFoundError(f"No SPE panel at {PANEL_CSV}")


# ─────────────────────────────────────────────────────────────────────────────
def compute_shocks(verbose=True):
    """
    Compute Theme 3 shock vector.

    x_i = g_yoy(t) − g_bar_48(t)
      g_bar_48(t) = 48-month trailing avg of g_yoy, lagged 1 period

    Same structure as Theme 1: shock = deviation from trend.
    Dedup: keep last row per (category_code, year, month) before computing.
    """
    def log(msg):
        if verbose: print(msg)

    df = pd.read_csv(PANEL_CSV)
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))

    # Dedup: keep last row per (category_code, date) — last = latest BI revision
    df = (df.sort_values(["category_code","date"])
            .drop_duplicates(subset=["category_code","date"], keep="last")
            .reset_index(drop=True))

    shocks, t_str = {}, None
    for cat, grp in df.groupby("category_code"):
        grp = grp.sort_values("date").reset_index(drop=True)
        grp["g_bar_48"] = grp["yoy_growth"].rolling(48, min_periods=48).mean().shift(1)
        grp["x_i"]      = grp["yoy_growth"] - grp["g_bar_48"]
        valid = grp.dropna(subset=["x_i"])
        if valid.empty:
            shocks[cat] = np.nan
            continue
        latest      = valid.iloc[-1]
        shocks[cat] = float(latest["x_i"])
        t_str = latest["date"].strftime("%Y-%m")

    log(f"  Theme 3 shocks ({t_str})  [x_i = g_yoy − 48M avg g_yoy]:")
    for k, v in sorted(shocks.items()):
        if not np.isnan(v):
            log(f"    {k:<28}  {v:+.2f} pp")

    # Save
    rows = [{"category_code": k, "x_i": v} for k, v in shocks.items() if not np.isnan(v)]
    pd.DataFrame(rows).to_csv(SHOCKS_CSV, index=False)

    return shocks, t_str


# ─────────────────────────────────────────────────────────────────────────────
def refresh(verbose=True):
    refresh_spe(verbose)
    shocks, period = compute_shocks(verbose)
    return {"x_i": shocks, "period": period}


if __name__ == "__main__":
    result = refresh(verbose=True)
