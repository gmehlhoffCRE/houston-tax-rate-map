"""
Builds the inline data blob for the single-file prototype (one clipped area).
Superseded at county scale by vector tiles, but kept as the reference for joins and encoding.

Inputs (all from HCAD, see HANDOFF.md):
  Parcels.zip -> Parcels.gdb, Real_acct_owner.zip, overlay zips (City, School, Water_district,
  Emergency, Special, TIRZ), plus hcad_account_rates.csv.gz, hcad_combos.csv, hcad_rate_table.csv
  from build_rates.py.
Usage: python build_prototype_data.py --gis ./gis --rates . --bbox -95.25 29.665 -95.10 29.77
       python inject.py   (writes the HTML)
"""
import argparse, glob, json, os, zipfile
import numpy as np, pandas as pd, geopandas as gpd, pyogrio
from pyproj import Transformer
from shapely.geometry import box, mapping

ap = argparse.ArgumentParser()
ap.add_argument("--gis", default="gis"); ap.add_argument("--rates", default=".")
ap.add_argument("--bbox", nargs=4, type=float, default=[-95.25, 29.665, -95.10, 29.77])
ap.add_argument("--out", default="proto_data.json")
a = ap.parse_args()
W, S, E, N = a.bbox
tr = Transformer.from_crs(4326, 2278, always_xy=True)
x0, y0 = tr.transform(W, S); x1, y1 = tr.transform(E, N)
s_ = lambda v: " ".join(v.split()) if isinstance(v, str) else ""
i_ = lambda v: None if pd.isna(v) else int(float(v))

# parcels (EPSG:2278 source), simplify 2 ft, to WGS84
g = pyogrio.read_dataframe(os.path.join(a.gis, "Parcels.gdb"), bbox=(x0, y0, x1, y1),
                           columns=["HCAD_NUM_1", "CurrOwner", "LocAddr", "city", "Acreage"])
g = g[g.HCAD_NUM_1.notna()].copy(); g["acct"] = g.HCAD_NUM_1.str.strip()
g["geometry"] = g.geometry.force_2d().simplify(2.0); g = g.to_crs(4326)

need = set(g.acct); parts = []
z = zipfile.ZipFile(os.path.join(a.gis, "Real_acct_owner.zip"))
for ch in pd.read_csv(z.open("real_acct.txt"), sep="\t", dtype=str, chunksize=400000, encoding="latin-1", quoting=3,
                      usecols=["acct", "state_class", "bld_ar", "land_ar", "tot_appr_val", "site_addr_1", "site_addr_2"]):
    ch["acct"] = ch.acct.str.strip(); parts.append(ch[ch.acct.isin(need)])
ra = pd.concat(parts).drop_duplicates("acct").set_index("acct")
ar = pd.read_csv(os.path.join(a.rates, "hcad_account_rates.csv.gz"), dtype={"acct": str}).set_index("acct")
g = g.join(ra, on="acct").join(ar[["combo_id"]], on="acct")

def enc_ring(coords):  # 1e-5 deg grid, delta encoded, consecutive duplicates dropped
    q = np.round((np.array(coords)[:, :2] - [W, S]) * 1e5).astype(np.int64)
    keep = np.ones(len(q), bool); keep[1:] = np.any(np.diff(q, axis=0) != 0, axis=1); q = q[keep]
    return np.vstack([q[:1], np.diff(q, axis=0)]).flatten().tolist()

P, G = [], []
for r in g.itertuples():
    geom = r.geometry
    if geom is None or geom.is_empty: continue
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    G.append([[enc_ring(p.exterior.coords)] + [enc_ring(h.coords) for h in p.interiors] for p in polys])
    P.append([r.acct, i_(r.combo_id), s_(r.CurrOwner), s_(r.site_addr_1) or s_(r.LocAddr), s_(r.site_addr_2) or s_(r.city),
              s_(r.state_class), i_(r.tot_appr_val), i_(r.bld_ar), i_(r.land_ar)])

c = pd.read_csv(os.path.join(a.rates, "hcad_combos.csv")).set_index("combo_id")
t = pd.read_csv(os.path.join(a.rates, "hcad_rate_table.csv"), dtype={"tax_dist": str}).set_index("tax_dist")
combos = {}
for cid in sorted({p[1] for p in P if p[1] is not None}):
    row = c.loc[cid]
    combos[cid] = {"b": round(row.rate_base, 6), "m": round(row.rate_mgmt, 6),
                   "p": [[x.split(":")[0], round(float(x.split(":")[1]), 6)] for x in str(row.breakdown).split("|")],
                   "isd": s_(row.isd), "city": s_(row.city), "tirz": s_(row.tirz), "miss": int(row.n_missing_rates),
                   "water": s_(row.water_districts), "esd": s_(row.esd), "college": s_(row.college), "mgmtN": s_(row.mgmt_districts)}
codes = {k for v in combos.values() for k, _ in v["p"]}
jur = {k: [t.loc[k, "name"], t.loc[k, "category"], t.loc[k, "bucket"]] for k in codes if k in t.index}

# overlays: dissolve by name, strip TIRZ participant suffixes, keep boundary LINES clipped inside the box
inner = box(W + 0.0005, S + 0.0005, E - 0.0005, N - 0.0005); layers = {}
for key, f in [("city", "City"), ("isd", "School"), ("water", "Water_district"), ("esd", "Emergency"), ("special", "Special"), ("tirz", "TIRZ")]:
    shp = glob.glob(os.path.join(a.gis, f, "**", "*.shp"), recursive=True)[0]
    o = pyogrio.read_dataframe(shp, bbox=(x0 - 5000, y0 - 5000, x1 + 5000, y1 + 5000))
    if not len(o): continue
    o["geometry"] = o.geometry.simplify(15); o = o.to_crs(4326)
    o = gpd.clip(o, box(W - .01, S - .01, E + .01, N + .01))
    o["name"] = o["name"].str.replace(r"\s*\(\d{3}\)", "", regex=True).str.strip()
    o = o.dissolve(by="name", as_index=False)
    feats = []
    for _, r in o.iterrows():
        lp = r.geometry.representative_point(); line = r.geometry.boundary.intersection(inner)
        if line.is_empty: continue
        feats.append({"type": "Feature", "properties": {"name": r["name"], "lp": [round(lp.x, 5), round(lp.y, 5)]},
                      "geometry": mapping(line.simplify(0))})
    layers[key] = {"type": "FeatureCollection", "features": feats}

data = {"origin": [W, S], "scale": 1e5, "fields": ["acct", "combo", "owner", "addr", "city", "cls", "val", "bldSF", "landSF"],
        "props": P, "geoms": G, "combos": combos, "jur": jur, "layers": layers, "taxYear": 2025, "valueYear": 2026, "bbox": [W, S, E, N]}
json.dump(data, open(a.out, "w"), separators=(",", ":"))
print(f"{len(P):,} parcels, {len(combos)} combos -> {a.out}")
