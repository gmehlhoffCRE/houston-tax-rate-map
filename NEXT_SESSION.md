# Houston Property Tax Rate Map: handoff for the next session

Updated Nov 6, 2026. Read this first, then `README.md` (how to run) and `HANDOFF.md` (original spec and decisions).

## Where the code is

- Private repo `gmehlhoffCRE/houston-tax-rate-map`, branch `main` (moved Nov 6, 2026 with its full history from
  `gmehlhoffCRE/.claude-skills-`, branch `claude/relaxed-ritchie-7m99j6`, folder `houston-tax-rate-map/`; that copy
  is now stale). Waller work is on branch `claude/waller-county` until merged.
- Cloud environment **"claude-skills tax map data"**. Hosts now also include the Waller sources:
  `services3.arcgis.com` (Waller CAD parcels), `gisweb.tceq.texas.gov` (TCEQ districts), `waller-cad.org`,
  `www.arcgis.com` (item search) and a few others. The environment lists only `.claude-skills-` as its repo; add
  `houston-tax-rate-map` in Settings so new sessions clone it.
- Built outputs (tiles, shards, local files) and raw downloads live in a session's scratchpad and are gone.
  Rebuilding everything takes about 40 minutes (downloads about 10, data about 5, tiles about 15, test about 10).
  Waller alone: about 1 minute to download, 10 s for rates, 10 s for data, 6 s for tiles.

## What works today

| County | Parcels | Rates | Values | Notes |
|---|---|---|---|---|
| Harris | 1,536,057 from HCAD `Parcels.zip` | 2025 adopted, `build_rates.py` | 2026 appraised, `real_acct.txt` | Acceptance accounts pass (0281700000001 = 1.9557, 0402040000009 = 2.1252 + TIRZ Eastside 6) |
| Fort Bend | 386,201 from FBCAD public ArcGIS layer | 2025 from the Fort Bend rate grid CSV (`data/fortbend/fb_rates_2025_grid.csv`) | current FBCAD values | R101338 = 2.2859. Building area is living area only, so tax/SF is often blank for commercial |
| Montgomery (demo) | 329,989 from the City of Houston mirror of MCAD parcels | 2025 from user's workbook (`data/montgomery/...xlsx`) joined through `data/montgomery/mc_code_map.csv` | **none yet** | 352872 = 1.9071. About 15% of accounts "rate incomplete" (about 79 unknown unit codes); about 90 codes matched by pattern, unconfirmed |
| Chambers | 38,500 shapes / 43,198 accounts from Chambers CAD's 2026 certified roll + parcel shapefile | 2025 from the Comptroller's rates and levies files (`data/chambers/ch_units_2025.csv`) | 2026 certified market value | C49490 = 2.2568. 5 unit codes unidentified (no rate). No building area |
| Galveston | 188,039 shapes / 202,064 accounts from GCAD's 2026 certified export + parcels | 2025 from GCAD's rate sheet (`data/galveston/gv_units_2025.csv`) | 2026 certified market value | G112187 = 1.7190, G744654 = 1.6758 + Kemah MD 1.00. Building area from improvement records |
| Liberty | 147,249 shapes / 113,909 accounts from Liberty CAD's public layer | 2025 from LCAD's rate sheet; districts by CAD and TCEQ polygons | LCAD market value | L18096 = 2.2120, L254876 = 1.5041 + MMD 1 0.35. MMD 1 polygon covers about a third of its accounts |
| Brazoria | 255,806 shapes / 252,094 rated accounts from BCAD's 2026 certified export + parcel shapefile | 2025 from the Comptroller (`data/brazoria/br_units_2025.csv`) | 2026 certified market value | B600116 = 2.3546 (+ Pearland MMD 2), B500027 = 2.8546. Building area from improvement records |
| Waller | 54,128 shapes / 47,907 accounts from Waller CAD's public layer | 2025 from WCAD's rate list (`data/waller/wc_rates_2025.csv`); MUD/district areas by TCEQ and county polygons | WCAD market value | W44584 = 1.7322, W248025 = 3.1361. ESD 200 applied countywide (unconfirmed). No property class or building area |

Map features: Cresa styling, Google basemap (Esri fallback), PMTiles via deck.gl 9.0.38 `MVTLayer` + pmtiles 3.2.1,
dissolved "zones" layer below Google zoom 14, parcels from 14 up, GPU filters, owner/address/account search,
rate shading and parcel line toggles, county on/off toggles, card with monthly tax per SF, missing-file message
for the folder build. Browser test: `tests/e2e.js` (24 checks, all passing on the three-county build with the Google basemap). On the
four-county build without a Maps key (Esri basemap, blocked in the sandbox) 19 pass: the 2 basemap-error checks
fail on the blocked host, and hover/click on dense Harris parcels fail because headless software GL renders
about 2 fps, so deck.gl drops the click (it never reaches onClick; Waller clicks work). Same with the old template.
Fixed: `setView` in Esri mode now updates the page's zoom state (deck.gl does not report camera moves made in code).

## Delivery formats

- **Hosted** (recommended for brokers): `pipeline/inject.py --tiles <bucket url> --shards <bucket url>`, then
  `deploy/upload_gcs.sh` to the Firebase/GCS bucket and Netlify for the page. Not deployed yet.
- **Local folder** (what the user has): `build_tiles.sh OUT lean` then
  `inject.py --embed OUT --split --chunk-mb 40 --part-ext txt --out houston-3county-tax-map.html`.
  Seven files (page + six .txt), about 200 MB, opens in about 10 s. `.js` parts failed to download for the user;
  `.txt` works.

## Open items (in priority order)

