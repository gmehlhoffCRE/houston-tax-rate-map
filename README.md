# Houston Property Tax Rate Map (Cresa Houston)

Internal map that colors every Harris County parcel by its combined property tax rate, overlays taxing district
boundaries, and opens a detail card on click. Phase 1 scales the Ship Channel prototype to the full county with
vector tiles. Background, conventions and locked decisions: [HANDOFF.md](HANDOFF.md).

## How it fits together

```
HCAD downloads ──> build_rates.py ──> data/hcad_*.csv  (rates per jurisdiction combo, stable combo IDs)
                                   │
Parcels.gdb, real_acct.txt ──> build_county_data.py ──> out/parcels.geojsonl
                                   │                     out/web/data/combos.json, boundaries/*.json
                                   │                     out/bucket/shards/a/*.json   account records
                                   │                     out/bucket/shards/s/*.json   search index
                                   └──> build_tiles.sh ──> out/bucket/harris_parcels.pmtiles
inject.py ──> out/web/index.html (single file page)

Netlify:   out/web/            index.html + data/ (combos.json about 2 MB, boundaries)
GCS/Firebase Storage bucket:   harris_parcels.pmtiles (read with HTTP Range), shards/
```

### Tiles: two layers in one PMTiles file

| Layer | Tile zoom | Google zoom | Contents |
|---|---|---|---|
| `zones` | 7 to 12 | 8 to 13 | combo id + property type group, neighboring parcels with equal values merged. Keeps the county view light (under 300 features per tile in the fixture) |
| `parcels` | 13 to 16 | 14 and up | one feature per parcel: `a` account, `c` combo id, `t` type group, `v` appraised value. Never dropped or merged. Overzoomed past Google zoom 17 |

Owner and address are not in the tiles. The drawer and search read them from the account shards, so the tiles
stay small and owner data can refresh without re-tiling. Tiles only need rebuilding when parcel shapes or
combo assignments change; rates live in `combos.json`.

### How the page reads PMTiles with no build step

deck.gl 9.0.38 `MVTLayer` with a custom `fetch` prop. The layer requests `pmtiles://{z}/{x}/{y}`; `fetch` reads
the tile with the protomaps `pmtiles` 3.2.1 library (UMD script tag) and hands the bytes to deck's normal MVT
loader through a short-lived `blob:` URL, so decoding still runs in the loaders.gl worker. All scripts come from
jsDelivr: deck.gl, pmtiles, and the matching `@loaders.gl/mvt@4.2.0-beta.2` worker.

### Speed

- Rate, colors, filters and the drawer all resolve through `combo_id` (7,271 combos) instead of per-parcel data.
- Rate range and appraised value filters run on the GPU (`DataFilterExtension`), so slider drags do not recompute
  parcels. Property type, school district, city, water district and histogram band clicks fold into one
  pass/fail value per parcel, recomputed only when those selections change.
- Histogram and match count: from parcels loaded in view at Google zoom 14+, from countywide account counts
  per combo and type below that (labeled in the rail).

### Search

One box for owner name, site address, and HCAD account number, all from static JSON shards (no database, no
Google Places cost):

- Account numbers (6 to 13 digits) look up the account shards by prefix.
- Words look up the search shard for the longest word typed (first 3+ letters); the other words narrow the
  results in the browser. Results are ordered by exact word matches, then appraised value.
- Shards split into longer prefixes when they pass 3,000 records (`shards/manifest.json`), so no file is large.

## Fort Bend County

Fort Bend CAD publishes one parcel layer that carries shapes, owner, site address, value, state code and each
parcel's taxing units (`taxunits`, e.g. `C09,D01,G01,J07,M25,S07,CAD`), plus a rate sheet by unit code.

```bash
python pipeline/fetch_fortbend.py --out fortbend                    # 386,201 parcels + rate sheet from FBCAD
python pipeline/build_fortbend_rates.py --src fortbend --out data --year 2024
python pipeline/build_county_data.py --gis gis --rates data --out out \
  --parcels gis/Parcels.gdb --cama Real_acct_owner.zip \
  --parcels fortbend/fb_parcels.gpkg --cama fortbend/fb_real_acct.txt
```

- Combo ids start at 50000 (`data/fb_combo_registry.csv`), unit codes are prefixed `FB-`, and every combo
  carries its county and rate year, so the page labels cards "FBCAD account" and shows each county's rate year.
