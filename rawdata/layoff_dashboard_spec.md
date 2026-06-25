# Layoff-Risk Dashboard: Methodology and Build Specification

## 1. Purpose

A dashboard mapping current economic shocks (external commodity/growth shocks
and domestic demand conditions) into a **52-sector × 34-province** matrix of
employment change, used as a layoff-risk signal for Indonesia. The dashboard
updates on a "press update" basis without re-solving the CGE (IndoTERM) live;
instead it looks up pre-calibrated elasticities and multiplies them by
freshly-retrieved shock magnitudes. A future version (see §8) replaces this
shortcut with a live CGE solve once server-side IndoTERM is feasible.

## 2. Notation

| Symbol | Meaning |
|---|---|
| $i$ | Sector index, $i = 1,\dots,52$ (IndoTERM's `AGGIND` classification) |
| $r$ | Province index, $r = 1,\dots,34$ |
| $j$ | Generic shock index within a theme |
| $\eta_{i,r,j}^{(\theta)}$ | Calibrated elasticity: % employment change in cell $(i,r)$ from a 1% shock to driver $j$ under theme $\theta \in \{1,2,3\}$ |
| $x_j$ | Live shock magnitude for driver $j$ |
| $E_{i,r}^{(\theta)}$ | Theme $\theta$'s contribution to % employment change in cell $(i,r)$ |
| $E_{i,r}$ | Total % employment change, summed across themes |
| $L_{i,r}^{0}$ | Baseline (latest observed) employment in cell $(i,r)$ |
| $\Delta L_{i,r}$ | Absolute employment change — **the dashboard's primary heatmap output** |

## 3. Sector and Region Classification

Sectors: the 52-industry IndoTERM aggregation (`AGGIND`/`AGGCOM`), itself an
aggregation of a 185-sector base classification (`IND`/`COM`), with the
many-to-one mapping held in `MIND`/`MCOM`. Source file: `sec52.agg` (GEMPACK
HAR format — requires GEMPACK/HARpy tooling to parse, not plain text).

The 52 sectors, in order:

```
 1. FoodCrops      14. Textiles       27. OtherMan       40. Hotels
 2. HortiCrops     15. Leather        28. Electricity    41. Restaurant
 3. Estates        16. WoodProd       29. CityGas        42. Telecom
 4. Livestock      17. PaperProd      30. WasteMan       43. Finance
 5. AgricService   18. NonMetalProd   31. Construction   44. Insurance
 6. Forestry       19. CoalOilMan     32. VehicTrade     45. OthFinance
 7. Fishery        20. Chemical       33. OthTrade       46. FinanSvc
 8. Coal           21. Rubber         34. RailTransp     47. RealEstate
 9. OilGasGeo      22. BasicMetal     35. LandTransp     48. BusSvc
10. IronOre        23. MetalProd      36. SeaTransp      49. GovAdmin
11. OtherMine      24. Machinery      37. WaterTransp    50. Education
12. FoodMan        25. TranspEquip    38. AirTransp      51. HealthSvc
13. Tobacco        26. Furniture      39. TranspSvc      52. OtherSvc
```

Regions: Indonesia's 34 provinces.

Provenance note: this is the user's own IndoTERM model file (file history
shows prior aggregation work by "kang arief" / Megananda, `data_cge_indoterm`),
not a generic public classification — treat it as authoritative for this
project.

## 4. Three Shock Themes

The design separates *shock magnitude construction* (§5–7, data-engineering
problem) from *elasticity calibration* (CGE-modeling problem, the user's own
work, not automated). Each theme produces its own $x_j$ values; elasticities
are **theme-specific** even when the same sector is the shock target, because
domestic-demand, export-demand, and export-price shocks are mechanically
different perturbations to IndoTERM and may propagate differently through the
economy. No interaction terms or shared tensors are assumed across themes.

### Theme 1 — Commodity Price Shocks (8 shocks)

Direct world/domestic commodity price changes.

