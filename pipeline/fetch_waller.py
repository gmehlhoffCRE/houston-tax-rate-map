"""
Downloads the Waller County inputs into one folder.

  python fetch_waller.py --out waller
      -> waller/wc_parcels_raw.geojsonl   Waller CAD parcels (BIS public layer): owner, situs, values, school/city codes
      -> waller/wc_county.geojson         county outline (same service)
      -> waller/wc_tceq_districts.geojson TCEQ water and special districts that touch the county (MUD, WCID, MMD, DD...)
      -> waller/wc_bkdd.geojson           Brookshire-Katy Drainage District (Waller County GIS)

Waller CAD's parcel layer carries only the school, city and county codes. Every other taxing unit (MUDs, WCIDs,
management and road districts, drainage) is assigned by overlaying these district polygons in
build_waller_rates.py, as listed in data/waller/wc_district_map.csv.

Hosts: services3.arcgis.com (Waller CAD), services1.arcgis.com (Waller County GIS), gisweb.tceq.texas.gov (TCEQ).
"""
import argparse, json, os, urllib.parse

from fetch_fortbend import get

CAD = "https://services3.arcgis.com/KKhSlBnH1Rm0YK62/arcgis/rest/services/WallerCADWebService/FeatureServer"
TCEQ = "https://gisweb.tceq.texas.gov/arcgis/rest/services/Public/WaterDistricts/MapServer/0"
BKDD = ("https://services1.arcgis.com/BqVKz0o32DERqyE4/arcgis/rest/services/"
        "Brookshire_Katy_Drainage_District1/FeatureServer/54")
FIELDS = ["ObjectID_1", "prop_id", "file_as_name", "legal_acreage", "hood_cd", "school", "city", "county",
          "legal_desc", "land_val", "imprv_val", "market", "geo_id", "situs_num", "situs_street_prefx",
          "situs_street", "situs_street_sufix", "situs_city", "situs_zip"]


def query(layer, **kw):
    q = {"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson"}
    q.update(kw)
    return json.loads(get(f"{layer}/query?{urllib.parse.urlencode(q)}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="waller")
    ap.add_argument("--page", type=int, default=2000)
    ap.add_argument("--skip-parcels", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    w = lambda name, obj: json.dump(obj, open(os.path.join(a.out, name), "w"))

    county = query(f"{CAD}/8")
    w("wc_county.geojson", county)
    xs, ys = zip(*[pt for ring in county["features"][0]["geometry"]["coordinates"]
                   for part in ([ring] if isinstance(ring[0][0], float) else ring) for pt in part])
    bbox = f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"

    feats, off = [], 0
    while True:   # TCEQ caps pages; the bbox catches a few districts outside the county, which the overlay ignores
        g = query(TCEQ, geometry=bbox, geometryType="esriGeometryEnvelope", inSR=4326,
                  spatialRel="esriSpatialRelIntersects", outFields="NAME,DISTRICT_ID,TYPE,COUNTY,STATUS,UPDATED",
                  resultOffset=off, resultRecordCount=500)
        feats += g["features"]; off += len(g["features"])
        if len(g["features"]) < 500:
            break
    w("wc_tceq_districts.geojson", {"type": "FeatureCollection", "features": feats})
    print(f"{len(feats)} TCEQ districts in the county's box", flush=True)
    w("wc_bkdd.geojson", query(BKDD))

    if not a.skip_parcels:
        import subprocess, sys
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "fetch_fortbend.py"),
                        "--out", a.out, "--prefix", "wc", "--no-rates", "--oid", "ObjectID_1",
                        "--page", str(a.page), "--fields", ",".join(FIELDS), "--layer", f"{CAD}/0"], check=True)


if __name__ == "__main__":
    main()
