"""
Build placeholder elasticity matrices for all 39 shocks.

Each matrix M[s, p] (52 x 34) gives the % change in employment
in sector s, province p, per +1 pp shock.

Structure per shock:
  - Direct sectors: base_elasticity * relative_intensity * province_share[s, p]
  - IO-linked sectors: 0.30 * base_elasticity * province_share[s, p]
  - All others (GE spillover): 0.05 * base_elasticity * province_share[s, p]

Province weights come from actual employment distribution in lo.csv.
New 2022 Papua provinces (Barat Daya, Selatan, Tengah, Pegunungan) excluded
to match IndoTERM 34-province structure.

Outputs:
  data/elasticity/eta_matrices.npz   — all 39 arrays (named by shock key)
  data/elasticity/eta_meta.json      — shock keys, dimensions, province/sector order
  data/elasticity/eta_{key}.csv      — one CSV per matrix (52 rows x 34 cols)

Replace with real CGE matrices by overwriting eta_matrices.npz (same key names).
"""
import os, json
import numpy as np
import pandas as pd

ROOT    = os.path.join(os.path.dirname(__file__), "..", "..")
LO_CSV  = os.path.join(ROOT, "rawdata", "lo.csv")
OUT_DIR = os.path.join(ROOT, "data", "elasticity")
os.makedirs(OUT_DIR, exist_ok=True)

N_SECT = 52
N_PROV = 34
NEW_PAPUA = [9200, 9500, 9600, 9700]   # 2022 split provinces, excluded from 34-prov model

K_SECTORS = [2,3,6,7,8,9,10,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27]

# Base elasticities (% employment per pp shock)
BASE_T1 = 0.20   # commodity price → profitability → employment
BASE_T2 = 0.15   # export demand revision → output → employment
BASE_T3 = 0.10   # domestic demand → retail/output → employment


# ─── Province employment shares ──────────────────────────────────────────────
lo = pd.read_csv(LO_CSV)
lo = lo[~lo["id"].isin(NEW_PAPUA + [9900])].copy()

prov_order = sorted(lo["id"].unique().tolist())
sect_order = list(range(1, N_SECT + 1))

emp_pivot = (lo.pivot_table(index="sector_52", columns="id", values="emp", aggfunc="sum")
               .reindex(index=sect_order, columns=prov_order)
               .fillna(0))

# shares[s, p] = fraction of sector-s national employment in province p
shares = emp_pivot.div(emp_pivot.sum(axis=1), axis=0).values   # shape (52, 34)

prov_labels = (lo.drop_duplicates("id")
                 .set_index("id")["id_label"]
                 .reindex(prov_order)
                 .tolist())

sect_labels = [f"s{i:02d}" for i in sect_order]


# ─── Matrix builder ───────────────────────────────────────────────────────────
def make_matrix(direct_sectors, linked_sectors, base):
    """
    direct_sectors : list of (sector_idx_1based, relative_intensity)
    linked_sectors : list of sector_idx_1based (indirect IO linkage)
    base           : base elasticity magnitude
    """
    M = np.zeros((N_SECT, N_PROV))

    direct_set = {s for s, _ in direct_sectors}
    linked_set = set(linked_sectors) - direct_set

    # GE spillover: tiny positive to everything
    for s in range(N_SECT):
        s1 = s + 1
        if s1 not in direct_set and s1 not in linked_set:
            M[s] = 0.05 * base * shares[s]

    # IO-linked sectors
    for s1 in linked_set:
        s = s1 - 1
        M[s] = 0.30 * base * shares[s]

    # Direct sectors (overwrites GE/linked for same sector)
    for s1, intensity in direct_sectors:
        s = s1 - 1
        M[s] = base * intensity * shares[s]

    return M


# ─────────────────────────────────────────────────────────────────────────────
# THEME 1 — Commodity price shocks (7 matrices)
# ─────────────────────────────────────────────────────────────────────────────
#
# Sector codes (IO52):
#   1=FoodCrops  2=HortiCrops  3=Estates    4=Livestock  5=AgricSvc
#   6=Forestry   7=Fishery     8=Coal       9=OilGasGeo 10=IronOre
#  11=OtherMine 12=FoodMan    13=Tobacco   14=Textiles  15=Leather
#  16=WoodProd  17=PaperProd  18=NonMetal  19=CoalOilMan 20=Chemical
#  21=Rubber    22=BasicMetal 23=MetalProd 24=Machinery  25=TranspEquip
#  26=Furniture 27=OtherMan  ...

