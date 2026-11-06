"""
Chambers County rates in the same shape as the Harris pipeline, so build_county_data.py can map it.

Inputs
  --src     folder from fetch_chambers.py (ch_roll.csv, ch_parcels.zip)
  --units   data/chambers/ch_units_2025.csv: one row per Chambers CAD unit code with name, category, bucket and
            2025 adopted rate (Comptroller 2025 rates and levies files, county from chamberscountytx.gov).
            Codes were matched to names from the "(code) - NAME" header on each of the CAD's 2026 certified value
            reports. Codes with no certified value report carry no rate and a note
Outputs (into --out): ch_rate_table.csv, ch_combos.csv, ch_account_rates.csv.gz, ch_combo_registry.csv
        (into --src): ch_real_acct.txt, ch_parcels.gpkg

The certified roll lists each account's taxing units (Jur 1..Jur 12), so no polygon overlay is needed. Accounts
are "C" + Chambers CAD property id (Parcel_ID; the CAD's search takes it), one record per parcel: parcels with
several owners have one roll row per owner's share, so values are summed and the first owner is shown.
Values are the certified market value; exemptions and ag use value are not applied. No building area.

Usage: python build_chambers_rates.py --src chambers --units ../data/chambers/ch_units_2025.csv --out ../data
"""
import argparse, glob, os, zipfile
import numpy as np, pandas as pd, geopandas as gpd

