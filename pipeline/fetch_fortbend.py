"""
Downloads Fort Bend CAD public parcel data (shapes + owner, address, value, state code, taxing units)
from FBCAD's ArcGIS server, and the FBCAD tax rate sheet.

  python fetch_fortbend.py --out fortbend
      -> fortbend/fb_parcels_raw.geojsonl   one GeoJSON feature per line, WGS84
      -> fortbend/fb_rates.xls             FBCAD rate sheet (code, description, type, rates)

Source layer: https://gisweb.fbcad.org/arcgis/rest/services/Hosted/FBCADPublicData/FeatureServer/0
Rate sheets: https://www.fbcad.org/tax-rates/ (newest posted as of Nov 2026: 2024 rates, Feb 2025 file).
Pass --rates-url to use a newer sheet when FBCAD posts one.
"""
import argparse, json, os, time, urllib.parse, urllib.request

LAYER = "https://gisweb.fbcad.org/arcgis/rest/services/Hosted/FBCADPublicData/FeatureServer/0"
RATES = "https://www.fbcad.org/wp-content/uploads/2025/02/2024-TaxRate-Feb.xls"
FIELDS = ["objectid", "quickrefid", "propnumber", "ownername", "situs", "totalvalue", "landvalue", "impvalue",
          "totsqftlvg", "landsizeft", "landsizeac", "taxunits", "exemptions", "land_state_code",
          "building_sptb_code", "building_class", "yearbuilt"]


def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "tax-rate-map-pipeline"}),
                                        timeout=120) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
            print(f"  retry after {e}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="fortbend")
    ap.add_argument("--rates-url", default=RATES)
    ap.add_argument("--page", type=int, default=2000)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    with open(os.path.join(a.out, "fb_rates.xls"), "wb") as f:
        f.write(get(a.rates_url))
    total = json.loads(get(LAYER + "/query?where=1%3D1&returnCountOnly=true&f=json"))["count"]
    print(f"{total:,} parcels to fetch", flush=True)

    last, n = -1, 0
    with open(os.path.join(a.out, "fb_parcels_raw.geojsonl"), "w") as fo:
        while True:   # page by objectid: steadier than offsets on a large layer
            q = urllib.parse.urlencode({"where": f"objectid>{last}", "outFields": ",".join(FIELDS),
                                        "orderByFields": "objectid", "resultRecordCount": a.page,
                                        "outSR": 4326, "geometryPrecision": 6, "f": "geojson"})
            feats = json.loads(get(f"{LAYER}/query?{q}")).get("features", [])
            if not feats:
                break
            for ft in feats:
                fo.write(json.dumps(ft, separators=(",", ":")) + "\n")
            n += len(feats)
            last = max(ft["properties"]["objectid"] for ft in feats)
            if n % 40000 < a.page:
                print(f"  {n:,}/{total:,}", flush=True)
    print(f"{n:,} parcels written", flush=True)


if __name__ == "__main__":
    main()
