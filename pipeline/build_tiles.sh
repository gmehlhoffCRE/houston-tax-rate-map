#!/usr/bin/env bash
# Builds the parcel PMTiles from build_county_data.py output.
#
#   ./build_tiles.sh out            # reads out/parcels.geojsonl, writes out/bucket/harris_parcels.pmtiles
#
# Needs tippecanoe 2.17 or later (PMTiles support): `brew install tippecanoe` on a Mac,
# or `pip install tippecanoe` (bundles felt/tippecanoe binaries), plus `pip install pmtiles`
# for the merge step (merge_pmtiles.py; the zoom ranges do not overlap, so tile-join is not needed).
#
# Two layers in one archive. The page draws 512 px tiles, so tile zoom z is shown at Google zoom z+1.
#   zones    tile z7-12  (Google zoom 8-13)   combo id + type group only; parcels dissolved into block-sized
#                                             shapes by build_zones.py, so the county view stays light
#   parcels  tile z13-16 (Google zoom 14+)    one feature per parcel: a acct, c combo, t type, v value.
#                                             Never dropped or merged; z16 is overzoomed past Google zoom 17
set -euo pipefail
OUT="${1:-out}"
SRC="$OUT/parcels.geojsonl"
DST="$OUT/bucket/harris_parcels.pmtiles"
TMP="$OUT/tiles_tmp"
mkdir -p "$TMP" "$OUT/bucket"

# zones: parcels dissolved by combo and type first (build_zones.py), then tiled
python "$(dirname "$0")/build_zones.py" "$SRC" "$TMP/zones.geojsonl"
tippecanoe -o "$TMP/zones.pmtiles" --force -P -l zones -Z7 -z12 \
  -y c -y t --reorder --coalesce --detect-shared-borders \
  --simplification=4 --coalesce-densest-as-needed \
  "$TMP/zones.geojsonl"

tippecanoe -o "$TMP/parcels.pmtiles" --force -P -l parcels -Z13 -z16 \
  -y a -y c -y t -y v --detect-shared-borders \
  --no-tiny-polygon-reduction --no-feature-limit --maximum-tile-bytes=2500000 \
  "$SRC"

python "$(dirname "$0")/merge_pmtiles.py" "$DST" "$TMP/zones.pmtiles" "$TMP/parcels.pmtiles" \
  --name "Harris County parcels" --description "Parcels with tax rate combo, Cresa Houston"

rm -rf "$TMP"
ls -lh "$DST"
