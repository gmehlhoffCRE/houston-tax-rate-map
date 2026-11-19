"""
City extraterritorial jurisdictions (ETJ) in the region.

  python build_etj.py --raw layers_raw --out out
      -> out/web/data/layers/etj.json

Source: H-GAC Open Data, HGAC_City_ETJ_Boundaries (gis.h-gac.com, Open_Data/Boundaries/MapServer/9), fetched one
city at a time by raw/etj/fetch.py into layers_raw/etj.geojson (Esri rings: clockwise = outer, counterclockwise = hole).
Inside an ETJ a site pays no city property tax but city platting and subdivision rules apply; since SB 2038 (2023)
owners can petition to be released, so ETJs have holes.

H-GAC's layer leaves out many cities, so city and county layers fill them in (name: a fixed city, or a field):
"""
import argparse, json, os, sys
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(__file__))
from build_layers import fetch, load, simplify, write

A = "https://services{}.arcgis.com/{}/arcgis/rest/services/{}/FeatureServer/{}"
EXTRA = [   # (key, url, city name or field)
    ("gvcad", A.format(5, "HX1EVnYCHIQ7lExY", "GVCAD_ETJ", 33), "field:City"),                       # Galveston County cities
    ("liberty", A.format(8, "oC43KEw3oqxdIPOH", "Liberty_County_ETJs", 3), "field:CITY"),            # Liberty County, Mont Belvieu
    ("katy", A.format(8, "ihZy0ZJt5Ea5u0dK", "Katy_ETJ", 16), "Katy"),
    ("baytown", A.format(8, "2iaYWEMdQLPv0ZUw", "City_of_Baytown_Citizen_Map_WFL1", 11), "Baytown"),
    ("tomball", A.format(2, "Q162lMMZLeb8KwDU", "Municipal_Boundaries_(Public_View)", 66), "Tomball"),
    ("alvin", A.format(3, "dViPBrlsejmXK64z", "Alvin_ETJ", 2), "Alvin"),
    ("angleton", A.format(3, "KGWVkDBbmA3Jt2Ut", "ETJ", 0), "Angleton"),
    ("manvel", A.format(7, "Bh9vn7pCTjhyhpch", "Manvel_City_Limits_ETJ", 44), "Manvel"),
    ("dayton", A.format(6, "1zuvRnm7tm3WFwVI", "ETJ", 13), "Dayton"),
    ("waller", A.format(2, "SzVJ1uMIzN11sEGj", "Boundaries", 1), "Waller"),
]


def esri_to_shape(rings):
    outer, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        a = sum((r[i + 1][0] - r[i][0]) * (r[i + 1][1] + r[i][1]) for i in range(len(r) - 1))
        (outer if a > 0 else holes).append(Polygon(r))     # clockwise rings have a positive sum
    if not outer:
        return None
    shp = unary_union([p.buffer(0) for p in outer])
    if holes:
        shp = shp.difference(unary_union([h.buffer(0) for h in holes]))
    return shp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    src = json.load(open(os.path.join(a.raw, "etj.geojson")))
    rows = []
    for f in src["features"]:
        s = esri_to_shape(f["geometry"]["coordinates"])
        if s is not None and not s.is_empty:
            rows.append({"city": f["properties"]["city"].title(), "geometry": s})
    have = {r["city"] for r in rows}
    for key, url, nm in EXTRA:
        p = os.path.join(a.raw, f"etj_{key}.geojson")
        if not os.path.exists(p):
            try:
                fetch(url, "*", p)
            except Exception as e:
                print(f"  {key}: fetch failed ({e})"); continue
        x = load(a.raw, f"etj_{key}")
        for r in x.itertuples():
            c = getattr(r, nm[6:]) if nm.startswith("field:") else nm
            c = (c or "").upper().replace(" ETJ", "").replace("CITY OF ", "").strip().title()
            if c and c not in have or key in ("gvcad", "liberty"):
                rows.append({"city": c, "geometry": r.geometry})
        print(f"  {key}: {len(x)} shapes")
    g = gpd.GeoDataFrame(rows, crs=4326)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    g["geometry"] = g.geometry.make_valid()
    g = g.dissolve(by="city", as_index=False)
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    n, mb = write(simplify(g, 15), os.path.join(od, "etj.json"), ["city"])
    print(f"{n} city ETJs ({mb:.2f} MB): {', '.join(sorted(g.city))}")


if __name__ == "__main__":
    main()
