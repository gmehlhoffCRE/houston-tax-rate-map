"""
Rail-served parcels: every parcel shape within 100 ft of an active rail line (main lines, sidings, spurs and
yards in the US DOT BTS North American Rail Network).

  python build_rail_served.py --parcels out/parcels.geojsonl --raw layers_raw --out layers_out
      -> layers_out/web/data/layers/rail_served.json   {"ft": 100, "a": {account: [owner, feet], ...}}

"Within 100 ft" is a screen, not a confirmed spur or served track: NARN lines are mapped to about 10-40 m,
and a parcel next to a main line may have no spur. The owner is the railroad that owns the nearest track.
"""
import argparse, json, os, sys, time
import geopandas as gpd, numpy as np, pandas as pd, shapely
from pyproj import Transformer

FT = 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcels", required=True)
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="layers_out")
    a = ap.parse_args()
    r = gpd.read_file(os.path.join(a.raw, "rail.geojson"))
    r = r[r.geometry.notna() & ~r.geometry.is_empty & ~r.get("NET", pd.Series("", index=r.index)).fillna("").isin(["X"])]
    r = r.set_crs(4326, allow_override=True).to_crs(2278)   # Texas South Central, feet
    lines = r.geometry.values; owners = r.RROWNER1.fillna("").values
    tree = shapely.STRtree(lines)
    tf = Transformer.from_crs(4326, 2278, always_xy=True)
    hit, n, t = {}, 0, time.time()
    with open(a.parcels) as fh:
        for line in fh:
            n += 1
            f = json.loads(line); acct = f["properties"]["a"]
            g = shapely.geometry.shape(f["geometry"])
            g = shapely.transform(g, lambda xy: np.column_stack(tf.transform(xy[:, 0], xy[:, 1])))
            idx = tree.query(g, predicate="dwithin", distance=FT)
            if len(idx):
                d = shapely.distance(lines[idx], g); k = int(np.argmin(d))
                hit[acct] = [owners[idx[k]], int(round(float(d[k])))]
            if n % 500000 == 0:
                print(f"  {n:,} parcels, {len(hit):,} rail-served ({time.time() - t:.0f} s)", flush=True)
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    json.dump({"ft": FT, "a": hit}, open(os.path.join(od, "rail_served.json"), "w"), separators=(",", ":"))
    by = pd.Series([v[0] for v in hit.values()]).value_counts()
    print(f"{len(hit):,} of {n:,} parcels within {FT} ft of rail; " + ", ".join(f"{k or 'unknown'} {v:,}" for k, v in by.items()))


if __name__ == "__main__":
    main()
