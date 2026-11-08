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

## Chambers County

Chambers CAD (Pritchard & Abbott) publishes its certified appraisal roll as a CSV with each account's taxing
unit codes (`Jur 1` to `Jur 12`), market value, state class, owner and situs, plus a parcel shapefile keyed by
`ParcelCAMA` = the roll's `Parcel_ID`. So Chambers needs no polygon overlay.

- Unit codes to names: the `(code) - NAME` header on each of the CAD's 2026 certified value reports (e.g.
  `(31) - BARBERS HILL ISD`, `(31BC) - LEE COLLEGE - Barbers Hill`, `(64) - LEE COLLEGE`).
- 2025 rates: Texas Comptroller 2025 rates and levies files (Chambers rows kept in
  `data/chambers/comptroller_2025_chambers_units.csv`); county 0.414192 includes the FM/FC road fund (CAD code
  01R), matching chamberscountytx.gov/191. All in `data/chambers/ch_units_2025.csv`.
- Codes with no certified value report carry no rate and a note: 12 Beach City, 13 Cove, 16 Old River-Winfree
  (cities with no property tax), and 21, 23, 69, 70, 78 (unidentified; 70 covers exactly East Chambers ISD's
  area and may be the Winnie-Stowell Hospital District).

```bash
python pipeline/fetch_chambers.py --out chambers          # 2026 certified roll CSV + newest parcel shapefile
python pipeline/build_chambers_rates.py --src chambers --units data/chambers/ch_units_2025.csv --out data
```

then `build_county_data.py` with `--parcels chambers/ch_parcels.gpkg --cama chambers/ch_real_acct.txt` added.

