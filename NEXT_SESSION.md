# Houston Property Tax Rate Map: handoff for the next session

Updated Nov 6, 2026. Read this first, then `README.md` (how to run) and `HANDOFF.md` (original spec and decisions).

## Where the code is

- Repo `gmehlhoffCRE/.claude-skills-` (public), branch `claude/relaxed-ritchie-7m99j6`, folder `houston-tax-rate-map/`.
- Start the new session in the cloud environment **"claude-skills tax map data"**. It allows
  `download.hcad.org`, `hcad.org`, `fbcad.org`, `www.fbcad.org`, `gisweb.fbcad.org`, `mcad-tx.org`,
  `www.mcad-tx.org`, `services1.arcgis.com`, `cms2.revize.com`, `prod-container.trueprodigyapi.com`,
  `cdn.builder.io`, `geohwp.houstontx.gov`. Waller hosts are not added yet.
- Built outputs (tiles, shards, local files) and raw downloads lived in the old session's scratchpad and are gone.
  Rebuilding everything takes about 40 minutes (downloads about 10, data about 5, tiles about 15, test about 10).

## First step: move to the new private repo

The user is creating a private repo (e.g. `gmehlhoffCRE/houston-tax-rate-map`, empty). Attach it with `add_repo`
(push access), then move the folder with its history:

```bash
cd .claude-skills- && git subtree split -P houston-tax-rate-map -b taxmap-export
git push https://github.com/gmehlhoffCRE/<new-repo>.git taxmap-export:main
```

Then work in the new repo (paths in this file drop the `houston-tax-rate-map/` prefix). Being private, it may hold
built outputs that stay under GitHub's 100 MB per-file limit (use the `.txt` parts); keep the Maps key out of git.

## What works today

| County | Parcels | Rates | Values | Notes |
|---|---|---|---|---|
| Harris | 1,536,057 from HCAD `Parcels.zip` | 2025 adopted, `build_rates.py` | 2026 appraised, `real_acct.txt` | Acceptance accounts pass (0281700000001 = 1.9557, 0402040000009 = 2.1252 + TIRZ Eastside 6) |
| Fort Bend | 386,201 from FBCAD public ArcGIS layer | 2025 from the Fort Bend rate grid CSV (`data/fortbend/fb_rates_2025_grid.csv`) | current FBCAD values | R101338 = 2.2859. Building area is living area only, so tax/SF is often blank for commercial |
| Montgomery (demo) | 329,989 from the City of Houston mirror of MCAD parcels | 2025 from user's workbook (`data/montgomery/...xlsx`) joined through `data/montgomery/mc_code_map.csv` | **none yet** | 352872 = 1.9071. About 15% of accounts "rate incomplete" (about 79 unknown unit codes); about 90 codes matched by pattern, unconfirmed |

Map features: Cresa styling, Google basemap (Esri fallback), PMTiles via deck.gl 9.0.38 `MVTLayer` + pmtiles 3.2.1,
dissolved "zones" layer below Google zoom 14, parcels from 14 up, GPU filters, owner/address/account search,
rate shading and parcel line toggles, county on/off toggles, card with monthly tax per SF, missing-file message
for the folder build. Browser test: `tests/e2e.js` (24 checks, all passing on the three-county build).

## Delivery formats

- **Hosted** (recommended for brokers): `pipeline/inject.py --tiles <bucket url> --shards <bucket url>`, then
  `deploy/upload_gcs.sh` to the Firebase/GCS bucket and Netlify for the page. Not deployed yet.
- **Local folder** (what the user has): `build_tiles.sh OUT lean` then
  `inject.py --embed OUT --split --chunk-mb 40 --part-ext txt --out houston-3county-tax-map.html`.
  Seven files (page + six .txt), about 200 MB, opens in about 10 s. `.js` parts failed to download for the user;
  `.txt` works.

## Open items (in priority order)

1. **Waller County** (user asked; not started). Plan: same pattern as Montgomery.
   - Parcels: TxGIO statewide StratMap parcels (Waller tax year 2026) or Waller County GIS open data hub
     (waller-county-gis-open-data-portal-wallercounty-gis.hub.arcgis.com). Check for a per-parcel taxing unit field.
   - Rates: ask the user for a 2025 rate list for all Waller units (county 2025 = 0.439463 M&O + 0.093133 I&S).
   - If no unit codes on parcels: Waller CAD code list or certified export (search.waller-cad.org is the property search).
   - Needs hosts added to the environment (propose with update_environment).
   - Write `build_waller_rates.py` modeled on `build_montgomery_rates.py`; add `"wc": "Waller"` to `COUNTIES`
     in `build_county_data.py`; extend `countyOf`/`CAD` in the page if Waller account ids are distinct.
2. **MCAD code list** (user is asking the county): fill `data/montgomery/mc_code_map.csv` (entity = exact
   workbook name, confirmed = yes), rerun `build_montgomery_rates.py`, then `build_county_data.py` and `inject.py`.
   Tiles do not need rebuilding.
3. **MCAD appraised values**: 2025 certified export from mcad-tx.org/appraisal-data-exports (user download;
   the site's file links go through True Prodigy, and extracting them from the site's code was correctly blocked).
4. **2026 switch** once HCAD's `curr` column is filled: `build_rates.py --year 2026`,
   `build_fortbend_rates.py --rates-file data/fortbend/fb_rates_2026_grid.csv --year 2026`,
   `build_montgomery_rates.py --year 2026`. Combo ids are stable, so no re-tiling.
5. Fort Bend boundary overlays (FBCAD GIS "Shapefiles Only" zip) and county outlines for Fort Bend/Montgomery.
6. Hosted deploy (bucket + Netlify), and optionally a separate private repo for the project.

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
