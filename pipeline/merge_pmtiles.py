"""
Merges PMTiles archives whose zoom ranges do not overlap (zones z7-12 + parcels z13-16) into one.
Replaces tile-join, which is not needed when no tile has to be combined, and avoids a dependency on it.

Usage: python merge_pmtiles.py out.pmtiles zones.pmtiles parcels.pmtiles [--name N] [--description D]
Requires: pip install pmtiles
"""
import argparse, json
from pmtiles.reader import Reader, MmapSource, all_tiles
from pmtiles.writer import Writer
from pmtiles.tile import zxy_to_tileid, Compression

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("inputs", nargs="+")
ap.add_argument("--name", default="")
ap.add_argument("--description", default="")
a = ap.parse_args()

srcs = [open(p, "rb") for p in a.inputs]
readers = [Reader(MmapSource(f)) for f in srcs]
headers = [r.header() for r in readers]
metas = [r.metadata() for r in readers]

# zoom ranges must not overlap, otherwise tiles would need combining
ranges = sorted((h["min_zoom"], h["max_zoom"], i) for i, h in enumerate(headers))
for (a0, a1, _), (b0, b1, _) in zip(ranges, ranges[1:]):
    if b0 <= a1:
        raise SystemExit(f"zoom ranges overlap: {a0}-{a1} and {b0}-{b1}")
comp = {h["tile_compression"] for h in headers}
if len(comp) != 1:
    raise SystemExit("inputs use different tile compression")

tiles = []
for r in readers:
    for (z, x, y), data in all_tiles(r.get_bytes):
        tiles.append((zxy_to_tileid(z, x, y), data))
tiles.sort(key=lambda t: t[0])

layers, seen = [], set()
for m in metas:
    for l in m.get("vector_layers", []):
        if l["id"] not in seen:
            layers.append(l); seen.add(l["id"])
meta = {"name": a.name or metas[0].get("name", ""), "description": a.description,
        "format": "pbf", "vector_layers": layers}

h0 = headers[0]
header = {
    "tile_type": h0["tile_type"], "tile_compression": h0["tile_compression"],
    "min_zoom": min(h["min_zoom"] for h in headers), "max_zoom": max(h["max_zoom"] for h in headers),
    "min_lon_e7": min(h["min_lon_e7"] for h in headers), "min_lat_e7": min(h["min_lat_e7"] for h in headers),
    "max_lon_e7": max(h["max_lon_e7"] for h in headers), "max_lat_e7": max(h["max_lat_e7"] for h in headers),
    "center_zoom": h0["center_zoom"], "center_lon_e7": h0["center_lon_e7"], "center_lat_e7": h0["center_lat_e7"],
}
with open(a.out, "wb") as f:
    w = Writer(f)
    for tid, data in tiles:
        w.write_tile(tid, data)
    w.finalize(header, meta)
for f in srcs:
    f.close()
print(f"{a.out}: {len(tiles):,} tiles, zoom {header['min_zoom']}-{header['max_zoom']}, layers {[l['id'] for l in layers]}")
