"""
Test fixture: rebuilds HCAD-shaped inputs from the prototype's embedded data (proto_data.json,
48,686 Ship Channel parcels) so the countywide pipeline can be run end to end without the
HCAD downloads.

Writes into --out:
  gis/Parcels.gpkg            EPSG:2278, fields HCAD_NUM_1, CurrOwner   (stands in for Parcels.gdb)
  gis/<Overlay>.gpkg          overlay polygons dissolved from parcels by combo names (School, City, ...)
  cama/real_acct.txt          tab separated, latin-1, the real_acct.txt columns the pipeline reads

Usage: python make_fixture.py proto_data.json --combos ../data/hcad_combos.csv --out fixture
"""
import argparse, json, os
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon

ap = argparse.ArgumentParser()
ap.add_argument("proto")
ap.add_argument("--combos", required=True)
ap.add_argument("--out", default="fixture")
a = ap.parse_args()
d = json.load(open(a.proto))
ox, oy = d["origin"]; sc = d["scale"]


def ring(enc):
    q = np.array(enc, dtype=np.int64).reshape(-1, 2).cumsum(axis=0)
    return np.column_stack([ox + q[:, 0] / sc, oy + q[:, 1] / sc])


geoms = []
for g in d["geoms"]:
    polys = [Polygon(ring(p[0]), [ring(h) for h in p[1:]]) for p in g]
    geoms.append(polys[0] if len(polys) == 1 else MultiPolygon(polys))
P = pd.DataFrame(d["props"], columns=d["fields"])
os.makedirs(os.path.join(a.out, "gis"), exist_ok=True)
os.makedirs(os.path.join(a.out, "cama"), exist_ok=True)

gdf = gpd.GeoDataFrame({"HCAD_NUM_1": P.acct, "CurrOwner": P.owner}, geometry=geoms, crs=4326).to_crs(2278)
gdf["geometry"] = gdf.geometry.buffer(0)
gdf.to_file(os.path.join(a.out, "gis", "Parcels.gpkg"), driver="GPKG")

ra = pd.DataFrame({"acct": P.acct, "mailto": P.owner, "site_addr_1": P.addr, "site_addr_2": P.city,
                   "state_class": P.cls, "tot_appr_val": P.val, "bld_ar": P.bldSF, "land_ar": P.landSF})
ra.to_csv(os.path.join(a.out, "cama", "real_acct.txt"), sep="\t", index=False, encoding="latin-1")

cb = pd.read_csv(a.combos, dtype=str, keep_default_na=False).set_index("combo_id")
combo = P.combo.fillna(-1).astype(int).astype(str)
grow = gdf.assign(geometry=gdf.geometry.buffer(150))   # close street gaps between parcels
for name, col in [("School", "isd"), ("City", "city"), ("Water_district", "water_districts"),
                  ("Emergency", "esd"), ("Special", "mgmt_districts"), ("TIRZ", "tirz")]:
    names = combo.map(cb[col]).fillna("")
    rows = []
    for nm in sorted({x.strip() for v in names for x in v.split(";") if x.strip()}):
        mask = names.str.contains(nm, regex=False)
        rows.append({"name": nm, "geometry": grow[mask.to_numpy()].geometry.union_all().buffer(-145).buffer(0)})
    if rows:
        gpd.GeoDataFrame(rows, crs=2278).to_file(os.path.join(a.out, "gis", name + ".gpkg"), driver="GPKG")
    print(name, len(rows))
print(f"{len(gdf):,} parcels -> {a.out}")
