#!/usr/bin/env bash
# End-to-end test on the Ship Channel fixture (48,686 parcels from the prototype), no HCAD downloads needed.
#
#   tests/run_fixture_test.sh <proto_data.json> <work dir> [cdn map json]
#
# proto_data.json is the data blob embedded in the prototype tax-rate-map.html (<script id="data">).
# Needs: python with geopandas pyogrio pyproj shapely pandas pmtiles tippecanoe, node with playwright.
# GMAPS_KEY (optional) exercises the Google basemap; without it the page uses the Esri fallback.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/.."
PROTO="$1"; WORK="$2"; CDN="${3:-}"
mkdir -p "$WORK"; cd "$WORK"
python "$HERE/make_fixture.py" "$PROTO" --combos "$ROOT/data/hcad_combos.csv" --out fixture
python "$ROOT/pipeline/build_county_data.py" --gis fixture/gis --parcels fixture/gis/Parcels.gpkg \
  --cama fixture/cama/real_acct.txt --rates "$ROOT/data" --out out --bbox -95.25 29.665 -95.10 29.77
"$ROOT/pipeline/build_tiles.sh" out 2>&1 | tr '\r' '\n' | grep -E "features|tiles|pmtiles" || true
python "$ROOT/pipeline/inject.py" --key "${GMAPS_KEY:-}" --tiles /bucket/harris_parcels.pmtiles \
  --shards /bucket/shards/ --data data/ --out out/web/index.html
node "$HERE/serve.js" out 8090 & SERVER=$!; trap 'kill $SERVER' EXIT; sleep 1
mkdir -p shots
node "$HERE/e2e.js" http://localhost:8090/web/index.html shots $CDN