T1_SPECS = {
    # key: (direct=[(sector, intensity)], linked=[sector, ...])
    "t1_cpo": (
        [(3, 1.0), (12, 0.6)],           # Estates (main), FoodMan (palm processing)
        [1, 21, 20],                      # FoodCrops, Rubber, Chemical (linked via supply)
    ),
    "t1_coal": (
        [(8, 1.0), (19, 0.5)],           # Coal (main), CoalOilMan (processing)
        [22, 31, 35],                     # BasicMetal, Construction, LandTransp
    ),
    "t1_nickel": (
        [(11, 1.0), (22, 0.6)],          # OtherMine (main), BasicMetal (smelting)
        [10, 23, 24],                     # IronOre, MetalProd, Machinery
    ),
    "t1_copper": (
        [(10, 1.0), (11, 0.6)],          # IronOre (main), OtherMine
        [22, 23],                         # BasicMetal, MetalProd
    ),
    "t1_rubber": (
        [(3, 0.7), (21, 1.0)],           # Estates, Rubber (processing, main)
        [20, 15, 14],                     # Chemical, Leather, Textiles
    ),
    "t1_oilgas": (
        [(9, 1.0), (19, 0.7)],           # OilGasGeo (main), CoalOilMan (refining)
        [20, 28, 29],                     # Chemical, Electricity, CityGas
    ),
    "t1_electronics": (
        [(27, 1.0), (24, 0.6)],          # OtherMan (main, incl. electronics assembly), Machinery
        [14, 23, 25, 42],                 # Textiles, MetalProd, TranspEquip, Telecom
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# THEME 2 — Tradable sector export demand shocks (23 matrices)
# Each k sector fires its own employment directly; IO linkages carry the spillover.
# ─────────────────────────────────────────────────────────────────────────────
T2_LINKED_MAP = {
    2:  [1, 3, 12],           # HortiCrops → FoodCrops, Estates, FoodMan
    3:  [1, 12, 21],          # Estates → FoodCrops, FoodMan, Rubber
    6:  [16, 17],             # Forestry → WoodProd, PaperProd
    7:  [12, 41, 40],         # Fishery → FoodMan, Restaurant, Hotels
    8:  [19, 22, 31],         # Coal → CoalOilMan, BasicMetal, Construction
    9:  [19, 20, 28],         # OilGasGeo → CoalOilMan, Chemical, Electricity
    10: [22, 23],             # IronOre → BasicMetal, MetalProd
    12: [1, 4, 13, 41],       # FoodMan → FoodCrops, Livestock, Tobacco, Restaurant
    13: [1, 12],              # Tobacco → FoodCrops, FoodMan
    14: [3, 15, 21],          # Textiles → Estates, Leather, Rubber
    15: [14, 3],              # Leather → Textiles, Estates
    16: [6, 17, 26],          # WoodProd → Forestry, PaperProd, Furniture
    17: [6, 16, 20],          # PaperProd → Forestry, WoodProd, Chemical
    18: [11, 31],             # NonMetalProd → OtherMine, Construction
    19: [9, 8, 20],           # CoalOilMan → OilGasGeo, Coal, Chemical
    20: [9, 21, 19],          # Chemical → OilGasGeo, Rubber, CoalOilMan
    21: [3, 14, 20],          # Rubber → Estates, Textiles, Chemical
    22: [10, 11, 23],         # BasicMetal → IronOre, OtherMine, MetalProd
    23: [22, 24, 26],         # MetalProd → BasicMetal, Machinery, Furniture
    24: [22, 23, 25],         # Machinery → BasicMetal, MetalProd, TranspEquip
    25: [22, 23, 24],         # TranspEquip → BasicMetal, MetalProd, Machinery
    26: [16, 23, 6],          # Furniture → WoodProd, MetalProd, Forestry
    27: [14, 20, 24],         # OtherMan → Textiles, Chemical, Machinery
}

IO52_NAMES = {
    2: "HortiCrops", 3: "Estates",    6: "Forestry",    7: "Fishery",
    8: "Coal",       9: "OilGasGeo", 10: "IronOre",    12: "FoodMan",
   13: "Tobacco",   14: "Textiles",  15: "Leather",    16: "WoodProd",
   17: "PaperProd", 18: "NonMetalProd", 19: "CoalOilMan", 20: "Chemical",
   21: "Rubber",    22: "BasicMetal", 23: "MetalProd",  24: "Machinery",
   25: "TranspEquip", 26: "Furniture", 27: "OtherMan",
}

T2_SPECS = {}
for k in K_SECTORS:
    name = IO52_NAMES[k]
    T2_SPECS[f"t2_{name}"] = (
        [(k, 1.0)],
        T2_LINKED_MAP.get(k, []),
    )

# ─────────────────────────────────────────────────────────────────────────────
# THEME 3 — SPE domestic demand shocks (9 matrices)
# ─────────────────────────────────────────────────────────────────────────────
T3_SPECS = {
    "t3_food_bev_tobacco": (
        [(12, 1.0), (13, 0.8), (1, 0.5), (4, 0.4)],  # FoodMan, Tobacco, FoodCrops, Livestock
        [3, 7, 41],                                    # Estates, Fishery, Restaurant
    ),
    "t3_fuel": (
        [(19, 0.8), (9, 0.6), (35, 0.5)],             # CoalOilMan, OilGasGeo, LandTransp
        [8, 20, 28],                                   # Coal, Chemical, Electricity
    ),
    "t3_ict_equipment": (
        [(42, 1.0), (27, 0.7)],                        # Telecom, OtherMan (assembly)
        [24, 48, 43],                                  # Machinery, BusSvc, Finance
    ),
    "t3_household_equip": (
        [(26, 1.0), (27, 0.7), (20, 0.4)],             # Furniture, OtherMan, Chemical
        [16, 23, 22],                                  # WoodProd, MetalProd, BasicMetal
    ),
    "t3_cultural_rec": (
        [(52, 1.0), (40, 0.8), (41, 0.6)],             # OtherSvc, Hotels, Restaurant
        [50, 38, 47],                                  # Education, AirTransp, RealEstate
    ),
    "t3_spare_parts": (
        [(32, 1.0), (23, 0.7), (24, 0.5)],             # VehicTrade, MetalProd, Machinery
        [25, 22, 35],                                  # TranspEquip, BasicMetal, LandTransp
    ),
    "t3_sandang": (
        [(14, 1.0), (15, 0.8), (3, 0.4)],              # Textiles, Leather, Estates
        [21, 27, 33],                                  # Rubber, OtherMan, OthTrade
    ),
    "t3_other_goods": (
        [(33, 1.0), (27, 0.6)],                        # OthTrade, OtherMan
        [32, 12, 26],                                  # VehicTrade, FoodMan, Furniture
    ),
    # total_index excluded: weighted composite of sub-categories → double-counts if included
}


# ─────────────────────────────────────────────────────────────────────────────
# Generate all 39 matrices
# ─────────────────────────────────────────────────────────────────────────────
ALL_SPECS = {}
for key, (direct, linked) in T1_SPECS.items():
    ALL_SPECS[key] = (direct, linked, BASE_T1)
for key, (direct, linked) in T2_SPECS.items():
    ALL_SPECS[key] = (direct, linked, BASE_T2)
for key, (direct, linked) in T3_SPECS.items():
    ALL_SPECS[key] = (direct, linked, BASE_T3)

assert len(ALL_SPECS) == 38, f"Expected 38 matrices, got {len(ALL_SPECS)}"

matrices = {}
for key, (direct, linked, base) in ALL_SPECS.items():
    M = make_matrix(direct, linked, base)
    matrices[key] = M

# Save NPZ
npz_path = os.path.join(OUT_DIR, "eta_matrices.npz")
np.savez_compressed(npz_path, **matrices)
print(f"Saved: eta_matrices.npz  ({len(matrices)} matrices, each {N_SECT}x{N_PROV})")

# Save individual CSVs
csv_dir = os.path.join(OUT_DIR, "csv")
os.makedirs(csv_dir, exist_ok=True)
for key, M in matrices.items():
    df = pd.DataFrame(M, index=[f"s{i:02d}" for i in range(1, N_SECT+1)], columns=prov_order)
    df.to_csv(os.path.join(csv_dir, f"eta_{key}.csv"))

print(f"Saved: {len(matrices)} CSV files in data/elasticity/csv/")

# Save metadata
io52 = pd.read_csv(os.path.join(ROOT, "data", "cache", "io52_sectors.csv"))
sect_names = io52.set_index("io52_idx")["io52_name"].to_dict()

meta = {
    "n_sectors":       N_SECT,
    "n_provinces":     N_PROV,
    "province_order":  prov_order,
    "province_labels": prov_labels,
    "sector_order":    sect_order,
    "sector_labels":   [sect_names.get(i, f"s{i:02d}") for i in sect_order],
    "matrix_keys":     list(matrices.keys()),
    "base_elasticities": {
        "theme1": BASE_T1,
        "theme2": BASE_T2,
        "theme3": BASE_T3,
    },
    "note": (
        "PLACEHOLDER matrices — replace with calibrated CGE values. "
        "Each matrix M[s,p] = % employment change in sector s, province p "
        "per +1 pp shock. Province weights from lo.csv employment shares. "
        "New 2022 Papua provinces excluded to match IndoTERM 34-province structure."
    ),
    "theme1_shocks": list(T1_SPECS.keys()),
    "theme2_shocks": list(T2_SPECS.keys()),
    "theme3_shocks": list(T3_SPECS.keys()),
}

with open(os.path.join(OUT_DIR, "eta_meta.json"), "w") as f:
    json.dump(meta, f, indent=2)
print("Saved: eta_meta.json")

# Summary statistics
print("\nMatrix summary:")
print(f"  {'Key':<24}  {'max':>7}  {'mean':>7}  {'direct sectors'}")
print("  " + "-" * 65)
for key, (direct, linked, base) in ALL_SPECS.items():
    M = matrices[key]
    dsect = ",".join(str(s) for s, _ in direct)
    print(f"  {key:<24}  {M.max():>7.4f}  {M.mean():>7.4f}  sectors {dsect}")
