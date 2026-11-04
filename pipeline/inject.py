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
          memory). Practical up to a few hundred thousand parcels, e.g. a --bbox build of a submarket; the full
          county is far too large for one file.

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
    if len(records) > 400_000:
        print(f"warning: {len(records):,} accounts; the file will be very large and slow to open. Use a --bbox build.")
    bounds = {os.path.splitext(os.path.basename(f))[0]: json.load(open(f))
              for f in glob.glob(os.path.join(o, "web", "data", "boundaries", "*.json"))}
    bundle = {"combos": json.load(open(os.path.join(o, "web", "data", "combos.json"))),
              "boundaries": bounds, "records": records}
    data_b64 = base64.b64encode(gzip.compress(json.dumps(bundle, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(), 9)).decode()
    tiles_b64 = base64.b64encode(open(os.path.join(o, "bucket", "harris_parcels.pmtiles"), "rb").read()).decode()
    embed = (f'<script id="emb-data" type="application/octet-stream">{data_b64}</script>\n'
             f'<script id="emb-tiles" type="application/octet-stream">{tiles_b64}</script>')
    cfg.update({"embed": True, "tiles": "", "shards": "", "data": ""})
    print(f"embedded {len(records):,} account records, {len(bounds)} boundary layers, "
          f"{len(tiles_b64) * 3 // 4 / 1e6:.1f} MB of tiles")
t = t.replace("__MARK__", mark).replace("__CONFIG__", json.dumps(cfg)).replace("<!--__EMBED__-->", embed)
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
open(a.out, "w").write(t)
print(f"wrote {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB, " +
      ("embedded data" if a.embed else f"tiles {a.tiles}, shards {a.shards}, data {a.data}") +
      f", maps key {'set' if a.key else 'not set'})")