| Commodity | Reference series | Source | Access |
|---|---|---|---|
| CPO / palm oil | Bursa Malaysia FCPO | Commodities-API or WB Pink Sheet | Paid API (real-time) or monthly XLSX (free) |
| Coal | Newcastle, 6000 kcal/kg | World Bank Pink Sheet | Monthly XLSX, free |
| Nickel | LME cathodes | World Bank Pink Sheet | Monthly XLSX, free |
| Copper | LME grade A | World Bank Pink Sheet | Monthly XLSX, free |
| Textiles/garments/footwear (TGF) | demand-side, no single price | proxy needed (see Theme 2) | — |
| Electronics | demand-side, no single price | PHLX Semiconductor Index (SOX) or BLS export price index (FRED `IY3344`) | Market API / FRED API, free |
| Rubber | Asia TSR 20, SICOM | World Bank Pink Sheet | Monthly XLSX, free |
| Oil/gas | Brent/Dubai/WTI average | World Bank Pink Sheet (monthly) or FRED/EIA (daily) | Free API |

Shock magnitude (correct formula — see warning below):
$$x_j = 100 \times \frac{X_{j,t} - X_{j,t-1}}{X_{j,t-1}}$$

**Bug warning carried over from v1:** $x_j = 100 \cdot X_{j,t}/X_{j,t-1}$
(without subtracting 1, equivalently without subtracting $X_{j,t-1}$ in the
numerator) does **not** return zero under no change. Enforce with a unit
test: a flat synthetic series must yield $x_j = 0$ exactly.

Elasticity tensor: $\eta_{i,r,j}^{(1)}$, $j = 1,\dots,8$ — **8 full $52\times34$
matrices**, each from one IndoTERM run with a 1% perturbation to that
commodity's price, all else held at zero.

### Theme 2 — Trading-Partner Growth Shocks (~17 shocks, tradable sectors only)

**Mechanism:** a country's growth-forecast revision is a uniform, economy-wide
demand shifter facing *all* Indonesian exports to that country (unit
pass-through assumed: a 1pp growth revision ⇒ 1% demand change for any
Indonesian export to that country). Product-level differentiation in the
final shock comes entirely from *which countries buy how much of each
product* — not from a separately estimated income elasticity per product.

**Step 1 — country growth revisions.**
$$d^g_c = g_{c,t}^{\text{(current WEO vintage)}} - g_{c,t}^{\text{(prior WEO vintage)}}$$
for the same target year $t$, per country $c$. Source: IMF World Economic
Outlook, free SDMX 2.1/3.0 REST API (`api.imf.org`, no key required).
Published 3×/year (April, September/October, January Update) — **this is a
discrete, low-frequency input; the dashboard will not see a new value between
WEO releases.**

**Step 2 — export-share weights.** For each tradable sector $k$, pull
Indonesia's export value to its top destination countries from UN Comtrade
(free API key, `comtradeapicall`/`comtradr` wrappers, ~500 calls/day,
100k records/query) or BPS's own export-import WebAPI endpoint
(`webapi.bps.go.id`, `dataexim` resource, HS-code based). Compute
$w_{k,c} = X_{k,c} / \sum_{c'} X_{k,c'}$.

**Step 3 — aggregate (algebraically collapses, no per-country $q_{k,c}$
needs to be materialized):**
$$x_k = q_k^T = \sum_{c} w_{k,c} \cdot d^g_c$$

**Tradable sector set $\mathcal{K}$** (export-share above a chosen threshold;
$\mathcal{K} \subset \{1,\dots,52\}$, determined from the IO table's export
column, not assumed): candidates identified by category — Estates(3),
Fishery(7), Coal(8), OilGasGeo(9), IronOre(10), OtherMine(11), FoodMan(12),
Textiles(14), Leather(15), WoodProd(16), CoalOilMan(19), Chemical(20),
Rubber(21), BasicMetal(22), MetalProd(23), Machinery(24), TranspEquip(25),
Furniture(26) — **~17–18 sectors**, to be confirmed against actual
export/output ratios in the IO table once opened.

Elasticity tensor: $\eta_{i,r,k}^{(2)}$, $k \in \mathcal{K}$ — **~17 full
$52\times34$ matrices.**

### Theme 3 — Domestic Demand Shocks (52 shocks, all sectors)

