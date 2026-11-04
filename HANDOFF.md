# Houston Property Tax Rate Map: Claude Code Handoff

## Goal

An internal Cresa Houston web tool that colors every parcel by its combined property tax rate, overlays taxing district boundaries, and opens a detail card on click. Audience: Cresa's 28 brokers comparing occupancy cost across submarkets. Scope order: Harris County first, then Fort Bend and Montgomery.

## Status

Phase 1 (full Harris County) is built and tested end to end on the Ship Channel fixture; see [README.md](README.md).
It still needs one run on the real HCAD downloads (Parcels.gdb, overlay zips, Real_acct_owner.zip), an upload
to a bucket, and a Netlify deploy. The original single-file prototype is kept under `legacy/`.

Phase 1 changes to the decisions below (requested Nov 4, 2026):

- Two-layer PMTiles: merged rate zones at Google zoom 8 to 13, individual parcels from zoom 14.
- Owner and address are not in the tiles; drawer and search read static account shards.
- Search covers owner, address and account from our own shards. Google Places is not used.
- `combo_id` is stable across runs (`combo_registry.csv`), so a rate-year switch needs no re-tiling.
- Color breaks recalibrated to the countywide distribution: 2.0, 2.1, 2.2, 2.3, 2.45, 2.7 (2.125, the Houston ISD
  plus City of Houston rate, gets its own band). Confirm with Grant.
- "Rate shading" toggle and opacity slider on the map; boundary lines get a white casing.
- Filter lists split combined names, so picking "Pasadena ISD" includes parcels straddling two ISDs.
- Accounts with a missing jurisdiction rate show gray ("Rate incomplete or not found").

## Conventions (must follow)

- Single-file HTML, no build step, deployed on Netlify. Firebase is available for storage and auth.
- Visual style matches the Cresa Houston Industrial Lease Comps Database: Arial, white top bar with Cresa wordmark, 280 px white filter rail, navy `#001E5A`, gold `#FFB600`, slate `#2A3F92`, tokens copied into the template's `:root`. Light mode only, to match that app.
- No em dashes in UI copy.
- Confirm specs with Grant before major feature work.
- Do not use the Google Static Maps API anywhere (quota). The Maps JavaScript API is fine.

## Locked decisions

