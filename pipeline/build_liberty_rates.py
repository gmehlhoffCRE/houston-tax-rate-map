"""
Liberty County rates in the same shape as the Harris pipeline, so build_county_data.py can map it.

Inputs
  --src     folder from fetch_liberty.py
  --units   data/liberty/lc_units_2025.csv: one row per Liberty CAD unit code with name, category, bucket,
            2025 rate (Liberty CAD's "2025 TAX RATES" sheet, lcad_2025_tax_rates.pdf) and how its area is found:
              cad:school | cad:city | cad:county   code is on the parcel (Liberty CAD school / city / county field)
              cad:special:<CODE>                  CAD "Special Districts" layer feature whose name ends "(<CODE>)"
              tceq:<NAME>                         TCEQ water district polygon with that NAME
Outputs (into --out): lc_rate_table.csv, lc_combos.csv, lc_account_rates.csv.gz, lc_combo_registry.csv
        (into --src): lc_real_acct.txt, lc_parcels.gpkg

Accounts are "L" + Liberty CAD property id (plain ids collide with MCAD's). Values are Liberty CAD market value
(ag use value and exemptions not applied). The public layer has no state class or building area.

Usage: python build_liberty_rates.py --src liberty --units ../data/liberty/lc_units_2025.csv --out ../data
"""
import argparse, collections, json, os, re
import numpy as np, pandas as pd, geopandas as gpd, shapely