**Mechanism:** domestic retail sales volume (already real/deflated, not a
price series) compared against its own trailing trend, by category, used
directly as the demand shock — capturing *slowdown relative to normal*, not
just outright contraction, so a deceleration from +8% to +1% growth still
registers as a negative shock even though growth never turns negative.

**Source.** Bank Indonesia Survey Penjualan Eceran (SPE) — Indeks Penjualan
Riil (IPR), a real (volume) retail sales index. Monthly. No REST API;
predictable, scriptable URL pattern per release:
```
https://www.bi.go.id/id/publikasi/laporan/Documents/Data-Series-SPE-{Month}-{Year}.zip
```
(Indonesian month name, e.g. `Data-Series-SPE-Februari-2026.zip`.) Dashboard
update logic: construct this URL from the current month/year, check if newer
than the last cached vintage, download+unzip+re-run pipeline only if so.

**IPR categories (7), as published, kept in full** — manual mapping onto the
52 sectors is the user's task, not pre-filtered by data availability:
- Makanan, Minuman, dan Tembakau (Food, Beverages, Tobacco)
- Sandang (Clothing/Textiles)
- Suku Cadang dan Aksesori (Automotive Spare Parts/Accessories)
- Bahan Bakar Kendaraan Bermotor (Motor Vehicle Fuel)
- Barang Budaya dan Rekreasi (Cultural/Recreational Goods)
- Peralatan Informasi dan Komunikasi (Information/Communication Equipment)
- Perlengkapan Rumah Tangga Lainnya (Other Household Equipment)

IPR publishes both yoy and mtm growth directly — **use yoy only** ($g_{i,t}^{yoy}$);
mtm is heavily contaminated by religious-calendar seasonality (Ramadan/Idulfitri,
Christmas/New Year) shifting dates each Gregorian year, and is not safe to
annualize by compounding.

**Benchmark/trend.** Trailing 36-month moving average of $g_{i,t}^{yoy}$ per
category $i$:
$$\bar g_{i,t} = \frac{1}{36}\sum_{k=1}^{36} g_{i,t-k}^{yoy}$$
**Requires a one-time historical backfill of ≥3 years of past SPE zips**
before $\bar g_{i,t}$ is computable for the first time; each subsequent
monthly refresh just slides the window forward by one observation.

**Shock magnitude:**
$$x_i = g_{i,t}^{yoy} - \bar g_{i,t}$$

**Superseded design note (kept for record):** an earlier draft of this theme
paired IPR with CPI to check price/quantity co-movement before treating a
move as demand-driven (to rule out cost-push price changes being
misread as demand). This was dropped: IPR is *already* a real/volume series,
so the price/demand identification problem that motivated the check doesn't
arise from this series in the first place. Caveat carried into §9 instead:
if BI's internal deflator is imperfect, some residual price-driven noise could
still leak into IPR — accepted as a transparent, contestable simplification
for this version, not re-litigated with an extra CPI pull.

**Regional dimension — explicitly simplified.** The shock $x_i$ is
**national only**, not per-province; IPR's underlying survey only covers a
limited set of cities, not all 34 provinces, so no province-level shock
panel is constructed. All regional differentiation comes from $\eta_{i,r,i}^{(3)}$
alone, which IS fully calibrated at $52\times34$. This mirrors Theme 1 and
Theme 2, which are also national-shock/regional-elasticity by construction
(a world commodity price or a country's growth forecast has no Indonesian
regional dimension either) — all three themes share this same structural
pattern.

Elasticity tensor: $\eta_{i,r,m}^{(3)}$, $m = 1,\dots,52$ — **52 full
$52\times34$ matrices**, one per sector, covering every sector as a
domestic-demand-shock target regardless of whether a given IPR category
currently observes it (data availability for $x_j$ and the need to calibrate
$\eta$ are treated as separate questions — elasticities are calibrated for
all 52 up front so the design isn't blocked by today's IPR granularity).

## 5. Aggregation Across Themes

