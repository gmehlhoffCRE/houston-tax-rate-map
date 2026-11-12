"""
Regional boundary overlays: complete outlines for the whole 8-county area, replacing the Harris-only HCAD lines
that build_county_data.py writes (those stop at the Harris County line, so districts that cross it show open).

  python build_boundaries.py --gis hcad_gis --raw layers_raw --out OUT
      -> OUT/web/data/boundaries/{isd,city,water,esd,special,tirz}.json   (same format the page already reads)

  isd      Texas Education Agency school districts, school year 2025-26 (statewide layer)
  city     TxDOT city boundaries (statewide)
  water    TCEQ water districts, active: MUD, WCID, FWSD, SUD, LID, WID (statewide)
  esd      HCAD emergency services districts (Harris) + FBCAD (Fort Bend) + Montgomery County ESDs
  special  HCAD special (management and industrial) districts + TCEQ municipal management districts outside Harris
  tirz     HCAD TIRZ (Harris) + FBCAD TIRZ (Fort Bend)

Every district that touches the 8 counties is kept whole (outlines are not cut at county lines). Each feature is
the district's outline plus a label point. Hosts: services.arcgis.com, services1/2.arcgis.com,
gisweb.tceq.texas.gov.
"""
import argparse, json, os, sys
import geopandas as gpd, numpy as np, pandas as pd, pyogrio, shapely

sys.path.insert(0, os.path.dirname(__file__))
from build_layers import fetch
from build_county_data import find_source

BBOX = (-96.45, 28.75, -94.35, 30.65)
COUNTIES = ["Harris", "Fort Bend", "Montgomery", "Waller", "Chambers", "Brazoria", "Liberty", "Galveston"]
SRC = {
    "tea": ("https://services2.arcgis.com/5MVN2jsqIrNZD4tP/arcgis/rest/services/School_Districts__2026/FeatureServer/0", "NAME"),
    "txdot_city": ("https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/TxDOT_City_Boundaries/FeatureServer/0", "CITY_NM"),
    "tceq_wd": ("https://gisweb.tceq.texas.gov/arcgis/rest/services/Public/WaterDistricts/MapServer/0", "NAME,TYPE,STATUS"),
    "fb_esd": ("https://services2.arcgis.com/D4saGHECICkCeoJm/arcgis/rest/services/ESD_Districts_view/FeatureServer/0", "ESDName"),
    "mc_esd": ("https://services1.arcgis.com/PRoAPGnMSUqvTrzq/arcgis/rest/services/EmergencyServiceDistrict/FeatureServer/0", "ESD_NAME"),
    "fb_tirz": ("https://services2.arcgis.com/D4saGHECICkCeoJm/arcgis/rest/services/TIRZ_Districts_view/FeatureServer/0", "TIRZName"),
}
WATER_TYPES = {"MUD", "WCID", "FWSD", "SUD", "LID", "WID"}


def raw(a, key):
    p = os.path.join(a.raw, "bnd_" + key + ".geojson")
    if not os.path.exists(p):
        n = fetch(SRC[key][0], SRC[key][1], p, page=1000 if "MapServer" in SRC[key][0] else 2000)
        print(f"fetched {key}: {n:,}", flush=True)
    g = gpd.read_file(p)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].set_crs(4326, allow_override=True)
    g["geometry"] = g.geometry.make_valid()
    return g


def hcad(a, name):
    src = find_source(a.gis, name)
    if not src:
        print(f"HCAD {name}: no source in {a.gis}", flush=True)
        return gpd.GeoDataFrame({"name": []}, geometry=[], crs=4326)
    o = pyogrio.read_dataframe(src, force_2d=True)
    ncol = next(c for c in o.columns if c.lower() == "name")
    o = o[[ncol, "geometry"]].rename(columns={ncol: "name"})
    o = o[o.geometry.notna()]
    if o.crs is None:
        o = o.set_crs(2278)
    o["geometry"] = o.geometry.buffer(0)
    o = o.to_crs(4326)
    o["name"] = o["name"].astype(str).str.replace(r"\s*\(\d{3}\)", "", regex=True).str.strip()
    return o


