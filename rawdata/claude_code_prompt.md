# Prompt for Claude Code (Plan Mode)

Copy everything below into Claude Code at the start of the new project.

---

I'm building a layoff-risk early-warning dashboard for Indonesia's Ministry
of Manpower, on top of a CGE model called IndoTERM. Before doing anything
else, **read all three of the following files in full**:
`layoff_dashboard_spec.md`, `layoff_dashboard_full.tex`, and
`layoff_dashboard_full.pdf` — all in this project folder. The `.tex` and
`.pdf` contain the same methodology as the `.md` but in a more complete,
narrative, citable form, with worked explanations and explicit "design
decision" / "implementation warning" call-outs that the `.md` compresses or
omits. Read them, not just the `.md` — do not rely on the `.md` alone, and
do not rely on anything I summarize below as a substitute for reading the
source documents yourself. Treat the `.md` as the structured checklist and
the `.tex`/`.pdf` as the authoritative explanation of *why* each part of the
pipeline is built the way it is.

**Do not write any implementation code yet.** I want a plan first.

## Quick-reference summary of the pipeline (verify this against Section 8,
## "Computational Architecture: Press Update Logic," in the .tex/.pdf —
## this is my own condensed restatement of that section, not a replacement
## for reading it)

1. **Theme 1 (commodity prices).** For each of the 8 commodities, check the
   latest available value from its source (World Bank Pink Sheet monthly
   file, or FRED/EIA daily API for oil/gas) against the last cached value.
   If newer, fetch and recompute the shock magnitude.
2. **Theme 2 (trading-partner growth).** Check whether a new IMF World
   Economic Outlook release has been published since the last cached one
   (these come out 3 times a year: April, September/October, January). If
   so, re-pull the growth-forecast revision for all relevant countries via
   the IMF's API and recompute the export-demand shock for each tradable
   sector, combined with cached export-share weights (these weights are
   recomputed on a much slower cadence, e.g. annually, from trade data —
   not on every refresh).
3. **Theme 3 (domestic demand).** Construct the expected Bank Indonesia
   retail-sales zip file URL for the current month; check existence/
   freshness against the cached vintage; if newer, download, unzip, append
   the new month's category-level data to the trailing panel, and recompute
   the benchmark-deviation shock for all seven retail categories.
4. **Multiply and aggregate.** Each theme's shock vector is multiplied
   against its own pre-stored elasticity tensor (a simple matrix
   multiplication, not a CGE solve), summed across all three themes, and
   scaled by baseline employment to get the absolute employment-change
   matrix.
5. **Render.** The resulting absolute-employment-change matrix is rendered
   as the heatmap; the percentage-change matrix is exposed as supplementary
   detail (e.g. a tooltip).

The elasticity tensors themselves (step 4) are never recomputed on refresh —
they're supplied externally by me from IndoTERM runs and only change when I
re-run the model, not on any dashboard-refresh schedule.

## What I need a plan for

1. **Project structure.** Propose a file/folder layout for a pipeline
   implementing the five steps above, including:
   - One ingestion module per theme (steps 1–3), each with its own
     caching/vintage-checking logic so a "press update" only re-fetches
     when genuinely new data is available, per source.
   - A storage format for the elasticity tensors (52×34 matrices), one set
     per theme.
   - The aggregation and scaling logic (step 4) and the rendering layer
     (step 5) — the rendering technology (web app, notebook, dashboard
     framework) is open; propose options and trade-offs rather than
     assuming one.

2. **Baseline employment $L_{i,r}^0$ — I will supply this directly, as
   `l0.csv` in this project folder. I'm still preparing this file and it is
   not in the folder yet — I'll add it shortly.** Once added, it will be
   real data for the 52×34 baseline employment matrix used in step 4
   above. This resolves one of the spec's "open items" — treat $L_{i,r}^0$
   as a known, user-supplied input that is coming, not something to source
   or estimate yourself, and don't assume it's already present or try to
   read it now. I haven't fixed the internal layout of `l0.csv` yet (e.g.,
   whether sectors are rows and provinces are columns, or vice versa;
   whether labels are the 52 sector codes from the spec or numeric indices)
   — propose the layout you'd want, and once I confirm and add the file,
   validate on load that it's actually 52×34, has no missing cells, and
   has no negative values, before it's used anywhere downstream. In the
   meantime, your plan should make clear which steps can proceed without
   `l0.csv` (e.g. building the ingestion modules, the placeholder
   elasticity generator) and which are genuinely blocked until it arrives
   (e.g. producing an actual $\Delta L_{i,r}$ heatmap).

