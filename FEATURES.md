# Feature list

Running list of everything built into the Houston Property Tax Rate Map, for deciding what to keep. Update it
whenever a feature is added, changed or removed.

Status: **Core** (the app's purpose), **Keep** (user confirmed), **Review** (built, value not yet confirmed),
**Removed** (taken out; note when and why). Everything below is Review unless marked otherwise.

Layer keys are the `key` in the `IND` list in `web/tax-rate-map-template.html`; data comes from the pipeline
script named. Removing a layer means deleting its `IND` entry (and preset or site-check references) and, if
nothing else uses it, its output from `pipeline/build_layers.py`.

## Core map

| Feature | Added | Status | Notes / source |
|---|---|---|---|
| Combined tax rate shading by parcel, 8 counties | Oct-Nov 2026 | Core | HCAD, FBCAD, MCAD, WCAD, Chambers CAD, BCAD, LCAD, GCAD; county rate builders |
| Base rate vs incl. management districts toggle | Oct 2026 | Core | |
| Filters: rate range and histogram, property type, ISD, city, water district, appraised value, counties | Oct-Nov 2026 | Core | |
| Search (address, owner, account) | Oct 2026 | Core | |
| Parcel drawer: rate breakdown, est. tax, tax per SF | Oct 2026 | Core | |
| Boundary overlays: city, school, industrial/improvement districts, water, ESD, TIRZ | Oct 2026 | Core | |
| Basemaps: Map / Satellite / Hybrid (Esri without a key, Google with `?key=`) | Nov 6 | Keep | |
| Esri tile retry (no blank squares) | Nov 7 | Keep | |
| Folder build (.txt parts) | Nov 6 | Keep | `inject.py --split --part-ext txt` |
| Land use coloring (Tax rate / Land use switch) | Nov 8 | Review | CAD state class groups, parcel zoom only. Clicking the lit button again turns parcel shading off (same as the Parcel shading checkbox; share link `s=0`) |

## Layer panel and styling

| Feature | Added | Status | Notes |
|---|---|---|---|
| Grouped, collapsible layer panel (6 groups) | Nov 8 | Review | |
| Presets: Logistics, Trucking, Utilities, Risk, Development, Clear | Nov 8 | Review | |
| Per-layer opacity sliders | Nov 8 | Review | |
| Swatches drawn in each layer's map style | Nov 8 | Review | |
| Dynamic legend (only layers that are on) | Nov 8 | Review | |
| Multi-feature hover tooltip | Nov 8 | Review | |
| Fade parcel shading to 30% under layers (toggle in legend) | Nov 8 | Review | |
| Per-network line styles (rail ties, dashed pipelines, dotted power, tower dots), white casings | Nov 8 | Review | |
| Zoom-dependent detail (small pipelines, low-voltage lines and substations from zoom 12) | Nov 8 | Review | |
| Cresa map pins for ports, airports, rail terminals | Nov 8 | Review | `web/icons/*.svg`, anchored at the pointer tip |

## Layers: Logistics

| Layer (key) | Added | Status | Source |
|---|---|---|---|
| Rail lines by owner (`rail`) | Nov 7 | Review | US DOT BTS North American Rail Network |
| Rail-served parcels, 100 ft (`rail_served`) + "only rail-served" filter | Nov 8 | Review | `build_rail_served.py` |
| Road projects by timeline (`road_projects`) | Nov 8 | Review | TxDOT DCIS, H-GAC TIP, Houston, Fort Bend, Montgomery bond |
| Rail intermodal terminals (`intermodal`) | Nov 7 | Review | US DOT BTS |
| Ports, terminals and airports (`ports`) | Nov 7, terminals Nov 8 | Review | BTS ports, FAA, `data/ports/port_terminals.csv` |
| Ship docks and drafts (`docks`) | Nov 8 | Review | Houston Pilots list, `data/ports/houston_pilots_docks_2025-05-20.csv` |
| Foreign-Trade Zones and subzones (`ftz`) | Nov 7, subzones Nov 8 | Review | ITA grantees; subzones from a third-party ArcGIS list |
| Traffic counts (`aadt`) | Nov 7 | Review | TxDOT AADT |

## Layers: Trucking

| Layer (key) | Added | Status | Source |
|---|---|---|---|
| Truck restrictions, problem bridges (`bridges`) | Nov 8 | Review | TxDOT bridge inventory |
| Highway freight network (`freight`) | Nov 8 | Review | TxDOT |

## Layers: Infrastructure

| Layer (key) | Added | Status | Source |
|---|---|---|---|
| Pipelines (`pipelines`) | Nov 7 | Review | Texas Railroad Commission |
| Transmission lines (`power`) | Nov 7 | Review | HIFLD copy |
| Substations (`substations`) | Nov 7 | Review | HIFLD copy |
| Water and sewer service areas (`water_ccn`, `sewer_ccn`) | Nov 7 | Review | Texas PUC |
| Electric service areas (`electric`) | Nov 8 | Review | PUCT (unofficial map) |
| Gas utility service areas (`gas_util`) | Nov 8 | Review | HIFLD copy, 2017 |

## Layers: Workforce access, Environment, Planning

| Layer (key) | Added | Status | Source |
|---|---|---|---|
| METRO transit (`transit`) | Nov 8 | Review | METRO |
| Flood zones (`flood`) | Nov 7 | Review | FEMA (Esri copy) |
| Wetlands (`wetlands`) | Nov 8 | Review | USFWS NWI; largest layer (25 MB) |
| Hurricane evacuation zones (`evac`) | Nov 8 | Review | H-GAC 2025 |
| Watersheds (`watersheds`) | Nov 8 | Review | HCFCD, Harris County only |
| Superfund and brownfield sites (`contam`) | Nov 8 | Review | EPA NPL, EPA ACRES, TCEQ |
| Zoning, 14 cities (`zoning`) | Nov 8 | Review | City GIS; categories inferred from codes |
| Texas Enterprise Zones (`tez`) | Nov 8 | Review | Governor's office |
| Opportunity Zones (`opp_zones`) | Nov 8 | Review | HUD |

## Drive time and labor

| Feature | Added | Status | Notes |
|---|---|---|---|
| Drive time, car and truck, 15/30/45/60 min bands | Nov 7 | Review | `build_drive_grid.py` (TxDOT roads, 200 m grid) |
| Water mask (no crossing bays except on bridges) | Nov 7 | Review | |
| Start from an address (parcel addresses + Esri geocoder) | Nov 7 | Review | |
| "Drive time from here" in the parcel drawer | Nov 7 | Review | |
| Labor shed: labor force, unemployment | Nov 8 | Review | ACS employment by tract |
| Labor shed: production/warehouse workers, their pay, industrial jobs nearby | Nov 8 | Review | `build_labor.py` (ACS C24010, B24021, LEHD 2024) |

## Site checks (parcel drawer)

All added Nov 8 unless noted; each is one block in `siteChecks()` and appears in CSV and Compare.

| Check | Status |
|---|---|
| Rail (railroad, feet to track) | Review |
| Zoning | Review |
| Opportunity Zone | Review |
| Enterprise Zone | Review |
| Foreign-Trade Zone within 5 mi | Review |
| Electric utility | Review |
| Gas utility | Review |
| Watershed (Harris) | Review |
| Flood zone | Review |
| Wetlands at the parcel center | Review |
| Evacuation zone | Review |
| Nearest cleanup site within 2 mi | Review |
| Freeway access (truck minutes) | Review |
| Truck time to Barbours Cut, Bayport, Velasco | Review |
| Truck-restriction bridges within 2 mi | Review |
| Highway freight network distance | Review |
| Transit (nearest bus stop, transit center or park and ride) | Review |
| Road projects within 1 mi | Review |

## Workflow tools

| Feature | Added | Status | Notes |
|---|---|---|---|
| Shortlist (saved in the browser) | Nov 8 | Review | |
| Shortlist CSV export (includes site checks) | Nov 8 | Review | |
| Compare up to 6 sites, print or save as PDF | Nov 8 | Review | |
| Share link (view, layers, parcel, drive time in the URL) | Nov 8 | Review | Works only where the same folder exists, or once hosted |
| Development sites filter (undeveloped, N acres and up) | Nov 8 | Review | No Montgomery land areas yet |

## Removed

| Feature | Removed | Why |
|---|---|---|
| (none yet) | | |