CH_OFFSET = 80000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="chambers")
    ap.add_argument("--units", required=True)
    ap.add_argument("--out", default="../data")
    ap.add_argument("--year", type=int, default=2025)
    a = ap.parse_args()

    U = pd.read_csv(a.units, dtype={"code": str}, keep_default_na=False).set_index("code")
    U["rate"] = pd.to_numeric(U[f"rate_{a.year}"])

    # ---- roll: one row per account and owner share
    r = pd.read_csv(os.path.join(a.src, "ch_roll.csv"), dtype=str, keep_default_na=False)
    r["mv"] = pd.to_numeric(r.Market_Value, errors="coerce").fillna(0)
    jc = [f"Jur {i}" for i in range(1, 13)]
    r["acct"] = "C" + r.Parcel_ID.str.strip()
    r = r.sort_values(["acct", "Ownership_Sequence"])
    units = r.groupby("acct")[jc].agg(lambda s: set(v for v in s if v)).apply(lambda row: sorted(set().union(*row)),
                                                                              axis=1)
    first = r.drop_duplicates("acct").set_index("acct")
    owners = r.groupby("acct").Name.nunique()
    unknown = sorted({c for us in units for c in us} - set(U.index))
    if unknown:
        raise SystemExit(f"unit codes missing from {a.units}: {unknown}")
    acc = pd.DataFrame({"acct": units.index, "units": [[c for c in us if U.bucket[c] != "excluded" or U.category[c] == "TIRZ"]
                                                        for us in units]})
    acc["key"] = acc.units.map("|".join)
    print(f"{len(r):,} roll rows, {len(acc):,} accounts, {len(set(c for us in acc.units for c in us))} unit codes; "
          f"{(acc.key == '').sum():,} list no taxing unit (left without a rate)")
    acc = acc[acc.key != ""]

    # ---- rate table
    used = pd.Series([c for us in acc.units for c in us]).value_counts()
    t = pd.DataFrame({"tax_dist": "CH-" + U.index, "name": U.name.values, "tp_cd": "", "category": U.category.values,
                      "bucket": U.bucket.values, "accounts": [int(used.get(c, 0)) for c in U.index],
                      "rate_prior": U.rate.values, "rate_current": np.nan, "rate_used": U.rate.values,
                      "missing_rate": False})
    t.to_csv(os.path.join(a.out, "ch_rate_table.csv"), index=False)
    T = t.set_index("tax_dist")

    # ---- combos with stable ids
    reg_path = os.path.join(a.out, "ch_combo_registry.csv")
    reg = pd.read_csv(reg_path, keep_default_na=False).set_index("combo_key").combo_id if os.path.exists(reg_path) \
        else pd.Series(dtype=np.int64)
    nxt = int(reg.max()) + 1 if len(reg) else CH_OFFSET
    keys = acc.key.value_counts(); ids = {}
    for k in keys.index:
        if k in reg.index:
            ids[k] = int(reg[k])
        else:
            ids[k] = nxt; reg[k] = nxt; nxt += 1
    reg.rename("combo_id").rename_axis("combo_key").reset_index().to_csv(reg_path, index=False)
    out = []
    for k, n in keys.items():
        rr = T.reindex(["CH-" + c for c in k.split("|")] if k else [])
        names = lambda m: "; ".join(sorted(set(rr[m].name)))
        base = rr[rr.bucket == "base"].rate_used.sum(); mgmt = rr[rr.bucket == "mgmt"].rate_used.sum()
        out.append({"combo_id": ids[k], "rate_base": round(base, 6), "rate_mgmt": round(mgmt, 6),
                    "isd": names(rr.category == "ISD"), "city": names((rr.category == "City") & (rr.rate_used > 0)),
                    "water_districts": names(rr.category.isin(["Water District (MUD/WCID/UD)", "Drainage District"])
                                             & (rr.rate_used > 0)),
                    "esd": "", "college": names(rr.category == "College District"),
                    "mgmt_districts": names((rr.bucket == "mgmt") & (rr.rate_used > 0)),
                    "tirz": names(rr.category == "TIRZ"), "pid": "", "n_missing_rates": 0,
                    "breakdown": "|".join(f"{c}:{round(float(v), 6)}" for c, v, b in
                                          zip(rr.index, rr.rate_used, rr.bucket) if b != "excluded"),
                    "rate_total_incl_mgmt": round(base + mgmt, 6), "accounts": int(n), "tax_year": a.year})
    C = pd.DataFrame(out).sort_values("combo_id")
    C.to_csv(os.path.join(a.out, "ch_combos.csv"), index=False)
    ar = acc.assign(combo_id=acc.key.map(ids)).merge(C[["combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]],
                                                     on="combo_id")
    ar[["acct", "combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]].to_csv(
        os.path.join(a.out, "ch_account_rates.csv.gz"), index=False, compression="gzip")

    # ---- account details (real_acct layout)
    situs = first[["Prop_Street_Number", "Prop_Street", "Prop_Street_Dir"]].apply(lambda s: s.str.strip()) \
        .agg(" ".join, axis=1).str.split().str.join(" ")
    owner = first.Name.str.strip() + np.where(owners.reindex(first.index) > 1, " ET AL", "")
    acres = pd.to_numeric(first.Acres, errors="coerce")
    ra = pd.DataFrame({
        "acct": first.index, "mailto": owner.values, "site_addr_1": situs.values,
        "site_addr_2": first.Prop_City.str.strip().values, "state_class": first.Primary_Category_Code.str.strip().values,
        "tot_appr_val": r.groupby("acct").mv.sum().reindex(first.index).values, "bld_ar": np.nan,
        "land_ar": (acres * 43560).round().values,
    })
    ra.to_csv(os.path.join(a.src, "ch_real_acct.txt"), sep="\t", index=False, encoding="latin-1", errors="replace")

    # ---- parcel shapes keyed by account
    z = os.path.join(a.src, "ch_parcels.zip")
    shp = [n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith(".shp")][0]
    g = gpd.read_file(f"/vsizip/{os.path.abspath(z)}/{shp}")
    g = g[pd.to_numeric(g.ParcelCAMA, errors="coerce").fillna(0) > 0]
    g["acct"] = "C" + g.ParcelCAMA.astype("int64").astype(str)
    g = g[g.geometry.notna()][["acct", "geometry"]].to_crs(2278)
    g["geometry"] = g.geometry.make_valid()
    g.to_file(os.path.join(a.src, "ch_parcels.gpkg"), driver="GPKG")
    print(f"{len(g):,} parcel shapes, {g.acct.isin(set(acc.acct)).mean():.1%} on the roll; "
          f"{acc.acct.isin(set(g.acct)).mean():.1%} of accounts have a shape (personal property and minerals do not)")
    print(f"{len(C):,} combos")
    print("base rate, accounts weighted:", ar.rate_base.describe(percentiles=[.05, .5, .95]).round(3).to_dict())


if __name__ == "__main__":
    main()
