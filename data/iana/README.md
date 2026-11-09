# IANA Intermodal Facilities: Map Data

Source: IANA Intermodal System Map (intermodal.org/intermodalsystem), the same JSON feed that drives the site's map. Pulled 2026-11-09.

## Files

| File | Records | Use |
|---|---|---|
| `iana_intermodal_all.geojson` | 1,111 | All North American facilities, ready for Google Maps `map.data.loadGeoJson()`, Mapbox, or Leaflet |
| `iana_intermodal_all.csv` | 1,111 | Same data as a spreadsheet |
| `iana_intermodal_houston.geojson` / `.csv` | 66 | Upper Texas coast subset (lat 27.68 to 30.66, lng -97.99 to -92.50) |

## Fields

- `iana_code`: unique facility ID (use as the primary key)
- `facility_name`, `address`, `city`, `state`, `zip`
- `lat`, `lng` (CSV only; in GeoJSON they are the point geometry, [lng, lat])
- `facility_type`: `CY/DEPOT`, `MARINE`, `RAIL` (plus 1 `RAIL & CY/DEPOT` and 3 blank)
- `facility_type_label`: display name (Container Yard / Depot, Marine, Rail)
- `pin_color`: matches IANA's map key (yellow = CY/Depot `#F2C230`, blue = Marine `#1F3A93`, red = Rail `#D62828`)
- `splc`, `bic_code`, `smdg_code`: industry location codes (often blank)
- `in_houston_view`: true/false flag for the Houston subset

## Counts

- All: 762 CY/Depot, 200 Rail, 145 Marine, 4 other/blank
- Houston subset: 49 CY/Depot, 11 Marine, 6 Rail

## Data quality notes

- 2 source records had no coordinates and were dropped (Integrated Industries Storage Yard Fairburn GA; Container Maintenance Yard Baltimore).
- Source data has some typos (e.g. city "HOUTON", city "PO BOX 1729" for one Flexi Van record) and at least one mismatch: "The Mobile Storage Group" lists Corpus Christi but its pin plots in Houston. Coordinates are as published by IANA.
- A few facilities share identical coordinates (same yard, multiple operators). Consider jittering or clustering pins.

## Suggested prompt for Claude Code

> Add a toggleable "Intermodal Facilities" layer to the map using `iana_intermodal_houston.geojson`. Color pins by `pin_color`, cluster at low zoom, and show an info window with facility name, type, full address, and IANA code. Add a filter for the three facility types.
