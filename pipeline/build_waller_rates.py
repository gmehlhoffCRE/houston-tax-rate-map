"""
Waller County rates in the same shape as the Harris pipeline, so build_county_data.py can map it.

Inputs
  --src        folder from fetch_waller.py (wc_parcels_raw.geojsonl, wc_tceq_districts.geojson, wc_bkdd.geojson)
  --rates      data/waller/wc_rates_2025.csv: Waller CAD's adopted rate list by entity code
               (from wcad_2025_tax_rates.pdf; M&O, I&S, total; "no levy" = 0)
  --map        data/waller/wc_district_map.csv: one row per CAD entity code, how its area is found:
                 cad:school | cad:city   code is on the parcel (Waller CAD school / city field)
                 countywide              every parcel (Waller County, RFM road levy, ESD 200)
                 tceq:<NAME>             TCEQ water district polygon with that NAME
                 county:bkdd             Waller County GIS Brookshire-Katy Drainage District polygon
                 none                    no boundary (TIFs, abatement zone, districts with no levy and no polygon)
Outputs (into --out): wc_rate_table.csv, wc_combos.csv, wc_account_rates.csv.gz, wc_combo_registry.csv
        (into --src): wc_real_acct.txt, wc_parcels.gpkg

Accounts are "W" + Waller CAD property id, because Waller ids are plain integers that collide with MCAD's.
Values are Waller CAD market value (ag-use valuation and exemptions are not applied). The public layer has no
state class or building area, so Waller parcels show as property type "other" with no tax per building SF.

Usage: python build_waller_rates.py --src waller --rates ../data/waller/wc_rates_2025.csv \
         --map ../data/waller/wc_district_map.csv --out ../data --year 2025
"""
import argparse, collections, json, os
import numpy as np, pandas as pd, geopandas as gpd, shapely

WC_OFFSET = 70000
MGMT = {"EWCMD", "SERMD", "WCID2", "THPID"}   # management / improvement districts: the map's "incl. mgmt" rate


