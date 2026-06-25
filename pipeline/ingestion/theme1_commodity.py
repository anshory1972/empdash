"""
Theme 1 ingestion: commodity price shocks.

Sources:
  - World Bank Pink Sheet (CPO, Coal, Nickel, Copper, Rubber, Oil/Gas)
    URL discovered by scraping the WB commodity-markets page — hash changes each update.
  - FRED IY3344 (Electronics export price index)
    Stable API endpoint; API key from .env.

Shock formula (consistent with Theme 3):
  x_j = YoY%(t) - YoY%_bar_48(t)
  where YoY%(t)        = 100 * (P_t - P_{t-12}) / P_{t-12}
        YoY%_bar_48(t) = trailing 48-month avg of YoY%, lagged 1 period (t-48..t-1)

Shock = deviation from trend, NOT raw price level change.
Same 48-month window and lag structure as Theme 3.
Window rationale: 48M (4-year) avoids post-crash bias (36M) and avoids the
2021-2022 commodity supercycle distorting the BAU baseline (60M).
"""
import os, re, json, requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import pandas as pd
import numpy as np

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

CACHE    = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache", "theme1")
os.makedirs(CACHE, exist_ok=True)

FRED_KEY = os.getenv("FRED_API_KEY", "")

WB_PAGE_URL = "https://www.worldbank.org/en/research/commodity-markets"
WB_FILENAME = "CMO-Historical-Data-Monthly.xlsx"

FRED_SERIES = "IY3344"
FRED_URL    = f"https://api.stlouisfed.org/fred/series/observations?series_id={FRED_SERIES}&file_type=json&api_key={FRED_KEY}"

