"""
empdash — Layoff Risk Early-Warning Dashboard
Ministry of Manpower (Kemnaker), Indonesia
"""
import os, sys, json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GEO_PATH = os.path.join(ROOT, "data", "geo", "indonesia_adm2.geojson")
sys.path.insert(0, ROOT)

from pipeline.aggregation import decompose, compute_custom, _load_L0
from pipeline.refresh import run as refresh_run
from pipeline.config import K_SECTORS

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Employment Pressure Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');
:root {
  --high:#d23b34; --high-bg:#fbe9e7;
  --med:#c07e00;  --med-bg:#fef3c7;
  --low:#1f9d57;  --low-bg:#e7f6ee;
  --navy:#1f2d3d; --navy-2:#2d4060; --navy-3:#334155;
  --muted:#64748b; --muted-2:#94a3b8;
  --accent:#2563eb; --accent-soft:#eff6ff;
  --surface:#ffffff; --surface-2:#f8fafc;
  --line:#e2e8f0; --line-2:#f1f5f9; --ink:#1e293b;
  --radius:10px;
  --shadow:0 1px 3px rgba(0,0,0,.07),0 1px 2px rgba(0,0,0,.04);
}

/* ── Base ── */
.stApp { background:#f1f4f8; font-family:'Inter',sans-serif; }
[data-testid="stSidebar"] { background:#1f2d3d; }
[data-testid="stSidebar"] * { color:#d0daf0 !important; font-family:'Inter',sans-serif !important; }

/* ── Banner ── */
.banner {
  background:linear-gradient(120deg,#1f2d3d 0%,#2d4060 55%,#2563eb 100%);
  border-radius:12px; padding:1rem 1.5rem; margin-bottom:.8rem;
  display:flex; align-items:center; justify-content:space-between;
}
.banner-left h1 {
  font-family:'Plus Jakarta Sans',sans-serif; color:#fff;
  font-size:1.35rem; font-weight:800; margin:0; letter-spacing:-.2px;
}
.banner-left p { color:rgba(255,255,255,.62); font-size:.73rem; margin:.2rem 0 0; }
.banner-right { text-align:right; }
.banner-right .bstat { color:rgba(255,255,255,.78); font-size:.73rem; margin:.1rem 0; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { gap:3px; background:transparent; margin-bottom:.5rem; }
.stTabs [data-baseweb="tab"] {
  background:white; border-radius:7px 7px 0 0;
  padding:.35rem 1rem; font-family:'Plus Jakarta Sans',sans-serif;
  font-weight:700; font-size:.8rem; border:1px solid var(--line);
  border-bottom:none; color:var(--muted);
}
.stTabs [aria-selected="true"] {
  background:var(--navy) !important; color:white !important;
  border-color:var(--navy) !important;
}

/* ── Cards ── */
.card {
  background:var(--surface); border-radius:var(--radius);
  border:1px solid var(--line); padding:8px 10px;
  box-shadow:var(--shadow); margin-bottom:10px;
}
.card h3 {
  font-family:'Plus Jakarta Sans',sans-serif; font-weight:800;
  font-size:13px; color:var(--navy); margin:0 0 3px;
}
.card .csub { font-size:11.5px; color:var(--muted); margin:0 0 8px; }
.card-t1 { border-top:3px solid #e67e22; }
.card-t2 { border-top:3px solid var(--accent); }
.card-t3 { border-top:3px solid #7c3aed; }

/* ── Section label (matches HTML .section-label) ── */
.section-label {
  font-family:'Plus Jakarta Sans',sans-serif; font-weight:800;
  font-size:11px; text-transform:uppercase; letter-spacing:1px;
  color:var(--navy-3); margin:20px 0 10px;
  display:flex; align-items:center; gap:10px;
}
.section-label:before {
  content:""; flex:none; width:4px; height:14px;
  border-radius:3px; background:var(--accent);
}
.section-label .ln { flex:1; height:1px; background:var(--line); }

/* ── Methbar (methodology note) ── */
.methbar {
  display:flex; gap:10px; align-items:flex-start;
  background:var(--accent-soft); border:1px solid #cfe0fb;
  border-radius:8px; padding:10px 12px; font-size:12.5px;
  color:#22406e; margin-bottom:14px; line-height:1.5;
}

/* ── Simbig stats row ── */
.simbig {
  display:flex; align-items:center; gap:14px; padding:13px 15px;
  border-radius:var(--radius); background:var(--surface-2);
  border:1px solid var(--line); margin-bottom:10px;
}
.simbig .sb { flex:1; text-align:center; }
.simbig .sb .n {
  font-family:'Plus Jakarta Sans',sans-serif; font-weight:800;
  font-size:24px; letter-spacing:-1px;
}
.simbig .sb .l { font-size:20px; color:var(--muted); font-weight:600; margin-top:2px; }
.simbig .arrow { font-size:18px; color:var(--muted-2); }

/* ── Theme breakdown cards ── */
.theme-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:9px; }
.theme-card {
  background:var(--surface); border:1px solid var(--line);
  border-radius:8px; padding:10px 12px; text-align:center;
}
.theme-card .tl { font-size:11px; color:var(--muted); font-weight:600; margin-bottom:4px; }
.theme-card .tv {
  font-family:'Plus Jakarta Sans',sans-serif; font-weight:800;
  font-size:20px; letter-spacing:-.5px;
}
.badge {
  display:inline-flex; align-items:center; padding:2px 7px;
  border-radius:99px; font-size:10.5px; font-weight:700;
  font-family:'Plus Jakarta Sans',sans-serif; margin-top:4px;
}
.badge.high { background:var(--high-bg); color:var(--high); }
.badge.med  { background:var(--med-bg);  color:var(--med);  }
.badge.low  { background:var(--low-bg);  color:var(--low);  }
.badge.neut { background:#f1f5f9; color:var(--muted); }

/* ── Metric override ── */
div[data-testid="metric-container"] {
  background:white; border-radius:8px; padding:.6rem .9rem;
  box-shadow:var(--shadow); border:1px solid var(--line);
}

</style>""", unsafe_allow_html=True)

# ─── Labels ───────────────────────────────────────────────────────────────────
T2_LABELS = {
    "HortiCrops":   "Tanaman hortikultura",
    "Estates":      "Perkebunan",
    "Forestry":     "Kehutanan",
    "Fishery":      "Perikanan",
    "Coal":         "Pertambangan batu bara",
    "OilGasGeo":    "Minyak & gas bumi",
    "IronOre":      "Bijih besi & tambang mineral",
    "FoodMan":      "Industri makanan & minuman",
    "Tobacco":      "Industri tembakau",
    "Textiles":     "Industri tekstil",
    "Leather":      "Industri kulit & alas kaki",
    "WoodProd":     "Industri kayu & produk kayu",
    "PaperProd":    "Industri kertas & percetakan",
    "NonMetalProd": "Industri produk non-logam",
    "CoalOilMan":   "Industri batu bara & migas olahan",
    "Chemical":     "Industri kimia",
    "Rubber":       "Industri karet & plastik",
    "BasicMetal":   "Industri logam dasar",
    "MetalProd":    "Industri produk logam",
    "Machinery":    "Industri mesin & peralatan",
    "TranspEquip":  "Industri alat transportasi",
    "Furniture":    "Industri furnitur",
    "OtherMan":     "Industri manufaktur lainnya",
}

T1_LABELS = {
    "cpo":         "Harga CPO Rotterdam",
    "coal":        "Harga batu bara Newcastle",
    "nickel":      "Harga nikel LME",
    "copper":      "Harga tembaga LME",
    "rubber":      "Harga karet TSR20",
    "oilgas":      "Harga minyak Brent crude",
    "electronics": "Indeks harga semikonduktor",
}
T3_LABELS = {
    "food_bev_tobacco": "Makanan, minuman & tembakau",
    "sandang":          "Pakaian & alas kaki",
    "spare_parts":      "Suku cadang kendaraan",
    "fuel":             "Bahan bakar kendaraan",
    "ict_equipment":    "Peralatan ICT & komunikasi",
    "household_equip":  "Peralatan rumah tangga",
    "cultural_rec":     "Budaya, olahraga & rekreasi",
}
T1_DESC = T1_LABELS
T3_DESC = T3_LABELS
TOP5 = {"CHN":"China","SGP":"Singapore","JPN":"Japan","USA":"United States","PHL":"Philippines"}

# ─── Card icons (two-tone inline SVG) ────────────────────────────────────────
_ICO_T1 = (
    '<svg width="22" height="22" viewBox="0 0 22 22" fill="none" '
    'style="vertical-align:middle;margin-right:5px;flex-shrink:0">'
    '<circle cx="11" cy="11" r="11" fill="#fde8d0"/>'
    '<polyline points="4,16 8,10 12,13 17,7" stroke="#e67e22" stroke-width="2.2" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="17" cy="7" r="2.8" fill="#e67e22"/>'
    '<circle cx="17" cy="7" r="1.2" fill="#fde8d0"/>'
    '</svg>'
)
_ICO_T2 = (
    '<svg width="22" height="22" viewBox="0 0 22 22" fill="none" '
    'style="vertical-align:middle;margin-right:5px;flex-shrink:0">'
    '<circle cx="11" cy="11" r="11" fill="#dbeafe"/>'
    '<circle cx="11" cy="11" r="7" stroke="#2563eb" stroke-width="1.6" fill="none"/>'
    '<ellipse cx="11" cy="11" rx="3.2" ry="7" stroke="#2563eb" stroke-width="1.3" fill="none"/>'
    '<line x1="4" y1="11" x2="18" y2="11" stroke="#2563eb" stroke-width="1.3"/>'
    '<circle cx="11" cy="5" r="1.8" fill="#2563eb"/>'
    '</svg>'
)
_ICO_T3 = (
    '<svg width="22" height="22" viewBox="0 0 22 22" fill="none" '
    'style="vertical-align:middle;margin-right:5px;flex-shrink:0">'
    '<rect x="1" y="1" width="20" height="20" rx="6" fill="#ede9fe"/>'
    '<path d="M7 10 H15 L14 18 H8 Z" fill="#7c3aed" opacity="0.25"/>'
    '<path d="M7 10 H15 L14 18 H8 Z" stroke="#7c3aed" stroke-width="1.5" '
    'stroke-linejoin="round" fill="none"/>'
    '<path d="M9 10 Q9 6.5 11 6.5 Q13 6.5 13 10" stroke="#7c3aed" stroke-width="1.8" '
    'stroke-linecap="round" fill="none"/>'
    '<circle cx="9.5" cy="13" r="1" fill="#7c3aed"/>'
    '<circle cx="12.5" cy="13" r="1" fill="#7c3aed"/>'
    '</svg>'
)

# ─── Cached loaders ───────────────────────────────────────────────────────────
@st.cache_data
def load_labels():
    lo   = pd.read_csv(os.path.join(ROOT, "rawdata", "lo.csv"))
    lo   = lo[~lo["id"].isin([9200,9500,9600,9700,9900])]
    raw  = lo.drop_duplicates("id").set_index("id")["id_label"]
    prov_map = raw.str.title().to_dict()
    upper_id = {v: k for k, v in raw.to_dict().items()}
    try:
        io52     = pd.read_csv(os.path.join(ROOT, "data","cache","io52_sectors.csv"))
        sect_map = io52.set_index("io52_idx")["io52_name"].to_dict()
    except FileNotFoundError:
        sect_map = {i: f"Sector {i}" for i in range(1,53)}
    return prov_map, upper_id, sect_map

@st.cache_data
def load_geo():
    if not os.path.exists(GEO_PATH):
        return None
    import geopandas as gpd
    gdf  = gpd.read_file(GEO_PATH)
    prov = gdf.dissolve(by="province", as_index=False)[["province","geometry"]]
    return json.loads(prov.to_json())

@st.cache_data
def load_weights():
    p = os.path.join(ROOT,"data","cache","theme2","export_weights_52_2023.csv")
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

def _load_spe_meta():
    p = os.path.join(ROOT,"data","cache","theme3","spe_meta.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}

_ID_MONTHS = {
    "01":"Januari","02":"Februari","03":"Maret","04":"April",
    "05":"Mei","06":"Juni","07":"Juli","08":"Agustus",
    "09":"September","10":"Oktober","11":"November","12":"Desember",
    "January":"Januari","February":"Februari","March":"Maret","April":"April",
    "May":"Mei","June":"Juni","July":"Juli","August":"Agustus",
    "September":"September","October":"Oktober","November":"November","December":"Desember",
}

def _fmt_period(p):
    """Format period string to Indonesian month-year. e.g. '2026M05' → 'Mei 2026'."""
    if not p:
        return "—"
    if isinstance(p, str) and "M" in p:
        yr, mo = p.split("M")
        return f"{_ID_MONTHS.get(mo, mo)} {yr}"
    if isinstance(p, str) and "-" in p and len(p) == 7:
        yr, mo = p.split("-")
        return f"{_ID_MONTHS.get(mo, mo)} {yr}"
    return str(p)

def data_vintage_bar(periods):
    """Render a compact row showing release dates for T1/T2/T3."""
    p = periods or {}

    # T1 — commodity prices: period from aggregation meta
    t1_str = _fmt_period(p.get("theme1"))

    # T2 — WEO release name (e.g. "WEO April 2026"), not download date
    t2_raw = p.get("theme2")
    if isinstance(t2_raw, dict):
        cur = t2_raw.get("current", "")
        pri = t2_raw.get("prior", "")
        # Translate month names inside the WEO label
        for en, id_ in _ID_MONTHS.items():
            cur = cur.replace(en, id_)
            pri = pri.replace(en, id_)
        t2_str = f"{cur} vs {pri}"
    else:
        t2_str = _fmt_period(t2_raw)

    # T3 — SPE BI release name from spe_meta.json (vintage_month + vintage_year)
    spe = _load_spe_meta()
    if spe.get("vintage_month") and spe.get("vintage_year"):
        mo_id = _ID_MONTHS.get(spe["vintage_month"], spe["vintage_month"])
        t3_str = f"Survei Penjualan Eceran BI — {mo_id} {spe['vintage_year']}"
    else:
        t3_str = _fmt_period(p.get("theme3"))

    chip = (
        'style="background:var(--surface);border:1px solid var(--line);'
        'border-radius:5px;padding:2px 8px;font-size:10.5px;color:var(--muted);'
        'white-space:nowrap"'
    )
    lbl = 'style="font-size:10px;font-weight:700;color:var(--navy-3);margin-right:3px"'
    return (
        f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;margin-bottom:8px">'
        f'<span {chip}><span {lbl}>Harga komoditas</span>{t1_str}</span>'
        f'<span {chip}><span {lbl}>WEO IMF</span>{t2_str}</span>'
        f'<span {chip}><span {lbl}>SPE BI</span>{t3_str}</span>'
        f'</div>'
    )


def _parse_dt(s):
    """Parse ISO or loose date string to Indonesian date string."""
    if not s:
        return None
    try:
        from datetime import datetime, timezone
        s = str(s).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S-%f"):
            try:
                dt = datetime.strptime(s, fmt)
                return f"{dt.day} {_ID_MONTHS[f'{dt.month:02d}']} {dt.year}"
            except ValueError:
                pass
        # fallback: just take the date part
        dt = datetime.fromisoformat(s[:19])
        return f"{dt.day} {_ID_MONTHS[f'{dt.month:02d}']} {dt.year}"
    except Exception:
        return s


def _note_html(lines):
    """Render a small muted note block below a shock card."""
    inner = "<br>".join(lines)
    return (f'<div style="font-size:9.5px;color:var(--muted);'
            f'margin-top:0;margin-bottom:10px;line-height:1.5;padding:0 2px">'
            f'{inner}</div>')


@st.cache_data
def load_shock_notes():
    """Read cache metadata files and return per-theme note lines."""
    cache = os.path.join(ROOT, "data", "cache")
    notes = {}

    # ── T1 ──────────────────────────────────────────────────────────────────
    wb_p  = os.path.join(cache, "theme1", "wb_pinksheet_meta.json")
    fr_p  = os.path.join(cache, "theme1", "fred_IY3344_meta.json")
    t1_lines = ["<b>Sumber:</b> World Bank Pink Sheet (6 komoditas) &amp; FRED (elektronik)",
                "Shock = YoY% dikurangi rata-rata 48 bulan sebelumnya (basis 4-tahun)"]
    if os.path.exists(wb_p):
        with open(wb_p) as f: wb = json.load(f)
        notice = wb.get("file_update_notice", "")
        # "Updated on June 02, 2026" → parse it
        try:
            from datetime import datetime
            dt = datetime.strptime(notice.replace("Updated on ","").strip(), "%B %d, %Y")
            wb_rel = f"{dt.day} {_ID_MONTHS[f'{dt.month:02d}']} {dt.year}"
        except Exception:
            wb_rel = notice
        dl = _parse_dt(wb.get("downloaded_at"))
        t1_lines.append(f"Rilis World Bank: {wb_rel} · Diunduh: {dl}")
    if os.path.exists(fr_p):
        with open(fr_p) as f: fr = json.load(f)
        fr_rel = _parse_dt(fr.get("last_updated"))
        t1_lines.append(f"FRED diperbarui: {fr_rel}")
    notes["t1"] = t1_lines

    # ── T2 ──────────────────────────────────────────────────────────────────
    weo_p = os.path.join(cache, "theme2", "weo_meta.json")
    ct_p  = os.path.join(cache, "theme2", "comtrade_meta.json")
    ew_p  = os.path.join(cache, "theme2", "export_weights_meta.json")
    t2_lines = ["<b>Sumber:</b> WEO IMF (pertumbuhan mitra) &amp; UN Comtrade (bobot ekspor)"]
    # WEO release name comes from aggregation_meta periods
    agg_mp = os.path.join(ROOT, "data", "output", "aggregation_meta.json")
    if os.path.exists(agg_mp):
        with open(agg_mp) as f: am = json.load(f)
        t2_p = am.get("periods", {}).get("theme2", {})
        cur = t2_p.get("current", "") if isinstance(t2_p, dict) else str(t2_p)
        pri = t2_p.get("prior", "")   if isinstance(t2_p, dict) else ""
        for en, id_ in _ID_MONTHS.items():
            cur = cur.replace(en, id_)
            pri = pri.replace(en, id_)
        if cur:
            t2_lines.append(f"Rilis WEO: {cur}" + (f" vs {pri}" if pri else ""))
    if os.path.exists(ct_p):
        with open(ct_p) as f: ct = json.load(f)
        dl = _parse_dt(ct.get("downloaded_at"))
        t2_lines.append(f"Data perdagangan: {ct.get('period','2023')} · Diunduh: {dl}")
    notes["t2"] = t2_lines

    # ── T3 ──────────────────────────────────────────────────────────────────
    spe = _load_spe_meta()
    t3_lines = ["<b>Sumber:</b> Survei Penjualan Eceran (SPE), Bank Indonesia",
                "Shock = YoY% dikurangi rata-rata 48 bulan sebelumnya (basis 4-tahun)"]
    if spe.get("vintage_month") and spe.get("vintage_year"):
        mo_id = _ID_MONTHS.get(spe["vintage_month"], spe["vintage_month"])
        t3_lines.append(f"Rilis SPE BI: {mo_id} {spe['vintage_year']}")
    dl = _parse_dt(spe.get("downloaded_at"))
    if dl:
        t3_lines.append(f"Diunduh: {dl}")
    notes["t3"] = t3_lines

    return notes


PROV_MAP, UPPER_ID, SECT_MAP = load_labels()

SECT_LONG = {
     1: "Tanaman pangan",
     2: "Tanaman hortikultura",
     3: "Perkebunan",
     4: "Peternakan",
     5: "Jasa pertanian",
     6: "Kehutanan",
     7: "Perikanan",
     8: "Pertambangan batu bara",
     9: "Minyak, gas & panas bumi",
    10: "Bijih besi & mineral logam",
    11: "Pertambangan lainnya",
    12: "Industri makanan & minuman",
    13: "Industri tembakau",
    14: "Industri tekstil",
    15: "Industri kulit & alas kaki",
    16: "Industri kayu & produk kayu",
    17: "Industri kertas & percetakan",
    18: "Industri produk non-logam",
    19: "Industri batu bara & migas olahan",
    20: "Industri kimia",
    21: "Industri karet & plastik",
    22: "Industri logam dasar",
    23: "Industri produk logam",
    24: "Industri mesin & peralatan",
    25: "Industri alat transportasi",
    26: "Industri furnitur",
    27: "Industri manufaktur lainnya",
    28: "Listrik",
    29: "Gas kota",
    30: "Pengelolaan sampah & limbah",
    31: "Konstruksi",
    32: "Perdagangan kendaraan",
    33: "Perdagangan lainnya",
    34: "Transportasi rel",
    35: "Transportasi darat",
    36: "Transportasi laut",
    37: "Transportasi sungai & danau",
    38: "Transportasi udara",
    39: "Jasa transportasi & pergudangan",
    40: "Penyediaan akomodasi",
    41: "Penyediaan makan & minum",
    42: "Telekomunikasi",
    43: "Perbankan & keuangan",
    44: "Asuransi",
    45: "Jasa keuangan lainnya",
    46: "Jasa penunjang keuangan",
    47: "Real estat",
    48: "Jasa perusahaan",
    49: "Administrasi pemerintahan",
    50: "Pendidikan",
    51: "Kesehatan & sosial",
    52: "Jasa lainnya",
}

PROV_SHORT = {
    "Aceh":                        "ACEH",
    "Sumatera Utara":              "SUMUT",
    "Sumatera Barat":              "SUMBAR",
    "Riau":                        "RIAU",
    "Jambi":                       "JAMBI",
    "Sumatera Selatan":            "SUMSEL",
    "Bengkulu":                    "BENGKULU",
    "Lampung":                     "LAMPUNG",
    "Kepulauan Bangka Belitung":   "BABEL",
    "Kepulauan Riau":              "KEPRI",
    "Dki Jakarta":                 "DKI",
    "Jawa Barat":                  "JABAR",
    "Jawa Tengah":                 "JATENG",
    "Di Yogyakarta":               "DIY",
    "Jawa Timur":                  "JATIM",
    "Banten":                      "BANTEN",
    "Bali":                        "BALI",
    "Nusa Tenggara Barat":         "NTB",
    "Nusa Tenggara Timur":         "NTT",
    "Kalimantan Barat":            "KALBAR",
    "Kalimantan Tengah":           "KALTENG",
    "Kalimantan Selatan":          "KALSEL",
    "Kalimantan Timur":            "KALTIM",
    "Kalimantan Utara":            "KALUT",
    "Sulawesi Utara":              "SULUT",
    "Sulawesi Tengah":             "SULTENG",
    "Sulawesi Selatan":            "SULSEL",
    "Sulawesi Tenggara":           "SULTRA",
    "Gorontalo":                   "GORONTALO",
    "Sulawesi Barat":              "SULBAR",
    "Maluku":                      "MALUKU",
    "Maluku Utara":                "MALUT",
    "Papua Barat":                 "PAPBAR",
    "Papua Barat Daya":            "PAPBARDA",
    "Papua":                       "PAPUA",
    "Papua Selatan":               "PAPSEL",
    "Papua Tengah":                "PAPTENG",
    "Papua Pegunungan":            "PAPGUN",
}

def _norm(name):
    u = name.upper().strip()
    return "DI YOGYAKARTA" if u == "DAERAH ISTIMEWA YOGYAKARTA" else u

# Colorscale matching HTML's cgeHeat / simMapColor: red → neutral → green
CGE_SCALE = [
    [0.0,  "rgb(210,59,52)"],
    [0.5,  "#f1f4f8"],
    [1.0,  "rgb(31,157,87)"],
]

# ─── HTML helpers ─────────────────────────────────────────────────────────────
def sl(text):
    """Section label matching HTML .section-label style."""
    return (f'<div class="section-label">{text}'
            f'<span class="ln"></span></div>')

def methbar(text):
    """Blue methodology note bar matching HTML .methbar."""
    icon = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none">'
            '<circle cx="12" cy="12" r="10" stroke="#2563eb" stroke-width="1.6"/>'
            '<path d="M12 8v0M12 11v5" stroke="#2563eb" stroke-width="1.8" stroke-linecap="round"/>'
            '</svg>')
    return f'<div class="methbar">{icon}<div>{text}</div></div>'

def simbig(items):
    """Stats bar matching HTML .simbig. items = [(value_html, label), ...]"""
    parts = []
    for i,(v,l) in enumerate(items):
        parts.append(f'<div class="sb"><div class="n">{v}</div><div class="l">{l}</div></div>')
        if i < len(items)-1:
            parts.append('<div class="arrow">·</div>')
    return f'<div class="simbig">{"".join(parts)}</div>'

def theme_breakdown(totals):
    """Three-card theme breakdown. totals = {'t1': float, 't2': float, 't3': float}"""
    labels = {"t1":"Tema 1 · Harga komoditas","t2":"Tema 2 · Mitra dagang","t3":"Tema 3 · Permintaan domestik"}
    cards = []
    for k in ("t1","t2","t3"):
        v = totals.get(k, 0.0)
        if v < 0:
            clr, badge = "var(--high)", '<span class="badge high">tekanan</span>'
        elif v > 0:
            clr, badge = "var(--low)", '<span class="badge low">dukungan</span>'
        else:
            clr, badge = "var(--muted)", '<span class="badge neut">netral</span>'
        sign = "+" if v > 0 else ""
        cards.append(
            f'<div class="theme-card">'
            f'<div class="tl">{labels[k]}</div>'
            f'<div class="tv" style="color:{clr}">{sign}{v:,.0f}</div>'
            f'{badge}</div>'
        )
    return f'<div class="theme-grid">{"".join(cards)}</div>'

# ─── Visualisation helpers ────────────────────────────────────────────────────
def province_map(prov_dict, title, height=220, unit="ΔL (tenaga kerja)", zoom=2.8):
    geo = load_geo()
    if not geo:
        return None
    rows = [{"province": f["properties"]["province"],
             "value": prov_dict.get(UPPER_ID.get(_norm(f["properties"]["province"])), 0.0)}
            for f in geo["features"]]
    df  = pd.DataFrame(rows)
    fmt = ":.2f" if unit.startswith("E") else ":,.0f"
    fig = px.choropleth_mapbox(
        df, geojson=geo,
        locations="province", featureidkey="properties.province",
        color="value",
        color_continuous_scale=CGE_SCALE, color_continuous_midpoint=0,
        mapbox_style="carto-positron",
        zoom=zoom, center={"lat":-2.5,"lon":118}, opacity=0.88,
        hover_name="province",
        hover_data={"value": fmt},
        labels={"value": unit},
    )
    fig.update_layout(
        height=height, margin={"r":0,"t":26,"l":0,"b":0},
        font_family="Inter",
        title=dict(text=title, font_size=11,
                   font_color="#1f2d3d", font_family="Plus Jakarta Sans", x=0.01),
        coloraxis_colorbar=dict(
            title=unit,
            tickformat="," if not unit.startswith("E") else ".2f",
            lenmode="fraction", len=0.55, thickness=9,
            tickfont_size=9,
        ),
        paper_bgcolor="white",
    )
    return fig


def heatmap(mat, sect_order, prov_order, title, height=720, unit="ΔL", show_ylabels=True):
    df = pd.DataFrame(
        mat,
        index=[SECT_LONG.get(s, SECT_MAP.get(s, f"s{s:02d}")) for s in sect_order],
        columns=[PROV_SHORT.get(PROV_MAP.get(p,str(p)), PROV_MAP.get(p,str(p))) for p in prov_order],
    )
    fig = px.imshow(df, color_continuous_scale=CGE_SCALE,
                    color_continuous_midpoint=0,
                    labels={"color": unit},
                    aspect="auto", height=height, title=title)
    fig.update_layout(
        margin=dict(l=220 if show_ylabels else 4, r=20, t=38, b=90),
        font_family="Inter",
        title_font_size=12, title_font_color="#1f2d3d",
        title_font_family="Plus Jakarta Sans",
        coloraxis_colorbar=dict(
            orientation="h", x=0.5, y=-0.13,
            xanchor="center", yanchor="top",
            title=dict(text=unit, side="bottom"),
            tickformat="," if unit=="ΔL" else ".2f",
            tickfont_size=9, thickness=10,
            lenmode="fraction", len=0.8,
        ),
        xaxis=dict(tickfont_size=8, tickangle=-90, tickfont_color="#64748b"),
        yaxis=dict(tickfont_size=8, tickfont_color="#334155",
                   showticklabels=show_ylabels, dtick=1),
        paper_bgcolor="white", plot_bgcolor="white",
    )
    return fig




def _prov_dict(agg, key):
    """Province → sum of ΔL over sectors."""
    mat = agg.get(key)
    return {} if mat is None else dict(zip(agg["prov_order"], mat.sum(axis=0)))


def _prov_pct_dict(agg, dl_key):
    """Province → sum of E (%) over sectors  (E = x × η, raw % change)."""
    e_mat = agg.get(f"e_{dl_key}")
    if e_mat is None:
        return {}
    return dict(zip(agg["prov_order"], e_mat.sum(axis=0)))


def _mat_and_label(agg, dl_key, use_e):
    """Return the right matrix + unit string for the chosen view."""
    if use_e:
        e_key = f"e_{dl_key}"
        mat   = agg.get(e_key)
        unit  = "E (%)"
    else:
        mat  = agg.get(dl_key)
        unit = "ΔL (tenaga kerja)"
    return mat, unit


def _view_toggle(tab_key):
    """Compact radio for ΔL vs E%."""
    return st.radio(
        "Tampilan",
        ["ΔL  (tenaga kerja)", "E  (% perubahan)"],
        horizontal=True,
        key=f"view_{tab_key}",
        label_visibility="collapsed",
    ).startswith("E")

# ─── Shock display helpers ────────────────────────────────────────────────────
def _val_html(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '<span style="color:var(--muted-2)">—</span>'
    c = "var(--low)" if v > 0 else ("var(--high)" if v < 0 else "var(--muted)")
    s = f"+{v:.2f}" if v > 0 else f"{v:.2f}"
    return f'<span style="color:{c};font-family:\'Plus Jakarta Sans\',sans-serif;font-weight:700;font-size:13px">{s} pp</span>'


_CARD_H = "240px"   # fixed height shared by all three shock cards

def shock_card(shocks, prefix, labels, color, icon, name, descs=None, formula=""):
    rows = "".join(
        f'<tr>'
        f'<td style="padding:0 5px;border-bottom:1px solid var(--line-2)">'
        f'  <div style="font-size:14px;color:var(--ink);line-height:1.1">{lbl}</div>'
        f'</td>'
        f'<td style="padding:1px 5px;text-align:right;border-bottom:1px solid var(--line-2);white-space:nowrap;vertical-align:middle">'
        f'  {_val_html(shocks.get(f"{prefix}_{code}"))}'
        f'</td>'
        f'</tr>'
        for code, lbl in labels.items()
    )
    formula_html = (
        f'<div style="font-size:9.5px;color:#22406e;background:var(--accent-soft);'
        f'border-radius:4px;padding:2px 6px;margin-bottom:5px">{formula}</div>'
    ) if formula else ""
    return (
        f'<div class="card" style="border-top:3px solid {color};height:{_CARD_H};'
        f'display:flex;flex-direction:column;box-sizing:border-box;">'
        f'<div style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:12px;font-weight:800;'
        f'color:var(--navy);margin-bottom:4px;display:flex;align-items:center">{icon}{name}</div>'
        f'{formula_html}'
        f'<div style="overflow-y:auto;flex:1">'
        f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
        f'</div>'
        f'</div>'
    )


def t2_shock_card(shocks):
    t2 = {k.replace("t2_",""):v for k,v in shocks.items() if k.startswith("t2_")}
    formula_html = (f'<div style="font-size:9.5px;color:#22406e;background:var(--accent-soft);'
                    f'border-radius:4px;padding:2px 6px;margin-bottom:5px">'
                    f'Kondisi ekonomi mitra dagang berdasarkan revisi WEO dikalikan bobot ekspor per sektor</div>')
    title = (f'<div style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:12px;font-weight:800;'
             f'color:var(--navy);margin-bottom:4px;display:flex;align-items:center">{_ICO_T2}T2 — Kondisi Ekonomi Mitra Dagang</div>')
    if not t2:
        return (f'<div class="card card-t2" style="height:{_CARD_H};box-sizing:border-box;">'
                f'{title}{formula_html}'
                f'<div style="color:var(--muted);font-size:11px">Belum ada data T2.</div>'
                f'</div>')
    rows = "".join(
        f'<tr>'
        f'<td style="padding:0 5px;border-bottom:1px solid var(--line-2)">'
        f'  <div style="font-size:14px;color:var(--ink);line-height:1.1">{T2_LABELS.get(sec, sec)}</div>'
        f'</td>'
        f'<td style="padding:1px 5px;text-align:right;border-bottom:1px solid var(--line-2);white-space:nowrap;vertical-align:middle">'
        f'  {_val_html(v)}'
        f'</td>'
        f'</tr>'
        for sec, v in sorted(t2.items(), key=lambda x: x[1])
    )
    return (
        f'<div class="card card-t2" style="height:{_CARD_H};display:flex;flex-direction:column;'
        f'box-sizing:border-box;">'
        f'{title}{formula_html}'
        f'<div style="overflow-y:auto;flex:1">'
        f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
        f'</div>'
        f'</div>'
    )


def simbig_from_agg(agg, key):
    """Render a .simbig stats row from an agg dict key."""
    mat = agg.get(key)
    if mat is None:
        return
    total = mat.sum()
    ps = pd.Series(mat.sum(axis=0), index=[PROV_MAP.get(p,str(p)) for p in agg["prov_order"]])
    ss = pd.Series(mat.sum(axis=1), index=[SECT_LONG.get(s, SECT_MAP.get(s,f"s{s:02d}")) for s in agg["sect_order"]])
    c_total = "var(--high)" if total < 0 else ("var(--low)" if total > 0 else "var(--muted)")
    sign = "+" if total > 0 else ""
    items = [
        (f'<span style="color:{c_total}">{sign}{total:,.0f}</span>', "Net ΔL (tenaga kerja)"),
        (f'<span style="font-size:17px;color:var(--navy-3)">{ps.idxmin()}</span>',
         f'{ps.min():+,.0f} tenaga kerja'),
        (f'<span style="font-size:14px;color:var(--navy-3)">{ss.idxmin()}</span>',
         f'{ss.min():+,.0f} tenaga kerja'),
        (f'<span style="color:var(--high)">{(ps<0).sum()}</span>&thinsp;/ 34',
         "provinsi terdampak negatif"),
    ]
    st.markdown(simbig(items), unsafe_allow_html=True)


# ─── Session state ────────────────────────────────────────────────────────────
for _k,_v in [("agg",None),("meta",{}),("refreshed",False),("sim_result",None)]:
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _load_disk():
    out = os.path.join(ROOT,"data","output")
    if not os.path.exists(os.path.join(out,"overall.npy")):
        return None
    _, prov_order, sect_order = _load_L0()
    d = {"prov_order":prov_order,"sect_order":sect_order}
    for fn in os.listdir(out):
        if fn.endswith(".npy"):
            d[fn[:-4]] = np.load(os.path.join(out, fn))
    meta = {}
    mp = os.path.join(out,"aggregation_meta.json")
    if os.path.exists(mp):
        with open(mp) as f: meta = json.load(f)
    if "shocks" not in d:
        d["shocks"] = meta.get("shocks_used", {})
    if "periods" not in d:
        d["periods"] = meta.get("periods", {})
    # Reconstruct any missing e_ matrices from dL / L0 * 100
    L0 = d.get("L0_matrix")
    if L0 is not None:
        dL_keys = [k for k in d if not k.startswith("e_")
                   and k not in ("L0_matrix","prov_order","sect_order","shocks","periods")]
        for k in dL_keys:
            e_key = f"e_{k}"
            if e_key not in d:
                with np.errstate(divide="ignore", invalid="ignore"):
                    d[e_key] = np.where(L0 > 0, d[k] / L0 * 100.0, 0.0)
    return d, meta


if st.session_state.agg is None:
    res = _load_disk()
    if res:
        st.session_state.agg, st.session_state.meta = res

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### EPM")
    if st.button("🔄 Perbarui Data", type="primary", use_container_width=True):
        with st.spinner("Mengambil & menghitung…"):
            try:
                rr  = refresh_run(verbose=False)
                agg = decompose(rr)
                st.session_state.agg      = agg
                st.session_state.meta     = agg.get("periods", {})
                st.session_state.refreshed = True
                st.success("Selesai.")
            except Exception as e:
                st.error(str(e))
    st.divider()
    meta = st.session_state.meta or {}
    p    = meta.get("periods", meta)
    for lbl, k in [("T1","theme1"),("T3","theme3")]:
        if p.get(k): st.caption(f"**{lbl}** `{p[k]}`")
    v2 = p.get("theme2")
    if isinstance(v2, dict):
        st.caption(f"**T2** `{v2.get('prior','?')}` → `{v2.get('current','?')}`")
    elif v2:
        st.caption(f"**T2** `{v2}`")

# ─── Banner ───────────────────────────────────────────────────────────────────
agg  = st.session_state.agg
n_sh = len(agg["shocks"]) if agg and "shocks" in agg else 0
n_pr = int((pd.Series(agg.get("overall", np.zeros((52,34))).sum(axis=0)) < 0).sum()) if agg else 0

st.markdown(f"""
<div class="banner">
  <div class="banner-left">
    <h1><svg width="44" height="44" viewBox="0 0 44 44" fill="none" style="vertical-align:middle;margin-right:10px;margin-bottom:3px;flex-shrink:0">
      <rect width="44" height="44" rx="12" fill="#1a2744"/>
      <rect x="3" y="3" width="38" height="38" rx="9" fill="none" stroke="#253659" stroke-width="1"/>
      <path d="M8 31 A14 14 0 1 1 36 31" stroke="#1e3a5f" stroke-width="5.5" stroke-linecap="round" fill="none"/>
      <path d="M8 31 A14 14 0 0 1 32 15" stroke="#3b82f6" stroke-width="5.5" stroke-linecap="round" fill="none"/>
      <circle cx="32" cy="15" r="3.5" fill="#93c5fd"/>
      <circle cx="32" cy="15" r="1.6" fill="#1a2744"/>
      <line x1="22" y1="29" x2="31" y2="16" stroke="#93c5fd" stroke-width="1.8" stroke-linecap="round"/>
      <circle cx="22" cy="29" r="4.2" fill="#3b82f6"/>
      <circle cx="22" cy="29" r="1.9" fill="#1a2744"/>
    </svg>Employment Pressure Monitor</h1>
    <p>Monitor Tekanan Sektor-Provinsi &nbsp;·&nbsp; Kemnaker &nbsp;·&nbsp;
       IndoTERM CGE &nbsp;·&nbsp; 52 Sektor × 34 Provinsi</p>
  </div>
  <div class="banner-right">
    <div class="bstat">Shocks aktif: <b>{n_sh} / 38</b></div>
    <div class="bstat">Provinsi tertekan: <b>{n_pr} / 34</b></div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_ov, tab_t1, tab_t2, tab_t3, tab_sim, tab_met = st.tabs([
    "📊 Ringkasan",
    "Harga Komoditas Utama",
    "Kondisi Ekonomi Mitra Dagang",
    "Kondisi Permintaan Domestik",
    "🎛️ Simulasi",
    "📖 Metodologi & Data",
])

NO_DATA = "Klik **🔄 Perbarui Data** di sidebar untuk memuat data terbaru."

# ═══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ov:
    if agg is None:
        st.info(NO_DATA)
    else:
        shocks = agg.get("shocks", {})

        # ── Stats row ─────────────────────────────────────────────────────────
        simbig_from_agg(agg, "overall")

        # ── Shock inputs ──────────────────────────────────────────────────────
        st.markdown(sl("Perubahan kondisi ekonomi terkini dibandingkan tahun sebelumnya"), unsafe_allow_html=True)
        _snotes = load_shock_notes()
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown(shock_card(shocks,"t1",T1_LABELS,"#e67e22",_ICO_T1,"T1 — Harga Komoditas Utama",
                        descs=T1_DESC,
                        formula="Perubahan harga komoditas internasional terhadap periode sebelumnya"),
                        unsafe_allow_html=True)
            st.markdown(_note_html(_snotes.get("t1",[])), unsafe_allow_html=True)
        with sc2:
            st.markdown(t2_shock_card(shocks), unsafe_allow_html=True)
            st.markdown(_note_html(_snotes.get("t2",[])), unsafe_allow_html=True)
        with sc3:
            st.markdown(shock_card(shocks,"t3",T3_LABELS,"#7c3aed",_ICO_T3,"T3 — Kondisi Permintaan Domestik",
                        descs=T3_DESC,
                        formula="Perubahan indeks pengeluaran riil rumah tangga per kategori IPR"),
                        unsafe_allow_html=True)
            st.markdown(_note_html(_snotes.get("t3",[])), unsafe_allow_html=True)

        # ── View toggle ───────────────────────────────────────────────────────
        use_e = _view_toggle("ov")
        unit  = "E (%)" if use_e else "ΔL (tenaga kerja)"

        # ── Province maps 2×2 ────────────────────────────────────────────────
        st.markdown(sl("Peta Provinsi"), unsafe_allow_html=True)
        p1, p2 = st.columns(2)
        with p1:
            pd_ = _prov_pct_dict(agg,"overall") if use_e else _prov_dict(agg,"overall")
            fig = province_map(pd_, "Dampak Keseluruhan  (T1 + T2 + T3)", unit=unit)
            if fig: st.plotly_chart(fig, use_container_width=True, key="ov_map_overall")
        with p2:
            pd_ = _prov_pct_dict(agg,"t1_total") if use_e else _prov_dict(agg,"t1_total")
            fig = province_map(pd_, "Dampak T1 — Harga Komoditas Utama", unit=unit)
            if fig: st.plotly_chart(fig, use_container_width=True, key="ov_map_t1")
        p3, p4 = st.columns(2)
        with p3:
            pd_ = _prov_pct_dict(agg,"t2_total") if use_e else _prov_dict(agg,"t2_total")
            fig = province_map(pd_, "Dampak T2 — Perubahan Kondisi Ekonomi Mitra Dagang", unit=unit)
            if fig: st.plotly_chart(fig, use_container_width=True, key="ov_map_t2")
        with p4:
            pd_ = _prov_pct_dict(agg,"t3_total") if use_e else _prov_dict(agg,"t3_total")
            fig = province_map(pd_, "Dampak T3 — Kondisi Permintaan Domestik", unit=unit)
            if fig: st.plotly_chart(fig, use_container_width=True, key="ov_map_t3")

        # ── Heatmaps ─────────────────────────────────────────────────────────
        st.markdown(sl("Matriks 52 × 34 Sektor-Provinsi"), unsafe_allow_html=True)
        _ov_pairs = [
            ("overall",  "Dampak Keseluruhan — semua tema"),
            ("t1_total", "Dampak T1 Total — harga komoditas"),
            ("t2_total", "Dampak T2 Total — perubahan kondisi ekonomi mitra dagang"),
            ("t3_total", "Dampak T3 Total — kondisi permintaan domestik"),
        ]
        for i in range(0, len(_ov_pairs), 2):
            c1, c2 = st.columns([3, 2])
            for col, show_y, (dk, title) in zip(
                [c1, c2], [True, False], _ov_pairs[i:i+2]
            ):
                mat, u = _mat_and_label(agg, dk, use_e)
                if mat is not None:
                    with col:
                        st.plotly_chart(
                            heatmap(mat, agg["sect_order"], agg["prov_order"],
                                    f"{title}  [{u}]", unit=u, show_ylabels=show_y),
                            use_container_width=True, key=f"ov_heat_{dk}")

# ═══════════════════════════════════════════════════════════════════════════════
# COMMODITIES (T1)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_t1:
    if agg is None:
        st.info(NO_DATA)
    else:
        shocks = agg.get("shocks", {})
        simbig_from_agg(agg, "t1_total")
        st.markdown(methbar(
            "Setiap bulan, pertumbuhan harga tahunan masing-masing komoditas ekspor utama Indonesia "
            "dibandingkan dengan rata-rata pertumbuhan harga selama 4 tahun sebelumnya. "
            "Angka yang ditampilkan mencerminkan seberapa jauh kondisi harga saat ini menyimpang dari kebiasaan. "
            "Jika harga suatu komoditas naik lebih cepat dari tren historisnya, sektor yang bergantung pada komoditas tersebut "
            "mendapat dorongan penyerapan tenaga kerja. "
            "Sebaliknya, harga yang tumbuh lebih lambat dari tren — atau bahkan turun — "
            "menandakan tekanan yang dapat berujung pada pengurangan tenaga kerja di sektor terkait."
        ), unsafe_allow_html=True)

        use_e = _view_toggle("t1")
        unit  = "E (%)" if use_e else "ΔL (tenaga kerja)"

        sc, mp = st.columns([1, 2])
        with sc:
            st.markdown(sl("Input Shock x<sub>j</sub>"), unsafe_allow_html=True)
            st.markdown(shock_card(shocks,"t1",T1_LABELS,"#e67e22",_ICO_T1,"T1 — Harga Komoditas Utama",
                        descs=T1_DESC,
                        formula="Perubahan harga komoditas internasional terhadap periode sebelumnya"),
                        unsafe_allow_html=True)
            st.markdown(_note_html(load_shock_notes().get("t1",[])), unsafe_allow_html=True)
        with mp:
            pd_ = _prov_pct_dict(agg,"t1_total") if use_e else _prov_dict(agg,"t1_total")
            fig = province_map(pd_, "T1 — Dampak per Provinsi", height=300, unit=unit, zoom=3.2)
            if fig: st.plotly_chart(fig, use_container_width=True, key="t1_map")

        st.markdown(sl("Matriks Per Komoditas  (52 × 34)"), unsafe_allow_html=True)
        t1_kl = [("t1_total", "T1 Total — semua komoditas")] + \
                [(f"t1_{c}", lbl) for c, lbl in T1_LABELS.items() if agg.get(f"t1_{c}") is not None]
        for i in range(0, len(t1_kl), 2):
            pair = t1_kl[i:i+2]
            cols = st.columns([3, 2])
            for j, (dl_key, lbl) in enumerate(pair):
                mat, u = _mat_and_label(agg, dl_key, use_e)
                if mat is not None:
                    with cols[j]:
                        st.plotly_chart(heatmap(mat, agg["sect_order"], agg["prov_order"],
                                                f"Dampak {lbl}  [{u}]", unit=u,
                                                show_ylabels=(j == 0)),
                                        use_container_width=True, key=f"t1_heat_{dl_key}")

# ═══════════════════════════════════════════════════════════════════════════════
# PARTNERS (T2)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_t2:
    if agg is None:
        st.info(NO_DATA)
    else:
        shocks = agg.get("shocks", {})
        simbig_from_agg(agg, "t2_total")
        st.markdown(methbar(
            "Setiap kali IMF menerbitkan edisi baru World Economic Outlook, proyeksi pertumbuhan ekonomi "
            "setiap negara mitra dagang Indonesia diperbarui. "
            "Perubahan yang ditampilkan mencerminkan selisih antara proyeksi terkini dan proyeksi edisi sebelumnya — "
            "jika suatu negara diproyeksikan tumbuh lebih tinggi dari perkiraan semula, "
            "permintaan mereka terhadap produk ekspor Indonesia cenderung meningkat. "
            "Dampak pada setiap sektor dihitung berdasarkan seberapa besar pangsa ekspor sektor tersebut "
            "ke negara yang bersangkutan — sektor dengan eksposur ekspor tinggi ke negara yang revisinya positif "
            "akan merasakan dampak yang lebih besar."
        ), unsafe_allow_html=True)

        use_e = _view_toggle("t2")
        unit  = "E (%)" if use_e else "ΔL (tenaga kerja)"

        sc, mp = st.columns([1, 2])
        with sc:
            st.markdown(sl("Input Shock x<sub>k</sub>"), unsafe_allow_html=True)
            st.markdown(t2_shock_card(shocks), unsafe_allow_html=True)
            st.markdown(_note_html(load_shock_notes().get("t2",[])), unsafe_allow_html=True)
        with mp:
            pd_ = _prov_pct_dict(agg,"t2_total") if use_e else _prov_dict(agg,"t2_total")
            fig = province_map(pd_, "T2 — Dampak per Provinsi", height=300, unit=unit, zoom=3.2)
            if fig: st.plotly_chart(fig, use_container_width=True, key="t2_map")

        st.markdown(sl("T2 Total  (52 × 34)"), unsafe_allow_html=True)
        mat, u = _mat_and_label(agg, "t2_total", use_e)
        if mat is not None:
            st.plotly_chart(heatmap(mat, agg["sect_order"], agg["prov_order"],
                                    f"Dampak T2 Total — perubahan kondisi ekonomi mitra dagang  [{u}]", unit=u),
                            use_container_width=True, key="t2_heat_total")

# ═══════════════════════════════════════════════════════════════════════════════
# DOMESTIC (T3)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_t3:
    if agg is None:
        st.info(NO_DATA)
    else:
        shocks = agg.get("shocks", {})
        simbig_from_agg(agg, "t3_total")
        st.markdown(methbar(
            "Survei Penjualan Eceran Bank Indonesia mengukur pertumbuhan pengeluaran riil rumah tangga "
            "per kategori barang setiap bulan. "
            "Perubahan yang ditampilkan mencerminkan seberapa jauh tingkat pengeluaran saat ini "
            "menyimpang dari rata-rata 4 tahun sebelumnya. "
            "Jika masyarakat membelanjakan lebih banyak dari kebiasaan pada suatu kategori, "
            "industri yang memproduksi atau mendistribusikan barang tersebut cenderung menyerap lebih banyak tenaga kerja. "
            "Sebaliknya, pengeluaran yang di bawah tren mengindikasikan perlambatan permintaan "
            "yang dapat menekan penyerapan tenaga kerja di sektor-sektor terkait."
        ),
                    unsafe_allow_html=True)

        use_e = _view_toggle("t3")
        unit  = "E (%)" if use_e else "ΔL (tenaga kerja)"

        sc, mp = st.columns([1, 2])
        with sc:
            st.markdown(sl("Input Shock x<sub>m</sub>"), unsafe_allow_html=True)
            st.markdown(shock_card(shocks,"t3",T3_LABELS,"#7c3aed",_ICO_T3,"T3 — Kondisi Permintaan Domestik (IPR)",
                        descs=T3_DESC,
                        formula="Perubahan indeks pengeluaran riil rumah tangga per kategori IPR"),
                        unsafe_allow_html=True)
            st.markdown(_note_html(load_shock_notes().get("t3",[])), unsafe_allow_html=True)
        with mp:
            pd_ = _prov_pct_dict(agg,"t3_total") if use_e else _prov_dict(agg,"t3_total")
            fig = province_map(pd_, "T3 — Dampak per Provinsi", height=300, unit=unit, zoom=3.2)
            if fig: st.plotly_chart(fig, use_container_width=True, key="t3_map")

        st.markdown(sl("Matriks Per Kategori IPR  (52 × 34)"), unsafe_allow_html=True)
        t3_kl = [("t3_total", "T3 Total — semua kategori IPR")] + \
                [(f"t3_{c}", lbl) for c, lbl in T3_LABELS.items() if agg.get(f"t3_{c}") is not None]
        for i in range(0, len(t3_kl), 2):
            pair = t3_kl[i:i+2]
            cols = st.columns([3, 2])
            for j, (dl_key, lbl) in enumerate(pair):
                mat, u = _mat_and_label(agg, dl_key, use_e)
                if mat is not None:
                    with cols[j]:
                        st.plotly_chart(heatmap(mat, agg["sect_order"], agg["prov_order"],
                                                f"Dampak {lbl}  [{u}]", unit=u,
                                                show_ylabels=(j == 0)),
                                        use_container_width=True, key=f"t3_heat_{dl_key}")

# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sim:
    st.markdown(methbar(
        "Simulasi ini memungkinkan Anda untuk mengatur sendiri besaran perubahan kondisi yang ingin diuji — "
        "baik perubahan harga komoditas ekspor, kondisi ekonomi negara mitra dagang, "
        "maupun pengeluaran rumah tangga per kategori barang. "
        "Masukkan angka dalam satuan persentase poin: positif berarti kondisi lebih baik dari tren normal, "
        "negatif berarti kondisi lebih buruk. "
        "Setelah selesai mengatur semua nilai yang ingin diuji, tekan tombol "
        "<b>Jalankan Simulasi</b> untuk melihat estimasi dampaknya pada penyerapan tenaga kerja "
        "di 52 sektor dan 34 provinsi Indonesia."
    ), unsafe_allow_html=True)

    st.markdown(sl("Input Perubahan Kondisi"), unsafe_allow_html=True)

    _hdr = (
        '<div style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:12px;font-weight:800;'
        'color:{c};border-bottom:2px solid {c};padding-bottom:.3rem;margin-bottom:.6rem">'
        '{ico}{lbl}</div>'
    )

    with st.form("sim_form"):
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown(_hdr.format(c="#e67e22", ico=_ICO_T1, lbl="T1 — Harga Komoditas"), unsafe_allow_html=True)
            t1_vals = {k: st.slider(lbl, -20.0, 20.0, 0.0, 0.5, key=f"sim_t1_{k}")
                       for k, lbl in T1_LABELS.items()}

        with c2:
            st.markdown(_hdr.format(c="#2563eb", ico=_ICO_T2, lbl="T2 — Mitra Dagang"), unsafe_allow_html=True)
            t2_vals = {iso: st.slider(name, -20.0, 20.0, 0.0, 0.5, key=f"sim_t2_{iso}")
                       for iso, name in TOP5.items()}

        with c3:
            st.markdown(_hdr.format(c="#7c3aed", ico=_ICO_T3, lbl="T3 — Permintaan Domestik"), unsafe_allow_html=True)
            t3_vals = {k: st.slider(lbl, -20.0, 20.0, 0.0, 0.5, key=f"sim_t3_{k}")
                       for k, lbl in T3_LABELS.items()}

        submitted = st.form_submit_button("▶  Jalankan Simulasi", type="primary", use_container_width=True)

    if submitted:
        try:
            st.session_state.sim_result = compute_custom(t1_vals, t2_vals, t3_vals)
        except Exception as e:
            st.error(f"Simulasi error: {e}")

    # ── Results ──────────────────────────────────────────────────────────────
    if st.session_state.sim_result is not None:
        agg_sim = st.session_state.sim_result
        dl  = agg_sim["dL"]
        E_  = agg_sim.get("e_overall", agg_sim.get("E", np.zeros_like(dl)))
        po  = agg_sim["prov_order"]
        so  = agg_sim["sect_order"]
        ps  = pd.Series(dl.sum(axis=0), index=[PROV_MAP.get(p,str(p)) for p in po])
        ss  = pd.Series(dl.sum(axis=1),
                        index=[SECT_LONG.get(s, SECT_MAP.get(s,f"s{s:02d}")) for s in so])

        total = dl.sum()
        c_t   = "var(--high)" if total < 0 else ("var(--low)" if total > 0 else "var(--muted)")
        sign  = "+" if total > 0 else ""
        st.markdown(simbig([
            (f'<span style="color:{c_t}">{sign}{total:,.0f}</span>',  "Net ΔL (tenaga kerja)"),
            (f'<span style="font-size:14px;color:var(--navy-3)">{ss.idxmin()}</span>',
             f'{ss.min():+,.0f} tenaga kerja'),
            (f'<span style="font-size:17px;color:var(--navy-3)">{ps.idxmin()}</span>',
             f'{ps.min():+,.0f} tenaga kerja'),
            (f'<span style="color:var(--high)">{(ps<0).sum()}</span>&thinsp;/ 34',
             "provinsi terdampak negatif"),
        ]), unsafe_allow_html=True)

        st.markdown(sl("Peta Provinsi"), unsafe_allow_html=True)
        p1, p2 = st.columns(2)
        with p1:
            fig = province_map(dict(zip(po, dl.sum(axis=0))),
                               "Dampak Simulasi — ΔL Tenaga Kerja", height=220)
            if fig: st.plotly_chart(fig, use_container_width=True, key="sim_map_dl")
        with p2:
            fig = province_map(dict(zip(po, E_.sum(axis=0))),
                               "Dampak Simulasi — Perubahan Tenaga Kerja (%)", height=220, unit="E (%)")
            if fig: st.plotly_chart(fig, use_container_width=True, key="sim_map_e")

        st.markdown(sl("Matriks 52 × 34 Sektor-Provinsi"), unsafe_allow_html=True)
        c1, c2 = st.columns([3, 2])
        with c1:
            st.plotly_chart(heatmap(dl, so, po, f"Dampak Simulasi — ΔL Tenaga Kerja  [ΔL (tenaga kerja)]",
                                    unit="ΔL (tenaga kerja)", show_ylabels=True),
                            use_container_width=True, key="sim_heat_dl")
        with c2:
            st.plotly_chart(heatmap(E_, so, po, f"Dampak Simulasi — Perubahan (%)  [E (%)]",
                                    unit="E (%)", show_ylabels=False),
                            use_container_width=True, key="sim_heat_e")

# ═══════════════════════════════════════════════════════════════════════════════
# METHODOLOGY & DATA
# ═══════════════════════════════════════════════════════════════════════════════
with tab_met:

    # ── helpers ──────────────────────────────────────────────────────────────
    def _mh(title, color="#1f2d3d"):
        return (f'<div style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:13px;'
                f'font-weight:800;color:{color};border-left:4px solid {color};'
                f'padding-left:10px;margin:18px 0 8px">{title}</div>')

    def _note(txt, color="#22406e", bg="#eff6ff", border="#cfe0fb"):
        return (f'<div style="background:{bg};border:1px solid {border};border-radius:7px;'
                f'padding:9px 12px;font-size:12px;color:{color};line-height:1.6;margin-bottom:10px">'
                f'{txt}</div>')

    def _warn(txt):
        return (f'<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:7px;'
                f'padding:9px 12px;font-size:12px;color:#7f1d1d;line-height:1.6;margin-bottom:10px">'
                f'⚠ {txt}</div>')

    def _formula(txt):
        return (f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;'
                f'padding:8px 14px;font-family:\'Courier New\',monospace;font-size:12.5px;'
                f'color:#1e293b;margin:8px 0 10px;letter-spacing:.02em">{txt}</div>')

    def _trow(cells, bold=False):
        style = "font-weight:700;" if bold else ""
        tds = "".join(f'<td style="padding:5px 10px;border-bottom:1px solid #e2e8f0;{style}">{c}</td>'
                      for c in cells)
        return f"<tr>{tds}</tr>"

    def _table(headers, rows):
        head_cells = "".join(
            f'<th style="padding:6px 10px;text-align:left;font-size:11px;font-weight:700;'
            f'color:#475569;border-bottom:2px solid #cbd5e1;white-space:nowrap">{h}</th>'
            for h in headers
        )
        body = "".join(_trow(r) for r in rows)
        return (f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;'
                f'font-size:12px;color:#334155">'
                f'<thead><tr>{head_cells}</tr></thead><tbody>{body}</tbody></table></div>')

    # ── 1. OVERVIEW ───────────────────────────────────────────────────────────
    st.markdown(_mh("1. Gambaran Umum"), unsafe_allow_html=True)
    st.markdown("""
Dashboard ini memetakan kondisi ekonomi terkini ke dalam matriks **52 sektor × 34 provinsi**
perubahan tenaga kerja, sebagai sinyal peringatan dini risiko PHK untuk Kementerian Ketenagakerjaan (Kemnaker).
Model dasar adalah IndoTERM, sebuah *computable general equilibrium* (CGE) multi-regional untuk Indonesia.
""")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(_note(
            "<b>Pendekatan Linearisasi IndoTERM.</b> Solusi penuh CGE mahal secara komputasi dan "
            "tidak dapat dijalankan secara langsung setiap kali data diperbarui. Dashboard ini "
            "memisahkan dua langkah: "
            "(1) <b>Kalibrasi offline</b> — IndoTERM diselesaikan sekali per shock pada gangguan kecil "
            "(1%) untuk memperoleh elastisitas yang telah dikalibrasi "
            "(matriks η); "
            "(2) <b>Agregasi live</b> — setiap pembaruan hanya mengalikan besaran shock terkini "
            "dengan matriks elastisitas yang tersimpan — kontraksi tensor, bukan solusi CGE."
        ), unsafe_allow_html=True)
    with col_b:
        st.markdown(_note(
            "<b>Dimensi model.</b> 52 sektor mengikuti agregasi AGGIND IndoTERM dari klasifikasi "
            "185-sektor dasar (IND/COM). 34 provinsi sesuai dengan Tabel Input-Output Antarregion "
            "BPS (52 Industri × 34 Provinsi, 2016). Matriks ketenagakerjaan dasar L⁰ bersumber "
            "dari tabel yang sama. Empat provinsi Papua baru (2022) dikecualikan untuk "
            "mempertahankan struktur 34 provinsi IndoTERM."
        ), unsafe_allow_html=True)

    # ── 2. KERANGKA MATEMATIKA ────────────────────────────────────────────────
    st.markdown(_mh("2. Kerangka Matematika"), unsafe_allow_html=True)

    with st.expander("Notasi dan persamaan utama", expanded=True):
        nc1, nc2 = st.columns([1, 1])
        with nc1:
            st.markdown(_note(
                "<b>Simbol utama</b><br>"
                "<i>i</i> = indeks sektor (1…52) &nbsp;·&nbsp; <i>r</i> = indeks provinsi (1…34)<br>"
                "<i>j</i> = indeks shock dalam tema &nbsp;·&nbsp; θ ∈ {1,2,3} = indeks tema<br>"
                "<i>η<sup>(θ)</sup><sub>i,r,j</sub></i> = elastisitas terkalibrasi: % perubahan "
                "tenaga kerja di sel (i,r) akibat shock 1% pada driver j di bawah tema θ<br>"
                "<i>x<sub>j</sub></i> = besaran shock live (input runtime dashboard)<br>"
                "<i>E<sub>i,r</sub></i> = % perubahan tenaga kerja total di sel (i,r)<br>"
                "<i>L⁰<sub>i,r</sub></i> = level ketenagakerjaan dasar<br>"
                "<i>ΔL<sub>i,r</sub></i> = perubahan ketenagakerjaan absolut (kepala)"
            ), unsafe_allow_html=True)
        with nc2:
            st.markdown("<b>Kontribusi per tema dan agregasi:</b>", unsafe_allow_html=True)
            st.markdown(_formula(
                "E<sup>(1)</sup><sub>i,r</sub> = Σ<sub>j=1..7</sub>  η<sup>(1)</sup><sub>i,r,j</sub> · x<sub>j</sub>"
            ), unsafe_allow_html=True)
            st.markdown(_formula(
                "E<sup>(2)</sup><sub>i,r</sub> = Σ<sub>k∈𝒦</sub>  η<sup>(2)</sup><sub>i,r,k</sub> · x<sub>k</sub>"
                "  di mana  x<sub>k</sub> = Σ<sub>c</sub> w<sub>k,c</sub> · d<sup>g</sup><sub>c</sub>"
            ), unsafe_allow_html=True)
            st.markdown(_formula(
                "E<sup>(3)</sup><sub>i,r</sub> = Σ<sub>m∈𝒮</sub>  η<sup>(3)</sup><sub>i,r,m</sub> · x<sub>m</sub>"
            ), unsafe_allow_html=True)
            st.markdown(_formula(
                "E<sub>i,r</sub> = E<sup>(1)</sup> + E<sup>(2)</sup> + E<sup>(3)</sup>"
                "     →     ΔL<sub>i,r</sub> = (E<sub>i,r</sub> / 100) · L⁰<sub>i,r</sub>"
            ), unsafe_allow_html=True)

        st.markdown(_note(
            "<b>Output utama heatmap adalah ΔL</b> (perubahan kepala tenaga kerja), bukan E (%). "
            "Ini disengaja: shock persentase besar pada sel kecil sama besarnya dengan shock "
            "persentase yang sama pada sel besar — lensa yang salah untuk dashboard risiko yang "
            "seharusnya menonjolkan eksposur jumlah pekerja. E (%) tetap tersedia sebagai lapisan "
            "sekunder untuk menjawab pertanyaan berbeda."
        ), unsafe_allow_html=True)

    # ── 3. TEMA 1 ─────────────────────────────────────────────────────────────
    st.markdown(_mh("3. Tema 1 — Harga Komoditas Ekspor Utama", color="#e67e22"), unsafe_allow_html=True)

    with st.expander("Detail Tema 1", expanded=False):
        t1c1, t1c2 = st.columns([3, 2])
        with t1c1:
            st.markdown("**Formula shock:**", unsafe_allow_html=True)
            st.markdown(_formula(
                "YoY%(t) = 100 × (P<sub>t</sub> − P<sub>t−12</sub>) / P<sub>t−12</sub>"
                "<br>"
                "YoY%<sub>bar,48</sub>(t) = rata-rata trailing 48 bulan YoY%, digeser 1 periode"
                "<br>"
                "x<sub>j</sub> = YoY%(t) − YoY%<sub>bar,48</sub>(t)"
            ), unsafe_allow_html=True)
            st.markdown(_note(
                "Shock = deviasi dari tren 4 tahun, bukan perubahan harga mentah. "
                "Kenaikan harga yang masih di bawah tren historisnya dicatat sebagai shock negatif. "
                "Window 48 bulan dipilih untuk menghindari bias supercycle komoditas 2021–2022 "
                "(window 60 bulan) sekaligus tidak terlalu pendek sehingga dipengaruhi crash pasca-COVID (36 bulan)."
            ), unsafe_allow_html=True)
            st.markdown(_warn(
                "Kalibrasi elastisitas η<sup>(1)</sup> memerlukan solusi IndoTERM untuk masing-masing dari 7 "
                "komoditas secara terpisah (perturbasi 1% pada harga komoditas tersebut). "
                "Ini dilakukan <em>di luar</em> pipeline otomatis dan hanya perlu diulang jika model "
                "CGE, closure rules, atau SAM base-year berubah."
            ), unsafe_allow_html=True)
        with t1c2:
            st.markdown(
                _table(
                    ["Kode", "Komoditas", "Sumber", "Frekuensi"],
                    [
                        ["cpo",         "CPO / Palm oil",          "World Bank Pink Sheet", "Bulanan"],
                        ["coal",        "Batu bara (Newcastle)",   "World Bank Pink Sheet", "Bulanan"],
                        ["nickel",      "Nikel (LME)",             "World Bank Pink Sheet", "Bulanan"],
                        ["copper",      "Tembaga (LME grade A)",   "World Bank Pink Sheet", "Bulanan"],
                        ["rubber",      "Karet (TSR20 SICOM)",     "World Bank Pink Sheet", "Bulanan"],
                        ["oilgas",      "Minyak mentah (avg)",     "World Bank Pink Sheet", "Bulanan"],
                        ["electronics", "Indeks harga ekspor semikonduktor", "FRED IY3344", "Bulanan"],
                    ]
                ),
                unsafe_allow_html=True
            )
            st.caption("World Bank Pink Sheet: CMO-Historical-Data-Monthly.xlsx, "
                       "URL stabil, tanpa API key. FRED IY3344: API key dari .env.")

    # ── 4. TEMA 2 ─────────────────────────────────────────────────────────────
    st.markdown(_mh("4. Tema 2 — Kondisi Ekonomi Mitra Dagang", color="#2563eb"), unsafe_allow_html=True)

    with st.expander("Detail Tema 2", expanded=False):
        t2c1, t2c2 = st.columns([3, 2])
        with t2c1:
            st.markdown("**Formula shock:**", unsafe_allow_html=True)
            st.markdown(_formula(
                "d<sup>g</sup><sub>c</sub> = proyeksi WEO terkini − proyeksi WEO sebelumnya  (tahun target sama)"
                "<br>"
                "x<sub>k</sub> = Σ<sub>c</sub> w<sub>k,c</sub> · d<sup>g</sup><sub>c</sub>"
                "     (bobot ekspor × revisi pertumbuhan mitra)"
            ), unsafe_allow_html=True)
            st.markdown(_note(
                "<b>Asumsi unit pass-through</b> (disengaja): revisi proyeksi +1 pp untuk negara c "
                "diasumsikan menghasilkan perubahan permintaan ekspor Indonesia sebesar +1% ke negara tersebut, "
                "seragam di semua produk. Diferensiasi sektor berasal sepenuhnya dari profil tujuan ekspor "
                "masing-masing sektor (bobot w<sub>k,c</sub>), bukan dari elastisitas pendapatan yang berbeda "
                "per produk/negara. Elastisitas pendapatan yang diestimasi secara empiris adalah jalur upgrade "
                "ke depan."
            ), unsafe_allow_html=True)
            st.markdown(_note(
                "<b>Set sektor tradable 𝒦 = 23 sektor</b> (dikunci berdasarkan Comtrade 2023, "
                "ekspor Indonesia > USD 0,1 miliar). Sektor non-tradable (konstruksi, jasa, utilitas) "
                "tidak memiliki eksposur ekspor yang berarti sehingga tidak dikejutkan oleh Tema 2."
            ), unsafe_allow_html=True)
            st.markdown(_warn(
                "WEO diterbitkan hanya <b>3 kali per tahun</b> (April, Oktober, dan Update Januari). "
                "d<sup>g</sup><sub>c</sub> tidak berubah di antara tanggal rilis tersebut. "
                "Dashboard menampilkan vintage WEO yang aktif saat ini — jangan diinterpretasikan "
                "sebagai data harian."
            ), unsafe_allow_html=True)
        with t2c2:
            st.markdown(
                _table(
                    ["Sumber data", "Keterangan"],
                    [
                        ["IMF WEO API", "SDMX 2.1/3.0 REST, indikator NGDP_RPCH, tanpa API key"],
                        ["UN Comtrade", "Bobot ekspor w_{k,c} per sektor, diperbarui tahunan, API key dari .env"],
                        ["Frekuensi efektif", "3× per tahun (mengikuti jadwal rilis WEO)"],
                        ["Negara mitra", "Seluruh negara dalam WEO (IMF)", ],
                        ["K = 23 sektor", "2,3,6,7,8,9,10,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27"],
                    ]
                ),
                unsafe_allow_html=True
            )

    # ── 5. TEMA 3 ─────────────────────────────────────────────────────────────
    st.markdown(_mh("5. Tema 3 — Permintaan Domestik (SPE/IPR)", color="#7c3aed"), unsafe_allow_html=True)

    with st.expander("Detail Tema 3", expanded=False):
        t3c1, t3c2 = st.columns([3, 2])
        with t3c1:
            st.markdown("**Formula shock:**", unsafe_allow_html=True)
            st.markdown(_formula(
                "g<sup>yoy</sup><sub>i,t</sub> = pertumbuhan YoY indeks penjualan riil (IPR) kategori i, bulan t"
                "<br>"
                "ḡ<sub>i,t</sub> = rata-rata trailing 48 bulan g<sup>yoy</sup>, digeser 1 periode"
                "<br>"
                "x<sub>i</sub> = g<sup>yoy</sup><sub>i,t</sub> − ḡ<sub>i,t</sub>"
            ), unsafe_allow_html=True)
            st.markdown(_note(
                "<b>Mengapa IPR, bukan CPI:</b> IPR adalah indeks volume/riil yang sudah dideflatkan "
                "oleh Bank Indonesia. CPI tidak bisa membedakan kenaikan harga akibat permintaan kuat "
                "(harga naik + volume naik) vs. shock penawaran negatif (harga naik + volume turun) — "
                "keduanya memiliki implikasi risiko PHK yang berlawanan. IPR langsung mengukur volume, "
                "sehingga masalah identifikasi tersebut tidak muncul."
            ), unsafe_allow_html=True)
            st.markdown(_note(
                "<b>Shock nasional, elastisitas regional:</b> Survei SPE hanya mencakup kota-kota tertentu, "
                "bukan 34 provinsi. x<sub>i</sub> digunakan sebagai nilai nasional tunggal — tidak ada "
                "x<sub>i,r</sub> per provinsi. Seluruh diferensiasi regional Tema 3 berasal dari tensor "
                "elastisitas η<sup>(3)</sup><sub>i,r,m</sub> yang dikalibrasi penuh pada 52×34."
            ), unsafe_allow_html=True)
            st.markdown(_warn(
                "Pipeline membutuhkan <b>minimal 48 bulan data historis</b> sebelum x<sub>i</sub> dapat "
                "dihitung untuk pertama kali. Pembaruan awal memerlukan pengunduhan arsip SPE beberapa tahun "
                "ke belakang."
            ), unsafe_allow_html=True)
        with t3c2:
            st.markdown(
                _table(
                    ["Kategori SPE/IPR", "Sektor IO52 yang dipetakan"],
                    [
                        ["Makanan, minuman & tembakau", "1 FoodCrops, 2 HortiCrops, 4 Livestock, 7 Fishery, 12 FoodMan, 13 Tobacco"],
                        ["Sandang",                      "14 Textiles, 15 Leather"],
                        ["Suku cadang kendaraan",        "23 MetalProd, 24 Machinery, 25 TranspEquip, 32 VehicTrade"],
                        ["Bahan bakar kendaraan",        "19 CoalOilMan"],
                        ["Peralatan ICT",                "27 OtherMan, 42 Telecom"],
                        ["Peralatan rumah tangga",       "16 WoodProd, 26 Furniture"],
                        ["Budaya & rekreasi",            "40 Hotels, 41 Restaurant, 52 OtherSvc"],
                    ]
                ),
                unsafe_allow_html=True
            )
            st.caption("24 dari 52 sektor dipetakan. 28 sektor lainnya tidak menerima shock Tema 3. "
                       "Sumber data: Survei Penjualan Eceran (SPE), Bank Indonesia — ZIP bulanan, tanpa API key.")

    # ── 6. BEBAN KALIBRASI ELASTISITAS ────────────────────────────────────────
    st.markdown(_mh("6. Beban Kalibrasi Elastisitas IndoTERM"), unsafe_allow_html=True)

    with st.expander("Scope kalibrasi CGE", expanded=False):
        st.markdown(_note(
            "<b>Elastisitas bersifat tema-spesifik</b> — tidak dibagi antar tema, meskipun sektor yang sama "
            "muncul di lebih dari satu tema. Alasan ekonomi: shock harga ekspor dan shock permintaan domestik "
            "pada sektor yang sama masuk ke model melalui kanal yang berbeda (harga ekspor vs. konsumsi akhir domestik) "
            "dan dapat mengaktifkan jalur substitusi dan umpan balik umum yang berbeda dalam CGE."
        ), unsafe_allow_html=True)
        st.markdown(
            _table(
                ["Tema", "Jumlah shock", "Matriks 52×34", "Dasar kalibrasi"],
                [
                    ["1 — Harga komoditas", "7", "7",
                     "Perturbasi 1% harga komoditas, 7 komoditas secara terpisah"],
                    ["2 — Pertumbuhan mitra", "23 (𝒦)", "23",
                     "Perturbasi 1% permintaan ekspor, sektor tradable saja"],
                    ["3 — Permintaan domestik", "52", "52",
                     "Perturbasi 1% permintaan domestik, semua 52 sektor"],
                    ["<b>Total</b>", "<b>82</b>", "<b>82</b>",
                     "Semua matriks disuplai dari IndoTERM (di luar pipeline otomatis)"],
                ]
            ),
            unsafe_allow_html=True
        )
        st.markdown(_note(
            "Matriks elastisitas <em>tidak pernah dicompute ulang pada setiap refresh</em>. "
            "Disuplai oleh pengembang model dari run IndoTERM dan hanya perlu diganti jika "
            "model CGE, closure rules, atau SAM base-year berubah."
        ), unsafe_allow_html=True)

    # ── 7. ASUMSI DAN KETERBATASAN ────────────────────────────────────────────
    st.markdown(_mh("7. Asumsi dan Keterbatasan"), unsafe_allow_html=True)

    with st.expander("Lihat asumsi dan keterbatasan model", expanded=False):
        lims = [
            ("<b>Linieritas lokal.</b>",
             "Setiap η dikalibrasi pada perturbasi 1%. Respons CGE umumnya nonlinier untuk shock besar "
             "(harga komoditas besar, revisi WEO besar). Hasil untuk shock di luar kisaran kecil merupakan "
             "ekstrapolasi linier yang nilainya hanya indikatif."),
            ("<b>Separabilitas aditif.</b>",
             "Menjumlahkan kontribusi shock di dalam satu tema dan antar tema mengasumsikan tidak ada efek "
             "interaksi. Ini hanya berlaku secara pendekatan di bawah market clearing CGE yang sebenarnya, "
             "dan degradasinya semakin terlihat ketika beberapa shock secara bersamaan menekan sektor atau "
             "faktor produksi yang sama."),
            ("<b>Unit pass-through Tema 2.</b>",
             "Revisi proyeksi +1 pp untuk negara c diasumsikan menghasilkan perubahan permintaan ekspor +1%. "
             "Elastisitas pendapatan impor yang sebenarnya sering berbeda dari 1, terutama untuk ekspor "
             "industri/komoditas seperti nikel atau baja."),
            ("<b>Shock nasional, bukan regional (Tema 3).</b>",
             "IPR digunakan sebagai nilai nasional tunggal per kategori — divergensi permintaan domestik "
             "antar provinsi tidak ditangkap. Hanya sisi elastisitas yang bervariasi per provinsi."),
            ("<b>Deflator IPR diterima apa adanya.</b>",
             "Apabila deflator internal BI tidak sepenuhnya menghilangkan efek harga per kategori, "
             "sebagian variasi harga masih bisa masuk ke x<sub>i</sub> Tema 3. Ini adalah penyederhanaan "
             "yang dinyatakan terbuka, bukan pengawasan."),
            ("<b>Elastisitas dan L⁰ bersifat time-invariant antar refresh.</b>",
             "Keduanya tetap tetap hingga pengguna secara manual melakukan rekalibrasi IndoTERM atau "
             "memperbarui data ketenagakerjaan dasar. Cadence rekalibrasi yang eksplisit "
             "dan vintage-tagging harus didefinisikan."),
            ("<b>Belum ada benchmarking joint re-solve.</b>",
             "Belum ada pemeriksaan periodik terhadap hasil aproksimasi linier-aditif "
             "(Σ tema) vs. solusi CGE penuh dengan kombinasi multi-tema shock yang realistis. "
             "Sebelum komunikasi kebijakan berdampak tinggi, benchmark ini sebaiknya dijalankan "
             "untuk menetapkan batas kesalahan empiris dari aproksimasi."),
        ]
        for title, body in lims:
            st.markdown(
                f'<div style="background:white;border:1px solid #e2e8f0;border-radius:7px;'
                f'padding:10px 14px;margin-bottom:8px;font-size:12px;line-height:1.6;color:#334155">'
                f'<span style="font-weight:700;color:#1e293b">{title}</span> {body}</div>',
                unsafe_allow_html=True
            )

    # ── 8. SUMBER DATA RINGKASAN ──────────────────────────────────────────────
    st.markdown(_mh("8. Ringkasan Sumber Data"), unsafe_allow_html=True)

    st.markdown(
        _table(
            ["Sumber", "Tema", "Data", "Akses", "Frekuensi pembaruan"],
            [
                ["World Bank Pink Sheet",    "T1", "Harga 6 komoditas (CPO, batu bara, nikel, tembaga, karet, minyak)", "XLSX gratis, tanpa API key", "Bulanan"],
                ["FRED IY3344",              "T1", "Indeks harga ekspor elektronik/semikonduktor", "REST API, key dari .env", "Bulanan"],
                ["IMF WEO (SDMX API)",       "T2", "Proyeksi pertumbuhan GDP riil semua negara (NGDP_RPCH)", "REST API, tanpa API key", "3× per tahun"],
                ["UN Comtrade",              "T2", "Nilai ekspor Indonesia per HS code, per negara tujuan", "REST API, key dari .env", "Tahunan (bobot w_{k,c})"],
                ["SPE Bank Indonesia (ZIP)", "T3", "Indeks Penjualan Riil 7 kategori (Tabel 2 XLSX)", "ZIP bulanan, tanpa API key", "Bulanan"],
                ["BPS lo.csv (statis)",      "All", "Ketenagakerjaan dasar L⁰ per sektor × provinsi", "File statis (rawdata/)", "Tidak berubah hingga rekalibrasi"],
                ["IndoTERM (NPZ matrices)",  "All", "Matriks elastisitas η (~82 matriks 52×34)", "File statis (data/elasticity/)", "Tidak berubah hingga rekalibrasi CGE"],
            ]
        ),
        unsafe_allow_html=True
    )
