"""
Travel-speed grid for drive-time estimates in the page.

  python build_drive_grid.py --raw layers_raw --out out
      -> out/web/data/layers/drivegrid.json

Roads: TxDOT Roadway Inventory (services.arcgis.com), all functional classes in the region. Each 200 m cell gets
the speed of the fastest road through it, for a car and a truck:

  F_SYSTEM 1-2 (interstates, freeways)   posted limit x 0.90   truck: min(posted, 65 mph) x 0.85
  F_SYSTEM 3 (principal arterials)       posted limit x 0.70   truck x 0.62   (signals, turns)
  F_SYSTEM 4-5 (minor arterials, major collectors)  x 0.65     truck x 0.58
  F_SYSTEM 6-7 (minor collectors, local streets)   x 0.60     truck x 0.52
  Missing posted limits use 65 / 45 / 40 / 30 mph by class. Cells with no road: 8 km/h (car and truck).
  Water (Esri USA Detailed Water Bodies, 0.05 sq km and up) and cells off the coastline (Esri generalized county
  outlines) are impassable, speed 0, unless a road crosses them (bridges, causeways).

The page runs a shortest-path search over the grid (8 neighbors) from the clicked point and draws 15/30/45/60
minute bands. This is an estimate: free-flow speeds, no live traffic, freeways can be joined anywhere along
them, no turn or signal timing beyond the factors above. Cells are stored as speed in km/h (uint8), base64.
"""
import argparse, base64, json, os, sys, time, urllib.parse
import numpy as np, geopandas as gpd, pandas as pd, shapely

sys.path.insert(0, os.path.dirname(__file__))
from fetch_fortbend import get

BBOX = (-96.75, 28.55, -94.05, 30.85)   # the 8 counties plus a buffer so radii near the edge are not cut short
CELL_M = 200.0
URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/TxDOT_Roadway_Inventory/FeatureServer/0"
ESRI = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services"
WATER = f"{ESRI}/USA_Detailed_Water_Bodies/FeatureServer/0"            # bays, lakes, rivers (USGS NHD based)
LAND = f"{ESRI}/USA_Counties_Generalized_Boundaries/FeatureServer/0"   # county outlines clipped to the shoreline
MPH = 1.609344