COMMODITIES = {
    "cpo":    "Palm oil",
    "coal":   "Coal, Australian",
    "nickel": "Nickel",
    "copper": "Copper",
    "rubber": "Rubber, TSR20 **",
    "oilgas": "Crude oil, average",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ─────────────────────────────────────────────────────────────────────────────
def _discover_pinksheet_url():
    """Scrape WB commodity-markets page to find current CMO Excel URL."""
    r = requests.get(WB_PAGE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    # Find href containing the filename
    match = re.search(
        r'href=["\']([^"\']*CMO-Historical-Data-Monthly\.xlsx[^"\']*)["\']',
        r.text
    )
    if match:
        url = match.group(1)
        if url.startswith("/"):
            url = "https://thedocs.worldbank.org" + url
        return url
    raise ValueError("Cannot find CMO-Historical-Data-Monthly.xlsx link on WB page")


def _parse_pinksheet(xlsx_bytes):
    """Extract monthly commodity prices from Pink Sheet XLSX."""
    xl = pd.ExcelFile(pd.io.common.BytesIO(xlsx_bytes) if isinstance(xlsx_bytes, bytes)
                      else xlsx_bytes)

    # Sheet "Monthly Prices" contains the data
    sheet = next((s for s in xl.sheet_names if "Monthly" in s and "Price" in s), None)
    if sheet is None:
        sheet = xl.sheet_names[1]   # fallback: second sheet

    raw = xl.parse(sheet, header=None)

    # Find the header row: contains "Period" or "Date" in the first column
    hdr_row = None
    for i, row in raw.iterrows():
        if any("period" in str(v).lower() or str(v).strip() == "Date"
               for v in row if pd.notna(v)):
            hdr_row = i
            break
    if hdr_row is None:
        raise ValueError("Cannot find header row in Pink Sheet")

    df = raw.iloc[hdr_row:].reset_index(drop=True)
    df.columns = [str(v).strip() for v in df.iloc[0]]
    df = df.iloc[1:].reset_index(drop=True)

    # Period column: filter to monthly rows (format "YYYYMNN")
    period_col = df.columns[0]
    df = df[df[period_col].astype(str).str.match(r"^\d{4}M\d{1,2}$")].copy()
    df = df.rename(columns={period_col: "period"})
    df["period"] = df["period"].astype(str).str.strip()

    # Map commodity names to short codes
    name_to_code = {v: k for k, v in COMMODITIES.items()}
    result = df[["period"]].copy()
    for col in df.columns[1:]:
        col_clean = str(col).strip()
        code = name_to_code.get(col_clean)
        if code:
            result[code] = pd.to_numeric(df[col], errors="coerce")

    # Ensure all commodity columns exist
    for code in COMMODITIES:
        if code not in result.columns:
            result[code] = np.nan

    return result.sort_values("period").reset_index(drop=True)


def refresh_pinksheet(verbose=True):
    """Download latest Pink Sheet if URL has changed or file is stale."""
    def log(msg):
        if verbose: print(msg)

    meta_path  = os.path.join(CACHE, "wb_pinksheet_meta.json")
    xlsx_path  = os.path.join(CACHE, "wb_pinksheet.xlsx")
    csv_path   = os.path.join(CACHE, "wb_pinksheet.csv")

    cached_url = None
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        cached_url = meta.get("source_url")

    log("Theme 1 (Pink Sheet): discovering current URL...")
    try:
        current_url = _discover_pinksheet_url()
        log(f"  Current URL hash: ...{current_url[-50:]}")
    except Exception as e:
        log(f"  WARNING: URL discovery failed ({e}) — using cached data")
        return _load_cached_pinksheet(csv_path)

    if current_url == cached_url and os.path.exists(csv_path):
        log("  No new Pink Sheet (URL unchanged)")
        return _load_cached_pinksheet(csv_path)

    log("  New Pink Sheet detected — downloading...")
    r = requests.get(current_url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    log(f"  Downloaded {len(r.content)/1024:.0f} KB")

    with open(xlsx_path, "wb") as f:
        f.write(r.content)

    df = _parse_pinksheet(r.content)
    df.to_csv(csv_path, index=False)

    # Extract update notice from page if available
    try:
        page_r = requests.get(WB_PAGE_URL, headers=HEADERS, timeout=30)
        notice_match = re.search(r"Updated on ([A-Za-z]+ \d+,? \d{4})", page_r.text)
        notice = notice_match.group(1) if notice_match else "unknown"
    except Exception:
        notice = "unknown"

    with open(meta_path, "w") as f:
        json.dump({
            "source_url":         current_url,
            "wb_page_url":        WB_PAGE_URL,
            "file_update_notice": f"Updated on {notice}",
            "downloaded_at":      datetime.now(timezone.utc).isoformat(),
            "period_start":       str(df["period"].iloc[0]),
            "period_end":         str(df["period"].iloc[-1]),
            "columns":            [c for c in COMMODITIES],
            "column_mapping":     COMMODITIES,
        }, f, indent=2)

    log(f"  Saved: {df['period'].iloc[-1]} latest, {len(df)} months")
    return df


def _load_cached_pinksheet(csv_path):
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    raise FileNotFoundError(f"No cached Pink Sheet at {csv_path}")


# ─────────────────────────────────────────────────────────────────────────────
def refresh_fred(verbose=True):
    """Download latest FRED IY3344 observations."""
    def log(msg):
        if verbose: print(msg)

    csv_path  = os.path.join(CACHE, "fred_IY3344.csv")
    meta_path = os.path.join(CACHE, "fred_IY3344_meta.json")

    if not FRED_KEY:
        log("  WARNING: FRED_API_KEY not set — using cached data")
        return pd.read_csv(csv_path) if os.path.exists(csv_path) else None

    log(f"Theme 1 (FRED {FRED_SERIES}): downloading observations...")
    try:
        r = requests.get(FRED_URL, timeout=30)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        log(f"  WARNING: FRED download failed ({e}) — using cached data")
        return pd.read_csv(csv_path) if os.path.exists(csv_path) else None

    obs = raw.get("observations", [])
    rows = []
    for o in obs:
        try:
            val = float(o["value"])
            rows.append({"date": o["date"], "electronics": val})
        except (ValueError, KeyError):
            pass

    df = pd.DataFrame(rows).dropna().sort_values("date").reset_index(drop=True)
    df.to_csv(csv_path, index=False)

    series_info = raw.get("seriess", [{}])[0] if raw.get("seriess") else {}
    # Fetch series metadata separately for title
    meta_r = requests.get(
        f"https://api.stlouisfed.org/fred/series?series_id={FRED_SERIES}&file_type=json&api_key={FRED_KEY}",
        timeout=20
    )
    series_meta = meta_r.json().get("seriess", [{}])[0] if meta_r.ok else {}

    with open(meta_path, "w") as f:
        json.dump({
            "series_id":     FRED_SERIES,
            "title":         series_meta.get("title", "Export Price Index: Electronics"),
            "units":         series_meta.get("units", "Index Dec 2005=100"),
            "frequency":     series_meta.get("frequency", "Monthly"),
            "last_updated":  series_meta.get("last_updated", ""),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "period_start":  str(df["date"].iloc[0]),
            "period_end":    str(df["date"].iloc[-1]),
            "missing_count": int(df["electronics"].isna().sum()),
        }, f, indent=2)

    log(f"  Saved: {df['date'].iloc[-1]} latest, {len(df)} observations")
    return df


# ─────────────────────────────────────────────────────────────────────────────
def compute_shocks(verbose=True):
    """
    Compute Theme 1 shock vector.

    x_j = YoY%(t) - YoY%_bar_36(t)
      YoY%(t)        = 100 * (P_t - P_{t-12}) / P_{t-12}
      YoY%_bar_36(t) = 36-month trailing avg of YoY%, lagged 1 period

    Same structure as Theme 3: shock = deviation from trend.
    """
    def log(msg):
        if verbose: print(msg)

    ps   = pd.read_csv(os.path.join(CACHE, "wb_pinksheet.csv"))
    fred = pd.read_csv(os.path.join(CACHE, "fred_IY3344.csv"))

    # Align FRED into monthly period string matching Pink Sheet
    fred = fred.dropna(subset=["electronics"]).sort_values("date").reset_index(drop=True)
    fred["date_dt"] = pd.to_datetime(fred["date"])
    fred["period"]  = (fred["date_dt"].dt.year.astype(str) + "M"
                       + fred["date_dt"].dt.month.astype(str).str.zfill(2))  # e.g. 2026M05

    ps = ps[ps["period"].str.match(r"^\d{4}M\d{1,2}$")].copy()
    ps = ps.merge(fred[["period","electronics"]], on="period", how="left", suffixes=("","_fred"))
    if "electronics_fred" in ps.columns:
        ps["electronics"] = ps["electronics"].combine_first(ps.pop("electronics_fred"))
    ps = ps.sort_values("period").reset_index(drop=True)

    all_codes = list(COMMODITIES.keys()) + ["electronics"]
    shocks    = {}
    t_str     = ps["period"].iloc[-1]

    for code in all_codes:
        if code not in ps.columns:
            continue
        col = pd.to_numeric(ps[code], errors="coerce")

        # YoY%: 12-period pct change (fill_method=None avoids forward-fill of gaps)
        yoy = col.pct_change(12, fill_method=None) * 100

        # 48-month trailing avg of YoY%, lagged 1 (same as Theme 3)
        yoy_bar = yoy.rolling(48, min_periods=48).mean().shift(1)

        # Shock = deviation from trend
        x_j_series = yoy - yoy_bar
        valid = x_j_series.dropna()
        if valid.empty:
            shocks[code] = np.nan
        else:
            shocks[code] = float(valid.iloc[-1])

    log(f"  Theme 1 shocks ({t_str})  [x_j = YoY% − 48M avg YoY%]:")
    for k, v in shocks.items():
        if not np.isnan(v):
            log(f"    {k:<14}  {v:+.2f} pp")

    return shocks, t_str


# ─────────────────────────────────────────────────────────────────────────────
def refresh(verbose=True):
    refresh_pinksheet(verbose)
    refresh_fred(verbose)
    shocks, period = compute_shocks(verbose)
    return {"x_j": shocks, "period": period}


if __name__ == "__main__":
    result = refresh(verbose=True)