$$E_{i,r}^{(1)} = \sum_{j=1}^{8} \eta_{i,r,j}^{(1)} \cdot x_j$$
$$E_{i,r}^{(2)} = \sum_{k \in \mathcal{K}} \eta_{i,r,k}^{(2)} \cdot q_k^T$$
$$E_{i,r}^{(3)} = \sum_{m=1}^{52} \eta_{i,r,m}^{(3)} \cdot \left(g_{m,t}^{yoy} - \bar g_{m,t}\right)$$
$$E_{i,r} = E_{i,r}^{(1)} + E_{i,r}^{(2)} + E_{i,r}^{(3)}$$

## 6. Severity-Weighted Heatmap

$E_{i,r}$ alone weights a large % shock to a small cell the same as to a
large one — wrong lens for *risk*. Primary output:
$$\Delta L_{i,r} = E_{i,r} \cdot L_{i,r}^{0}$$
$L_{i,r}^0$ = baseline employment per sector-province cell (from the same or
a more frequently updated source than the SAM — vintage mismatch should be
tagged in metadata if sourced differently). $\Delta L_{i,r}$ is the primary
heatmap (color $\propto$ magnitude/sign); $E_{i,r}$ (%) retained as a
secondary/tooltip layer.

## 7. Elasticity-Calibration Scope (CGE Workload Summary)

| Theme | # of shocks | # of $52\times34$ matrices | Calibration method |
|---|---|---|---|
| 1 — Commodity price | 8 | 8 | 1% price perturbation per commodity, IndoTERM |
| 2 — Partner growth (export demand) | ~17 ($\mathcal{K}$, tradable only) | ~17 | 1% export-demand perturbation per tradable sector |
| 3 — Domestic demand | 52 (all sectors) | 52 | 1% domestic-demand perturbation per sector |
| **Total** | | **~77** | User-supplied; not automated by this pipeline |

This pipeline's job is shock-magnitude construction and aggregation only.
Elasticity tensors are supplied externally by the user from IndoTERM runs.

## 8. Computational Architecture ("Press Update" Logic)

1. **Theme 1:** for each of 8 commodities, check latest available price vs.
   cached value; if newer, fetch and recompute $x_j$.
2. **Theme 2:** check latest IMF WEO vintage vs. cached; if a new WEO has been
   published, recompute $d^g_c$ for all countries, recombine with cached
   Comtrade export-share weights (these update far less often — annual
   recalibration is enough) to get $q_k^T$ for each $k \in \mathcal{K}$.
3. **Theme 3:** construct the SPE zip URL for the current month; HEAD-check
   against cached vintage; if newer, download, unzip, append to the trailing
   36-month panel, recompute $\bar g_{i,t}$ and $x_i$ for all 7 IPR
   categories (mapped by the user onto relevant sectors of the 52).
4. Multiply each theme's $x$ vector against its respective pre-stored
   $\eta^{(\theta)}$ tensor (simple tensor contraction, no CGE solve).
5. Sum across themes (§5), multiply by $L_{i,r}^0$ (§6), render heatmap.

Elasticity tensors themselves (the slow, expensive part) are never recomputed
on refresh — only re-supplied when the user re-runs IndoTERM.

## 9. Assumptions and Known Limitations

- **Local linearity.** Each $\eta^{(\theta)}_{i,r,j}$ is the slope at a 1%
  perturbation, applied as constant for any $x_j$ magnitude. Real shocks
  (coal/CPO/nickel price swings, large WEO revisions) are often far outside
  this neighborhood; CGE closures (e.g. the dual labor-market closure —
  rigid-wage/quantity-adjusting formal vs. underemployment-absorbing informal)
  may not respond proportionally at larger magnitudes.
- **Additive separability — within and across themes.** Summing across $j$
  within a theme, and across the three themes, assumes no interaction
  effects. True only approximately under joint general-equilibrium market
  clearing; worse when multiple shocks load on the same factor/sector
  simultaneously (e.g. Theme 1's TGF export-price shock and Theme 3's
  Sandang domestic-demand shock both hitting Textiles in the same period).
- **Theme-specific elasticities, no cross-theme reuse.** A deliberate
  modeling choice (not a shortcut): domestic-demand, export-demand, and
  export-price shocks to the same sector are assumed to propagate
  differently through IndoTERM, so each theme is calibrated separately even
  for overlapping sectors. This increases the CGE workload (~77 matrices)
  but avoids assuming away a real economic distinction.
