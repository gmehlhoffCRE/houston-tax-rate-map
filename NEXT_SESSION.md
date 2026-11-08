# Houston Property Tax Rate Map: handoff for the next session

Updated Nov 8, 2026. Read this first, then `README.md` (how to run, every layer and its source) and `HANDOFF.md`
(original spec). The previous chat ran out of context; everything it learned is here or in the README.

## Where the code is

- Private repo `gmehlhoffCRE/houston-tax-rate-map`. **All work since Nov 6 is on branch `claude/waller-county`**
  (latest commit "CenterPoint name casing; smaller development-site dots"). Not merged to `main` yet; ask the user
  before merging. `gmehlhoffCRE/.claude-skills-` has a stale old copy; ignore it.
- Cloud environment **"claude-skills tax map data"** (allowlisted hosts include services*.arcgis.com 1-9,
  www.arcgis.com, gis.rrc.texas.gov, gisweb.tceq.texas.gov, interactivemaps.sugarlandtx.gov, the CAD hosts,
  api.census.gov, lehd.ces.census.gov, www2.census.gov). Blocked: porthouston.com, hcfcd.org, ofis.trade.gov,
  comptroller.texas.gov, geocode.arcgis.com and server.arcgisonline.com (those two only matter in the user's
  browser, where they work).
- Built outputs and raw downloads lived in the old session's scratchpad and are gone. Full rebuild is about
  1 hour (see "Rebuild" below).

## What the user has now (delivered Nov 8)

Folder build `houston-8county-tax-map.html` + `-data-1..4.txt` + `-tiles-1..4.txt` (about 258 MB, 40 MB parts,
`.txt` because `.js` downloads were blocked for the user). Opens from a local folder; no Google key yet (Esri
basemaps, Map / Satellite / Hybrid). Counties: Harris, Fort Bend, Montgomery, Waller, Chambers, Brazoria,
Liberty, Galveston (3.01M accounts).

Features (details and sources in README "Map layers, site checks and drive times"):
- Rate map with filters, search, parcel drawer, Tax rate / Land use coloring, boundaries.
- Layer panel: 6 collapsible groups (Logistics, Trucking, Infrastructure, Workforce access, Environment,
  Planning and incentives), 26 layers, presets (Logistics, Trucking, Utilities, Risk, Development, Clear),
  per-layer opacity, dynamic legend, multi-feature hover, parcel shading fades to 30% under layers.
- Layers: rail by owner (cross ties), rail-served parcels (100 ft), road projects by timeline (TxDOT DCIS,
  H-GAC TIP, Houston, Fort Bend, Montgomery bond), intermodal (Cresa rail pin), ports/terminals/airports
  (Cresa vector pins in `web/icons/`, anchored at the pointer tip), Houston Pilots ship docks with drafts
  (`data/ports/`), FTZ grantees and 54 subzones, AADT, truck-restriction bridges (TxDOT, 1,046 flagged; 84,000 lb
  postings shown as permit-only), Texas Highway Freight Network, pipelines (dashed), transmission (dotted, towers),
  substations, water/sewer CCN, electric service areas (PUCT), gas territories (2017), METRO transit, flood,
  wetlands, evacuation zones, HCFCD watersheds, Superfund/brownfield, zoning (14 cities, categorized),
  Enterprise Zones, Opportunity Zones.
- Drive time (car/truck, 200 m TxDOT speed grid, water mask, address search via parcel addresses + Esri
  geocoder) with a labor shed table: labor force, production/warehouse workers (ACS C24010), their median pay
  (ACS B24021), industrial jobs in the band (LEHD 2024).
- Parcel drawer site checks: rail, zoning, OZ, Enterprise Zone, FTZ, electric and gas utility, watershed, flood,
  wetlands, evacuation, cleanup sites, truck time to Barbours Cut/Bayport/Velasco, freeway access minutes,
  truck-restriction bridges within 2 mi, freight network, METRO transit, road projects within 1 mi.
- Development sites filter (undeveloped parcels over N acres, gold dots at metro zoom).
- Shortlist (browser storage) with CSV export and Compare (up to 6 sites side by side, print/save as PDF).
- Share link (URL hash: view, layers, color mode, basemap, parcel, drive time, road-project stages).

## Rebuild (fresh session)

```bash
# county data and tiles: see README "Running it" (about 40 min); folder used: out8/
python pipeline/build_layers.py --raw layers_raw --out layers_out          # about 15 min (wetlands fetch is slow)
python pipeline/build_drive_grid.py --raw layers_raw --out layers_out      # about 5 min
python pipeline/build_rail_served.py --parcels out8/parcels.geojsonl --raw layers_raw --out layers_out
python pipeline/build_labor.py --layers layers_out/web/data/layers --raw layers_raw   # after build_layers
python pipeline/inject.py --embed out8 --layers layers_out/web/data/layers --split --chunk-mb 40 --part-ext txt \
  --out dist/houston-8county-tax-map.html
```

Tests (headless Chromium; CDN scripts routed to local npm copies of deck.gl 9.0.38, pmtiles 3.2.1,
@loaders.gl/mvt 4.2.0-beta.2 through a JSON map of URL regex to file, as in the old `cdnmap.json`):
`tests/layers_v3_check.js` (26 checks), `tests/site_tools_check.js` (6), `tests/dt_address_check.js` (11),
county checks `tests/*_check.js`. Serve the dist folder with `node tests/serve.js <dir> <port>`.
Last results: 26/26, 6/6, 11/11.

## Ideas discussed, not built

- Commuting flows (LEHD origin-destination) for a true labor shed; BLS county wages.
- City truck routes and oversize/overweight corridors (no public GIS found).
- Chapter 312 abatement zones, JETI, FTZ zone boundaries, CenterPoint capacity, detention rates: no public GIS
  (PDFs or tables only; hosts blocked).
- Interstate on-ramp points (freeway access currently = nearest freeway cell of the drive grid).
- Thinning wetlands (25 MB) if load time becomes a complaint.

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

- Census API now requires a key; `build_labor.py` streams the ACS table-based summary files from
  www2.census.gov instead (245 + 180 MB nationwide, filtered to Texas tracts).
- TxDOT DCIS project layer rejects date filters in `where`; fetch all and filter in pandas.
- Worker restarts kill background jobs started with `&`; rerun them (raw downloads are cached in layers_raw).
- deck.gl CollisionFilterExtension tests an icon at its anchor: with pins anchored at the tip it drew them half
  transparent, so the icon layer has no collision filter.
- A trailing `//` comment on a line of joined statements silently disabled the next statements once (icon canvas
  size); keep statements on their own lines.
- Headless clicks time out when many layers are on (software GL); tests click through `$eval(el=>el.click())`.

## User preferences

- Grant (Cresa Houston). No em dashes in UI copy. Cresa styling. Confirm specs before major features.
- Show 2025 rates until Harris has 2026, then switch all counties together.
- Prefers files delivered in chat; large files as `.txt` parts of 40 MB or less. When only the page changed,
  send just the html (data parts differ only by a gzip timestamp).
- Industrial real estate focus (logistics, trucking, labor, utilities). Likes being offered next ideas.
