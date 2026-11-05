"""
Fort Bend County rates in the same shape as the Harris pipeline, so build_county_data.py can map both.

Input (from fetch_fortbend.py): fb_parcels_raw.geojsonl, fb_rates.xls
Output (into --out, alongside the hcad_* files):
  fb_rate_table.csv          one row per taxing unit: tax_dist (prefixed FB-), name, category, bucket, rate_used, ...
  fb_combos.csv              one row per unique set of taxing units, same columns as hcad_combos.csv
  fb_account_rates.csv.gz    account (FBCAD quick ref id, e.g. R100842) -> combo_id
  fb_real_acct.txt           owner, site address, state class, value, areas, in real_acct.txt layout
  fb_parcels.gpkg            parcel shapes in EPSG:2278 (same as HCAD) with an acct field
  fb_combo_registry.csv      stable combo ids, starting at 50000 so they never collide with Harris ids

FBCAD lists each parcel's taxing units as codes (e.g. "C09,D01,G01,J07,M25,S07,CAD"). Unlike HCAD there is
no split percentage, so every unit applies in full. "CAD" (the appraisal district) levies nothing.

Usage: python build_fortbend_rates.py --src fortbend --out ../data --year 2024
"""
import argparse, json, os, re
import numpy as np, pandas as pd, geopandas as gpd, shapely

