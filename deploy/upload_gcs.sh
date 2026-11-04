#!/usr/bin/env bash
# Uploads the tiles and shards to a Google Cloud Storage bucket (a Firebase Storage bucket works too:
# it is a GCS bucket, usually named <project>.appspot.com or <project>.firebasestorage.app).
#
#   deploy/upload_gcs.sh gs://YOUR-BUCKET out
#
# Then build the page with:
#   python pipeline/inject.py --key "$GMAPS_KEY" \
#     --tiles  https://storage.googleapis.com/YOUR-BUCKET/taxmap/harris_parcels.pmtiles \
#     --shards https://storage.googleapis.com/YOUR-BUCKET/taxmap/shards/ \
#     --data data/ --out out/web/index.html
set -euo pipefail
BUCKET="${1:?gs://bucket}"; OUT="${2:-out}"; HERE="$(cd "$(dirname "$0")" && pwd)"

# CORS: edit deploy/cors.json to list the Netlify domain first
gsutil cors set "$HERE/cors.json" "$BUCKET"
# public read (skip if the bucket already allows it)
gsutil iam ch allUsers:objectViewer "$BUCKET"

# PMTiles: never gzip-transcode, the browser reads byte ranges of the raw file
gsutil -h "Cache-Control:public, max-age=3600" -h "Content-Type:application/octet-stream" \
  cp "$OUT/bucket/harris_parcels.pmtiles" "$BUCKET/taxmap/harris_parcels.pmtiles"

# Shards: tens of thousands of small JSON files, stored gzipped and served with Content-Encoding: gzip
gsutil -m -h "Cache-Control:public, max-age=3600" -h "Content-Type:application/json" \
  cp -r -z json "$OUT/bucket/shards" "$BUCKET/taxmap/"

# Check: a range request must return 206
URL="https://storage.googleapis.com/${BUCKET#gs://}/taxmap/harris_parcels.pmtiles"
code=$(curl -s -o /dev/null -w "%{http_code}" -r 0-127 "$URL")
echo "range request on $URL -> $code (want 206)"
