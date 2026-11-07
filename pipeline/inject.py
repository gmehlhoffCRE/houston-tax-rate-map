"""
Assembles the deployable page from web/tax-rate-map-template.html.

  python inject.py --key "$GMAPS_KEY" \
      --tiles  https://storage.googleapis.com/<bucket>/taxmap/harris_parcels.pmtiles \
      --shards https://storage.googleapis.com/<bucket>/taxmap/shards/ \
      --data   data/ \
      --out    out/web/index.html

--key     Maps JavaScript API key (or set GMAPS_KEY). Omit to use the Esri fallback basemap.
--tiles   PMTiles URL. Host must answer HTTP Range requests with 206 and allow CORS from the site.
--shards  base URL of the account and search shards (bucket/shards/ from build_county_data.py), ends with /
--data    base URL of combos.json and boundaries/ (web/data/), relative to the page or absolute, ends with /
--embed   OUT folder from build_county_data.py + build_tiles.sh. Packs tiles, combos, boundaries and account
          records into the one HTML file so it opens from disk with no server (search scans the records in
          memory). Uses harris_parcels_lean.pmtiles when present (build_tiles.sh OUT lean). Countywide that is
          a 129 MB file (about 10 s to open, 660 MB of memory); a --bbox submarket build is 5 to 15 MB.

  python inject.py --key "$GMAPS_KEY" --embed out --out ship-channel-map.html
"""
import argparse, base64, glob, gzip, json, os

here = os.path.dirname(os.path.abspath(__file__))
web = os.path.join(here, "..", "web")
ap = argparse.ArgumentParser()
ap.add_argument("--key", default=os.environ.get("GMAPS_KEY", ""))
ap.add_argument("--tiles", default="harris_parcels.pmtiles")
ap.add_argument("--shards", default="shards/")
ap.add_argument("--data", default="data/")
ap.add_argument("--out", default="index.html")
ap.add_argument("--embed", metavar="OUT_DIR")
ap.add_argument("--layers", metavar="DIR", help="industrial layers from build_layers.py / build_drive_grid.py "
                "(default <embed>/web/data/layers); hosted builds serve them at <data>layers/")
ap.add_argument("--chunk-mb", type=float, default=95, help="with --split: max size of each data file in MB")
ap.add_argument("--part-ext", default="js", help="with --split: data file extension; 'txt' avoids download blocks on .js")
ap.add_argument("--split", action="store_true",
                help="with --embed: put the data in .js files (each under 95 MB) next to the page instead of inline, "
                     "for hosts with a per-file limit such as GitHub (100 MB). Keep the files in one folder.")
a = ap.parse_args()

t = open(os.path.join(web, "tax-rate-map-template.html")).read()
mark = open(os.path.join(web, "cresa_mark.svg")).read().replace(
    'width="118" height="21"', 'width="112" height="20" aria-label="Cresa" style="display:block;flex-shrink:0"')
cfg = {"gkey": a.key or "__NO_KEY__", "tiles": a.tiles, "shards": a.shards, "data": a.data}
embed = ""
if a.embed:
    o = a.embed
    recs = {}
    for f in glob.glob(os.path.join(o, "bucket", "shards", "a", "*.json")):
        for r in json.load(open(f))["r"]:
            recs[r[0]] = r
    records = sorted(recs.values(), key=lambda r: -(r[5] or 0))   # highest appraised value first
    # columnar: one array per field compresses far better than one array per record
    names = ["acct", "owner", "addr", "city", "cls", "val", "bld", "land", "combo", "x", "y"]
    cols = {n: [r[i] for r in records] for i, n in enumerate(names)}
    if len(records) > 400_000:
        print(f"note: {len(records):,} accounts; expect a file over 100 MB that takes several seconds to open.")
    bounds = {os.path.splitext(os.path.basename(f))[0]: json.load(open(f))
              for f in glob.glob(os.path.join(o, "web", "data", "boundaries", "*.json"))}
    ldir = a.layers or os.path.join(o, "web", "data", "layers")
    layers = {os.path.splitext(os.path.basename(f))[0]: json.load(open(f)) for f in glob.glob(os.path.join(ldir, "*.json"))}
    bundle = {"combos": json.load(open(os.path.join(o, "web", "data", "combos.json"))),
              "boundaries": bounds, "layers": layers, "cols": cols}
    data_b64 = base64.b64encode(gzip.compress(json.dumps(bundle, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(), 9)).decode()
    lean = os.path.join(o, "bucket", "harris_parcels_lean.pmtiles")
    tpath = lean if os.path.exists(lean) else os.path.join(o, "bucket", "harris_parcels.pmtiles")
    tiles_b64 = base64.b64encode(open(tpath, "rb").read()).decode()
    print(f"tiles from {tpath}")
    if a.split:
        stem = os.path.splitext(os.path.basename(a.out))[0]
        outdir = os.path.dirname(os.path.abspath(a.out))
        tags, CH = [], int(a.chunk_mb * 1_000_000)   # default stays under GitHub's 100 MB file limit
        for kind, b64 in (("data", data_b64), ("tiles", tiles_b64)):
            for i in range(0, len(b64), CH):
                name = f"{stem}-{kind}-{i // CH + 1}.{a.part_ext}"
                with open(os.path.join(outdir, name), "w") as f:
                    f.write(f'(window.__emb=window.__emb||{{data:[],tiles:[]}}).{kind}.push("{b64[i:i + CH]}");\n')
                tags.append(f'<script src="{name}" onload="this.dataset.ok=1"></script>')
                print(f"wrote {name} ({os.path.getsize(os.path.join(outdir, name)) / 1e6:.1f} MB)")
        embed = "\n".join(tags)
        cfg["parts"] = [t.split('"')[1] for t in tags]   # lets the page name any file that failed to load
    else:
        embed = (f'<script id="emb-data" type="application/octet-stream">{data_b64}</script>\n'
                 f'<script id="emb-tiles" type="application/octet-stream">{tiles_b64}</script>')
    cfg.update({"embed": True, "tiles": "", "shards": "", "data": ""})
    print(f"embedded {len(records):,} account records, {len(bounds)} boundary layers, {len(layers)} industrial layers, "
          f"{len(tiles_b64) * 3 // 4 / 1e6:.1f} MB of tiles")
t = t.replace("__MARK__", mark).replace("__CONFIG__", json.dumps(cfg)).replace("<!--__EMBED__-->", embed)
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
open(a.out, "w").write(t)
print(f"wrote {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB, " +
      ("embedded data" if a.embed else f"tiles {a.tiles}, shards {a.shards}, data {a.data}") +
      f", maps key {'set' if a.key else 'not set'})")
