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
  ports       Ports (US DOT BTS, Army Corps list), airports (FAA facilities, public use only) and port terminals
              (data/ports/port_terminals.csv: Port Houston public terminals, Port Freeport Velasco, Port of Galveston,
              Texas City; placed at their berths in the Army Corps / US DOT BTS Navigation Facilities (docks) data)
  docks       Ship docks and berths on the Houston Ship Channel and Galveston Bay with maximum draft (Houston Pilots
              dock list, data/ports/houston_pilots_docks_2025-05-20.csv; a few docks without coordinates are left out)
  zoning      City zoning districts where the city publishes a GIS layer (Houston, Pasadena and the counties have
              no zoning). Each district gets a category (industrial, commercial, mixed use, residential, planned,
              agricultural / open, other) from its code and description; the city's own code is kept
  opp_zones   Qualified Opportunity Zones (HUD, census tracts designated in 2018)
  contam      Contaminated and cleanup sites: EPA Superfund NPL, EPA brownfields (ACRES via FRS), TCEQ state
              Superfund, TCEQ brownfield site assessments, TCEQ Voluntary Cleanup Program
  wetlands    USFWS National Wetlands Inventory (Esri copy): emergent, forested/shrub and estuarine wetlands;
              lakes, ponds, rivers and open bay water left out (the basemap shows them)
  evac        Hurricane evacuation zones by ZIP (H-GAC 2025: A is the coast, then B, C)
  road_projects  Road and bridge projects with a timeline group (under construction, starting in about 1 to 3
              years, 3+ years out, finished since 2023): TxDOT project tracker (DCIS, all open projects plus
              those let since 2023), H-GAC 2027-2030 TIP projects by cities, counties, toll authorities and
              others (TxDOT's own TIP entries are left to DCIS), City of Houston Public Works active roadway
              projects, Fort Bend County mobility bond projects, Montgomery County 2025 road bond projects.
              Routine work (seal coat, overlay, landscaping, signs and striping) is flagged so the page can hide it
  labor       Workforce by census tract (ACS 5-year): population 16+, labor force, employed, unemployed;
              tract centroids, for the labor shed totals in the drive time panel

Raw downloads are cached in --raw; delete a file there to refetch it.
Hosts: services.arcgis.com, services1/2/3/5/6/8.arcgis.com, gis.rrc.texas.gov, gisweb.tceq.texas.gov,
interactivemaps.sugarlandtx.gov.
"""
import argparse, json, os, re, sys, time, urllib.parse
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
    "opp_zones": ("https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/Opportunity_Zones/FeatureServer/13", "*"),
    "npl": ("https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
            "Superfund_National_Priorities_List_(NPL)_Sites_with_Status_Information/FeatureServer/0",
            "Site_Name,Site_EPA_ID,Status,City,Listing_Date,Construction_Completion_Date,Deletion_Date"),
    "acres": ("https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/FRS_INTERESTS_ACRES/FeatureServer/0",
              "PRIMARY_NAME,LOCATION_ADDRESS,CITY_NAME,PGM_SYS_ID,FAC_URL"),
    "tceq_sf": ("https://gisweb.tceq.texas.gov/arcgis/rest/services/Public/Superfund/MapServer/0", "SITE_NAME,PHYS_ADDR,CITY,SF_ID,WEB_URL,EPA_TXID"),
    "tceq_bf": ("https://gisweb.tceq.texas.gov/arcgis/rest/services/Public/Brownfield/MapServer/0", "SITE_NAME,PHYS_ADDR,CITY,BSA_ID"),
    "tceq_vcp": ("https://gisweb.tceq.texas.gov/arcgis/rest/services/Public/VCP/MapServer/0", "SITE_NAME,PHYS_ADDR,CITY,VCP_ID"),
    "evac": ("https://services1.arcgis.com/Z6SBWLWGRRejblAA/arcgis/rest/services/Hurricane_Evacuation_ZipZones_2025/FeatureServer/0",
             "GEOID20,ZipZone,County"),
    "labor": ("https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/ACS_Employment_Status_Centroids/FeatureServer/2",
              "GEOID,NAME,B23025_001E,B23025_002E,B23025_004E,B23025_005E"),
}
TXDOT_PROJ = ("https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/TxDOT_DCIS_All_Projects/FeatureServer/0",
              "CONTROL_SECT_JOB,HIGHWAY_NUMBER,LIMITS_FROM,LIMITS_TO,PROJ_CLASS,TYPE_OF_WORK,EST_CONSTRUCTION_COST,PROJ_STG,"
              "PROJ_ESTMTD_LET_D,ACTUAL_LET_DATE,FREIGHT,COUNTY_NAME",
              "1=1")   # the server rejects date filters on this layer; closed projects let before 2023 are dropped below
LOCAL_PROJ = {
    "tip_pts": "https://services1.arcgis.com/Z6SBWLWGRRejblAA/arcgis/rest/services/TIP_2027_2030_WFL1/FeatureServer/0",
    "tip_lines": "https://services1.arcgis.com/Z6SBWLWGRRejblAA/arcgis/rest/services/TIP_2027_2030_WFL1/FeatureServer/1",
    "cohpw_roads": "https://services1.arcgis.com/XpTq0H1nJ5DHgofs/arcgis/rest/services/EngageHouston/FeatureServer/0",
    "fbc_mobility": "https://services.arcgis.com/HfQs2ClqmipKpmFK/arcgis/rest/services/All_Mobility_Projects_New_1/FeatureServer/0",
    "moco_cip": "https://services1.arcgis.com/PRoAPGnMSUqvTrzq/arcgis/rest/services/CIP_Project_Areas_View/FeatureServer/0",
}
ROUTINE = {"Seal Coat", "Overlay", "Landscape & Scenic Enhancement", "Traffic Control Devices", "Safety Improvement Projects",
           "Emergency Relief Projects", "Preliminary Engineering", "Rest Areas & Truck Weigh Stations"}


def stage_txdot(stg, let_ms):
    s = (stg or "").strip()
    if s == "Construction":
        return "now"
    if s in ("PS&E", "Letting", "Ready to Let", "Procurement", "Execute", "Design and Construct", "Dual"):
        return "soon"
    if s in ("Planning", "Initiate", "PE"):
        return "later"
    if s in ("Closed", "Operations and Maint"):
        return "done"
    return "later"


def road_projects(raw):
    """One GeoDataFrame of road projects from TxDOT and local agencies, with a common set of fields."""
    to_ms = lambda v: pd.to_datetime(v, unit="ms", errors="coerce")
    rows = []
    g = load(raw, "proj_txdot")
    act = to_ms(g.ACTUAL_LET_DATE)
    g = g[(g.PROJ_STG.fillna("") != "Closed") | (act >= pd.Timestamp("2023-01-01"))]
    let = to_ms(g.PROJ_ESTMTD_LET_D); act = to_ms(g.ACTUAL_LET_DATE)
    t = gpd.GeoDataFrame({
        "src": "TxDOT", "name": g.HIGHWAY_NUMBER.fillna(""),
        "limits": (g.LIMITS_FROM.fillna("") + " to " + g.LIMITS_TO.fillna("")).str.strip(" to"),
        "work": g.TYPE_OF_WORK.fillna("").str.capitalize(), "cls": g.PROJ_CLASS.fillna(""),
        "cost": pd.to_numeric(g.EST_CONSTRUCTION_COST, errors="coerce"),
        "phase": g.PROJ_STG.fillna(""), "stage": [stage_txdot(a, b) for a, b in zip(g.PROJ_STG, g.ACTUAL_LET_DATE)],
        "date": [("let " + d.strftime("%b %Y")) if d == d and d is not pd.NaT else ("est. let " + e.strftime("%b %Y")) if e == e and e is not pd.NaT else ""
                 for d, e in zip(act, let)],
        "freight": g.FREIGHT.fillna("N").eq("Y"), "id": "CSJ " + g.CONTROL_SECT_JOB.fillna(""),
        "routine": g.PROJ_CLASS.isin(ROUTINE)}, geometry=g.geometry, crs=4326)
    rows.append(t)
    for key in ("tip_pts", "tip_lines"):
        g = load(raw, "proj_" + key)
        g = g[~g.SPONSOR.fillna("").str.upper().str.startswith("TXDOT")]
        fy = pd.to_numeric(g.FISCAL__YR, errors="coerce")
        rows.append(gpd.GeoDataFrame({
            "src": g.SPONSOR.fillna("").str.title().str.replace(" Of ", " of ").str.replace(" And ", " and ").str.replace("Hctra", "HCTRA")
                   .str.replace("Fbctra", "FBCTRA").str.replace("Bctra", "BCTRA").str.replace("Metro", "METRO").str.replace(" Co. ", " County ").str.replace(r" - Houston Public Works$| - Parks .*$", "", regex=True).str.replace("Nctcog", "NCTCOG"),
            "name": g.STREET.fillna("").str.title(), "limits": (g.FROM_.fillna("") + " to " + g.TO_.fillna("")).str.replace(" to -", "").str.title(),
            "work": g.PROJ_DESCRIPTION.fillna("").str.capitalize(), "cls": g.get("Proj_Code", pd.Series("", index=g.index)).fillna(""),
            "cost": pd.to_numeric(g.ESTIMATED_COST, errors="coerce"), "phase": "TIP fiscal year " + fy.fillna(0).astype(int).astype(str),
            "stage": ["soon" if v == v and v <= 2028 else "later" for v in fy],
            "date": ["FY " + str(int(v)) + (" (" + str(c) + ")" if isinstance(c, str) and c.strip() not in ("", "-") else "") if v == v else ""
                     for v, c in zip(fy, g.get("COMMENT_", pd.Series(None, index=g.index)))],
            "freight": False, "id": "H-GAC TIP " + g.MPOID.fillna(0).astype(int).astype(str), "routine": False}, geometry=g.geometry, crs=4326))
    g = load(raw, "proj_cohpw_roads")
    st = g.PROJECT_STAGE.fillna("")
    rows.append(gpd.GeoDataFrame({
        "src": "City of Houston", "name": g.PROJECT_DESCRIPTION.fillna("").str.split(":").str[0].str.strip(),
        "limits": g.PROJECT_DESCRIPTION.fillna(""), "work": g.PROJECT_SCOPE.fillna(""), "cls": g.PROJECT_TYPE.fillna(""),
        "cost": float("nan"), "phase": st,
        "stage": ["done" if "COMPLET" in x.upper() else "now" if "CONSTRUCT" in x.upper() else "soon" if x else "later" for x in st],
        "date": [f"{a} to {b}" if a and b else a or b for a, b in zip(g.START_DATE.fillna(""), g.END_DATE.fillna(""))],
        "freight": False, "id": "CIP " + g.CIP_NUMBER.fillna(""), "routine": ~g.PROJECT_TYPE.fillna("").str.contains("Thoroughfare|Bridge|Intersection|Traffic")},
        geometry=g.geometry, crs=4326))
    g = load(raw, "proj_fbc_mobility")
    st = g.STATUS.fillna("").str.upper().str.strip()
    g = g[~st.str.contains("CANCEL|COMBINED|DEFER")]; st = g.STATUS.fillna("").str.upper().str.strip()
    rows.append(gpd.GeoDataFrame({
        "src": "Fort Bend County", "name": g.PROJECT_NAME.fillna("").str.title(), "limits": g.LIMITS.fillna("").str.title(),
        "work": g.DESCRIPTION.fillna("").str.capitalize(), "cls": "", "cost": pd.to_numeric(g.TOTAL_PROJECT_COST, errors="coerce"),
        "phase": st.str.title(),
        "stage": ["done" if ("COMPLETE" in x or "CLOSEOUT" in x) else "now" if ("CONSTRUCT" in x or x == "ACTIVE") else "soon" if ("DESIGN" in x or "BID" in x or "ROW" in x) else "later" for x in st],
        "date": "Bond " + g.BOND_YEAR.fillna(0).astype(int).astype(str), "freight": False, "id": "FBC " + g.PROJECT_NUMBER.fillna("").astype(str),
        "routine": False}, geometry=g.geometry, crs=4326))
    g = load(raw, "proj_moco_cip")
    g = g[g.PROJTYPE.fillna("").str.contains("Transport", case=False)]
    st = g.PROJSTAT.fillna("").str.upper()
    ps, pe = to_ms(g.PLANSTARTDT), to_ms(g.PLANENDDT)
    rows.append(gpd.GeoDataFrame({
        "src": "Montgomery County", "name": g.PROJNAME.fillna(""), "limits": (g.PROJFROM.fillna("") + " to " + g.PROJTO.fillna("")).str.strip(" to"),
        "work": g.DESCRIPTION.fillna(""), "cls": "", "cost": pd.to_numeric(g.ESTCOST, errors="coerce").fillna(pd.to_numeric(g.TOT_AMT, errors="coerce")),
        "phase": (g.PROJSTAT.fillna("") + " · " + g.PROJPHASE.fillna("")).str.strip(" ·"),
        "stage": ["done" if "COMPLETE" in x else "now" if "PROGRESS" in x else "soon" if "DESIGN" in x else "later" for x in st],
        "date": [f"{a.strftime('%b %Y')} to {b.strftime('%b %Y')}" if a == a and b == b and a is not pd.NaT and b is not pd.NaT else "" for a, b in zip(ps, pe)],
        "freight": False, "id": "MCTX " + g.PROJID.fillna(""), "routine": False}, geometry=g.geometry, crs=4326))
    g = gpd.GeoDataFrame(pd.concat(rows, ignore_index=True), crs=4326)
    g["cost"] = g.cost.where(g.cost > 0)
    for c in ("name", "limits", "work", "phase", "date", "src", "cls", "id"):
        g[c] = g[c].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return g


# wetlands: 217k NWI polygons in the region; ask the server for the wetland types only, pre-generalized
WETLANDS = ("https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Wetlands/FeatureServer/0",
            "WETLAND_TYPE,ATTRIBUTE",
            "WETLAND_TYPE IN ('Freshwater Emergent Wetland','Freshwater Forested/Shrub Wetland','Estuarine and Marine Wetland')")
# city zoning layers: (city, layer url, code field, description field or None)
ZONING = [
    ("Baytown", "https://services8.arcgis.com/2iaYWEMdQLPv0ZUw/arcgis/rest/services/Zoning_Municode/FeatureServer/16", "ULDCZON_20", "ORD_Text"),
    ("Pearland", "https://services5.arcgis.com/iJ6DPCVBtManqbJU/arcgis/rest/services/Zoning/FeatureServer/0", "Zone_Name", "Zone_Description"),
    ("Sugar Land", "https://interactivemaps.sugarlandtx.gov/512/rest/services/Planning/HomeBase/MapServer/9", "ZONE__", "ZONE_DEF"),
    ("Missouri City", "https://services2.arcgis.com/6vRbgYSxztFGZwla/arcgis/rest/services/Zoning2026_1/FeatureServer/0", "ZONE_", None),
    ("La Porte", "https://services3.arcgis.com/K8W2oZWmBOVHwjhP/arcgis/rest/services/ZONING_AUG_2018_Web_AppBuilder_Single_Services/FeatureServer/0", "zoning", "label"),
    ("Seabrook", "https://services5.arcgis.com/KkzTh8g0dTwlw3DH/arcgis/rest/services/Official_Zoning_Districts_March_2019/FeatureServer/0",
     "Zoning_Desktop_ZC_Abrv", "Zoning_Desktop_Zoning_Code"),
    ("Friendswood", "https://services6.arcgis.com/ghs8JYGzwZM6Zl6x/arcgis/rest/services/City_of_Friendswood_Zoning_by_Parcel/FeatureServer/4", "ZONE", "ZoneDescription"),
    ("Dickinson", "https://services3.arcgis.com/B9RpfHT8Gso9BEJP/arcgis/rest/services/Official_Zoning_Map/FeatureServer/5", "ZoningClass", None),
    ("Hitchcock", "https://services8.arcgis.com/PyYnLy003aIw1xC3/arcgis/rest/services/Zoning_Public/FeatureServer/0", "LAYER", None),
    ("Tomball", "https://services2.arcgis.com/Q162lMMZLeb8KwDU/arcgis/rest/services/Current_Zoning_(Public_View)/FeatureServer/344", "District_ID", "District"),
    ("Angleton", "https://services3.arcgis.com/KGWVkDBbmA3Jt2Ut/arcgis/rest/services/Zoning/FeatureServer/1", "ZoningDesig", None),
    ("Lake Jackson", "https://services6.arcgis.com/6L90KvW0ESJ4M9QG/arcgis/rest/services/Zoning_-_Public/FeatureServer/0", "REZONE_TO", None),
    ("Richmond", "https://services6.arcgis.com/riku34rn6C8cs2t5/arcgis/rest/services/CORZONINGDISTRICTS020320/FeatureServer/0", "Zone", "ECP_Zone_Description"),
    ("West University Place", "https://services2.arcgis.com/i0yOnTx5hca0RSx2/arcgis/rest/services/Zoning_Updated_WFL1/FeatureServer/18", "UpdatedZoningDistrict", None),
]


def zone_cat(code, desc):
    """Coarse zoning category from a city's district code and description (codes differ city to city).
    The description wins when there is one; the code patterns cover cities that publish codes only."""
    c = (code or "").upper().strip(); d = re.sub(r"\s+", " ", (desc or "").upper())
    if d:
        for pat, cat in ((r"MANUFACTURED HOM|MANUFACTURED HOUS|MOBILE HOME|MIXED RES|SINGLE-FAM", "residential"),
                         (r"INDUSTR|MANUFACTUR|WAREHOUS", "industrial"),
                         (r"MIXED|SPECTRUM|LIVABLE CENTER", "mixed"),
                         (r"PLANNED|\bPUD\b|CLUSTER", "planned"),
                         (r"OPEN SPACE|PARK(S|WAY)? AND|CONSERVATION|RECREATION|AGRICULT", "ag_open"),
                         (r"RESID|FAMILY|TOWNH|DUPLEX|ESTATE|GARDEN HOME", "residential"),
                         (r"COMMERC|BUSINESS|RETAIL|OFFICE|SHOPPING|DOWNTOWN|SERVICE|ENTERTAIN|MAIN STREET", "commercial"),
                         (r"PUBLIC|INSTITUTION", "other")):
            if re.search(pat, d):
                return cat
    if re.match(r"^CLUSTER", c):
        return "planned"
    if re.match(r"^(ROW|ROADS|ETJ|SUP|NO ZONING|-9)", c):
        return "other"
    if re.match(r"^(MH|MHP|MHR)$", c):
        return "residential"
    if re.match(r"^(M-?\d|LI|HI|BI|GI|IN$|IND|I-?\d?$|I$|ISOD)", c):
        return "industrial"
    if re.match(r"^(MU|MXD|MX|TCC|OT|C-MU|G/O-MU|TOD)", c):
        return "mixed"
    if re.match(r"^(PD|PUD|PDD|P-?D)", c):
        return "planned"
    if re.match(r"^(SF|MF|R-?\d|R$|RR|SR|RS|RM|TH|PH|GH|UR|LLD|\dF|D$)", c):
        return "residential"
    if re.match(r"^(C-?\d?|GC|NC|CG|CS|CR|B-?\d|GB|LC|OP|O$|CBD|SC|RC|HC|BP|NS)", c):
        return "commercial"
    if re.match(r"^(AG|A-?\d|OS|P$|PARK|RE$|SD$)", c):
        return "ag_open"
    return "other"


def fetch(url, fields, path, page=1000, where="1=1", offset=None):
    """Pages an ArcGIS layer (bbox filter) to a GeoJSON FeatureCollection file."""
    feats, off = [], 0
    while True:
        q = {"where": where, "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope",
             "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "outSR": 4326,
             "resultOffset": off, "resultRecordCount": page, "f": "geojson"}
        if offset:
            q["maxAllowableOffset"] = offset
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
    g = g[g.geometry.notna() & ~g.geometry.is_empty]   # noqa
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
    p = os.path.join(a.raw, "proj_txdot.geojson")
    if not os.path.exists(p):
        t = time.time(); n = fetch(TXDOT_PROJ[0], TXDOT_PROJ[1], p, page=2000, where=TXDOT_PROJ[2])
        print(f"fetched TxDOT projects: {n:,} ({time.time() - t:.0f} s)", flush=True)
    for key, url in LOCAL_PROJ.items():
        p = os.path.join(a.raw, "proj_" + key + ".geojson")
        if not os.path.exists(p):
            n = fetch(url, "*", p, page=1000)
            print(f"fetched {key}: {n:,}", flush=True)
    p = os.path.join(a.raw, "wetlands.geojson")
    if not os.path.exists(p):
        t = time.time(); n = fetch(WETLANDS[0], WETLANDS[1], p, page=2000, where=WETLANDS[2], offset=0.00005)
        print(f"fetched wetlands: {n:,} features ({time.time() - t:.0f} s)", flush=True)
    for city, url, code, desc in ZONING:
        p = os.path.join(a.raw, "zoning_" + re.sub(r"\W+", "_", city.lower()) + ".geojson")
        if not os.path.exists(p):
            try:
                t = time.time(); n = fetch(url, ",".join(x for x in (code, desc) if x), p, page=1000)
                print(f"fetched zoning {city}: {n:,} features ({time.time() - t:.0f} s)", flush=True)
            except Exception as e:
                print(f"zoning {city}: skipped ({e})", flush=True)
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
    tp = os.path.join(os.path.dirname(__file__), "..", "data", "ports", "port_terminals.csv")
    t = pd.read_csv(tp)
    term = gpd.GeoDataFrame({"name": t.name, "kind": "terminal", "major": t.container.astype(bool), "port": t.port, "cargo": t.cargo,
                             "note": t.note}, geometry=gpd.points_from_xy(t.lon, t.lat), crs=4326)
    g = gpd.GeoDataFrame(pd.concat([ports[["name", "kind", "major", "geometry"]],
                                    ap_[["name", "kind", "major", "geometry"]], term]), crs=4326)
    out["ports"] = (g, ["name", "kind", "major", "port", "cargo", "note"])

    dp = os.path.join(os.path.dirname(__file__), "..", "data", "ports", "houston_pilots_docks_2025-05-20.csv")
    d = pd.read_csv(dp, dtype={"draft": str, "note": str})
    out["docks"] = (gpd.GeoDataFrame(d[["name", "draft", "note"]], geometry=gpd.points_from_xy(d.lon, d.lat), crs=4326), ["name", "draft", "note"])

    # zoning: one dissolved polygon set per city and district code
    zs = []
    for city, url, code, desc in ZONING:
        p = os.path.join(a.raw, "zoning_" + re.sub(r"\W+", "_", city.lower()) + ".geojson")
        if not os.path.exists(p):
            continue
        g = load(a.raw, os.path.basename(p)[:-8])
        if g.empty or code not in g:
            print(f"zoning {city}: no features", flush=True); continue
        g["code"] = g[code].fillna("").astype(str).str.strip()
        g["desc"] = g[desc].fillna("").astype(str).str.strip() if desc and desc in g else ""
        g = g[g.code != ""]
        g = g.dissolve(by=["code"], as_index=False, aggfunc={"desc": "first"})
        g["city"] = city
        g["cat"] = [zone_cat(c, d) for c, d in zip(g.code, g.desc)]
        g["desc"] = g.desc.str.replace(r"^\s*" + "", "", regex=True)
        zs.append(g[["city", "code", "desc", "cat", "geometry"]])
        print(f"zoning {city:<22}{len(g):>4} districts  " + ", ".join(f"{k} {v}" for k, v in g.cat.value_counts().items()), flush=True)
    if zs:
        g = gpd.GeoDataFrame(pd.concat(zs), crs=4326)
        out["zoning"] = (simplify(g.explode(index_parts=False), 4), ["city", "code", "desc", "cat"])

    g = load(a.raw, "opp_zones")
    tract = next((c for c in g.columns if c.upper() in ("GEOID10", "GEOID", "TRACT", "TRACTCE10", "GEOID_1")), None)
    g["tract"] = g[tract].astype(str) if tract else ""
    out["opp_zones"] = (simplify(g, 10), ["tract"])

    rows = []
    g = load(a.raw, "npl"); g["kind"] = "npl"; g["name"] = g.Site_Name.str.title(); g["id"] = g.Site_EPA_ID
    g["status"] = g.Status; g["city"] = g.City; rows.append(g)
    g = load(a.raw, "tceq_sf"); g["kind"] = "state_sf"; g["name"] = g.SITE_NAME.str.title(); g["id"] = g.SF_ID
    g["addr"] = g.PHYS_ADDR; g["city"] = g.CITY; rows.append(g)
    g = load(a.raw, "acres"); g["kind"] = "brownfield"; g["name"] = g.PRIMARY_NAME.str.title(); g["id"] = "ACRES " + g.PGM_SYS_ID.astype(str)
    g["addr"] = g.LOCATION_ADDRESS; g["city"] = g.CITY_NAME; rows.append(g)
    g = load(a.raw, "tceq_bf"); g["kind"] = "brownfield"; g["name"] = g.SITE_NAME.str.title(); g["id"] = "TCEQ BSA " + g.BSA_ID.astype(str)
    g["addr"] = g.PHYS_ADDR; g["city"] = g.CITY; rows.append(g)
    g = load(a.raw, "tceq_vcp"); g["kind"] = "vcp"; g["name"] = g.SITE_NAME.str.title(); g["id"] = "VCP " + g.VCP_ID.astype(str)
    g["addr"] = g.PHYS_ADDR; g["city"] = g.CITY; rows.append(g)
    cols = ["kind", "name", "id", "status", "addr", "city"]
    g = gpd.GeoDataFrame(pd.concat([r[[c for c in cols if c in r] + ["geometry"]] for r in rows]), crs=4326)
    g = g[g.geom_type == "Point"]
    g["city"] = g.city.fillna("").str.title()
    out["contam"] = (g, cols)

    g = load(a.raw, "wetlands")
    g["type"] = g.WETLAND_TYPE.map({"Freshwater Emergent Wetland": "Emergent", "Freshwater Forested/Shrub Wetland": "Forested / shrub",
                                    "Estuarine and Marine Wetland": "Estuarine"})
    g = gpd.GeoDataFrame(g[["type"]], geometry=g.geometry.intersection(clip), crs=4326)
    g = simplify(g.dissolve(by="type", as_index=False).explode(index_parts=False), 12)
    g = g[g.to_crs(2278).area > 43560]   # 1 acre and up
    out["wetlands"] = (g, ["type"])

    g = load(a.raw, "evac")
    g = g.rename(columns={"ZipZone": "zone", "GEOID20": "zip", "County": "county"})
    g = g[g.zone.fillna("").str.strip().isin(["A", "B", "C"])]
    out["evac"] = (simplify(g, 25), ["zone", "zip", "county"])

    g = road_projects(a.raw)
    print("road projects by source: " + ", ".join(f"{k} {v}" for k, v in g.src.value_counts().head(12).items()), flush=True)
    print("road projects by stage: " + ", ".join(f"{k} {v}" for k, v in g.stage.value_counts().items()) + f"; routine {int(g.routine.sum())}", flush=True)
    g = simplify(g.explode(index_parts=False), 8)
    out["road_projects"] = (g, ["src", "name", "limits", "work", "cls", "cost", "phase", "stage", "date", "freight", "id", "routine"])

    g = load(a.raw, "labor")
    g = g.rename(columns={"B23025_001E": "p16", "B23025_002E": "lf", "B23025_004E": "emp", "B23025_005E": "unemp", "GEOID": "tract"})
    out["labor"] = (g, ["tract", "p16", "lf", "emp", "unemp"])

    for key, (g, cols) in out.items():
        g = g[g.intersects(clip)]
        n, mb = write(g, os.path.join(od, key + ".json"), cols)
        print(f"{key:<12}{n:>8,} features {mb:7.2f} MB", flush=True)


if __name__ == "__main__":
    main()
