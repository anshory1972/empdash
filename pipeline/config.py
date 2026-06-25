"""
Central configuration for the empdash pipeline.
All user-settable parameters live here — change here only.
"""

# ── Theme 2: tradable sectors (K set) ────────────────────────────────────────
# IO52 sector indices eligible for export-demand shocks.
# Locked at K=23 (Comtrade exports > $0.1B threshold, 2023).
K_SECTORS = [2,3,6,7,8,9,10,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27]

# ── Theme 3: SPE category → IO52 sector mapping ──────────────────────────────
# Source: KBLI 2009 codes (BI SPE Metadata 2022).
# Rules: one-to-many; each IO52 sector appears in at most one SPE category;
#        24 of 52 sectors mapped; remaining 28 receive no Theme 3 shock.
#
# KBLI 453  spare_parts      vehicle spare parts & accessories
# KBLI 472  food_bev_tobacco food, beverages & tobacco
# KBLI 473  fuel             vehicle fuel
# KBLI 474  ict_equipment    ICT equipment
# KBLI 475  household_equip  other household equipment
# KBLI 476  cultural_rec     cultural & recreational goods
# KBLI 477  other_goods      other goods (pharma, cosmetics, books — sandang is sub-item)
#           sandang          clothing sub-item of KBLI 477
#           total_index      aggregate retail index
SPE_TO_IO52 = {
    "food_bev_tobacco": [1, 2, 4, 7, 12, 13],   # FoodCrops,HortiCrops,Livestock,Fishery,FoodMan,Tobacco
    "sandang":          [14, 15],                 # Textiles, Leather
    "spare_parts":      [23, 24, 25, 32],         # MetalProd, Machinery, TranspEquip, VehicTrade
    "fuel":             [19],                     # CoalOilMan
    "ict_equipment":    [27, 42],                 # OtherMan, Telecom
    "household_equip":  [16, 26],                 # WoodProd, Furniture
    "cultural_rec":     [40, 41, 52],             # Hotels, Restaurant, OtherSvc
    "other_goods":      [17, 20],                 # PaperProd, Chemical
    # total_index excluded: it is a weighted composite of the 7 sub-categories above,
    # so using it as a separate shock would double-count.
}

# Inverse lookup: IO52 sector → SPE category
IO52_TO_SPE = {
    s: cat
    for cat, sectors in SPE_TO_IO52.items()
    for s in sectors
}

# ── Theme 1: commodity price series ──────────────────────────────────────────
# World Bank Pink Sheet column name → short code used in shock vector
COMMODITY_COLS = {
    "Palm oil":            "cpo",
    "Coal, Australian":    "coal",
    "Nickel":              "nickel",
    "Copper":              "copper",
    "Rubber, TSR20 **":    "rubber",
    "Crude oil, average":  "oilgas",
}
FRED_SERIES   = "IY3344"          # electronics export price index
FRED_CODE     = "electronics"

# ── IndoTERM dimensions ───────────────────────────────────────────────────────
N_SECTORS  = 52
N_PROVINCES = 34

# New 2022 Papua province splits — excluded to keep 34-province IndoTERM structure
EXCLUDED_PROVINCE_IDS = [9200, 9500, 9600, 9700]   # Barat Daya, Selatan, Tengah, Pegunungan
NATIONAL_ID           = 9900

# ── WEO settings ─────────────────────────────────────────────────────────────
WEO_FCAST_YEAR       = 2026
WEO_NEW_VINTAGE_THRESHOLD = 0.05   # pp mean difference across key countries
WEO_KEY_COUNTRIES    = ["CHN", "USA", "JPN", "IND", "SGP", "MYS", "IDN"]

# ── Shock window ─────────────────────────────────────────────────────────────
TREND_WINDOW = 36   # months — same for Theme 1 and Theme 3