**Google Maps key (user plans to set it up the weekend of Nov 7-8, 2026):** a new key just for this project,
restricted to the Maps JavaScript API, application restriction None (local file), daily quota and a billing
alert. The user opens the map as `houston-8county-tax-map.html?key=KEY`; no rebuild needed. If they want the
key built into the file, get it through a secure channel (not chat) and pass `inject.py --key`. Without a key
the page uses Esri basemaps, and Map / Satellite / Hybrid now works there too.

Coverage (Nov 6): the user has all the counties they care about for now: Harris, Fort Bend, Montgomery, Waller,
Chambers, Brazoria, Liberty, Galveston. Austin County (the ninth Houston MSA county) may be added later; ignore
until asked. Delivered build: `houston-8county-tax-map.html` + eight .txt parts (241 MB).

Load speed (user asked Nov 6, chose to leave as is): the folder build reads every data part before the map
shows, so county toggles (or a Harris-only default) do not speed opening. Options if it comes up again:
per-county data/tile parts loaded when a county is switched on; a separate Harris-only build; or the hosted
build (bucket + Netlify), which fetches only tiles and shards in view.

0. **Galveston County: built Nov 6** (README "Galveston County", `tests/galveston_check.js`). Comptroller's 2025
   special district rows for Galveston are wrong (copied rates); GCAD's own rate sheet is used.
0. **Liberty County: built Nov 6** (README "Liberty County", `tests/liberty_check.js`). Open: a current Liberty
   County MMD 1 boundary (LCAD certifies 32,363 accounts in it; TCEQ's polygon catches 10,735). Ask LCAD's GIS
   staff (936-336-5722). Also no state class or building area in the public layer.
0. **Brazoria County: built Nov 6** (README "Brazoria County", `tests/brazoria_check.js`). Open: five MUDs with
   no Comptroller rate (38, 48, 67, 90, Preservation Creek 1) carry 0; confirm with BCAD or the MUDs' tax
   assessors. 

1. **Chambers County: built Nov 6** from the CAD's 2026 certified roll (taxing units per account) and parcel
   shapefile; 2025 rates from the Comptroller (README "Chambers County"). C49490 = 2.2568, C67998 = 2.2509
   (`tests/chambers_check.js`). Open: identify unit codes 21, 23, 69, 70, 78 (no certified value report, no rate
   applied; ask Chambers CAD, 409-267-3795). 70 may be the Winnie-Stowell Hospital District.
2. **Waller County: delivered** in the Nov 6 folder builds (four-county, then five-county with Chambers).
   Open Waller questions for the user or WCAD:
   - Waller-Harris ESD 200 boundary (about 10% of the county is outside it; applied everywhere for now).
   - WCAD certified export (state class, building area, ag use value, exact taxing units per account) would
     replace the polygon overlay. WCAD sells bulk data; its eSearch terms prohibit scraping.
   - Brookshire MWD: TCEQ polygon catches about 55% of the certified parcels (rate is only 0.0139).
3. **MCAD code list** (user is asking the county): fill `data/montgomery/mc_code_map.csv` (entity = exact
   workbook name, confirmed = yes), rerun `build_montgomery_rates.py`, then `build_county_data.py` and `inject.py`.
   Tiles do not need rebuilding.
4. **MCAD appraised values**: 2025 certified export from mcad-tx.org/appraisal-data-exports (user download;
   the site's file links go through True Prodigy, and extracting them from the site's code was correctly blocked).
5. **2026 switch** once HCAD's `curr` column is filled: `build_rates.py --year 2026`,
   `build_fortbend_rates.py --rates-file data/fortbend/fb_rates_2026_grid.csv --year 2026`,
   `build_montgomery_rates.py --year 2026`. Combo ids are stable, so no re-tiling.
   Waller: WCAD posts the year's rate PDF on its certified totals page around January (the 2025 list came out
   Jan 16, 2026); parse it to `data/waller/wc_rates_2026.csv` like the 2025 one, then
   `build_waller_rates.py --rates data/waller/wc_rates_2026.csv --year 2026`.
6. Fort Bend boundary overlays (FBCAD GIS "Shapefiles Only" zip) and county outlines for Fort Bend/Montgomery.
7. Hosted deploy (bucket + Netlify).

## Gotchas learned the hard way

- `pip install tippecanoe` works (felt/tippecanoe 2.72 binaries); its `tile-join` segfaults, so `merge_pmtiles.py`
  merges the two layers. Never set a tile size limit: tippecanoe can loop forever on dense tiles.
- The zoomed-out layer must be pre-dissolved (`build_zones.py`); tippecanoe coalescing alone gives 1 MB+ tiles.
- pandas 3 infers integer categories: read codes as strings (fixed in `build_rates.py`).
- Never write NaN into JSON (allow_nan=False everywhere); it broke whole shard files once.
- HCAD's School layer extends to a rectangle beyond the county; boundaries are clipped to `County.shp`.
- The public repo must not receive built map files (owner and address data for 2M+ accounts) or the Maps key;
  `dist/` is gitignored. Git LFS uploads are blocked from this environment anyway.
- The Google Maps key worked from localhost, so it is not referrer-restricted. Recommend restricting it.
- Headless Chromium here renders with software GL (about 2 fps); the test waits on page state, not timers.
  CDN scripts (jsDelivr, unpkg) are blocked here, so tests route them to local npm copies (see
  `tests/run_fixture_test.sh` and the cdn map pattern in `tests/e2e.js` usage).
- FBCAD rate grid files: "Total Rate" is the file's year, "Prev Rate" the year before (2026 file = 2026 rates).

## User preferences

- Grant (Cresa Houston). No em dashes in UI copy. Cresa styling. Confirm specs before major features.
- Show 2025 rates until Harris has 2026, then switch all counties together.
- Prefers files delivered in chat; large files as `.txt` parts of 40 MB or less.