FB_OFFSET = 50000
CATEGORY = {  # FBCAD "Type" -> category and bucket used by the map (same names as build_rates.py)
    "School": ("ISD", "base"),
    "City": ("City", "base"), "Municipal": ("City", "base"),
    "County General": ("County / Countywide", "base"), "Public": ("County / Countywide", "base"),
    "Community College": ("College District", "base"),
    "Municipal Utility District": ("Water District (MUD/WCID/UD)", "base"),
    "Fresh Water": ("Water District (MUD/WCID/UD)", "base"),
    "Levy Improvement": ("Water District (MUD/WCID/UD)", "base"),
    "Drainage District": ("Drainage District", "base"),
    "Emergency": ("ESD", "base"),
    "Special": ("Management District", "mgmt"),
    "Special Management Districts": ("Management District", "mgmt"),
    "Special Management Districts Management Districts": ("Management District", "mgmt"),
    "Levy Improvement District": ("Water District (MUD/WCID/UD)", "base"),
    "Fresh Water Supply District": ("Water District (MUD/WCID/UD)", "base"),
    # no tax rate: agreements, foreign trade zones; PIDs bill assessments (one, W43, levies a real rate)
    "Agreement": ("Agreement", "excluded"),
    "Foreign Trade": ("Foreign Trade Zone", "excluded"),
    "Public Improvement District": ("Public Improvement District", "excluded"),
    "Public Improvement": ("Public Improvement District", "excluded"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="fortbend")
    ap.add_argument("--out", default="../data")
    ap.add_argument("--year", type=int, default=2025, help="tax year of the rates in the rate file")
    ap.add_argument("--rates-file", help="rate table to use instead of <src>/fb_rates.xls: FBCAD's xls, or a CSV "
                    "export of the Fort Bend tax rate grid (Code, Description, Type, ..., Total Rate)")
    a = ap.parse_args()

    # ---- rate table
    rf = a.rates_file or os.path.join(a.src, "fb_rates.xls")
    x = pd.read_csv(rf, dtype=str) if rf.lower().endswith(".csv") else pd.read_excel(rf)
    print(f"rates from {rf} (tax year {a.year})")
    x.columns = [str(c).strip() for c in x.columns]
    if "Description" not in x.columns and "Taxing Unit" in x.columns:   # grid exports name the column differently by year
        x = x.rename(columns={"Taxing Unit": "Description"})
    x = x[x.Code.notna()].copy()
    x["code"] = x.Code.astype(str).str.strip()
    x["type"] = x.Type.astype(str).str.strip()
    t = pd.DataFrame({
        "tax_dist": "FB-" + x.code, "name": x.Description.astype(str).str.strip(), "tp_cd": x.type,
        "rate_used": pd.to_numeric(x["Total Rate"], errors="coerce"),
    })
    t[["category", "bucket"]] = [CATEGORY.get(tp, ("Other", "base")) for tp in x.type]
    # management districts typed otherwise (SM110 "Municipal", M92 "Katy Management Dist 1" as a MUD)
    mg = x.code.str.startswith("SM").to_numpy() | x.Description.astype(str).str.contains("Management Dist", case=False).to_numpy()
    t.loc[mg, ["category", "bucket"]] = ["Management District", "mgmt"]
    # a PID with an actual tax rate (W43 Fort Bend Improvement District 24) is an improvement district levy
    pid_rate = (t.category == "Public Improvement District") & (t.rate_used > 0)
    t.loc[pid_rate, ["category", "bucket"]] = ["Management District", "mgmt"]
    t.loc[t.bucket == "excluded", "rate_used"] = 0.0
    unknown = sorted(set(x.type) - set(CATEGORY))
    if unknown:
        print("unmapped FBCAD types (treated as base):", unknown)

    # ---- parcels
    rows, geoms = [], []
    with open(os.path.join(a.src, "fb_parcels_raw.geojsonl")) as f:
        for line in f:
            ft = json.loads(line)
            p = ft["properties"]
            if not p.get("quickrefid") or not ft.get("geometry"):
                continue
            rows.append(p)
            geoms.append(json.dumps(ft["geometry"]))
    P = pd.DataFrame(rows)
    P["acct"] = P.quickrefid.astype(str).str.strip()
    print(f"{len(P):,} parcel shapes, {P.acct.nunique():,} accounts")

    def units(s):   # codes are comma separated; a few parcels use ";" or stray spaces
        return sorted({u.strip() for u in re.split(r"[,;]", str(s or "")) if u.strip() and u.strip() != "CAD"})
    P["units"] = P.taxunits.map(units)
    P["key"] = P.units.map("|".join)

    acc = P.drop_duplicates("acct")[["acct", "key", "units"]]
    used = sorted({u for us in acc.units for u in us})
    known = set(x.code)
    missing_codes = [u for u in used if u not in known]
    if missing_codes:
        print(f"{len(missing_codes)} codes on parcels but not in the rate sheet:", missing_codes[:20])
        # Codes absent from the rate sheet, by FBCAD prefix: T = TIRZ (no rate), P = public improvement
        # district (an assessment, not a rate), SM = management district. Anything else (MUDs, LIDs created
        # after the sheet) is a real gap and is flagged as a missing rate.
        def guess(c):
            if c.startswith("T"):   # TIRZ or zone code (T149 is a foreign trade zone); none levy a rate
                return (f"TIRZ {c}", "TIRZ", "excluded", 0.0)
            if c.startswith("P"):
                return (f"Public improvement district {c}", "Public Improvement District", "excluded", 0.0)
            if c.startswith("SM"):
                return (f"Management district {c}", "Management District", "mgmt", np.nan)
            return (f"Unit {c} (not in FBCAD rate sheet)", "Other", "base", np.nan)
        g = [guess(c) for c in missing_codes]
        extra = pd.DataFrame({"tax_dist": ["FB-" + c for c in missing_codes], "name": [x[0] for x in g],
                              "tp_cd": "", "rate_used": [x[3] for x in g], "category": [x[1] for x in g],
                              "bucket": [x[2] for x in g]})
        t = pd.concat([t, extra], ignore_index=True)
    t["accounts"] = t.tax_dist.map(pd.Series([u for us in acc.units for u in us]).value_counts()
                                   .rename(lambda c: "FB-" + c)).fillna(0).astype(int)
    t["missing_rate"] = t.rate_used.isna() & (t.accounts > 0) & (t.bucket != "excluded")
    t["rate_used"] = t.rate_used.fillna(0.0)
    t["rate_prior"] = t.rate_used
    t["rate_current"] = np.nan
    t[["tax_dist", "name", "tp_cd", "category", "bucket", "accounts", "rate_prior", "rate_current",
       "rate_used", "missing_rate"]].sort_values(["category", "name"]).to_csv(
        os.path.join(a.out, "fb_rate_table.csv"), index=False)
    T = t.set_index("tax_dist")

    # ---- combos with stable ids
    reg_path = os.path.join(a.out, "fb_combo_registry.csv")
    reg = pd.read_csv(reg_path, keep_default_na=False).set_index("combo_key").combo_id if os.path.exists(reg_path) \
        else pd.Series(dtype=np.int64)
    nxt = int(reg.max()) + 1 if len(reg) else FB_OFFSET
    keys = acc.key.value_counts()
    ids = {}
    for k in keys.index:
        if k in reg.index:
            ids[k] = int(reg[k])
        else:
            ids[k] = nxt; reg[k] = nxt; nxt += 1
    reg.rename("combo_id").rename_axis("combo_key").reset_index().to_csv(reg_path, index=False)

    out = []
    for k, n in keys.items():
        codes = ["FB-" + c for c in k.split("|")] if k else []
        r = T.reindex(codes)
        def names(mask):
            return "; ".join(sorted(set(r[mask].name)))
        base = r[r.bucket == "base"].rate_used.sum()
        mgmt = r[r.bucket == "mgmt"].rate_used.sum()
        out.append({
            "combo_id": ids[k], "rate_base": round(base, 6), "rate_mgmt": round(mgmt, 6),
            "isd": names(r.category == "ISD"), "city": names(r.category == "City"),
            "water_districts": names(r.category.isin(["Water District (MUD/WCID/UD)", "Drainage District"])),
            "esd": names(r.category == "ESD"), "college": names(r.category == "College District"),
            "mgmt_districts": names(r.bucket == "mgmt"), "tirz": names(r.category == "TIRZ"),
            "n_missing_rates": int(r.missing_rate.fillna(True).sum()),
            "breakdown": "|".join(f"{c}:{round(float(w), 6)}" for c, w, b in zip(r.index, r.rate_used.fillna(0), r.bucket)
                                  if b != "excluded"),
            "pid": names(r.category == "Public Improvement District"),
            "rate_total_incl_mgmt": round(base + mgmt, 6), "accounts": int(n), "tax_year": a.year,
        })
    C = pd.DataFrame(out).sort_values("combo_id")
    C.to_csv(os.path.join(a.out, "fb_combos.csv"), index=False)
    ar = acc.assign(combo_id=acc.key.map(ids)).merge(C[["combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]],
                                                     on="combo_id")
    ar[["acct", "combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]].to_csv(
        os.path.join(a.out, "fb_account_rates.csv.gz"), index=False, compression="gzip")

    # ---- account details in real_acct.txt layout
    first = P.drop_duplicates("acct")
    situs = first.situs.fillna("").astype(str)
    parts = situs.str.split(",")
    land_sf = pd.to_numeric(first.landsizeft, errors="coerce")
    land_sf = land_sf.where(land_sf > 0, pd.to_numeric(first.landsizeac, errors="coerce") * 43560)
    cls = first.building_sptb_code.where(first.building_sptb_code.notna() & (first.building_sptb_code != ""),
                                         first.land_state_code)
    ra = pd.DataFrame({
        "acct": first.acct, "mailto": first.ownername.fillna(""),
        "site_addr_1": parts.str[0].str.strip().str.upper(),
        "site_addr_2": parts.str[1].fillna("").str.strip().str.upper(),
        "state_class": cls.fillna(""), "tot_appr_val": pd.to_numeric(first.totalvalue, errors="coerce"),
        "bld_ar": pd.to_numeric(first.totsqftlvg, errors="coerce"), "land_ar": land_sf.round(),
    })
    ra.to_csv(os.path.join(a.src, "fb_real_acct.txt"), sep="\t", index=False, encoding="latin-1", errors="replace")

    # ---- shapes, in the same CRS as HCAD so build_county_data.py treats both alike
    g = gpd.GeoDataFrame({"acct": P.acct}, geometry=shapely.from_geojson(geoms), crs=4326).to_crs(2278)
    g.to_file(os.path.join(a.src, "fb_parcels.gpkg"), driver="GPKG")

    print(f"{len(t):,} taxing units, {len(C):,} combos, {len(ar):,} accounts")
    print("base rate, accounts weighted:",
          ar.rate_base.describe(percentiles=[.05, .5, .95]).round(3).to_dict())


if __name__ == "__main__":
    main()
