"""
Freeways and major highways with route labels, drawn above the map shading so the region reads at a glance.

  python build_highways.py --raw layers_raw --out out
      -> out/web/data/layers/highways.json

Source: TxDOT Roadway Inventory (services.arcgis.com). Kept: interstates, freeways and expressways (F_SYSTEM 1-2)
and principal arterials on the US / state highway system (F_SYSTEM 3). Route labels from HSYS + HNUM ("I-10",
"US 59", "SH 288", "Beltway 8"); toll road names where TxDOT lists one. Lines are merged per route and simplified
to about 15 m.

Output (compact): {"r": [label, ...], "k": [class, ...], "f": [[route index, [lon, lat, lon, lat, ...]], ...]}
  class: 1 = interstate / freeway / tollway, 2 = other US or state highway
"""
import argparse, json, os, re, sys, urllib.parse
import geopandas as gpd, pandas as pd, shapely

sys.path.insert(0, os.path.dirname(__file__))
from fetch_fortbend import get
from build_drive_grid import BBOX, URL

FIELDS = "F_SYSTEM,HSYS,HNUM,HSUF,TOLL_NM,STE_NAM,RDBD_ID"
WHERE = "F_SYSTEM IN (1,2) OR (F_SYSTEM = 3 AND HSYS IN ('IH','US','SH','UA','UP'))"
SYS = {"IH": "I-", "US": "US ", "UA": "US ", "UP": "US ", "SH": "SH ", "SA": "SH ", "SL": "Loop ", "SS": "Spur ",
       "FM": "FM ", "RM": "RM ", "BW": "Beltway ", "PA": "Park Rd ", "BI": "I-", "BU": "Bus. US ", "BS": "Bus. SH ",
       "BF": "Bus. FM "}
NAMED = {("SH", "99"): "Grand Pkwy", ("SL", "8"): "Beltway 8", ("BW", "8"): "Beltway 8", ("SL", "610"): "610 Loop",
         ("IH", "610"): "610 Loop", ("SH", "NASA"): "NASA Pkwy"}
BAD = {"I-35", "I-40"}   # a handful of mis-coded ramps in the inventory; no such routes here


def fetch(path):
    feats, off = [], 0
    while True:
        q = {"where": WHERE, "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "outFields": FIELDS, "outSR": 4326, "geometryPrecision": 5,
             "orderByFields": "OBJECTID", "resultOffset": off, "resultRecordCount": 2000, "f": "geojson"}
        fs = json.loads(get(f"{URL}/query?{urllib.parse.urlencode(q)}")).get("features", [])
        feats += fs; off += len(fs)
        if len(fs) < 2000:
            break
    json.dump({"type": "FeatureCollection", "features": feats}, open(path, "w"))
    print(f"fetched {len(feats):,} highway segments", flush=True)


def label(r):
    hs, hn = str(r.HSYS or "").strip(), str(r.HNUM or "").strip().lstrip("0")
    if (hs, hn) in NAMED:
        return NAMED[(hs, hn)]
    if hs in SYS and hn:
        return "" if SYS[hs] + hn in BAD else SYS[hs] + hn
    t = re.sub(r"\s*\(.*?\)", "", str(r.TOLL_NM or "")).strip()
    if t.lower() in ("", "nan", "none"):
        return ""
    return t.title().replace("Parkway", "Pkwy").replace("Mctra", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    p = os.path.join(a.raw, "highways.geojson")
    if not os.path.exists(p):
        fetch(p)
    g = gpd.read_file(p)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    g["lab"] = g.apply(label, axis=1)
    fs = pd.to_numeric(g.F_SYSTEM, errors="coerce").fillna(3).astype(int)
    hs = g.HSYS.fillna("").astype(str)
    g["cls"] = ((fs <= 2) | hs.isin(["IH", "BW"])).map({True: 1, False: 2})
    print(g.lab.value_counts().head(40).to_string())
    m = g.to_crs(2278)
    labs, kinds, feats = [], [], []
    for (lab, cls), part in m.groupby(["lab", "cls"]):
        merged = shapely.line_merge(shapely.union_all(part.geometry.values)).simplify(50)   # 50 ft
        geo = gpd.GeoSeries([merged], crs=2278).to_crs(4326).iloc[0]
        lines = [geo] if geo.geom_type == "LineString" else list(getattr(geo, "geoms", []))
        ri = len(labs); labs.append(lab); kinds.append(int(cls))
        for ln in lines:
            if ln.length == 0:
                continue
            c = [round(v, 5) for xy in ln.coords for v in xy[:2]]
            feats.append([ri, c])
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "highways.json")
    json.dump({"r": labs, "k": kinds, "f": feats}, open(out, "w"), separators=(",", ":"))
    print(f"{len(labs)} routes, {len(feats):,} lines, {os.path.getsize(out) / 1e6:.2f} MB -> {out}")


if __name__ == "__main__":
    main()
