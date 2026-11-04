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

Local preview: `node tests/serve.js out 8090` and open `http://localhost:8090/web/index.html` after running
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
| `pipeline/inject.py` | assembles `index.html` from the template, logo and config |
| `web/tax-rate-map-template.html` | the page |
| `deploy/` | bucket CORS and upload script |
| `tests/` | fixture builder, range-capable static server, browser test |
| `data/` | 2025 rate outputs (Nov 1, 2026 HCAD export) and the review workbook |
| `legacy/` | prototype template and its data builder, for reference |