| Topic | Decision |
|---|---|
| Rate source | HCAD account-level jurisdiction file, not spatial overlay |
| Rate year | 2025 adopted rates (complete). Switch to 2026 when HCAD's `curr` column fills in |
| Values | 2026 appraised values from `real_acct.txt`. Exemptions and abatements not applied |
| Map engine | Google Maps JS API (Cresa styled map type, Map/Satellite/Hybrid toggle) with deck.gl 9.0.38 `GoogleMapsOverlay`, `interleaved:false`. Esri light gray fallback via `deck.Deck` if the key fails (`gm_authFailure`) |
| Parcels shown | All parcels, all property types |
| TIRZ | Overlay and card note only. Never added to the rate |
| Management / improvement districts | Separate rate, off by default, toggled by "Incl. mgmt districts" (many assess commercial only) |
| Color ramp | 7 bands, low to high: `#001E5A #2A3F92 #5566AD #9AA6CF #FFE29A #FFCB45 #FFB600`. Breaks 2.0, 2.1, 2.2, 2.3, 2.45, 2.7 (countywide, pending Grant's confirmation; prototype used 2.0, 2.2, 2.4, 2.5, 2.6, 2.8) |
| Selection / hover | Selected outline red `[201,59,59]`, hover white wash (gold means high rate now) |
| Filter rail | All filters visible, nothing collapsed: search, base/mgmt toggle, rate range inputs + dual slider + clickable histogram, property type, school district, city, appraised value, water district. Boundaries pinned at the bottom of the rail. Footer shows "N parcels match" |
| Removed by request | Stat cards above the map, aerial image in the detail card |
| Detail card | Right-side drawer styled like the comps app's detail drawer: header with type/class tags and close, address, owner, ISD/city/TIRZ pills, KPI band (rate, est. annual tax, tax per bldg SF), field grid, rate bars by jurisdiction with combined total, notes, buttons "Open in Google Maps" and "Copy HCAD account" |

## Data sources (all public, direct download)

GIS (quarterly refresh): `https://download.hcad.org/data/GIS/<Name>.zip` where Name is `Parcels` (212 MB, FileGDB, EPSG:2278, field `HCAD_NUM_1` = account), `City`, `School`, `Water_district`, `Defined_area`, `TIRZ`, `Special`, `Emergency`, `Utility`, `College`, `Fire`, `County`. The file list comes from `https://hcad.org/actions/hcad-pdata/default/get-gis-files` (JSON).

Tabular (CAMA): `https://download.hcad.org/data/CAMA/2026/Real_jur_exempt.zip` and `.../Real_acct_owner.zip`.

- `jur_value.txt`: one row per account per jurisdiction (14.2M rows). Fields used: `acct`, `tax_district`, `tp_cd`, `pct_district`. Codes have stray whitespace, strip them.
- `jur_tax_dist_exempt_value_rate.txt`: one row per jurisdiction. `prop` = prior year adopted rate (verified equal to 2025: Harris County 0.38096, Flood Control 0.04966, Port 0.0059). `curr` = current year, partially loaded (about 208 of 654 levying units as of the Nov 1, 2026 export; Harris County's adopted 2026 rate of 0.4175 not yet in).
- `real_acct.txt` (latin-1, tab, use `quoting=3`): `state_class`, `tot_appr_val`, `bld_ar`, `land_ar`, `site_addr_1`, `site_addr_2`.

`tp_cd` meanings as used: I ISD, C city, N city industrial district, J college, T county/countywide, W water district, A defined area, D drainage, E/F/B ESD, M management district, Z special (TIRZ or improvement/management district; split by name pattern `TIRZ|TRIZ|T I F|ZONE|ZN|(nnn)`).

## Pipeline (done, in this folder)

`build_rates.py Real_jur_exempt.zip [--year 2025|2026] [--overrides rate_overrides.csv]` writes:

- `hcad_rate_table.csv`: one row per jurisdiction with category, bucket (`base`, `mgmt`, `excluded`), rates, `missing_rate` flag.
- `hcad_combos.csv`: one row per unique jurisdiction combination (7,271 countywide), with base and mgmt rates, ISD, city, water, ESD, college, mgmt, TIRZ names, a `code:rate` breakdown string, and account counts.
- `hcad_account_rates.csv.gz`: account to `combo_id` and rates.

Rates are weighted by `pct_district` for split parcels. Runs in about 4 GB of RAM by hashing each account's jurisdiction set into a combo. Validated: 3,000 random accounts recomputed from raw rows matched to 6 decimals. Countywide base rate: median 2.21, 5th to 95th percentile about 1.93 to 2.98.

`hcad_rate_table.xlsx` is the human review copy, with a yellow Override column and CHECK flags.

Known gaps: 36 levying jurisdictions have no rate. About 3,300 accounts are in base-rate gaps (small MUDs, HC FWSD 1A). Larger gaps are management districts billed outside HCAD (Greater Northside, HC ID 10, Montrose); source those rates from each district. Feed fixes through `rate_overrides.csv` (`tax_dist,rate`).

## Prototype build (done)

- `build_prototype_data.py --gis <dir> --rates <dir> --bbox W S E N` writes `proto_data.json`: parcels as delta-encoded integer rings on a 1e-5 degree grid, a props array per parcel (`acct, combo, owner, addr, city, cls, val, bldSF, landSF`), the combos used, jurisdiction names, and overlay boundary lines (dissolved by name, clipped inside the bbox so clip edges don't draw).
- `inject.py <MAPS_KEY>` merges `tax-rate-map-template.html` + `cresa_mark.svg` + data into `tax-rate-map.html` (6.8 MB).
- Grant's Maps JS key is the one already used in the comps database (`apiKey` in `loadGoogleMapsScript`).

The inline approach tops out around 50 to 100k parcels. It does not scale to the county.

## Next: Phase 1, full Harris County (needs Grant's sign-off on the spec below)

1. **Tiles.** Export all parcels (WGS84, simplified per zoom) with properties `acct`, `combo_id`, `cls` (state class), `val`, `bld`, `land`, and `addr`/`owner` (consider including those only at z14+ to control size). Build PMTiles with tippecanoe (suggested `-Z10 -z16 --coalesce-densest-as-needed --detect-shared-borders`). Expect a few hundred MB.
2. **Hosting.** Upload the PMTiles to Firebase Storage (or GCS bucket) with CORS allowing GET and `Range` from the Netlify domain. Confirm range requests return 206.
3. **Front end.** Replace the inline GeoJsonLayer with a deck.gl tile layer reading PMTiles. Options to evaluate: `MVTLayer` with the loaders.gl PMTiles source, or a `TileLayer` whose `getTileData` uses the protomaps `pmtiles` JS library. Load everything as UMD script tags (no build step). Keep `combos` and jurisdiction names as a separate small JSON (about 2 MB countywide) loaded at start; the rate, colors, mgmt toggle, filters, and drawer all resolve through `combo_id`.
4. **Filters at scale.** Pre-resolve ISD/city/water selections to a `Set` of allowed combo IDs and test `combo_id` per feature, instead of string matching per parcel. Option lists come from the combos table, with countywide parcel counts.
5. **Histogram.** Aggregate from features in loaded tiles within the current viewport (or `getRenderedFeatures`), debounced. It no longer covers every parcel when zoomed out, so label it "parcels loaded in view" or hide counts below a zoom threshold.
6. **Search.** The prototype's substring search won't scale. Proposed: Google Places Autocomplete restricted to Harris County for addresses, and an account-number lookup against sharded JSON (`acct` prefix files, account to centroid). Clicking a result flies there and opens the drawer.
7. **Overlays.** Countywide boundary layers as small GeoJSON files, simplified, with label points. Consider a thin white casing under navy and purple boundary lines so they stay visible over dark low-rate parcels (open item raised with Grant).
8. **Recalibrate bands** to the countywide distribution and confirm with Grant.

**Acceptance:** pans and zooms smoothly at county extent on a typical laptop; the parcel card for account `0281700000001` shows rate 1.9557 (Pasadena Refining, unincorporated, Pasadena ISD); for `0402040000009` it shows 2.1252 with TIRZ Eastside 6; the most common combo (HISD + City of Houston + HCC + countywide units) shows 2.1252.

## Later phases

- **2026 rates.** Rerun `build_rates.py --year 2026` once HCAD fills `curr`, then rebuild combos and the front-end JSON. Tiles only need rebuilding if `combo_id` assignments change (they're tied to the jurisdiction set, not rates). Add a rate-year label wherever rates appear.
- **Fort Bend and Montgomery.** Each needs a parser for that CAD's certified roll export (account to taxing entity codes) and an entity rate table, normalized into the same `combos` schema. FBCAD publishes GIS at fbcad.org/gis-data. Cross-check rates against the Texas Comptroller's Property Tax Rates and Levies data.
- **Annual refresh.** One script run each fall; optional quarterly parcel refresh.

## Caveats to keep in the UI

- The map shows rates, not bills. Exemptions and abatements are not applied. Industrial abatements along the ship channel can be large.
- Plants in industrial districts outside city limits pay cities through in-lieu agreements that aren't a rate, so they look cheaper than they are. The card says so.
- A few hundred parcels straddle two ISDs. The filter lists combined values such as "Deer Park ISD; Pasadena ISD."
- A rate of 0.47 appears for a handful of accounts carrying only a city levy. That's a data quirk worth a closer look.

## Files in this folder

| File | Purpose |
|---|---|
| `HANDOFF.md` | This spec |
| `tax-rate-map.html` | Current working prototype (built, includes Maps key) |
| `tax-rate-map-template.html` | Template with `__DATA__`, `__MARK__`, `__GKEY__` placeholders |
| `build_rates.py` | HCAD rate pipeline (county-wide) |
| `build_prototype_data.py` | Clip, join, encode prototype data |
| `inject.py` | Assembles the HTML |
| `cresa_mark.svg` | Cresa wordmark extracted from the comps database |
| `hcad_rate_table.xlsx` | Rate table review workbook |
| `hcad_rate_table.csv`, `hcad_combos.csv`, `hcad_account_rates.csv.gz` | Pipeline outputs, 2025 rates, Nov 1, 2026 HCAD export |

Not included: raw HCAD downloads (fetch from the URLs above).
