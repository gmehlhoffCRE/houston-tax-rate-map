"""
Two TxDOT trucking layers:

  python build_traffic.py --raw layers_raw --out out
      -> out/web/data/layers/congestion.json   TxDOT Top 100 Congested Roadways in the region
      -> out/web/data/layers/hazmat.json       designated non-radioactive hazardous materials routes

Congestion: TxDOT_Top_100_Congested_Roadways (TxDOT TPP, ranked yearly by the Texas A&M Transportation Institute).
  rank / trank   statewide rank, all vehicles and trucks
  dmi            annual hours of delay per mile
  tci            Texas Congestion Index: peak period travel time divided by free-flow travel time
  cost / tcost   annual cost of congestion on the segment, all vehicles and trucks
  tdly           annual truck hours of delay on the segment
  yr             ranking year

Hazmat: SWPM_Non_Radioactive_Hazardous_Materials_Routes (TxDOT Traffic Safety), the routes cities and counties have
designated or restricted under 49 CFR 397 and filed with TxDOT and FMCSA.
  k    through = designated through route; prohib = hazmat prohibited; hurr = prohibited during a hurricane warning
  city, desc, ord (ordinance), date (adopted)

Host: services.arcgis.com (TxDOT open data)
"""
import argparse, json, os, re, sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from build_layers import fetch, load, simplify, write

SVC = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/"
TOP100 = SVC + "TxDOT_Top_100_Congested_Roadways/FeatureServer/0"
HAZMAT = SVC + "SWPM_Non_Radioactive_Hazardous_Materials_Routes/FeatureServer/0"
COUNTIES = ("Harris", "Fort Bend", "Montgomery", "Waller", "Chambers", "Brazoria", "Liberty", "Galveston")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--out", default="out")
    ap.add_argument("--refetch", action="store_true")
    a = ap.parse_args()
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)

    p = os.path.join(a.raw, "congestion.geojson")
    if a.refetch or not os.path.exists(p):
        fetch(TOP100, "RANK,TRK_RANK,RD_NM,DLAY_MILE,TCI,COST_DLAY,TRK_DLY,COST_TRK,YR", p)
    g = load(a.raw, "congestion")
    g = g.rename(columns={"RANK": "rank", "TRK_RANK": "trank", "RD_NM": "name", "DLAY_MILE": "dmi", "TCI": "tci",
                          "COST_DLAY": "cost", "TRK_DLY": "tdly", "COST_TRK": "tcost", "YR": "yr"})
    g["mi"] = (g.to_crs(2278).length / 5280).round(1)
    g = g.sort_values("rank")
    n, mb = write(simplify(g, 8), os.path.join(od, "congestion.json"),
                  ["rank", "trank", "name", "dmi", "tci", "cost", "tdly", "tcost", "yr", "mi"])
    print(f"congestion: {n} top-100 segments in the region ({mb:.2f} MB); ranks {g['rank'].min()}-{g['rank'].max()}")

    p = os.path.join(a.raw, "hazmat.geojson")
    if a.refetch or not os.path.exists(p):
        fetch(HAZMAT, "CITY_NM,CNTY_NM,RTE_DESC,ORD_CODE,DATE,Type", p)
    g = load(a.raw, "hazmat")
    g = g[g.CNTY_NM.isin(COUNTIES)].copy()
    t = g.Type.fillna("").str.lower()
    g["k"] = ["hurr" if "hurricane" in x else "prohib" if "prohib" in x else "through" for x in t]
    g["city"] = g.CITY_NM.fillna("").str.replace("Hemptead", "Hempstead")
    g["desc"] = [re.sub(r"\s+", " ", re.sub(r"\s*\(SEE CITY OF.*$", "", d or "", flags=re.S)).strip() for d in g.RTE_DESC]
    g["ord"] = g.ORD_CODE.fillna("")
    g["date"] = [(date(1970, 1, 1) + timedelta(milliseconds=int(v))).isoformat() if v == v and v else "" for v in g.DATE]
    n, mb = write(simplify(g, 5), os.path.join(od, "hazmat.json"), ["k", "city", "desc", "ord", "date"])
    print(f"hazmat: {n} route segments ({mb:.2f} MB):", g.k.value_counts().to_dict())


if __name__ == "__main__":
    main()
