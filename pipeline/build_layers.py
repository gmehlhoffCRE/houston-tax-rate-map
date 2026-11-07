"""
Industrial context layers for the map: fetched from public ArcGIS services, clipped to the 8-county region,
simplified, and written as compact GeoJSON the page draws as toggles.

  python build_layers.py --raw layers_raw --out out
      -> out/web/data/layers/<key>.json   (inject.py --embed packs them into the folder build)

Layers (key: source)
  rail        US DOT BTS North American Rail Network lines (owner, track rights, Class I / short line)
  intermodal  US DOT BTS intermodal rail TOFC/COFC terminals (railroad)
  flood       FEMA flood hazard areas (Esri USA Flood Hazard Reduced Set): 100-year (A, AE, AO, AH, VE) and
              floodway, 500-year (X shaded); simplified to about 15 m
  pipelines   Texas Railroad Commission pipelines (operator, commodity, diameter, status)
  power       HIFLD electric power transmission lines (voltage, owner), Esri federal copy
  substations HIFLD substations (max voltage); a public copy, the federal HIFLD Open portal closed in 2025
  water_ccn   Texas PUC water CCN service areas (utility name)
  sewer_ccn   Texas PUC sewer CCN service areas (utility name)
  aadt        TxDOT annual average daily traffic count stations (latest year and count)
  ftz         Foreign-Trade Zone grantee locations (International Trade Administration list; points, not sites)
  ports       Ports (US DOT BTS, Army Corps list) and airports (FAA facilities, public use only)

Raw downloads are cached in --raw; delete a file there to refetch it.
Hosts: services.arcgis.com, services2.arcgis.com, services6.arcgis.com, gis.rrc.texas.gov.
"""
import argparse, json, os, sys, time, urllib.parse
import geopandas as gpd, pandas as pd, shapely

sys.path.insert(0, os.path.dirname(__file__))
from fetch_fortbend import get

BBOX = (-96.45, 28.75, -94.35, 30.65)   # Harris, Fort Bend, Montgomery, Waller, Chambers, Brazoria, Liberty, Galveston
AGO = "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services"
SOURCES = {
    "rail": (f"{AGO}/NTAD_North_American_Rail_Network_Lines/FeatureServer/0",
             "RROWNER1,RROWNER2,TRKRGHTS1,TRKRGHTS2,TRKRGHTS3,NET,PASSNGR,SUBDIV,YARDNAME,TRACKS,MILES"),
    "intermodal": (f"{AGO}/NTAD_Intermodal_Freight_Facilities_Rail_TOFC_COFC/FeatureServer/0", "TERMINAL,RAIL_CO,CITY,PORT"),
    "flood": ("https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Flood_Hazard_Reduced_Set_gdb/FeatureServer/0",
              "FLD_ZONE,ZONE_SUBTY,SFHA_TF"),
    "pipelines": ("https://gis.rrc.texas.gov/server/rest/services/rrc_public/RRC_Public_Viewer_Srvs/MapServer/13",
                  "OPERATOR,COMMODITY_DESCRIPTION,DIAMETER,SYSTEM_NAME,STATUS,INTERSTATE"),
    "power": ("https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/US_Electric_Power_Transmission_Lines/FeatureServer/0",
              "OWNER,VOLTAGE,VOLT_CLASS,STATUS,SUB_1,SUB_2"),
    "substations": ("https://services6.arcgis.com/OO2s4OoyCZkYJ6oE/arcgis/rest/services/Substations/FeatureServer/0",
                    "NAME,CITY,STATUS,MAX_VOLT,LINES"),
    "water_ccn": ("https://services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/Water_CCN_Service_Areas/FeatureServer/210", "*"),
    "sewer_ccn": ("https://services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/Sewer_CCN_Service_Areas/FeatureServer/230", "*"),
    "aadt": ("https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/TxDOT_AADT_Annuals_(Public_View)/FeatureServer/0",
             "TRFC_STATN_ID,AADT_RPT_YEAR,AADT_RPT_QTY,ACTIVE,CNTY_NM"),
    "ftz": ("https://services6.arcgis.com/BAJNi3EgCdtQ1BCG/arcgis/rest/services/FTZ_2023/FeatureServer/0", "Zone,Grantee,Location"),
    "ports_raw": (f"{AGO}/Petroleum_Ports/FeatureServer/0", "NAME,OPERATOR"),
    "airports_raw": (f"{AGO}/NTAD_Aviation_Facilities/FeatureServer/0",
                     "ARPT_ID,ARPT_NAME,CITY,SITE_TYPE_CODE,FACILITY_USE_CODE,OWNERSHIP_TYPE_CODE"),
}