def fetch(path):
    total = json.loads(get(f"{URL}/query?" + urllib.parse.urlencode({
        "where": "1=1", "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "returnCountOnly": "true", "f": "json"})))["count"]
    feats, off, t = [], 0, time.time()
    while off < total:
        q = {"where": "1=1", "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope",
             "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "F_SYSTEM,SPD_MAX,RDBD_ID,HSYS",
             "outSR": 4326, "geometryPrecision": 5, "orderByFields": "OBJECTID", "resultOffset": off,
             "resultRecordCount": 2000, "f": "geojson"}
        fs = json.loads(get(f"{URL}/query?{urllib.parse.urlencode(q)}")).get("features", [])
        if not fs:
            break
        feats += fs; off += len(fs)
        if off % 20000 < 2000:
            print(f"  roads {off:,}/{total:,} ({time.time() - t:.0f} s)", flush=True)
    json.dump({"type": "FeatureCollection", "features": feats}, open(path, "w"))
    print(f"fetched {len(feats):,} road segments", flush=True)


def fetch_polys(url, path, fields):
    feats, off = [], 0
    while True:
        q = {"where": "1=1", "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "outSR": 4326, "geometryPrecision": 5,
             "resultOffset": off, "resultRecordCount": 1000, "f": "geojson"}
        fs = json.loads(get(f"{url}/query?{urllib.parse.urlencode(q)}")).get("features", [])
        feats += fs; off += len(fs)
        if len(fs) < 1000:
            break
    json.dump({"type": "FeatureCollection", "features": feats}, open(path, "w"))
    print(f"fetched {len(feats):,} features from {url.split('/services/')[1].split('/')[0]}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)
    p = os.path.join(a.raw, "roads.geojson")
    if not os.path.exists(p):
        fetch(p)
    for name, url, fields in (("water", WATER, "NAME,FTYPE,SQKM"), ("land", LAND, "NAME,STATE_ABBR")):
        if not os.path.exists(os.path.join(a.raw, name + ".geojson")):
            fetch_polys(url, os.path.join(a.raw, name + ".geojson"), fields)
    g = gpd.read_file(p)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].explode(index_parts=False).reset_index(drop=True)
    g = g[(shapely.get_num_coordinates(g.geometry.values) >= 2) & (g.geometry.length > 0)]   # drop one-point lines
    fs = pd.to_numeric(g.F_SYSTEM, errors="coerce").fillna(7).astype(int)
    posted = pd.to_numeric(g.SPD_MAX, errors="coerce")
    default = np.select([fs <= 2, fs == 3, fs <= 5], [65, 45, 40], 30)
    posted = posted.where((posted >= 15) & (posted <= 85), default)
    car = np.select([fs <= 2, fs == 3, fs <= 5], [0.90, 0.70, 0.65], 0.60) * posted * MPH
    truck = np.select([fs <= 2, fs == 3, fs <= 5], [0.85 * np.minimum(posted, 65), 0.62 * posted, 0.58 * posted],
                      0.52 * posted) * MPH

    # grid in Web Mercator-free equal-ish cells: degrees sized to CELL_M at the region's mid latitude
    lat0 = (BBOX[1] + BBOX[3]) / 2
    dy = CELL_M / 111320.0
    dx = CELL_M / (111320.0 * np.cos(np.radians(lat0)))
    nx = int(np.ceil((BBOX[2] - BBOX[0]) / dx)); ny = int(np.ceil((BBOX[3] - BBOX[1]) / dy))
    gc = np.full((2, ny, nx), 8.0, dtype=np.float32)   # off-road / no mapped road
    # sample each line every ~40 m and keep the fastest speed per cell
    m = g.to_crs(2278)
    seg = m.geometry.segmentize(40 * 3.2808).to_crs(4326)
    coords = shapely.get_coordinates(seg.values, return_index=True)
    xy, idx = coords
    ix = ((xy[:, 0] - BBOX[0]) / dx).astype(int); iy = ((xy[:, 1] - BBOX[1]) / dy).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    for k, sp in enumerate((car, truck)):
        np.maximum.at(gc[k], (iy[ok], ix[ok]), np.asarray(sp, dtype=np.float32)[idx[ok]])
    # water mask: cells whose center is in a bay, lake or river, or off the coastline, are impassable (speed 0)
    # unless a road runs through them (bridges, causeways, the Galveston seawall)
    water = gpd.read_file(os.path.join(a.raw, "water.geojson"))
    water = water[pd.to_numeric(water.get("SQKM"), errors="coerce").fillna(1) >= 0.05]   # skip ponds
    land = gpd.read_file(os.path.join(a.raw, "land.geojson"))
    wu = shapely.make_valid(water.geometry.union_all()); lu = shapely.make_valid(land.geometry.union_all())
    shapely.prepare(wu); shapely.prepare(lu)
    cx = BBOX[0] + (np.arange(nx) + 0.5) * dx; cy = BBOX[1] + (np.arange(ny) + 0.5) * dy
    X, Y = np.meshgrid(cx, cy)
    wet = shapely.contains_xy(wu, X, Y) | ~shapely.contains_xy(lu, X, Y)
    road = gc[0] > 8
    for k in (0, 1):
        gc[k][wet & ~road] = 0
    print(f"water mask: {int((wet & ~road).sum()):,} impassable cells; {int((wet & road).sum()):,} road cells over water kept")
    b64 = [base64.b64encode(np.clip(np.rint(gc[k]), 0, 255).astype(np.uint8).tobytes()).decode() for k in (0, 1)]
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    out = {"bbox": BBOX, "nx": nx, "ny": ny, "dx": dx, "dy": dy, "cell_m": CELL_M, "unit": "km/h",
           "car": b64[0], "truck": b64[1]}
    json.dump(out, open(os.path.join(od, "drivegrid.json"), "w"), separators=(",", ":"))
    print(f"grid {nx} x {ny} = {nx * ny:,} cells of {CELL_M:.0f} m; road cells {int((gc[0] > 8).sum()):,}; "
          f"file {os.path.getsize(os.path.join(od, 'drivegrid.json')) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
