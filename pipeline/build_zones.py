"""
Builds the zoomed-out "zones" layer: parcels dissolved by rate combo and property type.

At Google zoom 8 to 13 individual parcels are a few pixels wide, so drawing 1.5 million of them is wasted work
and too big for a tile. This merges neighboring parcels that share a combo id (c) and type group (t) into
block-sized shapes: each parcel is grown by --gap meters, unioned with its neighbors, and shrunk back, which
closes alleys and local streets narrower than about twice --gap. Work is split into square cells so memory
stays flat and all CPU cores are used; shapes stop at cell edges, which is invisible once colored.

Usage: python build_zones.py out/parcels.geojsonl out/zones.geojsonl [--gap 12] [--cell 2000] [--simplify 6]
"""
import argparse, json, os, time
from multiprocessing import Pool
import numpy as np
import shapely
from pyproj import Transformer

TO_M = Transformer.from_crs(4326, 3857, always_xy=True)
TO_LL = Transformer.from_crs(3857, 4326, always_xy=True)


def reproject(geoms, tr):
    return shapely.transform(geoms, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))


def dissolve_cell(args):
    wkb, keys, gap, simp = args
    g = shapely.from_wkb(wkb)
    out = []
    for k in np.unique(keys):
        m = keys == k
        u = shapely.union_all(shapely.buffer(g[m], gap, quad_segs=2))
        u = shapely.buffer(u, -gap, quad_segs=2)
        u = shapely.simplify(u, simp, preserve_topology=True)
        if u is None or u.is_empty:
            continue
        out.append((int(k), shapely.to_wkb(u)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--gap", type=float, default=12.0, help="meters; closes gaps up to about twice this")
    ap.add_argument("--cell", type=float, default=2000.0, help="work cell size in meters")
    ap.add_argument("--simplify", type=float, default=6.0, help="meters")
    a = ap.parse_args()
    t0 = time.time()

    # stream the file: lines look like {"type":"Feature","properties":{...},"geometry":{...}}
    parts, cs, ts, batch = [], [], [], []
    with open(a.src) as f:
        for line in f:
            head, geo = line.rstrip("\n").split(',"geometry":', 1)
            p = json.loads(head[head.index('"properties":') + 13:])
            cs.append(p["c"]); ts.append(p["t"]); batch.append(geo[:-1])
            if len(batch) == 200_000:
                parts.append(shapely.from_geojson(batch)); batch = []
    if batch:
        parts.append(shapely.from_geojson(batch))
    geoms = np.concatenate(parts)
    c = np.array(cs, dtype=np.int64); t = np.array(ts, dtype=np.int64)
    del parts, cs, ts, batch
    ok = ~shapely.is_empty(geoms) & ~shapely.is_missing(geoms)
    geoms, c, t = geoms[ok], c[ok], t[ok]
    print(f"{len(geoms):,} parcels read in {time.time() - t0:.0f}s", flush=True)

    gm = reproject(geoms, TO_M)
    del geoms
    pts = shapely.get_coordinates(shapely.point_on_surface(gm))
    cx = np.floor(pts[:, 0] / a.cell).astype(np.int64)
    cy = np.floor(pts[:, 1] / a.cell).astype(np.int64)
    key = (c + 1) * 8 + t                          # combo and type in one integer
    cell = cx * 1_000_003 + cy
    order = np.argsort(cell, kind="stable")
    bounds = np.flatnonzero(np.diff(cell[order])) + 1
    jobs = [(shapely.to_wkb(gm[idx]), key[idx], a.gap, a.simplify) for idx in np.split(order, bounds)]
    print(f"{len(jobs):,} cells", flush=True)

    n = 0
    with Pool(os.cpu_count()) as pool, open(a.dst, "w") as fo:
        for res in pool.imap_unordered(dissolve_cell, jobs, chunksize=8):
            if not res:
                continue
            ks = [k for k, _ in res]
            ll = reproject(shapely.from_wkb([w for _, w in res]), TO_LL)
            ll = shapely.transform(ll, lambda xy: np.round(xy, 6))
            for k, gj in zip(ks, shapely.to_geojson(ll)):
                fo.write('{"type":"Feature","properties":{"c":%d,"t":%d},"geometry":%s}\n' % (k // 8 - 1, k % 8, gj))
                n += 1
    print(f"{n:,} zone shapes written to {a.dst} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