- Rates: Fort Bend tax rate grid exports in `data/fortbend/`. `fb_rates_2025_grid.csv` (Total Rate = 2025, Prev
  Rate = 2024) is the one in use, matching Harris's 2025 rates; Fort Bend ISD shows 1.0569 (prev 0.9869).
  `fb_rates_2026_grid.csv` (Total = 2026, Prev = 2025) is ready for the switch to 2026:
  `build_fortbend_rates.py --rates-file data/fortbend/fb_rates_2026_grid.csv --year 2026`. Combo ids stay the
  same, so tiles need no rebuild.
- Unit codes missing from the rate file: T codes (TIRZs and zones, e.g. T149 foreign trade zone) add no rate,
  P codes are public improvement district assessments (noted on the card), SM codes are management districts.
  Other missing codes (newer MUDs and LIDs) are flagged as incomplete rates (about 6,400 parcels).
- No split percentages: FBCAD lists units per parcel, so each applies in full.
- Building area is FBCAD's living area (`totsqftlvg`), often blank for commercial property, so tax per SF is
  often unavailable there. No Fort Bend boundary overlays yet.
- FBCAD account numbers are quick ref ids (`R100842`); search accepts them.

## Montgomery County (demo)

Parcels come from the City of Houston's public mirror of MCAD parcels (329,989, tax year 2026: owner, address,
state class, building SF, `TAXINGUNIT` codes). Rates come from the tax office workbook
(`data/montgomery/Montgomery_County_Tax_Rates_2025_2026.xlsx`, 2025 in use, "No Tax Levied" = 0), joined by
entity name through `data/montgomery/mc_code_map.csv`:

- 68 codes from the tax office's 2026 rate list (`mc_tax_office_codes_2026.csv`), marked confirmed
- codes suggested by pattern (M + number = Montgomery County MUD n, ME n = East Montgomery County MUD n, ...)
- zones (Z, RZ, ZE, FTZ) and P codes (improvement districts) carry no rate
- about 79 codes still unknown: their parcels (about 15%) show "rate incomplete"

When MCAD sends its code list, edit `mc_code_map.csv` (entity = exact workbook name, confirmed = yes) and rerun:

```bash
python pipeline/fetch_fortbend.py --out montgomery --prefix mc --no-rates \
  --layer https://geohwp.houstontx.gov/arcgis/rest/services/03_BaseData_External/Parcels_Current/FeatureServer/3 \
  --fields "OBJECTID,PARCEL_ID,STATECLASS,TAX_YEAR,OWNER,ADDRESS,TAXINGUNIT,TAX_EXEMPT,IMPR_SQ_FT,YEAR_BUILT,NGHD_CODE"
python pipeline/build_montgomery_rates.py --src montgomery --out data --year 2025 \
  --workbook data/montgomery/Montgomery_County_Tax_Rates_2025_2026.xlsx \
  --codes data/montgomery/mc_tax_office_codes_2026.csv --code-map data/montgomery/mc_code_map.csv
```