def fetch(url, fields, path, page=1000):
    """Pages an ArcGIS layer (bbox filter) to a GeoJSON FeatureCollection file."""
    feats, off = [], 0
    while True:
        q = {"where": "1=1", "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope",
             "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "outSR": 4326,
             "resultOffset": off, "resultRecordCount": page, "f": "geojson"}
        d = json.loads(get(f"{url}/query?{urllib.parse.urlencode(q)}"))
        fs = d.get("features", [])
        feats += fs; off += len(fs)
        if not fs or (len(fs) < page and not d.get("properties", {}).get("exceededTransferLimit")
                      and not d.get("exceededTransferLimit")):
            break
    json.dump({"type": "FeatureCollection", "features": feats}, open(path, "w"))
    return len(feats)


def load(raw, key):
    g = gpd.read_file(os.path.join(raw, key + ".geojson"))
    g = g[g.geometry.notna() & ~g.geometry.is_empty].set_crs(4326, allow_override=True)
    g["geometry"] = g.geometry.make_valid()
    return g


def simplify(g, meters):
    m = g.to_crs(2278)
    m["geometry"] = m.geometry.simplify(meters * 3.2808, preserve_topology=True)
    return m.to_crs(4326)


def write(g, path, cols, digits=5):
    g = g[[c for c in cols if c in g] + ["geometry"]].copy()
    g["geometry"] = shapely.set_precision(g.geometry, 10 ** -digits)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    fc = json.loads(g.to_json(drop_id=True))
    for f in fc["features"]:   # drop nulls to keep the file small
        f["properties"] = {k: v for k, v in f["properties"].items() if v not in (None, "", " ")}
    json.dump(fc, open(path, "w"), separators=(",", ":"), allow_nan=False)
    return len(fc["features"]), os.path.getsize(path) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)
    od = os.path.join(a.out, "web", "data", "layers")
    os.makedirs(od, exist_ok=True)
    for key, (url, fields) in SOURCES.items():
        p = os.path.join(a.raw, key + ".geojson")
        if not os.path.exists(p):
            t = time.time()
            n = fetch(url, fields, p, page=1000 if "MapServer" in url else 2000)
            print(f"fetched {key}: {n:,} features ({time.time() - t:.0f} s)", flush=True)
    clip = shapely.box(*BBOX)
    out = {}

    g = load(a.raw, "rail")
    g = g[~g.get("NET", pd.Series("", index=g.index)).fillna("").isin(["X"])]   # X = abandoned / not in service
    g["owner"] = g.RROWNER1.fillna("")
    g["rights"] = g[["TRKRGHTS1", "TRKRGHTS2", "TRKRGHTS3"]].fillna("").agg(lambda r: ", ".join(x for x in r if x), axis=1)
    g["yard"] = g.YARDNAME.fillna("") if "YARDNAME" in g else ""
    out["rail"] = (simplify(g, 5), ["owner", "rights", "SUBDIV", "yard"])

    g = load(a.raw, "intermodal")
    out["intermodal"] = (g.rename(columns={"TERMINAL": "name", "RAIL_CO": "railroad"}), ["name", "railroad", "CITY"])

    g = load(a.raw, "flood")
    z = g.FLD_ZONE.fillna("")
    sub = g.ZONE_SUBTY.fillna("").str.upper()
    g["zone"] = None
    g.loc[z.isin(["A", "AE", "AH", "AO", "A99", "V", "VE"]), "zone"] = "100-year"
    g.loc[sub.str.contains("FLOODWAY"), "zone"] = "Floodway"
    g.loc[(z == "X") & sub.str.contains("0.2 PERCENT|0.2 PCT|500"), "zone"] = "500-year"
    g = g[g.zone.notna()]
    g = gpd.GeoDataFrame(g[["zone"]], geometry=g.geometry.intersection(clip), crs=4326)
    g = simplify(g.dissolve(by="zone", as_index=False).explode(index_parts=False), 15)
    g = g[g.to_crs(2278).area > 20000]   # drop slivers under about 0.5 acre
    out["flood"] = (g, ["zone"])

    g = load(a.raw, "pipelines")
    g = g.rename(columns={"OPERATOR": "operator", "COMMODITY_DESCRIPTION": "commodity", "DIAMETER": "diameter",
                          "SYSTEM_NAME": "system", "STATUS": "status"})
    out["pipelines"] = (simplify(g, 10), ["operator", "commodity", "diameter", "system", "status"])

    g = load(a.raw, "power")
    g = g.rename(columns={"OWNER": "owner", "VOLTAGE": "kv", "VOLT_CLASS": "kv_class", "STATUS": "status"})
    out["power"] = (simplify(g, 10), ["owner", "kv", "kv_class", "status"])

    g = load(a.raw, "substations")
    g = g.rename(columns={"NAME": "name", "MAX_VOLT": "kv", "STATUS": "status"})
    out["substations"] = (g[g.status.fillna("") != "NOT AVAILABLE"] if "status" in g else g, ["name", "kv", "status"])

    for key in ("water_ccn", "sewer_ccn"):
        g = load(a.raw, key)
        nm = next((c for c in g.columns if c.upper() in ("UTILITY", "UTILITY_NAME", "UTILITYNAME", "NAME")), None)
        g["name"] = g[nm] if nm else ""
        g = gpd.GeoDataFrame(g[["name"]], geometry=g.geometry.intersection(clip), crs=4326)
        out[key] = (simplify(g, 20), ["name"])

    g = load(a.raw, "aadt")
    g = g.rename(columns={"AADT_RPT_QTY": "aadt", "AADT_RPT_YEAR": "year", "TRFC_STATN_ID": "station"})
    g = g[pd.to_numeric(g.aadt, errors="coerce") > 0]
    if "ACTIVE" in g:
        g = g[g.ACTIVE.fillna("Y").astype(str).str.upper().isin(["Y", "YES", "1", "TRUE", "ACTIVE"]) | (g.ACTIVE.isna())]
    out["aadt"] = (g, ["aadt", "year", "station"])

    g = load(a.raw, "ftz")
    out["ftz"] = (g.rename(columns={"Zone": "zone", "Grantee": "name", "Location": "location"}), ["zone", "name", "location"])

    ports = load(a.raw, "ports_raw").rename(columns={"NAME": "name", "OPERATOR": "operator"})
    ports["name"] = ports.name.str.replace(r",\s*TX$", "", regex=True).str.title().str.replace("Of", "of")
    ports["kind"] = "port"
    ap_ = load(a.raw, "airports_raw")
    ap_ = ap_[(ap_.SITE_TYPE_CODE == "A") & (ap_.FACILITY_USE_CODE == "PU")]
    ap_ = ap_.assign(name=ap_.ARPT_NAME.str.title() + " (" + ap_.ARPT_ID + ")", kind="airport")
    major = {"IAH", "HOU", "EFD", "SGR", "DWH", "CXO", "IWS", "LVJ", "GLS", "AXH", "TME", "LBX", "HPY", "T41", "EYQ"}
    ap_["major"] = ap_.ARPT_ID.isin(major)
    ports["major"] = True
    g = gpd.GeoDataFrame(pd.concat([ports[["name", "kind", "major", "geometry"]],
                                    ap_[["name", "kind", "major", "geometry"]]]), crs=4326)
    out["ports"] = (g, ["name", "kind", "major"])

    for key, (g, cols) in out.items():
        g = g[g.intersects(clip)]
        n, mb = write(g, os.path.join(od, key + ".json"), cols)
        print(f"{key:<12}{n:>8,} features {mb:7.2f} MB", flush=True)


if __name__ == "__main__":
    main()
