# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Cresa Houston brokers and analysts, at their desks, screening and comparing sites for industrial and commercial occupier clients (confirmed).
- The same brokers walking a client through the map live, in a meeting or on a screen share; the screen must read clearly to someone seeing it for the first time (confirmed).
- Prospects and recruits, as a demonstration of Cresa's capabilities (confirmed: recruiting / marketing use).

Brokers must be able to navigate it confidently and reach the right filter or layer without digging (confirmed).

## Product Purpose

Houston Site Selector (formerly the Houston Property Tax Rate Map) shows the combined property tax rate of every parcel in 8 Houston-area counties (Harris, Fort Bend, Montgomery, Waller, Chambers, Brazoria, Liberty, Galveston; about 3 million accounts) and layers site-selection data on top: rail, ports, intermodal and transload terminals, highways and truck restrictions, utilities, flood and environmental risk, zoning and incentives, labor and drive times. Success: a broker finds, checks and shortlists candidate sites quickly and can show the result to a client with confidence.

## Positioning

Occupier-side (Cresa represents tenants and buyers only). The map joins parcel-level combined tax rates for 8 counties with industrial site checks (rail service, terminals, freeway access, labor shed, utilities, flood) in one tool that opens from a local folder with no server.

## Operating Context

- Delivered as a folder: one HTML page plus data and tile files (`.txt` parts of 40 MB or less), opened from disk; a hosted build (bucket + Netlify) is planned but not deployed.
- Esri basemaps without a key; Google Maps with `?key=`.
- Workflows: search an address, owner or account; read the rate map; filter by rate, property type, district, value and development sites; open a parcel drawer with rate breakdown and site checks; drive time and labor shed; shortlist, Compare (print to PDF) and CSV export; share link.

## Capabilities and Constraints

- Single-file app built from `web/tax-rate-map-template.html` by `pipeline/inject.py`; deck.gl 9 and PMTiles from CDNs; no build tooling.
- About 30 map layers in 6 groups (Logistics, Trucking, Infrastructure, Workforce access, Environment, Planning and incentives), plus boundary outlines and parcel shading.
- Must work on desktop, tablet and phone (confirmed).
- Maps must stay legible with many layers on at once; pipelines and power lines in particular must be easy to tell apart (confirmed).
- First load should show only the tax-rate shading, with all other layers off (confirmed).
- No em dashes in UI copy (user preference).

## Brand Commitments

- Cresa brand: navy #001E5A, gold #FFB600, the Cresa wordmark (`web/cresa_mark.svg`), Cresa map pins (`web/icons/`).
- Product name: Houston Site Selector.

## Evidence on Hand

Real data only: CAD and Comptroller rates, public GIS layers, EIA-861, ACS/LEHD, researched rail terminals (`data/rail/`). No testimonials, client names or usage figures exist; do not invent them.

## Product Principles

1. Rate first: the tax-rate map is the core read; everything else is opt-in.
2. Find, don't dig: every filter and layer reachable in one or two steps, named the way brokers talk.
3. Legible when dense: many layers on at once must still read, each network distinct by form, not just color.
4. Client-ready at any moment: what is on screen should be presentable without cleanup.
5. Honest data: show sources, years and estimates (asterisks, "verify with operator") plainly.