then `build_county_data.py` with `--parcels montgomery/mc_parcels.gpkg --cama montgomery/mc_real_acct.txt` added.
No appraised values yet (MCAD's certified export would add them), so Montgomery cards show the rate only.

## Waller County

Waller CAD's public parcel layer (BIS, 54,128 shapes, 47,907 accounts) carries owner, site address, market value
and only the school, city and county codes. Every other taxing unit is placed by overlaying district polygons on
a point inside each parcel:

- MUDs, WCIDs, management, improvement and road districts, Brookshire MWD: TCEQ water district map
- Brookshire-Katy Drainage District: Waller County GIS
- Waller County, its road and FM levy (RFM) and Waller-Harris ESD 200: every parcel. ESD 200 has no public
  boundary and covers about 90% of the county (49,941 of 54,667 properties in 2025), so it is flagged on the card

Rates are Waller CAD's adopted 2025 list (`data/waller/wcad_2025_tax_rates.pdf`, parsed to `wc_rates_2025.csv`).
`data/waller/wc_district_map.csv` says how each CAD code is found (`cad:school`, `cad:city`, `countywide`,
`tceq:<name>`, `county:bkdd`, `none`) and holds the CAD's 2025 certified property count for each code.

```bash
python pipeline/fetch_waller.py --out waller        # parcels, county outline, TCEQ districts, B-K drainage (1 min)
python pipeline/build_waller_rates.py --src waller --out data --year 2025 \
  --rates data/waller/wc_rates_2025.csv --map data/waller/wc_district_map.csv
```

then `build_county_data.py` with `--parcels waller/wc_parcels.gpkg --cama waller/wc_real_acct.txt` added.

- Accounts are `W` + WCAD property id (plain WCAD ids collide with MCAD's). Cards show the bare id, labeled
  "WCAD property ID"; search finds a typed WCAD id with or without the `W`. Combo ids start at 70000.
- Overlay counts agree with the 2025 certified counts within a few percent for the established districts
  (Harris-Waller MUD 3 and 5, Waller MUD 35, 37 and 9B, Willow Creek Farms, Road District 1, ISDs, cities).
  New districts show many more parcels than certified in 2025 (Waller MUD 60A 656 vs 13, East Waller MD 414 vs
  2): these are builder-owned lots platted since certification (Sunterra, Lakes of Cane Island, Woodhaven).
- Values are WCAD market value; agricultural use value and exemptions are not applied, so ag land is overstated.
  The layer has no state class or building area: Waller parcels are property type "other", no tax per SF.
- Hosts: services3.arcgis.com, services1.arcgis.com, gisweb.tceq.texas.gov, waller-cad.org.
  WCAD's eSearch terms prohibit data scraping (bulk data is sold separately), so it is not used.

## Running it

```bash
pip install geopandas pyogrio pyproj shapely pandas pmtiles tippecanoe   # or brew install tippecanoe
```

```bash
# 1. rates (once per rate year; keep combo_registry.csv between runs so combo ids stay stable)
python pipeline/build_rates.py Real_jur_exempt.zip --year 2025 --registry data/combo_registry.csv

# 2. countywide data (GIS folder with Parcels.gdb and the overlay zips from download.hcad.org)
python pipeline/build_county_data.py --gis gis --cama Real_acct_owner.zip --rates data --out out

# 3. tiles
pipeline/build_tiles.sh out

# 4. upload tiles and shards, then build the page
deploy/upload_gcs.sh gs://YOUR-BUCKET out
python pipeline/inject.py --key "$GMAPS_KEY" \
  --tiles  https://storage.googleapis.com/YOUR-BUCKET/taxmap/harris_parcels.pmtiles \
  --shards https://storage.googleapis.com/YOUR-BUCKET/taxmap/shards/ \
  --data data/ --out out/web/index.html

# 5. deploy out/web to Netlify
netlify deploy --dir out/web --prod
```

### Single local file (no hosting)

`inject.py --embed` packs the tiles, rates, boundaries and account records into one HTML file that opens from
disk. Search scans the records in memory. It still needs internet for Google Maps and the deck.gl scripts.

```bash
pipeline/build_tiles.sh out lean      # parcels stored once at tile z13 and stretched closer in: 44 MB countywide
python pipeline/inject.py --key "$GMAPS_KEY" --embed out --out harris-county-tax-map.html
```

| Build | File | Opens in | Memory |
|---|---|---|---|
| Countywide (1,628,435 accounts) | 129 MB | about 10 s | about 660 MB |
| Ship Channel `--bbox` (48,686 parcels) | 11 MB | 1 to 2 s | small |

Too large to email countywide; share it through OneDrive or Teams, or build submarkets with `--bbox`.

Local preview of the hosted build: `node tests/serve.js out 8090` and open `http://localhost:8090/web/index.html` after running
`inject.py` with `--tiles /bucket/harris_parcels.pmtiles --shards /bucket/shards/`.

## Tests

`tests/run_fixture_test.sh` rebuilds HCAD-shaped inputs from the prototype's 48,686 Ship Channel parcels, runs
the whole pipeline, serves it, and drives the page in headless Chromium (`tests/e2e.js`): boot, acceptance
accounts, owner, address and account search, parcel click, shading toggle, filters, zoom modes.

## Files

| Path | Purpose |
|---|---|
| `pipeline/build_rates.py` | HCAD rates per jurisdiction combo. Now with stable combo ids (`combo_registry.csv`), TIRZ names deduplicated, pandas 3 safe |
| `pipeline/build_county_data.py` | parcels for tiling, account and search shards, `combos.json`, boundary lines |
| `pipeline/build_tiles.sh`, `merge_pmtiles.py` | tippecanoe runs and merge into one PMTiles file |
| `pipeline/fetch_waller.py`, `build_waller_rates.py` | Waller County parcels, district overlay and rates |
| `pipeline/inject.py` | assembles `index.html` from the template, logo and config |
| `web/tax-rate-map-template.html` | the page |
| `deploy/` | bucket CORS and upload script |
| `tests/` | fixture builder, range-capable static server, browser test, Waller browser check |
| `data/` | 2025 rate outputs (Nov 1, 2026 HCAD export) and the review workbook |
| `legacy/` | prototype template and its data builder, for reference |
