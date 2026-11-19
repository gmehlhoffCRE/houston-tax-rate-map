"""
Houston business crime heat map from Houston Police Department NIBRS incidents.

  python build_crime.py --hpd raw/hpd --raw layers_raw --out out
      -> out/web/data/layers/crime.json

Input: HPD_NIBRS_Yearly_Cases (City of Houston open data, services.arcgis.com), one layer per year, saved by
raw/hpd/fetch.py as hpd_<year>.jsonl. Houston PD covers the City of Houston only; the city limit (COH_City_Limit_view)
is drawn as the edge of the data, and the map says "no incident data" outside it.

Counts are averaged over the years present, per cell of a 1/4-mile grid:
  b   business crime: property offenses (burglary, theft, theft from or of vehicles and parts, vandalism, robbery,
      arson, trespass) at commercial, office, industrial, construction, storage, freight, dealership and parking sites
  a   all reported offenses, any premise
Output (compact grid): {x0, y0, dx, dy, years, cells: [[i, j, b, a], ...], dens: {b, a} per sq mi citywide,
                        sqmi, limit: city limit polygon}
"""
import argparse, glob, json, math, os, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from build_layers import fetch, load, simplify

LIMIT = "https://services.arcgis.com/NummVBqZSIJKUeVR/arcgis/rest/services/COH_City_Limit_view/FeatureServer/0"
OFFENSES = {"Burglary, Breaking and Entering", "Theft from motor vehicle", "Motor vehicle theft",
            "Theft of motor vehicle parts or accessory", "Destruction, damage, vandalism", "All other larceny",
            "Theft from building", "Robbery", "Arson", "Trespass of real property", "Stolen property offenses"}
PREMISES = {"Parking Lot, Garage", "Commercial, Office Building", "Industrial Site", "Construction Site",
            "Rental Storage Facility", "Dock/Wharf/Freight/Modal Terminal", "Auto Dealership New/Used",
            "Abandoned/Condemned Structure", "Field, Woods", "Rest Area"}
DY = 0.25 / 69.05                                  # 1/4 mile
DX = 0.25 / (69.17 * math.cos(math.radians(29.8)))
X0, Y0 = -95.95, 29.45


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hpd", default="raw/hpd")
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.hpd, "hpd_*.jsonl")))
    years = [int(os.path.basename(f)[4:8]) for f in files]
    cb, ca = defaultdict(float), defaultdict(float)
    nb = na = 0
    for f in files:
        for ln in open(f):
            r = json.loads(ln)
            x, y = r.get("Longitude"), r.get("Latitude")
            if not x or not y or not (-96.2 < x < -94.8 and 29.3 < y < 30.3):
                continue
            k = (int((x - X0) / DX), int((y - Y0) / DY)); n = r.get("HPD_Offense_Count") or 1
            ca[k] += n; na += n
            if r.get("HPD_NIBRSDescription") in OFFENSES and r.get("HPD_Premise") in PREMISES:
                cb[k] += n; nb += n
    ny = len(files)
    cells = [[i, j, round(cb.get((i, j), 0) / ny, 1), round(ca[(i, j)] / ny, 1)] for (i, j) in ca]

    p = os.path.join(a.raw, "houston_limit.geojson")
    if not os.path.exists(p):
        fetch(LIMIT, "OBJECTID_1", p)
    g = load(a.raw, "houston_limit")
    sqmi = float(g.to_crs(2278).area.sum() / 5280 ** 2)
    lim = json.loads(simplify(g.dissolve(), 30).geometry.to_json())["features"][0]["geometry"]
    def rnd(c):
        return [rnd(v) for v in c] if isinstance(c[0], list) else [round(c[0], 5), round(c[1], 5)]
    lim["coordinates"] = rnd(lim["coordinates"])

    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "crime.json")
    json.dump({"x0": X0, "y0": Y0, "dx": round(DX, 7), "dy": round(DY, 7), "years": years, "cells": cells,
               "dens": {"b": round(nb / ny / sqmi, 2), "a": round(na / ny / sqmi, 2)}, "sqmi": round(sqmi),
               "limit": lim}, open(out, "w"), separators=(",", ":"))
    print(f"{years}: {na:,.0f} offenses, {nb:,.0f} business ({nb / na:.1%}); {len(cells):,} cells; "
          f"city {sqmi:,.0f} sq mi; per sq mi a year: business {nb / ny / sqmi:.1f}, all {na / ny / sqmi:.1f}; "
          f"{os.path.getsize(out) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
