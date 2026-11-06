"""
Downloads the Liberty County inputs into one folder.

  python fetch_liberty.py --out liberty
      -> liberty/lc_parcels_raw.geojsonl     Liberty CAD parcels (BIS public layer): owner, situs, values,
                                             school / city / county codes
      -> liberty/lc_county.geojson           county outline
      -> liberty/lc_special_districts.geojson  CAD layer with hospital, water, drainage, ESD and navigation
                                             districts; the CAD code is in parentheses, e.g. "WATER DIST 5 (WD5)"
      -> liberty/lc_tceq_districts.geojson   TCEQ water and special districts in the county's box (MUDs, MMDs, ID)

build_liberty_rates.py assigns the units that are not on the parcel by overlaying these polygons, as listed in
data/liberty/lc_units_2025.csv. Hosts: services3.arcgis.com (Liberty CAD), gisweb.tceq.texas.gov (TCEQ).
"""
import argparse, json, os, subprocess, sys, urllib.parse

from fetch_fortbend import get

CAD = "https://services3.arcgis.com/LbQai106UcFy2LlR/arcgis/rest/services/LibertyCADWebService/FeatureServer"
EXTRA = "https://services3.arcgis.com/LbQai106UcFy2LlR/arcgis/rest/services/LibertyCADWebService_AdditionalLayers/FeatureServer"
TCEQ = "https://gisweb.tceq.texas.gov/arcgis/rest/services/Public/WaterDistricts/MapServer/0"
FIELDS = ["ObjectID_1", "prop_id", "file_as_name", "legal_acreage", "school", "city", "county", "legal_desc",
          "market", "geo_id", "situs_num", "situs_street_prefx", "situs_street", "situs_street_sufix", "situs_city"]


def query(layer, **kw):
    q = {"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson"}
    q.update(kw)
    return json.loads(get(f"{layer}/query?{urllib.parse.urlencode(q)}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="liberty")
    ap.add_argument("--skip-parcels", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    w = lambda name, obj: json.dump(obj, open(os.path.join(a.out, name), "w"))

    county = query(f"{CAD}/7")
    w("lc_county.geojson", county)
    pts = []
    def collect(c):
        if isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                collect(x)
    for f in county["features"]:
        collect(f["geometry"]["coordinates"])
    xs, ys = zip(*[(p[0], p[1]) for p in pts])
    bbox = f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"

    w("lc_special_districts.geojson", query(f"{EXTRA}/7"))
    feats, off = [], 0
    while True:
        g = query(TCEQ, geometry=bbox, geometryType="esriGeometryEnvelope", inSR=4326,
                  spatialRel="esriSpatialRelIntersects", outFields="NAME,DISTRICT_ID,TYPE,COUNTY,STATUS,UPDATED",
                  resultOffset=off, resultRecordCount=500)
        feats += g["features"]; off += len(g["features"])
        if len(g["features"]) < 500:
            break
    w("lc_tceq_districts.geojson", {"type": "FeatureCollection", "features": feats})
    print(f"{len(feats)} TCEQ districts in the county's box", flush=True)

    if not a.skip_parcels:
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "fetch_fortbend.py"),
                        "--out", a.out, "--prefix", "lc", "--no-rates", "--oid", "ObjectID_1",
                        "--fields", ",".join(FIELDS), "--layer", f"{CAD}/0"], check=True)


if __name__ == "__main__":
    main()
