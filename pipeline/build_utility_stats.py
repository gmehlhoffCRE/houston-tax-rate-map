"""
Electric utility statistics for the utilities serving the 8 counties, from EIA Form 861 (annual).

  python build_utility_stats.py --eia-dir f861_2025/ --year 2025 --out ../data/utilities/eia861_utilities.csv \
      [--layers layers_out/web/data/layers]     # also adds the figures to electric.json (run after build_layers.py)

Download https://www.eia.gov/electricity/data/eia861/zip/f861<year>.zip and unzip it. Reads
Service_Territory (counties served), Sales_Ult_Cust (bundled utilities: co-ops, Entergy Texas),
Delivery_Companies (ERCOT wires companies: CenterPoint, TNMP; their "sales" are energy delivered to
customers of all retail providers), Operational_Data (summer and winter peak) and Short_Form (small
municipal systems, no peak). EIA reports utility-wide totals, not counties.

The PUCT service-area names in electric.json (build_layers.py) are matched through PUCT_NAME below.
"""
import argparse, glob, os
import pandas as pd

COUNTIES = {"Harris", "Fort Bend", "Montgomery", "Waller", "Chambers", "Brazoria", "Liberty", "Galveston"}
PUCT_NAME = {   # EIA utility number -> PUCT service-area name in electric.json
    8901: "CenterPoint Energy Houston Electric, LLC", 55937: "Entergy Texas, Inc.", 40051: "Texas-New Mexico Power Company",
    16613: "Sam Houston Electric Cooperative, Inc.", 16638: "San Bernard Electric Cooperative, Inc.",
    12452: "Mid-South Electric Cooperative Association", 9590: "Jackson Electric Cooperative, Inc.",
    8435: "Hempstead Electric Department", 10982: "Liberty Municipal Electric System",
}


def sheet(path, name):
    d = pd.read_excel(path, name, header=None)
    top = d.iloc[0].ffill(); h = d.iloc[2]
    d = d.iloc[3:].copy()
    d.columns = [(str(top[i]).strip() + "|" if i >= 9 and pd.notna(top[i]) else "|") + str(h[i]).strip() for i in range(d.shape[1])]
    return d


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eia-dir", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--layers", help="layers folder: add the figures to electric.json service areas")
    a = ap.parse_args()
    f = lambda stem: glob.glob(os.path.join(a.eia_dir, f"{stem}_{a.year}.xlsx"))[0]
    st = pd.read_excel(f("Service_Territory"), "Counties_States"); st = st[st.State == "TX"]
    sales = sheet(f("Sales_Ult_Cust"), "States"); deliv = sheet(f("Delivery_Companies"), "Delivery Companies")
    op = pd.read_excel(f("Operational_Data"), "States", header=2); op = op[op.State == "TX"]
    sf = pd.read_excel(f("Short_Form"), header=None)
    hrow = next(i for i in range(6) if "Utility Number" in [str(v).strip() for v in sf.iloc[i]])
    sf.columns = [str(v).strip() for v in sf.iloc[hrow]]; sf = sf.iloc[hrow + 1:]
    rows = []
    for uid, puct in PUCT_NAME.items():
        cty = sorted(st[st["Utility Number"] == uid].County)
        r = {"eia_id": uid, "puct_name": puct, "year": a.year, "counties_served": len(cty),
             "counties_in_region": sum(c in COUNTIES for c in cty), "region_counties": ", ".join(c for c in cty if c in COUNTIES)}
        src = None
        for kind, df in (("delivery", deliv), ("bundled", sales)):
            x = df[(df["|Utility Number"] == uid) & (df["|State"] == "TX") & df["|Part"].isin(["A", "C"])]
            if len(x):
                x = x.iloc[0]; src = kind
                r.update(eia_name=x["|Utility Name"], ownership=x["|Ownership"], ba=x["|BA Code"], service=kind,
                         customers=num(x["TOTAL|Count"]), res_customers=num(x["RESIDENTIAL|Count"]), com_customers=num(x["COMMERCIAL|Count"]),
                         ind_customers=num(x["INDUSTRIAL|Count"]), sales_mwh=num(x["TOTAL|Megawatthours"]), ind_sales_mwh=num(x["INDUSTRIAL|Megawatthours"]),
                         revenue_k=num(x["TOTAL|Thousand Dollars"]))
                break
        if src is None:
            x = sf[sf["Utility Number"] == uid]
            if len(x):
                x = x.iloc[0]
                r.update(eia_name=x["Utility Name"], ownership=x["Ownership"], ba=x["BA Code"], service="bundled (short form)",
                         customers=num(x["Total Customers"]), sales_mwh=num(x["Total Sales (MWh)"]), revenue_k=num(x["Total Revenue (Thousand Dollars)"]))
        o = op[op["Utility Number"] == uid]
        if len(o):
            r.update(summer_peak_mw=num(o.iloc[0]["Summer Peak Demand"]), winter_peak_mw=num(o.iloc[0]["Winter Peak Demand"]))
        rows.append(r)
    out = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out.to_csv(a.out, index=False)
    if a.layers:
        import json
        p = os.path.join(a.layers, "electric.json"); fc = json.load(open(p))
        key = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())
        by = {key(r["puct_name"]): r for r in rows}
        n = 0
        for ft in fc["features"]:
            r = by.get(key(ft["properties"].get("name")))
            if not r:
                continue
            for k in ("customers", "res_customers", "com_customers", "ind_customers", "sales_mwh", "ind_sales_mwh", "revenue_k",
                      "summer_peak_mw", "winter_peak_mw", "counties_served", "counties_in_region"):
                v = r.get(k)
                if v is not None and v == v:
                    ft["properties"][k] = int(round(v)) if k not in ("summer_peak_mw", "winter_peak_mw") else round(v, 1)
            ft["properties"]["service"] = r.get("service", ""); ft["properties"]["eia_year"] = a.year; n += 1
        json.dump(fc, open(p, "w"), separators=(",", ":"), allow_nan=False)
        print(f"electric.json: EIA figures on {n} of {len(fc['features'])} service areas")
    print(out[["puct_name", "service", "customers", "sales_mwh", "summer_peak_mw", "counties_in_region", "counties_served"]].to_string())


if __name__ == "__main__":
    main()