- **Theme 3 shock is national, not regional.** IPR survey coverage doesn't
  span all 34 provinces; all regional variation in Theme 3's contribution
  comes from $\eta^{(3)}_{i,r,m}$ alone. Genuine sub-national divergence in
  domestic demand (e.g. one province's retail softening while another's
  strengthens) is not captured.
- **IPR's "real" deflation taken at face value.** If BI's internal
  deflator imperfectly strips out price effects, some residual price-driven
  variation could leak into the yoy growth figure used as Theme 3's shock.
  Accepted as a transparent simplification, not independently re-verified
  against CPI in this version.
- **Time-invariant elasticities and baseline employment between refreshes.**
  $\eta^{(\theta)}_{i,r,j}$ and $L_{i,r}^0$ are both held fixed until manually
  recalibrated/re-sourced. A recalibration cadence for each should be defined
  explicitly (they may come from different-vintage sources, which should be
  tagged in metadata).
- **Heterogeneous epistemic status of inputs across themes.** Theme 1 inputs
  are CGE primitives (simulated structural elasticities). Theme 2 combines a
  CGE primitive (export-demand elasticity) with a unit-pass-through
  assumption on growth-to-demand transmission (not separately estimated).
  Theme 3 is a CGE primitive (domestic-demand elasticity) combined with an
  empirical trend-deviation measure. None of these should be presented to a
  dashboard user with the same implied confidence.
- **Unit-elasticity pass-through assumption in Theme 2.** $q_{k,c} = d^g_c$
  for every product $k$ and country $c$ — a 1pp growth revision is assumed to
  produce exactly a 1% demand change for any Indonesian export to that
  country, regardless of product or country. True income elasticities of
  import demand often differ from 1 (frequently exceeding it for
  industrial/commodity inputs like nickel or steel). Adopted for simplicity;
  estimating product/country-specific elasticities is the natural upgrade.
- **No re-solve benchmarking yet.** Before high-stakes policy use, validate
  the additive-linear approximation (across shocks and across themes)
  against a true joint CGE re-solve under a few realistic historical shock
  combinations, to establish an empirical error bound.

## 10. Future Work

- **Retire the linear shortcut entirely**, not patch it: once IndoTERM can
  run live on a server with acceptable latency, move from "look up
  pre-calibrated elasticity, multiply" to "solve the full CGE on the actual
  observed shock combination on every refresh." This removes the linearity
  and additive-separability assumptions outright rather than approximating
  around them. Open questions for that transition: server sizing, solve
  time, and queuing/caching strategy under concurrent users — to be scoped
  separately.
- **Two-point calibration check** for Theme 1 commodities with historically
  large swings: run each at 1% and 10%, compare slopes; if unstable, fit a
  quadratic correction term.
- **Estimate product/country-specific elasticities for Theme 2** in place of
  the unit-pass-through assumption, using historical Comtrade export values
  regressed against historical partner GDP.
- **Sub-national domestic-demand data for Theme 3**, if/when a province-level
  consumption proxy becomes available (e.g. Susenas, though its frequency is
  far lower than IPR's monthly cadence — would need its own treatment, not a
  simple substitution).
- **Interaction terms across themes** for sectors known to be jointly hit
  (e.g. a sector appearing in both Theme 1 and Theme 3 simultaneously), once
  the re-solve benchmarking in §9 quantifies how large the omitted-interaction
  error actually is.

## 11. Open Items Still Requiring User Input

- Confirm $\mathcal{K}$ (Theme 2's tradable-sector set) against actual
  export/output ratios from the IO table — list in §4 is a category-level
  estimate, not yet verified row-by-row.
- Manual mapping of IPR's 7 categories onto the 52 sectors (Theme 3) —
  user's task; some categories may split across more than one sector.
- Export-share threshold for $\mathcal{K}$ (1%? 5%? other?) — not yet chosen.
- Source and vintage for $L_{i,r}^0$ (baseline employment) — not yet
  specified; should be tagged with its own update cadence, possibly distinct
  from the SAM/IndoTERM base year.