3. **Data ingestion modules** (steps 1–3 above), each additionally handling:
   - The specific access pattern documented in the spec (free REST APIs
     for Theme 1's World Bank Pink Sheet / FRED, Theme 2's IMF SDMX API and
     UN Comtrade/BPS WebAPI, Theme 3's BI zip-file URL pattern with no
     formal API).
   - The specific correctness pitfalls already identified in the spec —
     in particular the percent-change formula bug warning in Theme 1, the
     yoy-not-mtm requirement in Theme 3, and the 36-month historical
     backfill requirement before Theme 3's benchmark can be computed at
     all. Flag in your plan exactly where each of these gets enforced
     (e.g., as a unit test, an assertion, a backfill script).

4. **Synthetic/placeholder elasticity tensors — needed now, not after CGE
   runs are ready.** I will eventually supply ~77 real, CGE-calibrated
   52×34 elasticity matrices (8 for Theme 1, ~17 for Theme 2, 52 for Theme
   3) from my own IndoTERM runs, but that will take time. I want the
   dashboard's full pipeline (all five steps above) to be testable
   end-to-end *before* those are ready, using **educated-guess placeholder
   elasticities**, clearly labeled as synthetic and built so every cell can
   be swapped for a real CGE value later without changing any other code.

   **Use the simplest possible placeholder. Do not introduce any data
   dependency beyond $L_{i,r}^0$ (item 2 above) for this.** A placeholder
   elasticity tensor for a 1% shock to sector $k$ is itself a 52×34 matrix
   (the same object defined in the spec for $\eta_{i,r,j}$) — build it
   directly, in one step, as follows: every cell is 0, except the 34 cells
   for sector $k$ across all provinces. For those 34 cells, distribute a
   total of 1% across the provinces in proportion to each province's
   actual share of sector $k$'s baseline employment, read directly from
   the $L_{i,r}^0$ matrix I'm supplying (item 2 above) — a province with a
   bigger share of sector $k$'s employment in $L_{i,r}^0$ gets a
   proportionally bigger value in that province's cell for sector $k$.
   Repeat independently for every sector $k$ that needs a placeholder
   (i.e., once per shock, across all three themes) to build the full set
   of placeholder 52×34 matrices.

   Whatever you build, this "placeholder generator" should live in its own
   clearly separated module from the eventual "load real CGE output" path,
   so that swapping a placeholder for a real value later is a clean,
   isolated change — not a rewrite. Every output that uses a placeholder
   elasticity should be visibly flagged as such (in code structure and
   ideally in any rendered output/metadata), so it's never confused with a
   real, CGE-calibrated result once both start coexisting in the same
   dashboard.

5. **Open items.** The spec's final section lists unresolved decisions
   (verifying the tradable sector set $\mathcal{K}$, the export-share
   threshold, the IPR-to-52-sector mapping). Baseline employment
   $L_{i,r}^0$ is no longer an open item (see item 2) — exclude it from
   this list. Don't silently resolve the remaining items yourself — surface
   them in your plan as explicit decision points for me, with your
   recommendation if you have one, but flag clearly that they're pending
   confirmation rather than already settled.

6. **Sequencing.** Propose a build order across the five pipeline steps and
   the items above — e.g., which theme's ingestion module to stand up
   first, when to load and validate $L_{i,r}^0$, when to introduce the
   placeholder elasticities, when the heatmap rendering becomes testable —
   and your reasoning for that order.

Ask me any clarifying questions you need before finalizing the plan, but
don't start implementing — I want to review and approve the plan first.