LC_OFFSET = 100000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="liberty")
    ap.add_argument("--units", required=True)
    ap.add_argument("--out", default="../data")
    ap.add_argument("--year", type=int, default=2025)
    a = ap.parse_args()
    U = pd.read_csv(a.units, dtype=str, keep_default_na=False).set_index("code")
    U["rate"] = pd.to_numeric(U[f"rate_{a.year}"])

    rows, geoms = [], []
    with open(os.path.join(a.src, "lc_parcels_raw.geojsonl")) as f:
        for line in f:
            ft = json.loads(line)
            p = ft["properties"]
            if p.get("prop_id") is None or not ft.get("geometry"):
                continue
            rows.append(p); geoms.append(json.dumps(ft["geometry"]))
    P = gpd.GeoDataFrame(pd.DataFrame(rows), geometry=shapely.from_geojson(geoms), crs=4326)
    P["acct"] = "L" + P.prop_id.astype("int64").astype(str)
    P["geometry"] = P.geometry.make_valid()
    g2278 = P.to_crs(2278)
    P["sf"] = g2278.geometry.area
    for c in ("school", "city", "county"):
        P[c] = P[c].fillna("").astype(str).str.strip()
    big = P.sort_values("sf", ascending=False).drop_duplicates("acct")
    pts = gpd.GeoDataFrame({"acct": big.acct.values}, geometry=big.geometry.representative_point().values, crs=4326)
    first = big.set_index("acct")
    on_roll = first.county != ""
    print(f"{len(P):,} parcel shapes, {len(first):,} accounts ({(~on_roll).sum()} without CAD codes)")

    # ---- district polygons by code
    tceq = gpd.read_file(os.path.join(a.src, "lc_tceq_districts.geojson"))
    tceq["NAME"] = tceq.NAME.str.strip()
    sp = gpd.read_file(os.path.join(a.src, "lc_special_districts.geojson"))
    name_cols = [c for c in ("HOSPITAL", "WATER", "DRAIN", "ESD", "NAV") if c in sp]
    sp["code"] = sp[name_cols].fillna("").agg(" ".join, axis=1).str.extract(r"\((\w+)\)\s*$")[0]
    polys = []
    for code, r in U.iterrows():
        kind, _, ref = r.boundary.partition(":")
        if kind == "tceq":
            m = tceq[tceq.NAME == ref]
        elif kind == "cad" and ref.startswith("special:"):
            m = sp[sp.code == ref.split(":", 1)[1]]
        else:
            continue
        if m.empty:
            print(f"  ! {code}: no polygon for {r.boundary!r}")
            continue
        polys.append(gpd.GeoDataFrame({"code": [code]}, geometry=[m.geometry.make_valid().union_all()], crs=4326))
    D = pd.concat(polys, ignore_index=True)
    hit = gpd.sjoin(pts, D, predicate="within")[["acct", "code"]]

    on_parcel = {"cad:school": "school", "cad:city": "city", "cad:county": "county"}
    units = collections.defaultdict(set)
    for acct, r in first[on_roll].iterrows():
        for b, col in on_parcel.items():
            if r[col]:
                units[acct].add(r[col])
    for acct, code in zip(hit.acct, hit.code):
        if acct in units:
            units[acct].add(code)
    unknown = sorted({c for us in units.values() for c in us} - set(U.index))
    if unknown:
        raise SystemExit(f"unit codes missing from {a.units}: {unknown}")
    acc = pd.DataFrame({"acct": list(units), "units": [sorted(u) for u in units.values()]})
    acc["key"] = acc.units.map("|".join)
    used = collections.Counter(u for us in acc.units for u in us)

    t = pd.DataFrame({"tax_dist": "LC-" + U.index, "name": U.name.values, "tp_cd": "", "category": U.category.values,
                      "bucket": U.bucket.values, "accounts": [used.get(c, 0) for c in U.index],
                      "rate_prior": U.rate.values, "rate_current": np.nan, "rate_used": U.rate.values,
                      "missing_rate": False})
    t.to_csv(os.path.join(a.out, "lc_rate_table.csv"), index=False)
    T = t.set_index("tax_dist")

    reg_path = os.path.join(a.out, "lc_combo_registry.csv")
    reg = pd.read_csv(reg_path, keep_default_na=False).set_index("combo_key").combo_id if os.path.exists(reg_path) \
        else pd.Series(dtype=np.int64)
    nxt = int(reg.max()) + 1 if len(reg) else LC_OFFSET
    keys = acc.key.value_counts(); ids = {}
    for k in keys.index:
        if k in reg.index:
            ids[k] = int(reg[k])
        else:
            ids[k] = nxt; reg[k] = nxt; nxt += 1
    reg.rename("combo_id").rename_axis("combo_key").reset_index().to_csv(reg_path, index=False)
    out = []
    for k, n in keys.items():
        rr = T.reindex(["LC-" + c for c in k.split("|")])
        names = lambda m: "; ".join(sorted(set(rr[m].name)))
        base = rr[rr.bucket == "base"].rate_used.sum(); mgmt = rr[rr.bucket == "mgmt"].rate_used.sum()
        out.append({"combo_id": ids[k], "rate_base": round(base, 6), "rate_mgmt": round(mgmt, 6),
                    "isd": names(rr.category == "ISD"), "city": names((rr.category == "City") & (rr.rate_used > 0)),
                    "water_districts": names(rr.category.isin(["Water District (MUD/WCID/UD)", "Drainage District"])
                                             & (rr.rate_used > 0)),
                    "esd": names(rr.category == "ESD"), "college": "",
                    "mgmt_districts": names((rr.bucket == "mgmt") & (rr.rate_used > 0)), "tirz": "", "pid": "",
                    "n_missing_rates": 0,
                    "breakdown": "|".join(f"{c}:{round(float(v), 6)}" for c, v in zip(rr.index, rr.rate_used)),
                    "rate_total_incl_mgmt": round(base + mgmt, 6), "accounts": int(n), "tax_year": a.year})
    C = pd.DataFrame(out).sort_values("combo_id")
    C.to_csv(os.path.join(a.out, "lc_combos.csv"), index=False)
    ar = acc.assign(combo_id=acc.key.map(ids)).merge(C[["combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]],
                                                     on="combo_id")
    ar[["acct", "combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]].to_csv(
        os.path.join(a.out, "lc_account_rates.csv.gz"), index=False, compression="gzip")

    land = g2278.assign(acct=P.acct, sf=g2278.geometry.area).groupby("acct").sf.sum()
    acres = pd.to_numeric(first.legal_acreage, errors="coerce")
    situs = first[["situs_num", "situs_street_prefx", "situs_street", "situs_street_sufix"]].fillna("").astype(str) \
        .apply(lambda s: s.str.strip()).agg(" ".join, axis=1).str.split().str.join(" ")
    ra = pd.DataFrame({
        "acct": first.index, "mailto": first.file_as_name.fillna("").values, "site_addr_1": situs.values,
        "site_addr_2": first.situs_city.fillna("").str.strip().values, "state_class": "",
        "tot_appr_val": pd.to_numeric(first.market, errors="coerce").values, "bld_ar": np.nan,
        "land_ar": np.where(acres > 0, acres * 43560, land.reindex(first.index)).round(),
    })
    ra.to_csv(os.path.join(a.src, "lc_real_acct.txt"), sep="\t", index=False, encoding="latin-1", errors="replace")
    gpd.GeoDataFrame({"acct": P.acct}, geometry=g2278.geometry, crs=2278).to_file(
        os.path.join(a.src, "lc_parcels.gpkg"), driver="GPKG")
    print(f"{len(acc):,} accounts, {len(C):,} combos")
    print("base rate, accounts weighted:", ar.rate_base.describe(percentiles=[.05, .5, .95]).round(3).to_dict())
    print("accounts per unit:", ", ".join(f"{c} {n:,}" for c, n in used.most_common()))


if __name__ == "__main__":
    main()