def tidy(s):
    s = s.fillna("").astype(str).str.strip()
    return s.where(s.str.upper() != s, s.str.title()).str.replace(r"\bIsd\b", "ISD", regex=True)\
        .str.replace(r"\bMud\b", "MUD", regex=True).str.replace(r"\bEsd\b", "ESD", regex=True)\
        .str.replace(r"\bWcid\b", "WCID", regex=True).str.replace(r"\bFwsd\b", "FWSD", regex=True)\
        .str.replace(r"\bTirz\b", "TIRZ", regex=True).str.replace(r"\bNo\b", "No.", regex=True)


def write(g, region, path):
    """Dissolve by name, keep areas touching the region, write outline + label point."""
    g = g[g.name.fillna("").str.strip() != ""]
    g = gpd.GeoDataFrame(g[["name", "geometry"]], crs=4326)
    m = g.to_crs(2278)
    m["geometry"] = m.geometry.buffer(0).simplify(15)
    g = m.to_crs(4326).dissolve(by="name", as_index=False)
    g = g[g.intersects(region)]
    feats = []
    for _, r in g.iterrows():
        geom = r.geometry
        if geom is None or geom.is_empty:
            continue
        inside = geom.intersection(region)   # label inside the 8 counties when the district reaches outside them
        lp = (inside if not inside.is_empty else geom).representative_point()
        line = shapely.transform(geom.boundary, lambda c: np.round(c, 5))
        feats.append({"type": "Feature", "properties": {"name": r["name"], "lp": [round(lp.x, 5), round(lp.y, 5)]},
                      "geometry": json.loads(shapely.to_geojson(line))})
    json.dump({"type": "FeatureCollection", "features": feats}, open(path, "w"), separators=(",", ":"))
    print(f"{os.path.basename(path):<14}{len(feats):>5} areas  {os.path.getsize(path) / 1e6:.2f} MB", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gis", required=True, help="HCAD GIS download folder (as for build_county_data.py --gis)")
    ap.add_argument("--raw", default="layers_raw", help="cache of downloads (land.geojson from build_drive_grid.py)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    od = os.path.join(a.out, "web", "data", "boundaries"); os.makedirs(od, exist_ok=True)
    land = gpd.read_file(os.path.join(a.raw, "land.geojson"))
    cty = land[(land.STATE_ABBR == "TX") & land.NAME.str.replace(" County", "").isin(COUNTIES)]
    region = shapely.make_valid(cty.geometry.union_all())
    harris = shapely.make_valid(cty[cty.NAME.str.startswith("Harris")].geometry.union_all())
    print(f"region: {len(cty)} counties", flush=True)

    g = raw(a, "tea"); g["name"] = g.NAME
    write(g, region, os.path.join(od, "isd.json"))
    g = raw(a, "txdot_city"); g["name"] = g.CITY_NM.str.replace(r"^(?!City of )", "City of ", regex=True)
    write(g, region, os.path.join(od, "city.json"))
    w = raw(a, "tceq_wd")
    act = w.STATUS.fillna("").str.strip().str.upper() == "A"
    g = w[act & w.TYPE.isin(WATER_TYPES)].copy(); g["name"] = tidy(g.NAME)
    write(g, region, os.path.join(od, "water.json"))
    h = hcad(a, "Emergency")
    fb = raw(a, "fb_esd"); fb["name"] = tidy(fb.ESDName)
    mc = raw(a, "mc_esd"); mc["name"] = "Montgomery County " + tidy(mc.ESD_NAME)
    write(pd.concat([h, fb[["name", "geometry"]], mc[["name", "geometry"]]]), region, os.path.join(od, "esd.json"))
    h = hcad(a, "Special")
    mmd = w[act & (w.TYPE == "MMD")].copy(); mmd["name"] = tidy(mmd.NAME)
    mmd = mmd[~mmd.representative_point().within(harris)]
    write(pd.concat([h, mmd[["name", "geometry"]]]), region, os.path.join(od, "special.json"))
    h = hcad(a, "TIRZ")
    fb = raw(a, "fb_tirz"); fb["name"] = "Fort Bend " + tidy(fb.TIRZName)
    write(pd.concat([h, fb[["name", "geometry"]]]), region, os.path.join(od, "tirz.json"))


if __name__ == "__main__":
    main()
