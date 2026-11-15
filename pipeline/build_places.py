"""
City and community name labels for the map: incorporated cities plus unincorporated communities (Census CDPs such
as Cypress, Spring, Atascocita, Channelview), ranked by population so the larger names show first when zoomed out.

  python build_places.py --gaz 2024_Gaz_place_national.txt --pop sub-est2024_48.csv \
      --labor out/web/data/layers/labor.json --out out
      -> out/web/data/layers/places.json

Sources (Census Bureau):
  Gazetteer places file (label point, land area)
    https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip
  City population estimates, 2024 (incorporated places only)
    https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/cities/totals/sub-est2024_48.csv
  CDPs have no annual estimate, so their size is approximated from ACS tract population (labor.json, ages 16+,
  scaled to all ages) for tracts whose center falls within the community's area. Used only to rank labels.

Kept: places whose label point is inside the 8 counties (Esri county outlines from build_drive_grid.py).
Output: {"n": [name, ...], "p": [population, ...], "c": [[lon, lat], ...]}
"""
import argparse, json, math, os, re
import numpy as np, pandas as pd

COUNTIES = {"Harris", "Fort Bend", "Montgomery", "Waller", "Chambers", "Brazoria", "Liberty", "Galveston"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaz", required=True)
    ap.add_argument("--pop", required=True)
    ap.add_argument("--labor", required=True)
    ap.add_argument("--counties", default="layers_raw/land.geojson", help="county outlines (build_drive_grid.py)")
    ap.add_argument("--extra", default=os.path.join(os.path.dirname(__file__), "..", "data", "places", "extra_places.csv"),
                    help="well-known communities that are not Census places (Cypress, Kingwood, Clear Lake...)")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    gz = pd.read_csv(a.gaz, sep="\t", dtype=str, encoding="latin-1")
    gz.columns = [c.strip() for c in gz.columns]
    gz = gz[gz.USPS == "TX"].copy()
    gz["lat"] = gz.INTPTLAT.astype(float); gz["lon"] = gz.INTPTLONG.astype(float)
    gz["aland"] = gz.ALAND.astype(float)
    pe = pd.read_csv(a.pop, dtype=str, encoding="latin-1")
    pe = pe[pe.SUMLEV == "162"]
    pop = dict(zip("48" + pe.PLACE, pd.to_numeric(pe.POPESTIMATE2024, errors="coerce")))

    lab = json.load(open(a.labor))["features"]
    tx = np.array([f["geometry"]["coordinates"] for f in lab]); tp = np.array([f["properties"].get("p16") or 0 for f in lab], float)
    kx = 111.32 * math.cos(math.radians(29.8)); ky = 110.57   # km per degree

    import geopandas as gpd, shapely
    co = gpd.read_file(a.counties)
    co = co[(co.STATE_ABBR == "TX") & co.NAME.str.replace(" County", "").isin(COUNTIES)]
    region = shapely.make_valid(co.geometry.union_all()).buffer(0.01)
    gz = gz[shapely.contains_xy(region, gz.lon.values, gz.lat.values)]
    rows = []
    for r in gz.itertuples():
        d = np.hypot((tx[:, 0] - r.lon) * kx, (tx[:, 1] - r.lat) * ky)
        p = pop.get(r.GEOID)
        if p is None or pd.isna(p):   # CDP: tracts whose center is inside the community's equivalent radius
            rad = math.sqrt(r.aland / 1e6 / math.pi) + 0.5
            p = float(tp[d <= rad].sum()) / 0.78
        name = re.sub(r"\s+(city|town|village|CDP)$", "", r.NAME.strip())
        rows.append((name, int(round(p)), round(r.lon, 4), round(r.lat, 4)))
    have = {x[0] for x in rows}
    if os.path.exists(a.extra):
        for e in pd.read_csv(a.extra).itertuples():
            if e.name not in have:
                rows.append((e.name, int(e.rank_pop), round(e.lon, 4), round(e.lat, 4)))
    rows.sort(key=lambda x: -x[1])
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "places.json")
    json.dump({"n": [x[0] for x in rows], "p": [x[1] for x in rows], "c": [[x[2], x[3]] for x in rows]},
              open(out, "w"), separators=(",", ":"))
    print(f"{len(rows)} places -> {out}")
    for x in rows[:30]:
        print(f"  {x[0]:<28} {x[1]:>9,}")


if __name__ == "__main__":
    main()
