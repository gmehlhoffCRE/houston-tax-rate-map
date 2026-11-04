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
"""
import argparse, json, os

here = os.path.dirname(os.path.abspath(__file__))
web = os.path.join(here, "..", "web")
ap = argparse.ArgumentParser()
ap.add_argument("--key", default=os.environ.get("GMAPS_KEY", ""))
ap.add_argument("--tiles", default="harris_parcels.pmtiles")
ap.add_argument("--shards", default="shards/")
ap.add_argument("--data", default="data/")
ap.add_argument("--out", default="index.html")
a = ap.parse_args()

t = open(os.path.join(web, "tax-rate-map-template.html")).read()
mark = open(os.path.join(web, "cresa_mark.svg")).read().replace(
    'width="118" height="21"', 'width="112" height="20" aria-label="Cresa" style="display:block;flex-shrink:0"')
cfg = {"gkey": a.key or "__NO_KEY__", "tiles": a.tiles, "shards": a.shards, "data": a.data}
t = t.replace("__MARK__", mark).replace("__CONFIG__", json.dumps(cfg))
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
open(a.out, "w").write(t)
print(f"wrote {a.out} (tiles {a.tiles}, shards {a.shards}, data {a.data}, maps key {'set' if a.key else 'not set'})")
