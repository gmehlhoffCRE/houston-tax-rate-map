"""
City extraterritorial jurisdictions (ETJ) in the region.

  python build_etj.py --raw layers_raw --out out
      -> out/web/data/layers/etj.json

Source: H-GAC Open Data, HGAC_City_ETJ_Boundaries (gis.h-gac.com, Open_Data/Boundaries/MapServer/9), fetched one
city at a time by raw/etj/fetch.py into layers_raw/etj.geojson (Esri rings: clockwise = outer, counterclockwise = hole).
Inside an ETJ a site pays no city property tax but city platting and subdivision rules apply; since SB 2038 (2023)
owners can petition to be released, so ETJs have holes.
"""
import argparse, json, os, sys
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(__file__))
from build_layers import simplify, write


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
    g = gpd.GeoDataFrame(rows, crs=4326).dissolve(by="city", as_index=False)
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    n, mb = write(simplify(g, 15), os.path.join(od, "etj.json"), ["city"])
    print(f"{n} city ETJs ({mb:.2f} MB): {', '.join(sorted(g.city))}")


if __name__ == "__main__":
    main()