- Accounts are `C` + Chambers CAD property id (the CAD's search takes it); cards show the bare id. A parcel with
  several owners has one roll row per share: values are summed, the first owner is shown with "ET AL".
  Combo ids start at 80000. 323 accounts list no taxing unit and show no rate.
- Values are certified market value (2026); exemptions, ag use value and abatements are not applied. No
  building area. Personal property and mineral accounts (about 15%) have no parcel shape but are searchable.

## Brazoria County

Brazoria CAD posts its downloads on pCloud public folders (linked from brazoriacad.org's "Public GIS and Property
Data Downloads" page). The certified appraisal export (PACS 8.0 fixed-width layout, layout spreadsheet inside the
zip) lists each property's entities in `APPRAISAL_INFO.TXT`, so no overlay is needed; `PARCELS.shp` carries
`PID` = property id.

- Entity codes and names: `APPRAISAL_ENTITY_TOTALS.TXT` (157 codes; 42 inactive, TIRZ or agreements carry no rate).
- 2025 rates: Texas Comptroller rates and levies files, Brazoria rows in
  `data/brazoria/comptroller_2025_brazoria_units.csv`, matched by name into `data/brazoria/br_units_2025.csv`.
  By hand: road & bridge fund (RDB 0.04221, a separate entity from the county's 0.262548), Brookside Village,
  Angleton-Danbury hospital, West Brazoria drainage, and Fort Bend / Harris County for the few edge parcels
  BCAD lists with them. Port Freeport adopted a zero rate. MUD 38, 48, 67, 90 and Preservation Creek MUD 1 are
  not on the Comptroller's list and carry no rate.

```bash
python pipeline/fetch_brazoria.py --out brazoria     # 2026 certified export (191 MB) + parcels (103 MB)
python pipeline/build_pacs_rates.py --prefix br --letter B --offset 90000 --src brazoria \
  --units data/brazoria/br_units_2025.csv --out data
```

then `build_county_data.py` with `--parcels brazoria/br_parcels.gpkg --cama brazoria/br_real_acct.txt` added.

- Accounts are `B` + BCAD property id; cards show the bare id. Combo ids start at 90000. Partial owners: the
  larger value is shown and "ET AL" added. About 30% of accounts (personal property, minerals) have no shape.
- Building area: main-area improvement segments (type codes MA*, plus numeric commercial occupancy codes), so
  Brazoria cards show tax per building SF. Values are certified market value; exemptions are not applied.
- Hosts: brazoriacad.org, api.pcloud.com, def1..def4.pcloud.com.

## Liberty County

Liberty CAD uses the same BIS public layer as Waller (parcels with owner, situs, market value and school /
city / county codes only), so other units are placed by polygon overlay, listed in `data/liberty/lc_units_2025.csv`:

- hospital, navigation (north/south), ESD 1/2/3/7, drainage 1/2/4 and water districts 1/5: the CAD's own "Special
  Districts" layer (the code is in each name, e.g. `WATER DIST 5 (WD5)`)
- MUDs, River Ranch MUDs and improvement district, Liberty County MMD 1 and 2, Plum Creek MD 1A: TCEQ map
- rates: Liberty CAD's 2025 rate sheet (`data/liberty/lcad_2025_tax_rates.pdf`). Kenefick (CKE) has no city
  tax; MUD 10, MUD 16 and MMD 2 are not on the sheet (no rate). Southeast Regional MD uses Waller CAD's 1.23.

```bash
python pipeline/fetch_liberty.py --out liberty        # 156,254 parcel shapes + district layers (about 4 min)
python pipeline/build_liberty_rates.py --src liberty --units data/liberty/lc_units_2025.csv --out data
```

then `build_county_data.py` with `--parcels liberty/lc_parcels.gpkg --cama liberty/lc_real_acct.txt` added.

- Accounts are `L` + LCAD property id; combo ids start at 100000. The public layer has about 82% as many
  accounts as LCAD's 2026 certified real roll (113,909 vs 139,538), and most units overlay at about that ratio.
- Known gap: TCEQ's Liberty County MMD 1 polygon holds 10,735 accounts; LCAD certifies 32,363. MMD 1 (0.35) is a
  management district, so the base rate is unaffected, but "Incl. mgmt districts" misses it for about 21,000
  accounts. No public current boundary was found (LCAD GIS request or the district would have it).
- No state class or building area (property type "other", no tax per SF). Hosts: services3.arcgis.com,
  gisweb.tceq.texas.gov, libertycad.com.

## Galveston County

Galveston CAD posts the same PACS 8.0 certified export as Brazoria on its "Preliminary and Certified Roll Export
Data" page, and a parcels shapefile (PID = property id) on its "GIS Data" page, so it runs through the same
builder (`build_pacs_rates.py`, which was `build_brazoria_rates.py`).

- Rates: GCAD's own 2025 rate sheet with entity codes (`data/galveston/gcad_2025_tax_rates.pdf`), parsed into
  `data/galveston/gv_units_2025.csv` (74 levying units). Do not use the Comptroller's 2025 special district file
  for Galveston: several of its Galveston rows carry copied rates (seven districts at 0.085476, five at 0.060041).
- County 0.32266 plus road & flood (RFL) 0.003. Public improvement districts (P codes) are assessments, not
  rates; TIRZs add no rate. 20 inactive codes appear on property entity lists only (e.g. S15, La Marque ISD,
  merged into Texas City ISD) and carry no rate. Management districts (Westwood, GC MMD 1, Kemah MD 1, West
  Ranch) are in the "Incl. mgmt districts" total.

```bash
python pipeline/fetch_galveston.py --out galveston      # 2026 certified export (138 MB) + parcels (47 MB)
python pipeline/build_pacs_rates.py --prefix gv --letter G --offset 110000 --src galveston \
  --units data/galveston/gv_units_2025.csv --out data
```

then `build_county_data.py` with `--parcels galveston/gv_parcels.gpkg --cama galveston/gv_real_acct.txt` added.
Accounts are `G` + GCAD property id. 202,064 accounts, 188,039 parcel shapes, building area on 135,659.

## Map layers, site checks and drive times

The "Layers" panel in the rail groups the toggles into Logistics, Infrastructure, Environment, and Planning and
incentives. Each group collapses (the open/closed state is remembered in the browser), each layer has a swatch
drawn in its map style and an opacity slider while it is on, and preset buttons switch sets at once:
Logistics (rail, rail-served parcels, road projects, intermodal, ports, FTZ, traffic), Utilities (water and sewer CCN, power,
substations, pipelines), Risk (flood, wetlands, evacuation zones, cleanup sites), Development (zoning,
Opportunity Zones, cleanup sites, rail, road projects, ports) and Clear.

| Group | Layer | Source |
|---|---|---|
| Logistics | Rail lines by owner | US DOT BTS North American Rail Network; colored by owning railroad, solid line with cross ties |
| | Rail-served parcels | `build_rail_served.py`: parcels within 100 ft of an active track (dots for non-residential parcels at metro zoom, every one outlined in the railroad's color at parcel zoom; "show only rail-served" filter) |
| | Road projects | TxDOT project tracker (DCIS: open projects plus those let since 2023), H-GAC 2027-2030 TIP (cities, counties, toll authorities, METRO and others; TxDOT's entries come from DCIS), City of Houston Public Works active roadway projects, Fort Bend County mobility bond, Montgomery County 2025 road bond. Grouped by timeline: under construction, next 1 to 3 years (design, bidding), 3+ years out (planning, dashed), finished since 2023 (off by default). Line weight by estimated cost. Routine work (seal coat, overlay, landscaping, safety hardware, Houston local-street and sidewalk jobs) hidden unless turned on. Site checks list active projects within 1 mile. Harris County Engineering, Galveston and Brazoria counties publish no project layer beyond their TIP entries |
| | Ports, terminals and airports | Ports (Army Corps list via US DOT BTS), FAA public-use airports, and 12 port terminals (`data/ports/port_terminals.csv`): Port Houston's Barbours Cut and Bayport container terminals, Bayport cruise, Turning Basin, Woodhouse, Jacintoport, Care, Manchester and the Bulk Materials Handling Plant; Port Freeport Velasco; Port of Galveston cargo and cruise piers; Texas City docks. Placed at their berths (Houston Pilots dock list, Army Corps / BTS Navigation Facilities). Site checks give truck drive time to the three container terminals from the drive-time grid |
| | Ship docks and drafts | Houston Pilots dock list as of May 20, 2025 (`data/ports/houston_pilots_docks_2025-05-20.csv`, 175 docks with maximum draft); small dots from Google zoom 12, off by default and in no preset. Drafts change; check with the terminal and Houston Pilots |
| | Rail intermodal terminals | US DOT BTS intermodal TOFC/COFC terminals |
| | Foreign-Trade Zones and subzones | ITA grantee locations plus 73 subzone company sites (Feb 2025 list, third-party compilation on ArcGIS Online); points only, zone boundaries are PDFs at ofis.trade.gov |
| | Traffic counts | TxDOT AADT stations (from Google zoom 11) |
| Trucking | Truck restrictions (bridges) | TxDOT bridge inventory (NBI data), only bridges that can stop or reroute a truck: under 16 ft of clearance for the road underneath or over the deck, load posted (postings at 80,000 lb or more shown lighter: they only limit overweight permit loads), closed, poor condition (a component rated 4 or less), or over-height load damage on record. Site checks list the nearest within 2 miles (straight-line distance, not along a route) |
| | Highway freight network | TxDOT Texas Highway Freight Network; site checks give the distance to it |
| Infrastructure | Pipelines | Texas Railroad Commission; dashed, colored by product; under 8 in. only from zoom 12 |
| | Transmission lines, substations | HIFLD public copies; dotted, colored by voltage class; under 100 kV lines and substations from zoom 12; tower dots (line vertices) from zoom 15 |
| | Water and sewer service areas | Texas PUC CCN boundaries |
| | Electric service areas | PUCT investor-owned, co-op and municipal utility areas (marked unofficial). Feeder or substation capacity is not public in Texas; transmission lines and substations are the proxy |
| | Gas utility service areas | Natural gas distribution territories (HIFLD copy, 2017) |
| Workforce access | METRO transit | METRO bus routes, METRORail lines, transit centers and park and rides; bus stops from Google zoom 15. Site checks give the nearest bus stop and transit center or park and ride |
| Environment | Watersheds | HCFCD's 23 Harris County watersheds. Detention requirements live in the HCFCD criteria manual (PDF), not GIS |
| | Flood zones | FEMA (Esri USA Flood Hazard Reduced Set): floodway, 100-year, 500-year |
| | Wetlands | USFWS National Wetlands Inventory (Esri copy): emergent, forested/shrub, estuarine; 1 acre and up |
| | Hurricane evacuation zones | H-GAC 2025 ZIP zones A, B, C |
| | Superfund and brownfield sites | EPA NPL, EPA ACRES brownfields (FRS), TCEQ state Superfund, TCEQ brownfield assessments, TCEQ Voluntary Cleanup Program |
| Planning | Zoning | City GIS layers: Baytown, Pearland, Sugar Land, Missouri City, La Porte, Seabrook, Friendswood, Dickinson, Hitchcock, Tomball, Angleton, Lake Jackson, Richmond, West University Place. Each district is put in a category (industrial, commercial, mixed use, planned, residential, agricultural/open) from its code and description. Houston, Pasadena and unincorporated areas have no zoning |
| | Texas Enterprise Zones | Governor's office eligible block groups (2020 geography) |
| | Opportunity Zones | HUD Qualified Opportunity Zones (2018 census tracts) |

Map icons: Cresa map pins from the Cresa Icon Library ("Mapping Elements"), vector SVG: one for ports and port
terminals (`web/icons/port.svg`), one for airports (`airport.svg`) and one for rail intermodal terminals
(`rail.svg`); larger for major ports, container terminals and major airports. Each pin is anchored at the tip of
its pointer, so the tip sits on the location.

Styling: rail, pipelines and transmission lines use different line patterns (solid with ties, dashed, dotted)
so they read apart in grayscale, all on a white casing. With any layer on, parcel shading fades to 30%
("Fade parcel shading under layers" in the legend turns that off). Hovering lists every feature under the
cursor. The legend shows only the layers that are on, in their map styles.

Parcel shading can show the tax rate or land use (CAD state class groups: residential, commercial, industrial,
vacant, utility, exempt/public, other/agricultural; parcel zoom only).

Site checks: the parcel drawer lists rail access (railroad and distance), zoning, Opportunity Zone, flood zone,
wetlands at the parcel center, evacuation zone and the nearest cleanup site within 2 miles. These are screens
from public layers, not surveys or delineations.

Development sites: the Filters rail's "Development sites" option keeps only undeveloped parcels at or above an
acreage (default 10): vacant land (state class C), agricultural land (D) and commercial or industrial parcels with
no building area (F1, F2), from the appraisal records. At metro zoom gold dots mark them (size by acreage); the
match count switches to development sites. Montgomery County records have no land area yet.

Freeway access: site checks give the truck drive time to the nearest freeway or tollway cell of the drive-time
grid (roads whose modeled car speed is 78 km/h or more).

Compare: with two or more shortlisted sites, "Compare" in the shortlist opens a side-by-side table (up to 6
sites): property, tax, access (freeway, container terminals, rail, freight network, truck restrictions, road
projects, transit), a 30-minute car labor shed per site, and site checks (zoning, flood, wetlands, evacuation,
Opportunity and Enterprise Zones, FTZ, electric and gas utility, watershed, cleanup sites). "Print or save as PDF"
prints just the table, landscape, with the Cresa mark.

Not mapped (no public GIS found): Chapter 312 reinvestment zones and abatements, JETI agreements, CenterPoint
hosting or feeder capacity, detention rates by area.

Shortlist and sharing: "Add to shortlist" in the drawer saves a site in this browser; the Shortlist button lists
them and exports a CSV (county, ID, address, owner, class, value, rate, estimated tax, coordinates, site checks).
"Share" copies a link holding the view, layers, parcel color, basemap, selected parcel and drive time. Since the
viewer is a local folder, the link opens for anyone who has the same folder at the same path, or once the
viewer is hosted.

Drive time: the "Drive time" button under the basemap toggle, then a click on the map, shades 15/30/45/60-minute
reach for a car or a truck. It runs in the page on a 200 m speed grid built from TxDOT's Roadway Inventory (road
class and posted speed, with factors for signals and lower truck speeds; see `pipeline/build_drive_grid.py`).
It is a screening estimate: free-flow speeds, no live traffic, freeways can be joined anywhere along them.
OpenStreetMap hosts (Overpass, Geofabrik) were unreachable from the build environment, hence TxDOT.

The starting point can also be typed: the address box in the drive time panel matches parcel addresses in the
loaded counties (works offline) and Esri's World Geocoder (`geocode.arcgis.com`, any address, intersection or
place; free for lookups that are not stored, no key). A parcel's drawer has a "Drive time from here" button.
Water (bays, lakes, rivers, the Gulf) is impassable except where a road or bridge crosses it.

Labor shed: with a drive time drawn, the panel totals, for census tracts whose center falls inside each band:
the labor force (ACS employment status, Esri Living Atlas); residents working in production, transportation and
material moving occupations (ACS C24010) and their median earnings (ACS B24021, tract medians weighted by those
workers); and industrial jobs located in the band (manufacturing, wholesale, transportation and warehousing; LEHD
LODES workplace data), the competition for the same workers. `pipeline/build_labor.py` adds these to the labor
layer from the Census ACS table-based summary files (no API key) and LODES (www2.census.gov, lehd.ces.census.gov).
Not included: commuting flows (LODES origin-destination) and BLS county wages.

```bash
python pipeline/build_layers.py --raw layers_raw --out layers_out       # about 5 min, mostly flood zones
python pipeline/build_drive_grid.py --raw layers_raw --out layers_out   # about 5 min to fetch 200k road segments
python pipeline/build_rail_served.py --parcels out/parcels.geojsonl --raw layers_raw --out layers_out   # about 3 min
python pipeline/build_labor.py --layers layers_out/web/data/layers --raw layers_raw   # after build_layers.py; about 3 min
python pipeline/inject.py --embed out --layers layers_out/web/data/layers --split --chunk-mb 40 --part-ext txt \
  --out houston-8county-tax-map.html
```

Hosted builds serve the same files at `<data>/layers/<key>.json`. Hosts: services.arcgis.com,
services1/2/3/5/6/8.arcgis.com, gis.rrc.texas.gov, gisweb.tceq.texas.gov, interactivemaps.sugarlandtx.gov.
Wetlands take the longest to fetch (about 115,000 polygons).

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
| `pipeline/fetch_chambers.py`, `build_chambers_rates.py` | Chambers County roll, parcels and rates |
| `pipeline/fetch_brazoria.py`, `fetch_galveston.py`, `build_pacs_rates.py` | Brazoria and Galveston: PACS certified exports, parcels and rates |
| `pipeline/fetch_liberty.py`, `build_liberty_rates.py` | Liberty County parcels, district overlay and rates |
| `pipeline/build_layers.py`, `build_drive_grid.py`, `build_rail_served.py` | map layers (logistics, infrastructure, environment, zoning), the drive-time speed grid, rail-served parcels |
| `pipeline/inject.py` | assembles `index.html` from the template, logo and config |
| `web/tax-rate-map-template.html` | the page |
| `deploy/` | bucket CORS and upload script |
| `tests/` | fixture builder, range-capable static server, browser test, Waller, Chambers, Brazoria, Liberty and Galveston browser checks |
| `data/` | 2025 rate outputs (Nov 1, 2026 HCAD export) and the review workbook |
| `legacy/` | prototype template and its data builder, for reference |
