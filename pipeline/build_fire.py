"""
Fire stations in and around the 8 counties.

  python build_fire.py --raw layers_raw --out out
      -> out/web/data/layers/fire.json

Sources:
  Houston Fire Department stations: City of Houston (COH_Houston_Fire_Stations_view), with ladder trucks
  Everything else: HIFLD / USGS National Structures Dataset "Fire and Emergency Medical Service (EMS) Stations"
    (a hosted copy on services3.arcgis.com; the federal HIFLD Open site closed in 2025), loaded 2020-2022:
    city departments, emergency services districts and volunteer departments. HFD stations in it are replaced by
    the city's list; any other station within 150 m of a kept one is a duplicate.
Stations in neighboring counties are kept, so sites near a county line find their closest station.

Properties: n name, a address, c city, l 1 if HFD lists a ladder truck, s source (hfd | hifld)
"""
import argparse, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
from build_layers import fetch

HFD = "https://services.arcgis.com/NummVBqZSIJKUeVR/arcgis/rest/services/COH_Houston_Fire_Stations_view/FeatureServer/10"
HIFLD = ("https://services3.arcgis.com/v4Q3kjlmXMUBAQtv/arcgis/rest/services/"
         "Fire_and_Emergency_Medical_Service_(EMS)_Stations_(1)/FeatureServer/0")


def tc(s):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s.title() if s.isupper() else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    ph, pf = os.path.join(a.raw, "fire_hfd.geojson"), os.path.join(a.raw, "fire_hifld.geojson")
    if not os.path.exists(ph):
        fetch(HFD, "LABEL,ADDRESS,LADDERS", ph)
    if not os.path.exists(pf):
        fetch(HIFLD, "NAME,ADDRESS,CITY,COUNTY", pf)

    pts = []
    for f in json.load(open(ph))["features"]:
        p, (x, y) = f["properties"], f["geometry"]["coordinates"][:2]
        pts.append({"n": f"Houston Fire Department Station {p['LABEL']}", "a": tc(p.get("ADDRESS")), "c": "Houston",
                    "l": 1 if (p.get("LADDERS") or "").upper().startswith("Y") else 0, "s": "hfd", "xy": (x, y)})
    nh = len(pts); dup = hfd_skip = 0
    for f in json.load(open(pf))["features"]:
        p, (x, y) = f["properties"], f["geometry"]["coordinates"][:2]
        if re.match(r"Houston Fire Department", p.get("NAME") or "", re.I):
            hfd_skip += 1; continue
        if any(abs(q["xy"][0] - x) < .0016 and abs(q["xy"][1] - y) < .0014 for q in pts):
            dup += 1; continue
        pts.append({"n": tc(p.get("NAME")), "a": tc(p.get("ADDRESS")), "c": tc(p.get("CITY")), "l": 0, "s": "hifld", "xy": (x, y)})
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(q["xy"][0], 5), round(q["xy"][1], 5)]},
              "properties": {k: v for k, v in q.items() if k != "xy" and v not in ("", None)}} for q in pts]
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "fire.json")
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"), separators=(",", ":"))
    print(f"{len(feats)} stations: {nh} HFD (city list), {len(feats) - nh} others; replaced {hfd_skip} HFD entries "
          f"from HIFLD, dropped {dup} duplicates -> {out}")


if __name__ == "__main__":
    main()