def category(code, name):
    if code in ("GWA", "RFM"):
        return ("County / Countywide", "base")
    if code == "ESD":
        return ("ESD", "base")
    if code in MGMT:
        return ("Management District", "mgmt")
    if code == "DBK":
        return ("Drainage District", "base")
    if code == "R01":
        return ("Road District", "base")
    if code.startswith("S") and len(code) == 3:
        return ("ISD", "base")
    if code.startswith("C") and len(code) == 3:
        return ("City", "base")
    return ("Water District (MUD/WCID/UD)", "base")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="waller")
    ap.add_argument("--rates", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", default="../data")
    ap.add_argument("--year", type=int, default=2025)
    a = ap.parse_args()

    rates = pd.read_csv(a.rates, dtype={"code": str}).set_index("code")
    dm = pd.read_csv(a.map, dtype=str, keep_default_na=False).set_index("code")

    # ---- parcels: one row per shape
    rows, geoms = [], []
    with open(os.path.join(a.src, "wc_parcels_raw.geojsonl")) as f:
        for line in f:
            ft = json.loads(line)
            p = ft["properties"]
            if p.get("prop_id") is None or not ft.get("geometry"):
                continue
            rows.append(p); geoms.append(json.dumps(ft["geometry"]))
    P = gpd.GeoDataFrame(pd.DataFrame(rows), geometry=shapely.from_geojson(geoms), crs=4326)
    P["acct"] = "W" + P.prop_id.astype("int64").astype(str)
    P["geometry"] = P.geometry.make_valid()
    g2278 = P.to_crs(2278)
    P["sf"] = g2278.geometry.area
    for c in ("school", "city", "county"):
        P[c] = P[c].fillna("").astype(str).str.strip()

    # account's map point: a point inside its largest shape
    big = P.sort_values("sf", ascending=False).drop_duplicates("acct")
    pts = gpd.GeoDataFrame({"acct": big.acct.values}, geometry=big.geometry.representative_point().values, crs=4326)
    first = big.set_index("acct")
    on_roll = first.county != ""   # about 100 shapes have no codes at all (not on the roll); left without a rate
    print(f"{len(P):,} parcel shapes, {len(first):,} accounts ({(~on_roll).sum()} without CAD codes)")

    # ---- district polygons by CAD code
    tceq = gpd.read_file(os.path.join(a.src, "wc_tceq_districts.geojson"))
    tceq["NAME"] = tceq.NAME.str.strip()
    bkdd = gpd.read_file(os.path.join(a.src, "wc_bkdd.geojson"))
    polys = []
    for code, r in dm.iterrows():
        kind, _, ref = r.boundary.partition(":")
        if kind == "tceq":
            m = tceq[tceq.NAME == ref]
            if m.empty:
                print(f"  ! {code}: no TCEQ polygon named {ref!r}")
                continue
            polys.append(gpd.GeoDataFrame({"code": [code]}, geometry=[m.geometry.make_valid().union_all()], crs=4326))
        elif kind == "county" and ref == "bkdd":
            polys.append(gpd.GeoDataFrame({"code": [code]}, geometry=[bkdd.geometry.make_valid().union_all()], crs=4326))
    D = pd.concat(polys, ignore_index=True)
    hit = gpd.sjoin(pts, D, predicate="within")[["acct", "code"]]

    units = collections.defaultdict(set)
    countywide = [c for c, r in dm.iterrows() if r.boundary == "countywide"]
    for acct, r in first[on_roll].iterrows():
        u = units[acct]
        u.update(countywide)
        if r.school:
            u.add(r.school)
        if r.city:
            u.add(r.city)
    for acct, code in zip(hit.acct, hit.code):
        if acct in units:
            units[acct].add(code)
    acc = pd.DataFrame({"acct": list(units), "units": [sorted(u) for u in units.values()]})
    acc["key"] = acc.units.map("|".join)
    used = collections.Counter(u for us in acc.units for u in us)
    print(f"{len(acc):,} accounts with taxing units; {len(used)} unit codes in use")

    # ---- rate table, one row per code in use (plus every code on the rate list)
    recs = []
    for code in sorted(set(used) | set(rates.index)):
        name = rates.name[code] if code in rates.index else dm.cad_name.get(code, code).title()
        cat, bucket = category(code, name)
        rate = float(rates.total[code]) if code in rates.index else 0.0
        recs.append(["WC-" + code, name, cat, bucket, rate, False])
    t = pd.DataFrame(recs, columns=["tax_dist", "name", "category", "bucket", "rate_used", "missing_rate"])
    t["accounts"] = t.tax_dist.str[3:].map(used).fillna(0).astype(int)
    t["tp_cd"] = ""; t["rate_prior"] = t.rate_used; t["rate_current"] = np.nan
    t[["tax_dist", "name", "tp_cd", "category", "bucket", "accounts", "rate_prior", "rate_current",
       "rate_used", "missing_rate"]].to_csv(os.path.join(a.out, "wc_rate_table.csv"), index=False)
    T = t.set_index("tax_dist")

    # ---- combos with stable ids
    reg_path = os.path.join(a.out, "wc_combo_registry.csv")
    reg = pd.read_csv(reg_path, keep_default_na=False).set_index("combo_key").combo_id if os.path.exists(reg_path) \
        else pd.Series(dtype=np.int64)
    nxt = int(reg.max()) + 1 if len(reg) else WC_OFFSET
    keys = acc.key.value_counts(); ids = {}
    for k in keys.index:
        if k in reg.index:
            ids[k] = int(reg[k])
        else:
            ids[k] = nxt; reg[k] = nxt; nxt += 1
    reg.rename("combo_id").rename_axis("combo_key").reset_index().to_csv(reg_path, index=False)
    out = []
    for k, n in keys.items():
        r = T.reindex(["WC-" + c for c in k.split("|")])
        names = lambda m: "; ".join(sorted(set(r[m].name)))
        base = r[r.bucket == "base"].rate_used.sum(); mgmt = r[r.bucket == "mgmt"].rate_used.sum()
        out.append({"combo_id": ids[k], "rate_base": round(base, 6), "rate_mgmt": round(mgmt, 6),
                    "isd": names(r.category == "ISD"), "city": names(r.category == "City"),
                    "water_districts": names(r.category.isin(["Water District (MUD/WCID/UD)", "Drainage District",
                                                              "Road District"]) & (r.rate_used > 0)),
                    "esd": names(r.category == "ESD"), "college": "",
                    "mgmt_districts": names(r.bucket == "mgmt"), "tirz": "", "pid": "",
                    "n_missing_rates": 0,
                    "breakdown": "|".join(f"{c}:{round(float(v), 6)}" for c, v in zip(r.index, r.rate_used)),
                    "rate_total_incl_mgmt": round(base + mgmt, 6), "accounts": int(n), "tax_year": a.year})
    C = pd.DataFrame(out).sort_values("combo_id")
    C.to_csv(os.path.join(a.out, "wc_combos.csv"), index=False)
    ar = acc.assign(combo_id=acc.key.map(ids)).merge(C[["combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]],
                                                     on="combo_id")
    ar[["acct", "combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]].to_csv(
        os.path.join(a.out, "wc_account_rates.csv.gz"), index=False, compression="gzip")

    # ---- account details (real_acct layout)
    land = g2278.assign(acct=P.acct, sf=g2278.geometry.area).groupby("acct").sf.sum()
    acres = pd.to_numeric(first.legal_acreage, errors="coerce")
    situs = first[["situs_num", "situs_street_prefx", "situs_street", "situs_street_sufix"]].fillna("").astype(str) \
        .apply(lambda s: s.str.strip()).agg(" ".join, axis=1).str.split().str.join(" ")
    ra = pd.DataFrame({
        "acct": first.index, "mailto": first.file_as_name.fillna("").values,
        "site_addr_1": situs.values, "site_addr_2": first.situs_city.fillna("").str.strip().values,
        "state_class": "", "tot_appr_val": pd.to_numeric(first.market, errors="coerce").values,
        "bld_ar": np.nan,
        "land_ar": np.where(acres > 0, acres * 43560, land.reindex(first.index)).round(),
    })
    ra.to_csv(os.path.join(a.src, "wc_real_acct.txt"), sep="\t", index=False, encoding="latin-1", errors="replace")
    gpd.GeoDataFrame({"acct": P.acct}, geometry=g2278.geometry, crs=2278).to_file(
        os.path.join(a.src, "wc_parcels.gpkg"), driver="GPKG")

    print(f"{len(C):,} combos")
    print("base rate, accounts weighted:", ar.rate_base.describe(percentiles=[.05, .5, .95]).round(3).to_dict())
    print("accounts per unit:", ", ".join(f"{c} {n:,}" for c, n in used.most_common()))


if __name__ == "__main__":
    main()
