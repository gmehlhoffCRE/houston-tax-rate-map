"""
Qualified Opportunity Zones, both rounds:

  python build_opp_zones.py --raw layers_raw --out out
      -> out/web/data/layers/opp_zones.json      OZ 2.0: designated Nov 5, 2026, in effect Jan 1, 2027 - Dec 31, 2036
      -> out/web/data/layers/opp_zones_v1.json   OZ 1.0: designated 2018, designations end Dec 31, 2026

OZ 2.0 source: Texas Governor's Office of Economic Development and Tourism, "Opportunity Zones 2.0 (EDT Recommended
Tracts)" (services6.arcgis.com, the layer behind the state's Texas Opportunity Zones 2.0 map). EDT_REC = 'YES' marks
the 608 tracts the Governor nominated; Treasury certified all 608 in its Nov 5, 2026 list of 6,576 tracts nationwide.
FED_RURAL marks rural tracts, which get the larger rural fund benefit under the 2025 law.

OZ 1.0 source: HUD Opportunity Zones (2018 designations), previously the only OZ layer (raw file opp_zones.geojson).
"""
import argparse, json, os, sys
import geopandas as gpd, pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from build_layers import fetch, load, simplify, write

OZ2 = ("https://services6.arcgis.com/qBPMNP2zACwkFVPe/arcgis/rest/services/"
       "Opportunity_Zones_2.0_(EDT_Recommended_Tracts)/FeatureServer/0", "GEO_ID,FED_RURAL,CBSA_NAME,EDT_REC", "EDT_REC='YES'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)

    p = os.path.join(a.raw, "opp_zones2.geojson")
    if not os.path.exists(p):
        n = fetch(OZ2[0], OZ2[1], p, page=2000, where=OZ2[2])
        print(f"fetched OZ 2.0 tracts in the region: {n:,}")
    g = load(a.raw, "opp_zones2")
    g = g[g.EDT_REC.astype(str).str.upper() == "YES"].copy()
    g["tract"] = g.GEO_ID.astype(str).str[-11:]
    g["rural"] = (g.FED_RURAL.astype(str).str.strip().str.lower() == "rural").astype(int)
    write(simplify(g, 10), os.path.join(od, "opp_zones.json"), ["tract", "rural"])
    print(f"OZ 2.0: {len(g)} tracts ({int(g.rural.sum())} rural)")

    g = load(a.raw, "opp_zones")
    tract = next((c for c in g.columns if c.upper() in ("GEOID10", "GEOID", "TRACT", "TRACTCE10", "GEOID_1")), None)
    g["tract"] = g[tract].astype(str) if tract else ""
    write(simplify(g, 10), os.path.join(od, "opp_zones_v1.json"), ["tract"])
    print(f"OZ 1.0: {len(g)} tracts")


if __name__ == "__main__":
    main()
